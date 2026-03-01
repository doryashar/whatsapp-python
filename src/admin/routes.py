from fastapi import APIRouter, Request, Depends, HTTPException, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
from datetime import datetime
import json

from ..config import settings
from ..telemetry import get_logger
from ..tenant import tenant_manager
from ..middleware import rate_limiter
from .auth import AdminSession, require_admin_session, get_session_id

logger = get_logger("whatsapp.admin")

router = APIRouter(prefix="/admin", tags=["admin"])
api_router = APIRouter(prefix="/admin/api", tags=["admin-api"])


class TenantCreate(BaseModel):
    name: str


class TenantUpdate(BaseModel):
    name: Optional[str] = None


class WebhookAdd(BaseModel):
    url: str


def templates(request: Request) -> dict:
    return {"request": request}


@router.get("/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    if not settings.admin_password:
        return HTMLResponse(
            content="<h1>Admin interface not configured</h1><p>Set ADMIN_PASSWORD environment variable</p>",
            status_code=503,
        )

    html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Admin Login - WhatsApp API</title>
    <script src="https://cdn.tailwindcss.com"></script>
</head>
<body class="bg-gray-900 min-h-screen flex items-center justify-center">
    <div class="bg-gray-800 p-8 rounded-lg shadow-xl w-full max-w-md">
        <div class="text-center mb-8">
            <div class="w-16 h-16 bg-green-500 rounded-full flex items-center justify-center mx-auto mb-4">
                <svg class="w-10 h-10 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>
                </svg>
            </div>
            <h1 class="text-2xl font-bold text-white">Admin Login</h1>
            <p class="text-gray-400 mt-2">WhatsApp API Dashboard</p>
        </div>
        <form method="POST" action="/admin/login" class="space-y-6">
            <div>
                <label class="block text-sm font-medium text-gray-300 mb-2">Password</label>
                <input type="password" name="password" required
                    class="w-full px-4 py-3 bg-gray-700 border border-gray-600 rounded-lg text-white placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-green-500 focus:border-transparent"
                    placeholder="Enter admin password">
            </div>
            <button type="submit"
                class="w-full py-3 px-4 bg-green-600 hover:bg-green-700 text-white font-medium rounded-lg transition duration-200 flex items-center justify-center">
                <svg class="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 16l-4-4m0 0l4-4m-4 4h14m-5 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h7a3 3 0 013 3v1"></path>
                </svg>
                Sign In
            </button>
        </form>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html)


@router.post("/login")
async def admin_login(
    request: Request,
    password: str = Form(...),
):
    if not settings.admin_password:
        raise HTTPException(status_code=503, detail="Admin interface not configured")

    db = tenant_manager._db
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    admin_session = AdminSession(db)
    session_id = await admin_session.create_session(request, password)

    if not session_id:
        raise HTTPException(status_code=401, detail="Invalid password")

    response = RedirectResponse(url="/admin/dashboard", status_code=302)
    response.set_cookie(
        key="admin_session",
        value=session_id,
        httponly=True,
        max_age=86400,
        samesite="lax",
    )
    return response


@router.post("/logout")
async def admin_logout(
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    db = tenant_manager._db
    if db:
        admin_session = AdminSession(db)
        await admin_session.logout(session_id)

    response = RedirectResponse(url="/admin/login", status_code=302)
    response.delete_cookie("admin_session")
    return response


@router.get("/", response_class=HTMLResponse)
async def admin_root():
    return RedirectResponse(url="/admin/dashboard")


@router.get("/dashboard", response_class=HTMLResponse)
async def admin_dashboard(
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    return await render_dashboard(request)


@router.get("/tenants", response_class=HTMLResponse)
async def admin_tenants_page(
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    return await render_tenants_page(request)


@router.get("/messages", response_class=HTMLResponse)
async def admin_messages_page(
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    return await render_messages_page(request)


@router.get("/webhooks", response_class=HTMLResponse)
async def admin_webhooks_page(
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    return await render_webhooks_page(request)


@router.get("/security", response_class=HTMLResponse)
async def admin_security_page(
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    return await render_security_page(request)


# API Routes


@api_router.get("/stats")
async def get_stats(session_id: str = Depends(require_admin_session)):
    db = tenant_manager._db
    tenants = tenant_manager.list_tenants()

    connected = sum(1 for t in tenants if t.connection_state == "connected")
    pending = sum(1 for t in tenants if t.connection_state == "pending_qr")
    disconnected = sum(1 for t in tenants if t.connection_state == "disconnected")

    total_messages = 0
    total_webhook_attempts = 0
    webhook_success = 0
    webhook_failed = 0

    if db:
        for tenant in tenants:
            _, msg_count = await db.list_messages(
                tenant_hash=tenant.api_key_hash, limit=1
            )
            total_messages += msg_count

        stats = await db.get_webhook_stats()
        total_webhook_attempts = stats.get("total", 0)
        webhook_success = stats.get("success_count", 0)
        webhook_failed = stats.get("fail_count", 0)

    return {
        "tenants": {
            "total": len(tenants),
            "connected": connected,
            "pending_qr": pending,
            "disconnected": disconnected,
        },
        "messages": {
            "total": total_messages,
        },
        "webhooks": {
            "total_attempts": total_webhook_attempts,
            "successful": webhook_success,
            "failed": webhook_failed,
            "success_rate": round(webhook_success / total_webhook_attempts * 100, 1)
            if total_webhook_attempts > 0
            else 0,
        },
        "rate_limit": {
            "blocked_ips": len(rate_limiter.get_blocked_ips()),
        },
    }


@api_router.get("/tenants")
async def list_tenants_api(session_id: str = Depends(require_admin_session)):
    tenants = tenant_manager.list_tenants()
    return {
        "tenants": [
            {
                "api_key_hash": t.api_key_hash,
                "name": t.name,
                "created_at": t.created_at.isoformat(),
                "connection_state": t.connection_state,
                "self_phone": t.self_phone,
                "self_name": t.self_name,
                "webhook_count": len(t.webhook_urls),
                "last_connected_at": t.last_connected_at.isoformat()
                if t.last_connected_at
                else None,
                "has_auth": t.has_auth,
            }
            for t in tenants
        ]
    }


@api_router.post("/tenants")
async def create_tenant_api(
    data: TenantCreate,
    session_id: str = Depends(require_admin_session),
):
    tenant, api_key = await tenant_manager.create_tenant(data.name)
    return {
        "status": "created",
        "tenant": {
            "name": tenant.name,
            "api_key": api_key,
            "created_at": tenant.created_at.isoformat(),
        },
    }


@api_router.get("/tenants/{tenant_hash}")
async def get_tenant_api(
    tenant_hash: str,
    session_id: str = Depends(require_admin_session),
):
    tenant = tenant_manager._tenants.get(tenant_hash)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    db = tenant_manager._db
    messages_count = 0
    webhook_stats = {}

    if db:
        _, messages_count = await db.list_messages(tenant_hash=tenant_hash, limit=1)
        webhook_stats = await db.get_webhook_stats()

    return {
        "api_key_hash": tenant.api_key_hash,
        "name": tenant.name,
        "created_at": tenant.created_at.isoformat(),
        "connection_state": tenant.connection_state,
        "self_jid": tenant.self_jid,
        "self_phone": tenant.self_phone,
        "self_name": tenant.self_name,
        "webhook_urls": tenant.webhook_urls,
        "last_connected_at": tenant.last_connected_at.isoformat()
        if tenant.last_connected_at
        else None,
        "last_disconnected_at": tenant.last_disconnected_at.isoformat()
        if tenant.last_disconnected_at
        else None,
        "has_auth": tenant.has_auth,
        "messages_count": messages_count,
    }


@api_router.delete("/tenants/{tenant_hash}")
async def delete_tenant_api(
    tenant_hash: str,
    session_id: str = Depends(require_admin_session),
):
    tenant = tenant_manager._tenants.get(tenant_hash)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if tenant._raw_api_key:
        deleted = await tenant_manager.delete_tenant(tenant._raw_api_key)
        return {"status": "deleted" if deleted else "not_found"}
    raise HTTPException(
        status_code=400, detail="Cannot delete tenant without raw API key"
    )


@api_router.post("/tenants/{tenant_hash}/reconnect")
async def reconnect_tenant(
    tenant_hash: str,
    session_id: str = Depends(require_admin_session),
):
    tenant = tenant_manager._tenants.get(tenant_hash)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if tenant.bridge:
        await tenant.bridge.stop()

    bridge = await tenant_manager.get_or_create_bridge(tenant)
    await bridge.login()
    return {"status": "reconnecting"}


@api_router.delete("/tenants/{tenant_hash}/credentials")
async def clear_tenant_credentials(
    tenant_hash: str,
    session_id: str = Depends(require_admin_session),
):
    tenant = tenant_manager._tenants.get(tenant_hash)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    await tenant_manager.clear_creds(tenant)
    return {"status": "credentials_cleared"}


@api_router.get("/messages")
async def list_messages_api(
    tenant_hash: Optional[str] = Query(None),
    chat_jid: Optional[str] = Query(None),
    direction: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session_id: str = Depends(require_admin_session),
):
    db = tenant_manager._db
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    messages, total = await db.list_messages(
        tenant_hash=tenant_hash,
        chat_jid=chat_jid,
        direction=direction,
        search=search,
        limit=limit,
        offset=offset,
    )

    tenants = {t.api_key_hash: t.name for t in tenant_manager.list_tenants()}

    return {
        "messages": [
            {
                **msg,
                "tenant_name": tenants.get(msg.get("tenant_hash"), "Unknown"),
            }
            for msg in messages
        ],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@api_router.get("/webhooks")
async def list_webhooks_api(
    session_id: str = Depends(require_admin_session),
):
    webhooks = []
    for tenant in tenant_manager.list_tenants():
        for url in tenant.webhook_urls:
            webhooks.append(
                {
                    "tenant_hash": tenant.api_key_hash,
                    "tenant_name": tenant.name,
                    "url": url,
                }
            )
    return {"webhooks": webhooks}


@api_router.get("/webhooks/history")
async def webhook_history_api(
    tenant_hash: Optional[str] = Query(None),
    url: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session_id: str = Depends(require_admin_session),
):
    db = tenant_manager._db
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    attempts, total = await db.list_webhook_attempts(
        tenant_hash=tenant_hash,
        url=url,
        success=success,
        limit=limit,
        offset=offset,
    )

    tenants = {t.api_key_hash: t.name for t in tenant_manager.list_tenants()}

    return {
        "attempts": [
            {
                **a,
                "tenant_name": tenants.get(a.get("tenant_hash"), "Unknown"),
            }
            for a in attempts
        ],
        "total": total,
    }


@api_router.get("/webhooks/stats")
async def webhook_stats_api(
    url: Optional[str] = Query(None),
    session_id: str = Depends(require_admin_session),
):
    db = tenant_manager._db
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    stats = await db.get_webhook_stats(url=url)
    return stats


@api_router.post("/tenants/{tenant_hash}/webhooks")
async def add_tenant_webhook_api(
    tenant_hash: str,
    data: WebhookAdd,
    session_id: str = Depends(require_admin_session),
):
    tenant = tenant_manager._tenants.get(tenant_hash)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if not data.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Invalid webhook URL")

    await tenant_manager.add_webhook(tenant, data.url)
    return {"status": "added", "url": data.url}


@api_router.delete("/tenants/{tenant_hash}/webhooks")
async def remove_tenant_webhook_api(
    tenant_hash: str,
    url: str = Query(...),
    session_id: str = Depends(require_admin_session),
):
    tenant = tenant_manager._tenants.get(tenant_hash)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    removed = await tenant_manager.remove_webhook(tenant, url)
    return {"status": "removed" if removed else "not_found"}


@api_router.get("/rate-limit/blocked")
async def list_blocked_ips_api(session_id: str = Depends(require_admin_session)):
    return {"blocked_ips": rate_limiter.get_blocked_ips()}


@api_router.post("/rate-limit/block")
async def block_ip_api(
    ip: str = Query(...),
    reason: str = Query("admin"),
    session_id: str = Depends(require_admin_session),
):
    rate_limiter.block_ip(ip, reason=reason)
    return {"status": "blocked", "ip": ip}


@api_router.delete("/rate-limit/block")
async def unblock_ip_api(
    ip: str = Query(...),
    session_id: str = Depends(require_admin_session),
):
    unblocked = rate_limiter.unblock_ip(ip)
    return {"status": "unblocked" if unblocked else "not_blocked"}


@api_router.get("/rate-limit/failed-auth")
async def failed_auth_attempts_api(session_id: str = Depends(require_admin_session)):
    return rate_limiter.get_failed_auth_attempts()


@api_router.delete("/rate-limit/failed-auth")
async def clear_failed_auth_api(
    ip: Optional[str] = Query(None),
    session_id: str = Depends(require_admin_session),
):
    rate_limiter.clear_failed_auth(ip) if ip else rate_limiter.clear_failed_auth(None)
    return {"status": "cleared"}


# Template rendering functions


async def render_dashboard(request: Request) -> HTMLResponse:
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Dashboard - WhatsApp Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.6"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        whatsapp: '#25D366',
                        whatsappDark: '#128C7E',
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <div class="flex h-screen">
        <!-- Sidebar -->
        <aside class="w-64 bg-gray-800 border-r border-gray-700">
            <div class="p-4 border-b border-gray-700">
                <div class="flex items-center space-x-3">
                    <div class="w-10 h-10 bg-whatsapp rounded-full flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24">
                            <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/>
                        </svg>
                    </div>
                    <span class="text-xl font-bold">WhatsApp Admin</span>
                </div>
            </div>
            <nav class="p-4 space-y-2">
                <a href="/admin/dashboard" class="flex items-center space-x-3 px-4 py-3 bg-whatsapp/10 text-whatsapp rounded-lg">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path></svg>
                    <span>Dashboard</span>
                </a>
                <a href="/admin/tenants" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                    <span>Tenants</span>
                </a>
                <a href="/admin/messages" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                    <span>Messages</span>
                </a>
                <a href="/admin/webhooks" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                    <span>Webhooks</span>
                </a>
                <a href="/admin/security" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                    <span>Security</span>
                </a>
            </nav>
            <div class="absolute bottom-0 w-64 p-4 border-t border-gray-700">
                <form action="/admin/logout" method="POST">
                    <button type="submit" class="w-full flex items-center justify-center space-x-2 px-4 py-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition">
                        <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
                        <span>Sign Out</span>
                    </button>
                </form>
            </div>
        </aside>

        <!-- Main Content -->
        <main class="flex-1 overflow-y-auto">
            <header class="bg-gray-800 border-b border-gray-700 px-6 py-4">
                <h1 class="text-2xl font-bold">Dashboard</h1>
            </header>

            <div class="p-6">
                <!-- Stats Cards -->
                <div class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8" hx-get="/admin/api/stats" hx-trigger="load, every 30s">
                    <div class="bg-gray-800 rounded-xl p-6 border border-gray-700">
                        <div class="flex items-center justify-between">
                            <div>
                                <p class="text-gray-400 text-sm">Total Tenants</p>
                                <p class="text-3xl font-bold mt-1" id="stat-tenants">-</p>
                            </div>
                            <div class="w-12 h-12 bg-blue-500/20 rounded-lg flex items-center justify-center">
                                <svg class="w-6 h-6 text-blue-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                            </div>
                        </div>
                    </div>
                    <div class="bg-gray-800 rounded-xl p-6 border border-gray-700">
                        <div class="flex items-center justify-between">
                            <div>
                                <p class="text-gray-400 text-sm">Connected</p>
                                <p class="text-3xl font-bold mt-1 text-green-500" id="stat-connected">-</p>
                            </div>
                            <div class="w-12 h-12 bg-green-500/20 rounded-lg flex items-center justify-center">
                                <svg class="w-6 h-6 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg>
                            </div>
                        </div>
                    </div>
                    <div class="bg-gray-800 rounded-xl p-6 border border-gray-700">
                        <div class="flex items-center justify-between">
                            <div>
                                <p class="text-gray-400 text-sm">Messages</p>
                                <p class="text-3xl font-bold mt-1" id="stat-messages">-</p>
                            </div>
                            <div class="w-12 h-12 bg-purple-500/20 rounded-lg flex items-center justify-center">
                                <svg class="w-6 h-6 text-purple-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                            </div>
                        </div>
                    </div>
                    <div class="bg-gray-800 rounded-xl p-6 border border-gray-700">
                        <div class="flex items-center justify-between">
                            <div>
                                <p class="text-gray-400 text-sm">Webhook Success</p>
                                <p class="text-3xl font-bold mt-1 text-whatsapp" id="stat-webhook-rate">-</p>
                            </div>
                            <div class="w-12 h-12 bg-whatsapp/20 rounded-lg flex items-center justify-center">
                                <svg class="w-6 h-6 text-whatsapp" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- Quick Actions -->
                <div class="bg-gray-800 rounded-xl p-6 border border-gray-700 mb-8">
                    <h2 class="text-lg font-semibold mb-4">Quick Actions</h2>
                    <div class="flex flex-wrap gap-4">
                        <button onclick="showCreateTenantModal()" class="px-4 py-2 bg-whatsapp hover:bg-whatsappDark text-white rounded-lg transition flex items-center space-x-2">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path></svg>
                            <span>Add Tenant</span>
                        </button>
                        <a href="/admin/security" class="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition flex items-center space-x-2">
                            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                            <span>Manage Security</span>
                        </a>
                    </div>
                </div>

                <!-- Recent Activity -->
                <div class="bg-gray-800 rounded-xl border border-gray-700">
                    <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
                        <h2 class="text-lg font-semibold">Recent Tenants</h2>
                        <a href="/admin/tenants" class="text-whatsapp hover:underline text-sm">View All</a>
                    </div>
                    <div id="tenants-list" hx-get="/admin/api/tenants" hx-trigger="load, every 30s" class="divide-y divide-gray-700">
                        <div class="p-6 text-center text-gray-500">Loading...</div>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <!-- Create Tenant Modal -->
    <div id="create-tenant-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50">
        <div class="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-700">
            <h3 class="text-xl font-bold mb-4">Create New Tenant</h3>
            <form hx-post="/admin/api/tenants" hx-on="htmx:afterRequest: closeModalAndShowKey(event)">
                <div class="mb-4">
                    <label class="block text-sm font-medium text-gray-300 mb-2">Tenant Name</label>
                    <input type="text" name="name" required class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-whatsapp">
                </div>
                <div class="flex justify-end space-x-4">
                    <button type="button" onclick="hideCreateTenantModal()" class="px-4 py-2 text-gray-400 hover:text-white">Cancel</button>
                    <button type="submit" class="px-4 py-2 bg-whatsapp hover:bg-whatsappDark text-white rounded-lg">Create</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        function showCreateTenantModal() {
            document.getElementById('create-tenant-modal').classList.remove('hidden');
            document.getElementById('create-tenant-modal').classList.add('flex');
        }
        
        function hideCreateTenantModal() {
            document.getElementById('create-tenant-modal').classList.add('hidden');
            document.getElementById('create-tenant-modal').classList.remove('flex');
        }
        
        function closeModalAndShowKey(event) {
            if (event.detail.successful) {
                hideCreateTenantModal();
                const response = JSON.parse(event.detail.xhr.response);
                alert('Tenant created!\\n\\nAPI Key: ' + response.tenant.api_key + '\\n\\nSave this key - it won\\'t be shown again!');
                location.reload();
            }
        }
        
        document.body.addEventListener('htmx:beforeSwap', function(evt) {
            if (evt.detail.target.id === 'stat-tenants') {
                const stats = JSON.parse(evt.detail.xhr.response);
                document.getElementById('stat-tenants').textContent = stats.tenants.total;
                document.getElementById('stat-connected').textContent = stats.tenants.connected;
                document.getElementById('stat-messages').textContent = stats.messages.total;
                document.getElementById('stat-webhook-rate').textContent = stats.webhooks.success_rate + '%';
                evt.preventDefault();
            }
        });
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


async def render_tenants_page(request: Request) -> HTMLResponse:
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tenants - WhatsApp Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.6"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        whatsapp: '#25D366',
                        whatsappDark: '#128C7E',
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <div class="flex h-screen">
        <!-- Sidebar (same as dashboard) -->
        <aside class="w-64 bg-gray-800 border-r border-gray-700">
            <div class="p-4 border-b border-gray-700">
                <div class="flex items-center space-x-3">
                    <div class="w-10 h-10 bg-whatsapp rounded-full flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
                    </div>
                    <span class="text-xl font-bold">WhatsApp Admin</span>
                </div>
            </div>
            <nav class="p-4 space-y-2">
                <a href="/admin/dashboard" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path></svg>
                    <span>Dashboard</span>
                </a>
                <a href="/admin/tenants" class="flex items-center space-x-3 px-4 py-3 bg-whatsapp/10 text-whatsapp rounded-lg">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                    <span>Tenants</span>
                </a>
                <a href="/admin/messages" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                    <span>Messages</span>
                </a>
                <a href="/admin/webhooks" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                    <span>Webhooks</span>
                </a>
                <a href="/admin/security" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                    <span>Security</span>
                </a>
            </nav>
        </aside>

        <!-- Main Content -->
        <main class="flex-1 overflow-y-auto">
            <header class="bg-gray-800 border-b border-gray-700 px-6 py-4 flex items-center justify-between">
                <h1 class="text-2xl font-bold">Tenants</h1>
                <button onclick="showCreateTenantModal()" class="px-4 py-2 bg-whatsapp hover:bg-whatsappDark text-white rounded-lg transition flex items-center space-x-2">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path></svg>
                    <span>Add Tenant</span>
                </button>
            </header>

            <div class="p-6">
                <div class="bg-gray-800 rounded-xl border border-gray-700">
                    <div id="tenants-list" hx-get="/admin/api/tenants" hx-trigger="load" class="divide-y divide-gray-700">
                        <div class="p-6 text-center text-gray-500">Loading...</div>
                    </div>
                </div>
            </div>
        </main>
    </div>

    <!-- Create Tenant Modal (same as dashboard) -->
    <div id="create-tenant-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50">
        <div class="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-700">
            <h3 class="text-xl font-bold mb-4">Create New Tenant</h3>
            <form hx-post="/admin/api/tenants" hx-on="htmx:afterRequest: closeModalAndShowKey(event)">
                <div class="mb-4">
                    <label class="block text-sm font-medium text-gray-300 mb-2">Tenant Name</label>
                    <input type="text" name="name" required class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-whatsapp">
                </div>
                <div class="flex justify-end space-x-4">
                    <button type="button" onclick="hideCreateTenantModal()" class="px-4 py-2 text-gray-400 hover:text-white">Cancel</button>
                    <button type="submit" class="px-4 py-2 bg-whatsapp hover:bg-whatsappDark text-white rounded-lg">Create</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        function showCreateTenantModal() {
            document.getElementById('create-tenant-modal').classList.remove('hidden');
            document.getElementById('create-tenant-modal').classList.add('flex');
        }
        
        function hideCreateTenantModal() {
            document.getElementById('create-tenant-modal').classList.add('hidden');
            document.getElementById('create-tenant-modal').classList.remove('flex');
        }
        
        function closeModalAndShowKey(event) {
            if (event.detail.successful) {
                hideCreateTenantModal();
                const response = JSON.parse(event.detail.xhr.response);
                alert('Tenant created!\\n\\nAPI Key: ' + response.tenant.api_key + '\\n\\nSave this key - it won\\'t be shown again!');
                location.reload();
            }
        }
    </script>
</body>
</html>"""
    return HTMLResponse(content=html)


async def render_messages_page(request: Request) -> HTMLResponse:
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Messages - WhatsApp Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.6"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        whatsapp: '#25D366',
                        whatsappDark: '#128C7E',
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <div class="flex h-screen">
        <!-- Sidebar -->
        <aside class="w-64 bg-gray-800 border-r border-gray-700">
            <div class="p-4 border-b border-gray-700">
                <div class="flex items-center space-x-3">
                    <div class="w-10 h-10 bg-whatsapp rounded-full flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
                    </div>
                    <span class="text-xl font-bold">WhatsApp Admin</span>
                </div>
            </div>
            <nav class="p-4 space-y-2">
                <a href="/admin/dashboard" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path></svg>
                    <span>Dashboard</span>
                </a>
                <a href="/admin/tenants" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                    <span>Tenants</span>
                </a>
                <a href="/admin/messages" class="flex items-center space-x-3 px-4 py-3 bg-whatsapp/10 text-whatsapp rounded-lg">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                    <span>Messages</span>
                </a>
                <a href="/admin/webhooks" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                    <span>Webhooks</span>
                </a>
                <a href="/admin/security" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                    <span>Security</span>
                </a>
            </nav>
        </aside>

        <!-- Main Content -->
        <main class="flex-1 overflow-y-auto">
            <header class="bg-gray-800 border-b border-gray-700 px-6 py-4">
                <h1 class="text-2xl font-bold">Messages</h1>
            </header>

            <div class="p-6">
                <div class="bg-gray-800 rounded-xl border border-gray-700">
                    <div id="messages-list" hx-get="/admin/api/messages?limit=50" hx-trigger="load" class="divide-y divide-gray-700">
                        <div class="p-6 text-center text-gray-500">Loading...</div>
                    </div>
                </div>
            </div>
        </main>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)


async def render_webhooks_page(request: Request) -> HTMLResponse:
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Webhooks - WhatsApp Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.6"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        whatsapp: '#25D366',
                        whatsappDark: '#128C7E',
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <div class="flex h-screen">
        <!-- Sidebar -->
        <aside class="w-64 bg-gray-800 border-r border-gray-700">
            <div class="p-4 border-b border-gray-700">
                <div class="flex items-center space-x-3">
                    <div class="w-10 h-10 bg-whatsapp rounded-full flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
                    </div>
                    <span class="text-xl font-bold">WhatsApp Admin</span>
                </div>
            </div>
            <nav class="p-4 space-y-2">
                <a href="/admin/dashboard" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path></svg>
                    <span>Dashboard</span>
                </a>
                <a href="/admin/tenants" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                    <span>Tenants</span>
                </a>
                <a href="/admin/messages" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                    <span>Messages</span>
                </a>
                <a href="/admin/webhooks" class="flex items-center space-x-3 px-4 py-3 bg-whatsapp/10 text-whatsapp rounded-lg">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                    <span>Webhooks</span>
                </a>
                <a href="/admin/security" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                    <span>Security</span>
                </a>
            </nav>
        </aside>

        <!-- Main Content -->
        <main class="flex-1 overflow-y-auto">
            <header class="bg-gray-800 border-b border-gray-700 px-6 py-4">
                <h1 class="text-2xl font-bold">Webhooks</h1>
            </header>

            <div class="p-6">
                <div class="bg-gray-800 rounded-xl border border-gray-700">
                    <div id="webhooks-list" hx-get="/admin/api/webhooks" hx-trigger="load" class="divide-y divide-gray-700">
                        <div class="p-6 text-center text-gray-500">Loading...</div>
                    </div>
                </div>
            </div>
        </main>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)


async def render_security_page(request: Request) -> HTMLResponse:
    html = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Security - WhatsApp Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.6"></script>
    <script>
        tailwind.config = {
            darkMode: 'class',
            theme: {
                extend: {
                    colors: {
                        whatsapp: '#25D366',
                        whatsappDark: '#128C7E',
                    }
                }
            }
        }
    </script>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <div class="flex h-screen">
        <!-- Sidebar -->
        <aside class="w-64 bg-gray-800 border-r border-gray-700">
            <div class="p-4 border-b border-gray-700">
                <div class="flex items-center space-x-3">
                    <div class="w-10 h-10 bg-whatsapp rounded-full flex items-center justify-center">
                        <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
                    </div>
                    <span class="text-xl font-bold">WhatsApp Admin</span>
                </div>
            </div>
            <nav class="p-4 space-y-2">
                <a href="/admin/dashboard" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path></svg>
                    <span>Dashboard</span>
                </a>
                <a href="/admin/tenants" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>
                    <span>Tenants</span>
                </a>
                <a href="/admin/messages" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path></svg>
                    <span>Messages</span>
                </a>
                <a href="/admin/webhooks" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
                    <span>Webhooks</span>
                </a>
                <a href="/admin/security" class="flex items-center space-x-3 px-4 py-3 bg-whatsapp/10 text-whatsapp rounded-lg">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                    <span>Security</span>
                </a>
            </nav>
        </aside>

        <!-- Main Content -->
        <main class="flex-1 overflow-y-auto">
            <header class="bg-gray-800 border-b border-gray-700 px-6 py-4">
                <h1 class="text-2xl font-bold">Security & Rate Limiting</h1>
            </header>

            <div class="p-6 space-y-6">
                <!-- Blocked IPs -->
                <div class="bg-gray-800 rounded-xl border border-gray-700">
                    <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
                        <h2 class="text-lg font-semibold">Blocked IPs</h2>
                    </div>
                    <div id="blocked-ips" hx-get="/admin/api/rate-limit/blocked" hx-trigger="load, every 30s" class="divide-y divide-gray-700">
                        <div class="p-6 text-center text-gray-500">Loading...</div>
                    </div>
                </div>

                <!-- Failed Auth Attempts -->
                <div class="bg-gray-800 rounded-xl border border-gray-700">
                    <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
                        <h2 class="text-lg font-semibold">Failed Auth Attempts</h2>
                        <button hx-delete="/admin/api/rate-limit/failed-auth" hx-swap="none" hx-on="htmx:afterRequest: location.reload()" class="text-sm text-gray-400 hover:text-white">Clear All</button>
                    </div>
                    <div id="failed-auth" hx-get="/admin/api/rate-limit/failed-auth" hx-trigger="load, every 30s" class="p-6">
                        <div class="text-center text-gray-500">Loading...</div>
                    </div>
                </div>
            </div>
        </main>
    </div>
</body>
</html>"""
    return HTMLResponse(content=html)
