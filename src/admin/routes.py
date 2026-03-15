from fastapi import APIRouter, Request, Depends, HTTPException, Query, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime, UTC
import json

from ..config import settings
from ..telemetry import get_logger
from ..tenant import tenant_manager
from ..middleware import rate_limiter
from ..utils import is_safe_webhook_url
from .auth import AdminSession, require_admin_session, get_session_id
from .websocket import admin_ws_manager

logger = get_logger("whatsapp.admin")


router = APIRouter(prefix="/admin", tags=["admin"])
api_router = APIRouter(prefix="/admin/api", tags=["admin-api"])
fragments_router = APIRouter(prefix="/admin/fragments", tags=["admin-fragments"])


@router.get("/static/websocket.js")
async def get_websocket_js():
    from pathlib import Path
    from fastapi.responses import FileResponse

    js_path = Path(__file__).parent / "static" / "websocket.js"
    response = FileResponse(js_path, media_type="application/javascript")
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


class TenantCreate(BaseModel):
    name: str


class TenantUpdate(BaseModel):
    name: Optional[str] = None


class WebhookAdd(BaseModel):
    url: str


def templates(request: Request) -> dict:
    return {"request": request}


SIDEBAR_HTML = """
<aside class="w-64 bg-gray-800 border-r border-gray-700 flex flex-col h-full">
    <div class="p-4 border-b border-gray-700">
        <div class="flex items-center space-x-3">
            <div class="w-10 h-10 bg-whatsapp rounded-full flex items-center justify-center">
                <svg class="w-6 h-6 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z"/></svg>
            </div>
            <span class="text-xl font-bold">WhatsApp Admin</span>
        </div>
    </div>
    <nav class="p-4 space-y-2 flex-1">
        {nav_items}
    </nav>
    <div class="p-4 border-t border-gray-700">
        <form action="/admin/logout" method="POST">
            <button type="submit" class="w-full flex items-center justify-center space-x-2 px-4 py-2 text-gray-400 hover:text-white hover:bg-gray-700 rounded-lg transition">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"></path></svg>
                <span>Sign Out</span>
            </button>
        </form>
    </div>
</aside>
"""


def get_sidebar(active_page: str) -> str:
    nav_items = [
        (
            "dashboard",
            "Dashboard",
            "/admin/dashboard",
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z"></path>',
        ),
        (
            "tenants",
            "Tenants",
            "/admin/tenants",
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path>',
        ),
        (
            "messages",
            "Messages",
            "/admin/messages",
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z"></path>',
        ),
        (
            "webhooks",
            "Webhooks",
            "/admin/webhooks",
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path>',
        ),
        (
            "security",
            "Security",
            "/admin/security",
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path>',
        ),
        (
            "chatwoot",
            "Chatwoot",
            "/admin/chatwoot",
            '<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>',
        ),
    ]

    items_html = ""
    for key, label, href, icon in nav_items:
        if key == active_page:
            items_html += f'''<a href="{href}" class="flex items-center space-x-3 px-4 py-3 bg-whatsapp/10 text-whatsapp rounded-lg">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">{icon}</svg>
                <span>{label}</span>
            </a>'''
        else:
            items_html += f'''<a href="{href}" class="flex items-center space-x-3 px-4 py-3 text-gray-300 hover:bg-gray-700 rounded-lg transition">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">{icon}</svg>
                <span>{label}</span>
            </a>'''

    return SIDEBAR_HTML.format(nav_items=items_html)


PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title} - WhatsApp Admin</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/htmx.org@1.9.6"></script>
    <script>
        tailwind.config = {{
            darkMode: 'class',
            theme: {{
                extend: {{
                    colors: {{
                        whatsapp: '#25D366',
                        whatsappDark: '#128C7E',
                    }}
                }}
            }}
        }}
    </script>
    <script src="/admin/static/websocket.js?v=4"></script>
</head>
<body class="bg-gray-900 text-white min-h-screen">
    <div class="flex h-screen">
        {sidebar}
        <main class="flex-1 overflow-y-auto">
            {content}
        </main>
    </div>
    {modals}
    <script>{script}</script>
</body>
</html>
"""


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
        secure=not settings.debug,
        max_age=AdminSession.SESSION_DURATION_HOURS * 3600,
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
    content = """
<header class="bg-gray-800 border-b border-gray-700 px-6 py-4">
    <h1 class="text-2xl font-bold">Dashboard</h1>
</header>
<div class="p-6">
    <div hx-get="/admin/fragments/stats" hx-trigger="load, every 30s" class="grid grid-cols-1 md:grid-cols-4 gap-6 mb-8">
        <div class="bg-gray-800 rounded-xl p-6 border border-gray-700 animate-pulse"><div class="h-16"></div></div>
        <div class="bg-gray-800 rounded-xl p-6 border border-gray-700 animate-pulse"><div class="h-16"></div></div>
        <div class="bg-gray-800 rounded-xl p-6 border border-gray-700 animate-pulse"><div class="h-16"></div></div>
        <div class="bg-gray-800 rounded-xl p-6 border border-gray-700 animate-pulse"><div class="h-16"></div></div>
    </div>
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
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-8">
        <div class="lg:col-span-2 bg-gray-800 rounded-xl border border-gray-700">
            <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
                <h2 class="text-lg font-semibold">Recent Tenants</h2>
                <a href="/admin/tenants" class="text-whatsapp hover:underline text-sm">View All</a>
            </div>
            <div id="tenants-list" hx-get="/admin/fragments/tenants" hx-trigger="load, every 30s" class="divide-y divide-gray-700">
                <div class="p-6 text-center text-gray-500">Loading...</div>
            </div>
        </div>
        <div class="bg-gray-800 rounded-xl border border-gray-700">
            <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
                <h2 class="text-lg font-semibold">WebSocket Connections</h2>
                <span id="ws-count" class="text-xs bg-green-500/20 text-green-400 px-2 py-1 rounded">0</span>
            </div>
            <div id="ws-list" hx-get="/admin/fragments/websockets" hx-trigger="load, every 5s" class="p-4 max-h-80 overflow-y-auto">
                <div class="text-gray-500 text-sm">Loading...</div>
            </div>
        </div>
    </div>
</div>
"""
    modals = """
<div class="fixed top-20 right-4 z-40">
    <button id="bulk-action-btn" onclick="showBulkActions()" class="hidden px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-lg">
        Bulk Actions (<span id="selected-count">0</span>)
    </button>
</div>

<div id="bulk-actions-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50">
    <div class="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-700">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-xl font-bold">Bulk Actions</h3>
            <button onclick="hideBulkActions()" class="text-gray-400 hover:text-white">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
        <div class="space-y-3">
            <button onclick="bulkReconnect()" class="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition flex items-center justify-center gap-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                Reconnect Selected
            </button>
            <button onclick="bulkDelete()" class="w-full px-4 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg transition flex items-center justify-center gap-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                Delete Selected
            </button>
            <button onclick="hideBulkActions()" class="w-full px-4 py-3 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition">
                Cancel
            </button>
        </div>
        <p class="text-sm text-gray-400 mt-4 text-center" id="bulk-selected-text">0 tenants selected</p>
    </div>
</div>

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
<div id="tenant-actions-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50">
    <div class="bg-gray-800 rounded-xl p-6 w-full max-w-lg border border-gray-700">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-xl font-bold" id="tenant-actions-name">Tenant Actions</h3>
            <button onclick="hideTenantActionsModal()" class="text-gray-400 hover:text-white">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
        <div class="space-y-3">
            <button id="btn-reconnect" hx-post="" hx-on="htmx:afterRequest: handleAction(event, 'Reconnected')" class="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition flex items-center space-x-3">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                <span>Reconnect Session</span>
            </button>
            <button id="btn-clear-creds" hx-delete="" hx-on="htmx:afterRequest: handleAction(event, 'Credentials cleared')" class="w-full px-4 py-3 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition flex items-center space-x-3">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                <span>Clear Stored Credentials</span>
            </button>
            <div class="border-t border-gray-700 pt-3">
                <label class="block text-sm font-medium text-gray-300 mb-2">Add Webhook URL</label>
                <div class="flex gap-2">
                    <input type="url" id="new-webhook-url" placeholder="https://" class="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-whatsapp">
                    <button id="btn-add-webhook" onclick="addWebhook()" class="px-4 py-2 bg-whatsapp hover:bg-whatsappDark text-white rounded-lg text-sm">Add</button>
                </div>
            </div>
            <div class="border-t border-gray-700 pt-3">
                <button id="btn-delete" hx-delete="" hx-confirm="Are you sure you want to delete this tenant? This cannot be undone." hx-on="htmx:afterRequest: handleDelete(event)" class="w-full px-4 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg transition flex items-center space-x-3">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                    <span>Delete Tenant</span>
                </button>
            </div>
        </div>
    </div>
</div>
"""
    script = """
function selectContact(jid, name) {
    document.getElementById('send-to').value = jid;
    switchTab('messages');
    document.getElementById('send-text').focus();
}

let selectedTenants = new Set();

function toggleSelectAll() {
    const selectAll = document.getElementById('select-all-tenants');
    const checkboxes = document.querySelectorAll('.tenant-checkbox');
    
    checkboxes.forEach(cb => {
        cb.checked = selectAll.checked;
        const hash = cb.dataset.hash;
        if (selectAll.checked) {
            selectedTenants.add(hash);
        } else {
            selectedTenants.delete(hash);
        }
    });
    
    updateBulkUI();
}

function updateBulkSelection() {
    selectedTenants.clear();
    const checkboxes = document.querySelectorAll('.tenant-checkbox:checked');
    checkboxes.forEach(cb => selectedTenants.add(cb.dataset.hash));
    
    const selectAll = document.getElementById('select-all-tenants');
    const allCheckboxes = document.querySelectorAll('.tenant-checkbox');
    selectAll.checked = checkboxes.length === allCheckboxes.length;
    
    updateBulkUI();
}

function updateBulkUI() {
    const count = selectedTenants.size;
    const bulkBtn = document.getElementById('bulk-action-btn');
    const countSpan = document.getElementById('selected-count');
    const modalText = document.getElementById('bulk-selected-text');
    
    if (count > 0) {
        if (bulkBtn) {
            bulkBtn.classList.remove('hidden');
        }
        if (countSpan) {
            countSpan.textContent = count;
        }
        if (modalText) {
            modalText.textContent = count + ' tenant' + (count !== 1 ? 's' : '') + ' selected';
        }
    } else {
        if (bulkBtn) {
            bulkBtn.classList.add('hidden');
        }
    }
}

function showBulkActions() {
    if (selectedTenants.size === 0) {
        alert('No tenants selected');
        return;
    }
    const modal = document.getElementById('bulk-actions-modal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    }
}

function hideBulkActions() {
    const modal = document.getElementById('bulk-actions-modal');
    if (modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    }
}

async function bulkReconnect() {
    if (selectedTenants.size === 0) return;
    
    if (!confirm(`Reconnect ${selectedTenants.size} tenant(s)?`)) return;
    
    hideBulkActions();
    
    const hashes = Array.from(selectedTenants);
    const response = await fetch('/admin/api/tenants/bulk/reconnect', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tenant_hashes: hashes})
    });
    
    const data = await response.json();
    
    alert(`Reconnect complete:\n✅ Successful: ${data.successful}\n❌ Failed: ${data.failed}`);
    
    // Clear selection and refresh
    selectedTenants.clear();
    updateBulkUI();
    htmx.trigger('#tenants-list', 'load');
}

async function bulkDelete() {
    if (selectedTenants.size === 0) return;
    
    const count = selectedTenants.size;
    const confirmed = confirm(`Delete ${count} tenant(s)?\n\nThis CANNOT be undone!`);
    if (!confirmed) return;
    
    const typed = prompt(`Type "DELETE ${count} TENANTS" to confirm:`);
    if (typed !== `DELETE ${count} TENANTS`) {
        alert('Confirmation text did not match');
        return;
    }
    
    hideBulkActions();
    
    const hashes = Array.from(selectedTenants);
    const response = await fetch('/admin/api/tenants/bulk', {
        method: 'DELETE',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tenant_hashes: hashes})
    });
    
    const data = await response.json();
    
    alert(`Delete complete:\n✅ Deleted: ${data.deleted}\n❌ Failed: ${data.failed}`);
    
    // Clear selection and refresh
    selectedTenants.clear();
    updateBulkUI();
    htmx.trigger('#tenants-list', 'load');
}

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
        htmx.trigger('#tenants-list', 'load');
    }
}
function showTenantActions(hash, name) {
    document.getElementById('tenant-actions-name').textContent = name;
    document.getElementById('btn-reconnect').setAttribute('hx-post', '/admin/api/tenants/' + hash + '/reconnect');
    document.getElementById('btn-clear-creds').setAttribute('hx-delete', '/admin/api/tenants/' + hash + '/credentials');
    document.getElementById('btn-delete').setAttribute('hx-delete', '/admin/api/tenants/' + hash);
    document.getElementById('tenant-actions-modal').dataset.hash = hash;
    document.getElementById('new-webhook-url').value = '';
    document.getElementById('tenant-actions-modal').classList.remove('hidden');
    document.getElementById('tenant-actions-modal').classList.add('flex');
    htmx.process(document.getElementById('tenant-actions-modal'));
}
function hideTenantActionsModal() {
    document.getElementById('tenant-actions-modal').classList.add('hidden');
    document.getElementById('tenant-actions-modal').classList.remove('flex');
}
function addWebhook() {
    const url = document.getElementById('new-webhook-url').value;
    if (!url) { alert('Please enter a webhook URL'); return; }
    const hash = document.getElementById('tenant-actions-modal').dataset.hash;
    fetch('/admin/api/tenants/' + hash + '/webhooks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: url})
    }).then(r => r.json()).then(data => {
        if (data.status === 'added') {
            document.getElementById('new-webhook-url').value = '';
            alert('Webhook added!');
            htmx.trigger('#tenants-list', 'load');
        } else {
            alert('Failed: ' + (data.detail || JSON.stringify(data)));
        }
    }).catch(e => alert('Error: ' + e));
}
function handleAction(event, msg) {
    if (event.detail.successful) {
        alert(msg);
        htmx.trigger('#tenants-list', 'load');
        hideTenantActionsModal();
    }
}
function handleDelete(event) {
    if (event.detail.successful) {
        alert('Tenant deleted');
        htmx.trigger('#tenants-list', 'load');
        hideTenantActionsModal();
    }
}

async function toggleEnabled(hash, enabled) {
    const action = enabled ? 'enable' : 'disable';
    if (!confirm(`Are you sure you want to ${action} this tenant?`)) return;
    
    const response = await fetch('/admin/api/tenants/' + hash + '/enabled', {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({enabled: enabled})
    });
    
    const data = await response.json();
    if (response.ok) {
        htmx.trigger('#tenants-list', 'load');
    } else {
        alert('Failed: ' + (data.detail || JSON.stringify(data)));
    }
}

let expandedTenant = null;
function toggleTenantPanel(hash) {
    const panel = document.getElementById('tenant-panel-' + hash);
    const chevron = document.getElementById('chevron-' + hash);
    
    if (expandedTenant && expandedTenant !== hash) {
        const prevPanel = document.getElementById('tenant-panel-' + expandedTenant);
        const prevChevron = document.getElementById('chevron-' + expandedTenant);
        if (prevPanel) { prevPanel.classList.add('hidden'); prevPanel.innerHTML = ''; }
        if (prevChevron) { prevChevron.classList.remove('rotate-90'); }
    }
    
    if (panel.classList.contains('hidden')) {
        panel.classList.remove('hidden');
        chevron.classList.add('rotate-90');
        expandedTenant = hash;
        htmx.ajax('GET', '/admin/fragments/tenant-panel/' + hash, {target: panel, swap: 'innerHTML'});
    } else {
        panel.classList.add('hidden');
        chevron.classList.remove('rotate-90');
        panel.innerHTML = '';
        expandedTenant = null;
    }
}
function sendMsgAsTenant(hash) {
    const chatSelect = document.getElementById('chat-select-' + hash);
    const manualJid = document.getElementById('manual-jid-' + hash);
    const textInput = document.getElementById('msg-text-' + hash);
    
    const to = manualJid.value || chatSelect.value;
    const text = textInput.value;
    
    if (!to) { alert('Please select or enter a recipient'); return; }
    if (!text) { alert('Please enter a message'); return; }
    
    fetch('/admin/api/tenants/' + hash + '/send', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({to: to, text: text})
    }).then(r => r.json()).then(data => {
        if (data.status === 'sent') {
            textInput.value = '';
            htmx.ajax('GET', '/admin/fragments/tenant-panel/' + hash, {
                target: document.getElementById('tenant-panel-' + hash),
                swap: 'innerHTML'
            });
        } else {
            alert('Failed: ' + (data.detail || JSON.stringify(data)));
        }
    }).catch(e => alert('Error: ' + e));
}
"""
    html = PAGE_TEMPLATE.format(
        title="Dashboard",
        sidebar=get_sidebar("dashboard"),
        content=content,
        modals=modals,
        script=script,
    )
    return HTMLResponse(content=html)


@router.get("/tenants", response_class=HTMLResponse)
async def admin_tenants_page(
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    content = """
<header class="bg-gray-800 border-b border-gray-700 px-6 py-4 flex items-center justify-between">
    <h1 class="text-2xl font-bold">Tenants</h1>
    <div class="flex items-center gap-3">
        <button onclick="showBulkActions()" id="bulk-action-btn" class="hidden px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition">
            Bulk Actions
        </button>
        <button onclick="showCreateTenantModal()" class="px-4 py-2 bg-whatsapp hover:bg-whatsappDark text-white rounded-lg transition flex items-center space-x-2">
            <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 6v6m0 0v6m0-6h6m-6 0H6"></path></svg>
            <span>Add Tenant</span>
        </button>
    </div>
</header>
<div class="p-6">
    <div class="bg-gray-800 rounded-xl border border-gray-700">
        <div class="px-6 py-3 border-b border-gray-700 flex items-center gap-3">
            <input type="checkbox" id="select-all-tenants" onchange="toggleSelectAll()" class="w-4 h-4">
            <label for="select-all-tenants" class="text-sm text-gray-400">Select All</label>
            <span id="selected-count" class="text-sm text-gray-400 ml-4 hidden">0 selected</span>
        </div>
        <div id="tenants-list" hx-get="/admin/fragments/tenants" hx-trigger="load" class="divide-y divide-gray-700">
            <div class="p-6 text-center text-gray-500">Loading...</div>
        </div>
    </div>
</div>

<div id="bulk-actions-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50">
    <div class="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-700">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-xl font-bold">Bulk Actions</h3>
            <button onclick="hideBulkActions()" class="text-gray-400 hover:text-white">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
        <div class="space-y-3">
            <button onclick="bulkReconnect()" class="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition">
                Reconnect Selected
            </button>
            <button onclick="bulkDelete()" class="w-full px-4 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg transition">
                Delete Selected
            </button>
            <button onclick="hideBulkActions()" class="w-full px-4 py-3 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition">
                Cancel
            </button>
        </div>
    </div>
</div>
"""
    modals = """
<div class="fixed top-20 right-4 z-40">
    <button id="bulk-action-btn" onclick="showBulkActions()" class="hidden px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg shadow-lg">
        Bulk Actions (<span id="selected-count">0</span>)
    </button>
</div>

<div id="bulk-actions-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50">
    <div class="bg-gray-800 rounded-xl p-6 w-full max-w-md border border-gray-700">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-xl font-bold">Bulk Actions</h3>
            <button onclick="hideBulkActions()" class="text-gray-400 hover:text-white">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
        <div class="space-y-3">
            <button onclick="bulkReconnect()" class="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition flex items-center justify-center gap-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                Reconnect Selected
            </button>
            <button onclick="bulkDelete()" class="w-full px-4 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg transition flex items-center justify-center gap-2">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                Delete Selected
            </button>
            <button onclick="hideBulkActions()" class="w-full px-4 py-3 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition">
                Cancel
            </button>
        </div>
        <p class="text-sm text-gray-400 mt-4 text-center" id="bulk-selected-text">0 tenants selected</p>
    </div>
</div>

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
<div id="tenant-actions-modal" class="fixed inset-0 bg-black/50 hidden items-center justify-center z-50">
    <div class="bg-gray-800 rounded-xl p-6 w-full max-w-lg border border-gray-700">
        <div class="flex items-center justify-between mb-4">
            <h3 class="text-xl font-bold" id="tenant-actions-name">Tenant Actions</h3>
            <button onclick="hideTenantActionsModal()" class="text-gray-400 hover:text-white">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path></svg>
            </button>
        </div>
        <div class="space-y-3">
            <button id="btn-reconnect" hx-post="" hx-on="htmx:afterRequest: handleAction(event, 'Reconnected')" class="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition flex items-center space-x-3">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg>
                <span>Reconnect Session</span>
            </button>
            <button id="btn-clear-creds" hx-delete="" hx-on="htmx:afterRequest: handleAction(event, 'Credentials cleared')" class="w-full px-4 py-3 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition flex items-center space-x-3">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"></path></svg>
                <span>Clear Stored Credentials</span>
            </button>
            <div class="border-t border-gray-700 pt-3">
                <label class="block text-sm font-medium text-gray-300 mb-2">Add Webhook URL</label>
                <div class="flex gap-2">
                    <input type="url" id="new-webhook-url" placeholder="https://" class="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-whatsapp">
                    <button id="btn-add-webhook" onclick="addWebhook()" class="px-4 py-2 bg-whatsapp hover:bg-whatsappDark text-white rounded-lg text-sm">Add</button>
                </div>
            </div>
            <div class="border-t border-gray-700 pt-3">
                <button id="btn-delete" hx-delete="" hx-confirm="Are you sure you want to delete this tenant? This cannot be undone." hx-on="htmx:afterRequest: handleDelete(event)" class="w-full px-4 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg transition flex items-center space-x-3">
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"></path></svg>
                    <span>Delete Tenant</span>
                </button>
            </div>
        </div>
    </div>
</div>
"""
    script = """
function selectContact(jid, name) {
    document.getElementById('send-to').value = jid;
    switchTab('messages');
    document.getElementById('send-text').focus();
}

let selectedTenants = new Set();

function toggleSelectAll() {
    const selectAll = document.getElementById('select-all-tenants');
    const checkboxes = document.querySelectorAll('.tenant-checkbox');
    
    checkboxes.forEach(cb => {
        cb.checked = selectAll.checked;
        const hash = cb.dataset.hash;
        if (selectAll.checked) {
            selectedTenants.add(hash);
        } else {
            selectedTenants.delete(hash);
        }
    });
    
    updateBulkUI();
}

function updateBulkSelection() {
    selectedTenants.clear();
    const checkboxes = document.querySelectorAll('.tenant-checkbox:checked');
    checkboxes.forEach(cb => selectedTenants.add(cb.dataset.hash));
    
    const selectAll = document.getElementById('select-all-tenants');
    const allCheckboxes = document.querySelectorAll('.tenant-checkbox');
    selectAll.checked = checkboxes.length === allCheckboxes.length;
    
    updateBulkUI();
}

function updateBulkUI() {
    const count = selectedTenants.size;
    const bulkBtn = document.getElementById('bulk-action-btn');
    const countSpan = document.getElementById('selected-count');
    const modalText = document.getElementById('bulk-selected-text');
    
    if (count > 0) {
        if (bulkBtn) {
            bulkBtn.classList.remove('hidden');
        }
        if (countSpan) {
            countSpan.textContent = count;
        }
        if (modalText) {
            modalText.textContent = count + ' tenant' + (count !== 1 ? 's' : '') + ' selected';
        }
    } else {
        if (bulkBtn) {
            bulkBtn.classList.add('hidden');
        }
    }
}

function showBulkActions() {
    if (selectedTenants.size === 0) {
        alert('No tenants selected');
        return;
    }
    const modal = document.getElementById('bulk-actions-modal');
    if (modal) {
        modal.classList.remove('hidden');
        modal.classList.add('flex');
    }
}

function hideBulkActions() {
    const modal = document.getElementById('bulk-actions-modal');
    if (modal) {
        modal.classList.add('hidden');
        modal.classList.remove('flex');
    }
}

async function bulkReconnect() {
    if (selectedTenants.size === 0) return;
    
    if (!confirm(`Reconnect ${selectedTenants.size} tenant(s)?`)) return;
    
    hideBulkActions();
    
    const hashes = Array.from(selectedTenants);
    const response = await fetch('/admin/api/tenants/bulk/reconnect', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tenant_hashes: hashes})
    });
    
    const data = await response.json();
    
    alert(`Reconnect complete:\n✅ Successful: ${data.successful}\n❌ Failed: ${data.failed}`);
    
    // Clear selection and refresh
    selectedTenants.clear();
    updateBulkUI();
    htmx.trigger('#tenants-list', 'load');
}

async function bulkDelete() {
    if (selectedTenants.size === 0) return;
    
    const count = selectedTenants.size;
    const confirmed = confirm(`Delete ${count} tenant(s)?\n\nThis CANNOT be undone!`);
    if (!confirmed) return;
    
    const typed = prompt(`Type "DELETE ${count} TENANTS" to confirm:`);
    if (typed !== `DELETE ${count} TENANTS`) {
        alert('Confirmation text did not match');
        return;
    }
    
    hideBulkActions();
    
    const hashes = Array.from(selectedTenants);
    const response = await fetch('/admin/api/tenants/bulk', {
        method: 'DELETE',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({tenant_hashes: hashes})
    });
    
    const data = await response.json();
    
    alert(`Delete complete:\n✅ Deleted: ${data.deleted}\n❌ Failed: ${data.failed}`);
    
    // Clear selection and refresh
    selectedTenants.clear();
    updateBulkUI();
    htmx.trigger('#tenants-list', 'load');
}

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
        htmx.trigger('#tenants-list', 'load');
    }
}
function showTenantActions(hash, name) {
    document.getElementById('tenant-actions-name').textContent = name;
    document.getElementById('btn-reconnect').setAttribute('hx-post', '/admin/api/tenants/' + hash + '/reconnect');
    document.getElementById('btn-clear-creds').setAttribute('hx-delete', '/admin/api/tenants/' + hash + '/credentials');
    document.getElementById('btn-delete').setAttribute('hx-delete', '/admin/api/tenants/' + hash);
    document.getElementById('tenant-actions-modal').dataset.hash = hash;
    document.getElementById('new-webhook-url').value = '';
    document.getElementById('tenant-actions-modal').classList.remove('hidden');
    document.getElementById('tenant-actions-modal').classList.add('flex');
    htmx.process(document.getElementById('tenant-actions-modal'));
}
function hideTenantActionsModal() {
    document.getElementById('tenant-actions-modal').classList.add('hidden');
    document.getElementById('tenant-actions-modal').classList.remove('flex');
}
function addWebhook() {
    const url = document.getElementById('new-webhook-url').value;
    if (!url) { alert('Please enter a webhook URL'); return; }
    const hash = document.getElementById('tenant-actions-modal').dataset.hash;
    fetch('/admin/api/tenants/' + hash + '/webhooks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: url})
    }).then(r => r.json()).then(data => {
        if (data.status === 'added') {
            document.getElementById('new-webhook-url').value = '';
            alert('Webhook added!');
            htmx.trigger('#tenants-list', 'load');
        } else {
            alert('Failed: ' + (data.detail || JSON.stringify(data)));
        }
    }).catch(e => alert('Error: ' + e));
}
function handleAction(event, msg) {
    if (event.detail.successful) {
        alert(msg);
        htmx.trigger('#tenants-list', 'load');
        hideTenantActionsModal();
    }
}
function handleDelete(event) {
    if (event.detail.successful) {
        alert('Tenant deleted');
        htmx.trigger('#tenants-list', 'load');
        hideTenantActionsModal();
    }
}

async function toggleEnabled(hash, enabled) {
    const action = enabled ? 'enable' : 'disable';
    if (!confirm(`Are you sure you want to ${action} this tenant?`)) return;
    
    const response = await fetch('/admin/api/tenants/' + hash + '/enabled', {
        method: 'PATCH',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({enabled: enabled})
    });
    
    const data = await response.json();
    if (response.ok) {
        htmx.trigger('#tenants-list', 'load');
    } else {
        alert('Failed: ' + (data.detail || JSON.stringify(data)));
    }
}

let expandedTenant = null;
function toggleTenantPanel(hash) {
    const panel = document.getElementById('tenant-panel-' + hash);
    const chevron = document.getElementById('chevron-' + hash);
    
    if (expandedTenant && expandedTenant !== hash) {
        const prevPanel = document.getElementById('tenant-panel-' + expandedTenant);
        const prevChevron = document.getElementById('chevron-' + expandedTenant);
        if (prevPanel) { prevPanel.classList.add('hidden'); prevPanel.innerHTML = ''; }
        if (prevChevron) { prevChevron.classList.remove('rotate-90'); }
    }
    
    if (panel.classList.contains('hidden')) {
        panel.classList.remove('hidden');
        chevron.classList.add('rotate-90');
        expandedTenant = hash;
        htmx.ajax('GET', '/admin/fragments/tenant-panel/' + hash, {target: panel, swap: 'innerHTML'});
    } else {
        panel.classList.add('hidden');
        chevron.classList.remove('rotate-90');
        panel.innerHTML = '';
        expandedTenant = null;
    }
}
function sendMsgAsTenant(hash) {
    const chatSelect = document.getElementById('chat-select-' + hash);
    const manualJid = document.getElementById('manual-jid-' + hash);
    const textInput = document.getElementById('msg-text-' + hash);
    
    const to = manualJid.value || chatSelect.value;
    const text = textInput.value;
    
    if (!to) { alert('Please select or enter a recipient'); return; }
    if (!text) { alert('Please enter a message'); return; }
    
    fetch('/admin/api/tenants/' + hash + '/send', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({to: to, text: text})
    }).then(r => r.json()).then(data => {
        if (data.status === 'sent') {
            textInput.value = '';
            htmx.ajax('GET', '/admin/fragments/tenant-panel/' + hash, {
                target: document.getElementById('tenant-panel-' + hash),
                swap: 'innerHTML'
            });
        } else {
            alert('Failed: ' + (data.detail || JSON.stringify(data)));
        }
    }).catch(e => alert('Error: ' + e));
}
"""
    html = PAGE_TEMPLATE.format(
        title="Tenants",
        sidebar=get_sidebar("tenants"),
        content=content,
        modals=modals,
        script=script,
    )
    return HTMLResponse(content=html)


@router.get("/messages", response_class=HTMLResponse)
async def admin_messages_page(
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    # Get tenant list for filter dropdown
    tenants = tenant_manager.list_tenants()
    tenant_options = "".join(
        [f'<option value="{t.api_key_hash}">{t.name}</option>' for t in tenants]
    )

    content = f"""
<header class="bg-gray-800 border-b border-gray-700 px-6 py-4">
    <h1 class="text-2xl font-bold">Messages</h1>
</header>
<div class="p-6">
    <div class="bg-gray-800 rounded-lg p-4 mb-4 border border-gray-700">
        <div class="flex gap-4 items-center flex-wrap">
            <input type="text" 
                   id="message-search" 
                   placeholder="Search messages..."
                   class="flex-1 min-w-64 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-whatsapp"
                   onkeyup="debounceSearch()">
            
            <select id="tenant-filter" class="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-whatsapp" onchange="searchMessages()">
                <option value="">All Tenants</option>
                {tenant_options}
            </select>
            
            <select id="direction-filter" class="px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-whatsapp" onchange="searchMessages()">
                <option value="">All Directions</option>
                <option value="inbound">Inbound</option>
                <option value="outbound">Outbound</option>
            </select>
            
            <button onclick="searchMessages()" class="px-6 py-2 bg-whatsapp hover:bg-whatsappDark text-white rounded-lg font-medium transition">
                Search
            </button>
            
            <button onclick="clearSearch()" class="px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded-lg transition">
                Clear
            </button>
        </div>
    </div>
    
    <div class="bg-gray-800 rounded-xl border border-gray-700 overflow-hidden">
        <div id="messages-list" hx-get="/admin/fragments/messages?limit=50" hx-trigger="load" class="divide-y divide-gray-700">
            <div class="p-6 text-center text-gray-500">Loading...</div>
        </div>
    </div>
</div>
"""
    script = """
let searchTimeout = null;

function debounceSearch() {
    clearTimeout(searchTimeout);
    searchTimeout = setTimeout(() => {
        searchMessages();
    }, 300);
}

function searchMessages() {
    const search = document.getElementById('message-search').value;
    const tenant = document.getElementById('tenant-filter').value;
    const direction = document.getElementById('direction-filter').value;
    
    let url = '/admin/fragments/messages?limit=50';
    if (search) url += '&search=' + encodeURIComponent(search);
    if (tenant) url += '&tenant_hash=' + encodeURIComponent(tenant);
    if (direction) url += '&direction=' + encodeURIComponent(direction);
    
    htmx.ajax('GET', url, {
        target: '#messages-list',
        swap: 'innerHTML'
    });
}

function clearSearch() {
    document.getElementById('message-search').value = '';
    document.getElementById('tenant-filter').value = '';
    document.getElementById('direction-filter').value = '';
    searchMessages();
}
"""

    html = PAGE_TEMPLATE.format(
        title="Messages",
        sidebar=get_sidebar("messages"),
        content=content,
        modals="",
        script=script,
    )
    return HTMLResponse(content=html)


@router.get("/webhooks", response_class=HTMLResponse)
async def admin_webhooks_page(
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    content = """
<header class="bg-gray-800 border-b border-gray-700 px-6 py-4">
    <h1 class="text-2xl font-bold">Webhooks</h1>
</header>
<div class="p-6 space-y-6">
    <div class="bg-gray-800 rounded-xl border border-gray-700">
        <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <h2 class="text-lg font-semibold">Registered Webhooks</h2>
        </div>
        <div id="webhooks-list" hx-get="/admin/fragments/webhooks" hx-trigger="load" class="divide-y divide-gray-700">
            <div class="p-6 text-center text-gray-500">Loading...</div>
        </div>
    </div>
    <div class="bg-gray-800 rounded-xl border border-gray-700">
        <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <h2 class="text-lg font-semibold">Recent Webhook Attempts</h2>
        </div>
        <div id="webhook-history" hx-get="/admin/fragments/webhook-history?limit=50" hx-trigger="load" class="divide-y divide-gray-700">
            <div class="p-6 text-center text-gray-500">Loading...</div>
        </div>
    </div>
</div>
"""
    html = PAGE_TEMPLATE.format(
        title="Webhooks",
        sidebar=get_sidebar("webhooks"),
        content=content,
        modals="",
        script="",
    )
    return HTMLResponse(content=html)


@router.get("/security", response_class=HTMLResponse)
async def admin_security_page(
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    content = """
<header class="bg-gray-800 border-b border-gray-700 px-6 py-4">
    <h1 class="text-2xl font-bold">Security & Rate Limiting</h1>
</header>
<div class="p-6 space-y-6">
    <div class="bg-gray-800 rounded-xl border border-gray-700">
        <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <h2 class="text-lg font-semibold">Blocked IPs</h2>
            <span class="text-sm text-gray-400">Auto-blocked after 5 failed auth attempts</span>
        </div>
        <div id="blocked-ips" hx-get="/admin/fragments/blocked-ips" hx-trigger="load, every 30s" class="divide-y divide-gray-700">
            <div class="p-6 text-center text-gray-500">Loading...</div>
        </div>
    </div>
    <div class="bg-gray-800 rounded-xl border border-gray-700">
        <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <h2 class="text-lg font-semibold">Failed Auth Attempts</h2>
            <button hx-delete="/admin/api/rate-limit/failed-auth" hx-swap="none" hx-on="htmx:afterRequest: htmx.trigger('#failed-auth', 'load')" class="text-sm text-gray-400 hover:text-white px-3 py-1 rounded border border-gray-600 hover:border-gray-500">Clear All</button>
        </div>
        <div id="failed-auth" hx-get="/admin/fragments/failed-auth" hx-trigger="load, every 30s" class="divide-y divide-gray-700">
            <div class="p-6 text-center text-gray-500">Loading...</div>
        </div>
    </div>
</div>
"""
    html = PAGE_TEMPLATE.format(
        title="Security",
        sidebar=get_sidebar("security"),
        content=content,
        modals="",
        script="",
    )
    return HTMLResponse(content=html)


@router.get("/chatwoot", response_class=HTMLResponse)
async def admin_chatwoot_page(
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    content = """
<header class="bg-gray-800 border-b border-gray-700 px-6 py-4">
    <h1 class="text-2xl font-bold">Chatwoot Integration</h1>
</header>
<div class="p-6 space-y-6">
    <div class="bg-gray-800 rounded-xl border border-gray-700">
        <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <h2 class="text-lg font-semibold">Configuration</h2>
        </div>
        <div id="chatwoot-config" hx-get="/admin/fragments/chatwoot/config" hx-trigger="load" class="p-6">
            <div class="text-center text-gray-500">Loading...</div>
        </div>
    </div>
    <div class="bg-gray-800 rounded-xl border border-gray-700">
        <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <h2 class="text-lg font-semibold">Tenant Chatwoot Settings</h2>
        </div>
        <div id="chatwoot-tenants" hx-get="/admin/fragments/chatwoot/tenants" hx-trigger="load" class="divide-y divide-gray-700">
            <div class="p-6 text-center text-gray-500">Loading...</div>
        </div>
    </div>
</div>

<div id="chatwoot-tenant-modal" class="hidden fixed inset-0 bg-black/50 flex items-center justify-center z-50">
    <div class="bg-gray-800 rounded-xl border border-gray-700 w-full max-w-md mx-4">
        <div class="px-6 py-4 border-b border-gray-700 flex items-center justify-between">
            <h3 class="text-lg font-semibold">Tenant Chatwoot Settings</h3>
            <button onclick="closeChatwootTenantModal()" class="text-gray-400 hover:text-white">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
            </button>
        </div>
        <div class="p-6 space-y-4">
            <input type="hidden" id="chatwoot-tenant-hash">
            <div class="flex items-center gap-3">
                <input type="checkbox" id="chatwoot-tenant-enabled" class="w-4 h-4 rounded bg-gray-700 border-gray-600">
                <label for="chatwoot-tenant-enabled" class="text-sm">Enable Chatwoot</label>
            </div>
            <div class="flex items-center gap-3">
                <input type="checkbox" id="chatwoot-tenant-sign" class="w-4 h-4 rounded bg-gray-700 border-gray-600">
                <label for="chatwoot-tenant-sign" class="text-sm">Sign Messages</label>
            </div>
            <div class="flex items-center gap-3">
                <input type="checkbox" id="chatwoot-tenant-reopen" class="w-4 h-4 rounded bg-gray-700 border-gray-600">
                <label for="chatwoot-tenant-reopen" class="text-sm">Reopen Conversation</label>
            </div>
            <div id="chatwoot-tenant-status" class="text-sm"></div>
        </div>
        <div class="px-6 py-4 border-t border-gray-700 flex justify-end gap-3">
            <button onclick="closeChatwootTenantModal()" class="px-4 py-2 text-sm text-gray-400 hover:text-white">Cancel</button>
            <button onclick="saveChatwootTenantConfig()" class="px-4 py-2 text-sm bg-blue-600 hover:bg-blue-700 rounded-lg">Save</button>
        </div>
    </div>
</div>
"""
    script = """
async function toggleChatwootForTenant(tenantHash, currentEnabled) {
    const newEnabled = !currentEnabled;
    try {
        const response = await fetch(`/admin/api/tenants/${tenantHash}/chatwoot`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                enabled: newEnabled,
                sign_messages: true,
                reopen_conversation: true
            })
        });
        
        if (response.ok) {
            htmx.ajax('GET', '/admin/fragments/chatwoot/tenants', {target: '#chatwoot-tenants', swap: 'innerHTML'});
        } else {
            const data = await response.json();
            alert(data.detail || 'Failed to update');
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

function showChatwootTenantConfig(tenantHash) {
    document.getElementById('chatwoot-tenant-hash').value = tenantHash;
    document.getElementById('chatwoot-tenant-enabled').checked = false;
    document.getElementById('chatwoot-tenant-sign').checked = true;
    document.getElementById('chatwoot-tenant-reopen').checked = true;
    document.getElementById('chatwoot-tenant-modal').classList.remove('hidden');
}

function closeChatwootTenantModal() {
    document.getElementById('chatwoot-tenant-modal').classList.add('hidden');
}

async function saveChatwootTenantConfig() {
    const tenantHash = document.getElementById('chatwoot-tenant-hash').value;
    const enabled = document.getElementById('chatwoot-tenant-enabled').checked;
    const signMessages = document.getElementById('chatwoot-tenant-sign').checked;
    const reopenConversation = document.getElementById('chatwoot-tenant-reopen').checked;
    const status = document.getElementById('chatwoot-tenant-status');
    
    status.textContent = 'Saving...';
    status.className = 'text-sm text-gray-400';
    
    try {
        const response = await fetch(`/admin/api/tenants/${tenantHash}/chatwoot`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                enabled: enabled,
                sign_messages: signMessages,
                reopen_conversation: reopenConversation
            })
        });
        
        const data = await response.json();
        
        if (response.ok) {
            status.textContent = 'Saved!';
            status.className = 'text-sm text-green-400';
            setTimeout(() => {
                closeChatwootTenantModal();
                htmx.ajax('GET', '/admin/fragments/chatwoot/tenants', {target: '#chatwoot-tenants', swap: 'innerHTML'});
            }, 500);
        } else {
            status.textContent = data.detail || 'Failed to save';
            status.className = 'text-sm text-red-400';
        }
    } catch (e) {
        status.textContent = 'Error: ' + e.message;
        status.className = 'text-sm text-red-400';
    }
}

async function syncChatwootContacts(tenantHash) {
    if (!confirm('Sync all WhatsApp contacts to Chatwoot?')) return;
    
    try {
        const response = await fetch(`/admin/api/tenants/${tenantHash}/chatwoot/sync-contacts`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        
        const data = await response.json();
        
        if (response.ok) {
            alert('Contacts synced!\\nCreated: ' + data.created + '\\nUpdated: ' + data.updated + '\\nSkipped: ' + data.skipped);
        } else {
            alert(data.detail || 'Failed to sync contacts');
        }
    } catch (e) {
        alert('Error: ' + e.message);
    }
}

async function syncChatwootMessages(tenantHash) {
    if (!confirm('Sync WhatsApp message history to Chatwoot? This may take a while for large histories.')) return;
    
    const button = event.target;
    const originalText = button.textContent;
    button.disabled = true;
    button.textContent = 'Syncing...';
    
    try {
        const response = await fetch(`/admin/api/tenants/${tenantHash}/chatwoot/sync-messages`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'}
        });
        
        const data = await response.json();
        
        if (response.ok) {
            const errorInfo = data.errors > 0 ? '\\nErrors: ' + data.errors : '';
            alert('Messages synced!\\nSynced: ' + data.synced + '\\nSkipped: ' + data.skipped + errorInfo);
        } else {
            alert(data.detail || 'Failed to sync messages');
        }
    } catch (e) {
        alert('Error: ' + e.message);
    } finally {
        button.disabled = false;
        button.textContent = originalText;
    }
}
"""
    html = PAGE_TEMPLATE.format(
        title="Chatwoot",
        sidebar=get_sidebar("chatwoot"),
        content=content,
        modals="",
        script=script,
    )
    return HTMLResponse(content=html)


@router.get("/tenants/{tenant_hash}", response_class=HTMLResponse)
async def admin_tenant_details_page(
    tenant_hash: str,
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    tenant = tenant_manager._tenants.get(tenant_hash)
    if not tenant:
        return HTMLResponse(
            content='<h1 class="text-2xl text-red-400 p-6">Tenant not found</h1>',
            status_code=404,
        )

    db = tenant_manager._db
    messages_count = 0

    if db:
        _, messages_count = await db.list_messages(tenant_hash=tenant_hash, limit=1)

    # Build tenant info
    tenant_name = tenant.name
    tenant_phone = tenant.self_phone or "No phone"
    tenant_created = tenant.created_at.strftime("%Y-%m-%d")
    tenant_jid = tenant.self_jid or "N/A"
    tenant_last_conn = (
        tenant.last_connected_at.strftime("%Y-%m-%d %H:%M")
        if tenant.last_connected_at
        else "Never"
    )

    if tenant.connection_state == "connected":
        status_badge = '<span class="px-3 py-1 text-sm bg-green-500/20 text-green-400 rounded-full">Connected</span>'
    else:
        status_badge = '<span class="px-3 py-1 text-sm bg-gray-500/20 text-gray-400 rounded-full">Disconnected</span>'

    auth_badge = (
        '<span class="px-3 py-1 text-sm bg-blue-500/20 text-blue-400 rounded-full">Has Auth</span>'
        if tenant.has_auth
        else ""
    )

    # Build webhooks list
    if tenant.webhook_urls:
        webhooks_html = "".join(
            [
                f'<div class="flex items-center justify-between p-3 bg-gray-700/50 rounded-lg"><span class="text-whatsapp">{url}</span><button onclick="removeWebhook(\'{url}\')" class="text-red-400 hover:text-red-300">Remove</button></div>'
                for url in tenant.webhook_urls
            ]
        )
    else:
        webhooks_html = '<div class="text-gray-500">No webhooks configured</div>'

    content = f"""
<header class="bg-gray-800 border-b border-gray-700 px-6 py-4">
    <div class="flex items-center justify-between">
        <div class="flex items-center gap-4">
            <a href="/admin/tenants" class="text-gray-400 hover:text-white">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 19l-7-7 7-7"></path>
                </svg>
            </a>
            <div>
                <h1 class="text-2xl font-bold">{tenant_name}</h1>
                <p class="text-sm text-gray-400">{tenant_phone} | Created {tenant_created}</p>
            </div>
        </div>
        <div class="flex items-center gap-3">
            {status_badge}
            {auth_badge}
        </div>
    </div>
</header>

<div class="p-6">
    <div class="grid grid-cols-4 gap-4 mb-6">
        <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <p class="text-gray-400 text-sm">Messages</p>
            <p class="text-2xl font-bold mt-1">{messages_count:,}</p>
        </div>
        <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <p class="text-gray-400 text-sm">Webhooks</p>
            <p class="text-2xl font-bold mt-1">{len(tenant.webhook_urls)}</p>
        </div>
        <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <p class="text-gray-400 text-sm">JID</p>
            <p class="text-sm font-mono mt-1 truncate" title="{tenant_jid}">{tenant_jid}</p>
        </div>
        <div class="bg-gray-800 rounded-lg p-4 border border-gray-700">
            <p class="text-gray-400 text-sm">Last Connected</p>
            <p class="text-sm mt-1">{tenant_last_conn}</p>
        </div>
    </div>

    <div class="bg-gray-800 rounded-xl border border-gray-700">
        <div class="border-b border-gray-700">
            <nav class="flex -mb-px">
                <button onclick="switchTab('messages')" id="tab-messages" class="px-6 py-3 text-whatsapp border-b-2 border-whatsapp font-medium">
                    Messages
                </button>
                <button onclick="switchTab('contacts')" id="tab-contacts" class="px-6 py-3 text-gray-400 hover:text-white border-b-2 border-transparent font-medium">
                    Contacts
                </button>
                <button onclick="switchTab('webhooks')" id="tab-webhooks" class="px-6 py-3 text-gray-400 hover:text-white border-b-2 border-transparent font-medium">
                    Webhooks
                </button>
                <button onclick="switchTab('settings')" id="tab-settings" class="px-6 py-3 text-gray-400 hover:text-white border-b-2 border-transparent font-medium">
                    Settings
                </button>
            </nav>
        </div>
        
        <div id="tab-content-messages" class="tab-content">
            <div class="p-4 border-b border-gray-700 bg-gray-900/50">
                <div class="flex gap-4">
                    <input type="text" id="send-to" placeholder="Recipient phone or JID" 
                           class="flex-1 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white">
                    <input type="text" id="send-text" placeholder="Message..." 
                           class="flex-2 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white"
                           onkeypress="if(event.key==='Enter')sendMessage()">
                    <button onclick="sendMessage()" class="px-6 py-2 bg-whatsapp hover:bg-whatsappDark text-white rounded-lg font-medium">
                        Send
                    </button>
                </div>
            </div>
            <div id="tenant-messages" hx-get="/admin/fragments/tenant-messages/{tenant_hash}" hx-trigger="load" class="max-h-[600px] overflow-y-auto">
                <div class="p-6 text-center text-gray-500">Loading messages...</div>
            </div>
        </div>
        
        <div id="tab-content-contacts" class="tab-content hidden">
            <div id="tenant-contacts" hx-get="/admin/fragments/tenant-contacts/{tenant_hash}" hx-trigger="load" class="divide-y divide-gray-700">
                <div class="p-6 text-center text-gray-500">Loading contacts...</div>
            </div>
        </div>
        
        <div id="tab-content-webhooks" class="tab-content hidden">
            <div class="p-6">
                <div class="mb-6">
                    <h3 class="text-lg font-semibold mb-3">Configured Webhooks</h3>
                    <div id="tenant-webhooks" class="space-y-2">
                        {webhooks_html}
                    </div>
                </div>
                
                <div class="border-t border-gray-700 pt-6">
                    <h3 class="text-lg font-semibold mb-3">Add Webhook</h3>
                    <div class="flex gap-2">
                        <input type="url" id="new-webhook-url" placeholder="https://example.com/webhook" 
                               class="flex-1 px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white">
                        <button onclick="addWebhook()" class="px-6 py-2 bg-whatsapp hover:bg-whatsappDark text-white rounded-lg">
                            Add
                        </button>
                    </div>
                </div>
                
                <div class="border-t border-gray-700 pt-6 mt-6">
                    <h3 class="text-lg font-semibold mb-3">Recent Delivery Attempts</h3>
                    <div id="webhook-history" hx-get="/admin/fragments/webhook-history?tenant_hash={tenant_hash}&limit=20" hx-trigger="load" class="divide-y divide-gray-700">
                        <div class="p-4 text-center text-gray-500">Loading...</div>
                    </div>
                </div>
            </div>
        </div>
        
        <div id="tab-content-settings" class="tab-content hidden">
            <div class="p-6 space-y-6">
                <div>
                    <h3 class="text-lg font-semibold mb-3">Tenant Information</h3>
                    <div class="space-y-3">
                        <div class="flex items-center justify-between p-3 bg-gray-700/50 rounded-lg">
                            <span class="text-gray-400">Name</span>
                            <span class="font-medium">{tenant_name}</span>
                        </div>
                        <div class="flex items-center justify-between p-3 bg-gray-700/50 rounded-lg">
                            <span class="text-gray-400">API Key Hash</span>
                            <span class="font-mono text-sm">{tenant_hash[:32]}...</span>
                        </div>
                        <div class="flex items-center justify-between p-3 bg-gray-700/50 rounded-lg">
                            <span class="text-gray-400">Has Authentication</span>
                            <span class="font-medium">{"Yes" if tenant.has_auth else "No"}</span>
                        </div>
                    </div>
                </div>
                
                <div class="border-t border-gray-700 pt-6">
                    <h3 class="text-lg font-semibold mb-3">Actions</h3>
                    <div class="space-y-3">
                        <button onclick="reconnectTenant()" class="w-full px-4 py-3 bg-blue-600 hover:bg-blue-700 text-white rounded-lg transition">
                            Reconnect Session
                        </button>
                        <button onclick="clearCredentials()" class="w-full px-4 py-3 bg-yellow-600 hover:bg-yellow-700 text-white rounded-lg transition">
                            Clear Stored Credentials
                        </button>
                    </div>
                </div>
                
                <div class="border-t border-red-700 pt-6">
                    <h3 class="text-lg font-semibold mb-3 text-red-400">Danger Zone</h3>
                    <button onclick="deleteTenant()" class="w-full px-4 py-3 bg-red-600 hover:bg-red-700 text-white rounded-lg transition">
                        Delete Tenant
                    </button>
                    <p class="text-sm text-gray-500 mt-2">This action cannot be undone.</p>
                </div>
            </div>
        </div>
    </div>
</div>
"""

    script = (
        """
function switchTab(tabName) {
    document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
    document.querySelectorAll('nav button').forEach(el => {
        el.classList.remove('text-whatsapp', 'border-whatsapp');
        el.classList.add('text-gray-400', 'border-transparent');
    });
    document.getElementById('tab-content-' + tabName).classList.remove('hidden');
    const activeTab = document.getElementById('tab-' + tabName);
    activeTab.classList.remove('text-gray-400', 'border-transparent');
    activeTab.classList.add('text-whatsapp', 'border-whatsapp');
}

async function sendMessage() {
    const to = document.getElementById('send-to').value;
    const text = document.getElementById('send-text').value;
    if (!to || !text) {
        alert('Please enter recipient and message');
        return;
    }
    const response = await fetch('/admin/api/tenants/"""
        + tenant_hash
        + """/send', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({to: to, text: text})
    });
    const data = await response.json();
    if (response.ok) {
        document.getElementById('send-text').value = '';
        htmx.trigger('#tenant-messages', 'load');
    } else {
        alert('Failed: ' + (data.detail || JSON.stringify(data)));
    }
}

async function addWebhook() {
    const url = document.getElementById('new-webhook-url').value;
    if (!url) return;
    const response = await fetch('/admin/api/tenants/"""
        + tenant_hash
        + """/webhooks', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({url: url})
    });
    if (response.ok) {
        location.reload();
    } else {
        const data = await response.json();
        alert('Failed: ' + (data.detail || JSON.stringify(data)));
    }
}

async function removeWebhook(url) {
    if (!confirm('Remove this webhook?')) return;
    const response = await fetch('/admin/api/tenants/"""
        + tenant_hash
        + """/webhooks?url=' + encodeURIComponent(url), {
        method: 'DELETE'
    });
    if (response.ok) {
        location.reload();
    }
}

async function reconnectTenant() {
    if (!confirm('Reconnect this tenant session?')) return;
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = 'Connecting...';
    
    const response = await fetch('/admin/api/tenants/"""
        + tenant_hash
        + """/reconnect', {
        method: 'POST'
    });
    
    if (response.ok) {
        showNotification('Initiating connection... Watch for QR code.', 'info');
    } else {
        const data = await response.json();
        showNotification('Failed: ' + (data.detail || JSON.stringify(data)), 'error');
        btn.disabled = false;
        btn.textContent = 'Reconnect Session';
    }
}

function showNotification(message, type = 'info') {
    const colors = {
        'info': 'bg-blue-600',
        'success': 'bg-green-600',
        'warning': 'bg-yellow-600',
        'error': 'bg-red-600'
    };
    const notification = document.createElement('div');
    notification.className = `fixed top-4 right-4 px-6 py-3 rounded-lg shadow-lg z-50 transition-all transform translate-x-full \\${colors[type] || colors.info}`;
    notification.innerHTML = `
        <div class="flex items-center space-x-2">
            <span class="text-white font-medium">\\${message}</span>
            <button onclick="this.parentElement.parentElement.remove()" class="text-white hover:text-gray-200">
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12"></path>
                </svg>
            </button>
        </div>
    `;
    document.body.appendChild(notification);
    setTimeout(() => notification.classList.remove('translate-x-full'), 10);
    setTimeout(() => {
        notification.classList.add('translate-x-full');
        setTimeout(() => notification.remove(), 300);
    }, 5000);
}

async function clearCredentials() {
    if (!confirm('Clear stored credentials?')) return;
    const response = await fetch('/admin/api/tenants/"""
        + tenant_hash
        + """/credentials', {
        method: 'DELETE'
    });
    if (response.ok) {
        alert('Credentials cleared');
        location.reload();
    } else {
        const data = await response.json();
        alert('Failed: ' + (data.detail || JSON.stringify(data)));
    }
}

async function deleteTenant() {
    const confirmed = confirm('Delete this tenant? CANNOT BE UNDONE!');
    if (!confirmed) return;
    const typed = prompt('Type "DELETE """
        + tenant_name
        + """" to confirm:');
    if (typed !== 'DELETE """
        + tenant_name
        + """') {
        alert('Confirmation text did not match');
        return;
    }
    const response = await fetch('/admin/api/tenants/"""
        + tenant_hash
        + """', {
        method: 'DELETE'
    });
    if (response.ok) {
        alert('Tenant deleted');
        window.location.href = '/admin/tenants';
    } else {
        const data = await response.json();
        alert('Failed: ' + (data.detail || JSON.stringify(data)));
    }
}
"""
    )

    html = PAGE_TEMPLATE.format(
        title=f"{tenant_name} - Tenant Details",
        sidebar=get_sidebar("tenants"),
        content=content,
        modals="",
        script=script,
    )
    return HTMLResponse(content=html)


# HTML Fragment Routes


@fragments_router.get("/stats", response_class=HTMLResponse)
async def get_stats_fragment(session_id: str = Depends(require_admin_session)):
    db = tenant_manager._db
    tenants = tenant_manager.list_tenants()

    connected = sum(1 for t in tenants if t.connection_state == "connected")
    pending = sum(1 for t in tenants if t.connection_state == "pending_qr")
    disconnected = sum(1 for t in tenants if t.connection_state == "disconnected")

    total_messages = 0
    total_webhook_attempts = 0
    webhook_success = 0

    if db:
        for tenant in tenants:
            _, msg_count = await db.list_messages(
                tenant_hash=tenant.api_key_hash, limit=1
            )
            total_messages += msg_count

        stats = await db.get_webhook_stats()
        total_webhook_attempts = stats.get("total", 0)
        webhook_success = stats.get("success_count", 0)

    success_rate = (
        round(webhook_success / total_webhook_attempts * 100, 1)
        if total_webhook_attempts > 0
        else 0
    )

    # Database status
    db_type = (
        "PostgreSQL"
        if getattr(db, "_is_postgres", False)
        else "SQLite"
        if db
        else "None"
    )
    db_connected = getattr(db, "_pool", None) is not None
    db_status_color = "green" if db_connected else "red"
    db_status_text = "Connected" if db_connected else "Disconnected"

    # Get pool info for PostgreSQL
    pool_info = ""
    if db and getattr(db, "_is_postgres", False) and getattr(db, "_pool", None):
        try:
            pool = db._pool
            pool_info = f"Pool: {pool._queue.qsize()}/{pool._maxsize}"
        except Exception:
            pool_info = ""

    html = f"""
<div class="bg-gray-800 rounded-xl p-6 border border-gray-700">
    <div class="flex items-center justify-between">
        <div>
            <p class="text-gray-400 text-sm">Total Tenants</p>
            <p class="text-3xl font-bold mt-1">{len(tenants)}</p>
            <p class="text-xs text-gray-500 mt-1">{connected} connected, {pending} pending QR</p>
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
            <p class="text-3xl font-bold mt-1 text-green-500">{connected}</p>
            <p class="text-xs text-gray-500 mt-1">{disconnected} disconnected</p>
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
            <p class="text-3xl font-bold mt-1">{total_messages:,}</p>
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
            <p class="text-3xl font-bold mt-1 text-whatsapp">{success_rate}%</p>
            <p class="text-xs text-gray-500 mt-1">{total_webhook_attempts} total attempts</p>
        </div>
        <div class="w-12 h-12 bg-whatsapp/20 rounded-lg flex items-center justify-center">
            <svg class="w-6 h-6 text-whatsapp" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1"></path></svg>
        </div>
    </div>
</div>
<div class="bg-gray-800 rounded-xl p-6 border border-gray-700">
    <div class="flex items-center justify-between">
        <div>
            <p class="text-gray-400 text-sm">Database</p>
            <p class="text-3xl font-bold mt-1 text-{db_status_color}-500">{db_type}</p>
            <p class="text-xs text-gray-500 mt-1">{db_status_text}{f" · {pool_info}" if pool_info else ""}</p>
        </div>
        <div class="w-12 h-12 bg-{db_status_color}-500/20 rounded-lg flex items-center justify-center">
            <svg class="w-6 h-6 text-{db_status_color}-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 7v10c0 2.21 3.582 4 8 4s8-1.79 8-4V7M4 7c0 2.21 3.582 4 8 4s8-1.79 8-4M4 7c0-2.21 3.582-4 8-4s8 1.79 8 4m0 5c0 2.21-3.582 4-8 4s-8-1.79-8-4"></path></svg>
        </div>
    </div>
</div>
"""
    return HTMLResponse(content=html)


@fragments_router.get("/websockets", response_class=HTMLResponse)
async def get_websockets_fragment(session_id: str = Depends(require_admin_session)):
    connections = admin_ws_manager.get_connections_info()
    count = admin_ws_manager.get_connection_count()

    if count == 0:
        html = '<div class="text-gray-500 text-sm">No active connections</div>'
    else:
        rows = []
        for conn in connections:
            connected_at = conn.get("connected_at")
            if connected_at:
                try:
                    dt = datetime.fromisoformat(connected_at)
                    time_str = dt.strftime("%H:%M:%S")
                except Exception:
                    time_str = "unknown"
            else:
                time_str = "unknown"
            rows.append(f"""
                <div class="flex items-center justify-between py-2 border-b border-gray-700 last:border-0">
                    <div class="flex items-center gap-2">
                        <div class="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
                        <span class="text-sm font-mono">{conn["session_id"]}</span>
                    </div>
                    <span class="text-xs text-gray-500">Since {time_str}</span>
                </div>
            """)
        html = f'<div class="divide-y divide-gray-700">{"".join(rows)}</div>'

    return HTMLResponse(content=html)


@fragments_router.get("/tenants", response_class=HTMLResponse)
async def get_tenants_fragment(session_id: str = Depends(require_admin_session)):
    tenants = tenant_manager.list_tenants()

    if not tenants:
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">No tenants yet. Click "Add Tenant" to create one.</div>'
        )

    html_parts = []
    for t in tenants:
        state_badge = ""
        if t.connection_state == "connected":
            state_badge = '<span class="px-2 py-1 text-xs bg-green-500/20 text-green-400 rounded">Connected</span>'
        elif t.connection_state == "pending_qr":
            state_badge = '<span class="px-2 py-1 text-xs bg-yellow-500/20 text-yellow-400 rounded">Pending QR</span>'
        else:
            state_badge = '<span class="px-2 py-1 text-xs bg-gray-500/20 text-gray-400 rounded">Disconnected</span>'

        enabled_badge = ""
        if not t.enabled:
            enabled_badge = '<span class="px-2 py-1 text-xs bg-red-500/20 text-red-400 rounded">Disabled</span>'

        phone_info = (
            f"<span class='text-gray-400'>{t.self_phone}</span>"
            if t.self_phone
            else "<span class='text-gray-500'>No phone</span>"
        )
        webhook_count = len(t.webhook_urls)

        enable_disable_btn = f"""
            <button onclick="toggleEnabled('{t.api_key_hash}', {str(not t.enabled).lower()})"
                    class="px-3 py-1 text-sm {"text-red-400 hover:bg-red-500/20" if t.enabled else "text-green-400 hover:bg-green-500/20"} rounded transition">
                {"Disable" if t.enabled else "Enable"}
            </button>
        """

        html_parts.append(f"""
<div class="tenant-row" data-tenant-hash="{t.api_key_hash}">
    <div class="p-4 hover:bg-gray-700/50 transition">
        <div class="flex items-center justify-between">
            <div class="flex items-center gap-3 flex-1">
                <input type="checkbox" class="tenant-checkbox" data-hash="{t.api_key_hash}" onchange="updateBulkSelection()" onclick="event.stopPropagation()" ondblclick="event.stopPropagation()">
                <div onclick="toggleTenantPanel('{t.api_key_hash}')" class="cursor-pointer flex items-center gap-3 flex-1">
                    <svg id="chevron-{t.api_key_hash}" class="w-5 h-5 text-gray-400 transition-transform" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"></path></svg>
                <div class="flex-1">
                    <div class="flex items-center gap-3">
                        <h3 class="font-medium text-lg">{t.name}</h3>
                        {state_badge}
                        {enabled_badge}
                        {"<span class='px-2 py-1 text-xs bg-blue-500/20 text-blue-400 rounded'>Has Auth</span>" if t.has_auth else ""}
                    </div>
                    <div class="text-sm text-gray-400 mt-1">
                        {phone_info} | {webhook_count} webhook{"s" if webhook_count != 1 else ""} | Created {t.created_at.strftime("%Y-%m-%d")}
                    </div>
                </div>
                </div>
            </div>
            <div class="flex items-center gap-2" onclick="event.stopPropagation()">
                {enable_disable_btn}
                <a href="/admin/tenants/{t.api_key_hash}" class="px-3 py-1 text-sm text-whatsapp hover:bg-whatsapp/10 rounded transition">
                    View
                </a>
                <button onclick="showTenantActions('{t.api_key_hash}', '{t.name}')" class="px-3 py-1 text-sm text-gray-400 hover:text-white hover:bg-gray-600 rounded transition">
                    Actions
                </button>
            </div>
        </div>
    </div>
    <div id="tenant-panel-{t.api_key_hash}" class="hidden"></div>
</div>
""")

    return HTMLResponse(content="".join(html_parts))


@fragments_router.get("/messages", response_class=HTMLResponse)
async def get_messages_fragment(
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
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">Database not available</div>'
        )

    messages, total = await db.list_messages(
        tenant_hash=tenant_hash,
        chat_jid=chat_jid,
        direction=direction,
        search=search,
        limit=limit,
        offset=offset,
    )

    tenants = {t.api_key_hash: t.name for t in tenant_manager.list_tenants()}

    if not messages:
        if search or tenant_hash or direction:
            return HTMLResponse(
                content='<div class="p-6 text-center text-gray-500">No messages match your search criteria</div>'
            )
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">No messages found</div>'
        )

    # Add count header
    count_header = ""
    if total > len(messages):
        count_header = f'<div class="px-6 py-3 bg-gray-700/50 text-sm text-gray-400 border-b border-gray-700">Showing {len(messages)} of {total} messages</div>'
    elif messages:
        count_header = f'<div class="px-6 py-3 bg-gray-700/50 text-sm text-gray-400 border-b border-gray-700">{total} message{"s" if total != 1 else ""}</div>'

    html_parts = [count_header]
    for msg in messages:
        tenant_name = tenants.get(msg.get("tenant_hash") or "", "Unknown")
        direction_badge = (
            '<span class="px-2 py-1 text-xs bg-blue-500/20 text-blue-400 rounded">In</span>'
            if msg.get("direction") == "inbound"
            else '<span class="px-2 py-1 text-xs bg-purple-500/20 text-purple-400 rounded">Out</span>'
        )
        msg_type = msg.get("msg_type") or "text"
        raw_text = msg.get("text") or ""
        text = raw_text[:100] + "..." if len(raw_text) > 100 else raw_text

        # Highlight search terms
        if search:
            import re

            pattern = re.compile(re.escape(search), re.IGNORECASE)
            text = pattern.sub(
                lambda m: (
                    f'<mark class="bg-yellow-500/30 text-yellow-200">{m.group(0)}</mark>'
                ),
                text,
            )
        ts = msg.get("timestamp")
        if ts:
            if ts > 1e12:
                ts = ts / 1000
            timestamp = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
        else:
            timestamp = "-"
        is_group = msg.get("is_group") or False

        html_parts.append(f"""
<div class="p-4 hover:bg-gray-700/50 transition">
    <div class="flex items-start justify-between gap-4">
        <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium">{tenant_name}</span>
                {direction_badge}
                {"<span class='px-2 py-1 text-xs bg-orange-500/20 text-orange-400 rounded'>Group</span>" if is_group else ""}
                <span class="text-xs text-gray-500">{msg_type}</span>
            </div>
            <div class="text-sm text-gray-400 mt-1">
                From: <span class="text-gray-300">{msg.get("from_jid", "-")[:30]}</span>
                {"| Chat: <span class='text-gray-300'>" + msg.get("chat_jid", "-")[:30] + "</span>" if msg.get("chat_jid") else ""}
            </div>
            {"<div class='mt-2 text-sm text-gray-300 truncate'>" + (text or "<i class='text-gray-500'>No text content</i>") + "</div>" if text else ""}
        </div>
        <div class="text-xs text-gray-500 whitespace-nowrap">{timestamp}</div>
    </div>
</div>
""")

    return HTMLResponse(content="".join(html_parts))


@fragments_router.get("/webhooks", response_class=HTMLResponse)
async def get_webhooks_fragment(session_id: str = Depends(require_admin_session)):
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

    if not webhooks:
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">No webhooks registered. Add webhooks to tenants to receive event notifications.</div>'
        )

    html_parts = []
    for wh in webhooks:
        html_parts.append(f"""
<div class="p-4 hover:bg-gray-700/50 transition">
    <div class="flex items-center justify-between">
        <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2">
                <span class="font-medium">{wh["tenant_name"]}</span>
            </div>
            <div class="text-sm text-whatsapp truncate mt-1">{wh["url"]}</div>
        </div>
        <div class="flex items-center gap-2">
            <button hx-delete="/admin/api/tenants/{wh["tenant_hash"]}/webhooks?url={wh["url"]}" 
                    hx-on="htmx:afterRequest: htmx.trigger('#webhooks-list', 'load')"
                    hx-confirm="Remove this webhook?"
                    class="px-3 py-1 text-sm text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded transition">
                Remove
            </button>
        </div>
    </div>
</div>
""")

    return HTMLResponse(content="".join(html_parts))


@fragments_router.get("/webhook-history", response_class=HTMLResponse)
async def get_webhook_history_fragment(
    tenant_hash: Optional[str] = Query(None),
    url: Optional[str] = Query(None),
    success: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    session_id: str = Depends(require_admin_session),
):
    db = tenant_manager._db
    if not db:
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">Database not available</div>'
        )

    attempts, total = await db.list_webhook_attempts(
        tenant_hash=tenant_hash,
        url=url,
        success=success,
        limit=limit,
        offset=offset,
    )

    tenants = {t.api_key_hash: t.name for t in tenant_manager.list_tenants()}

    if not attempts:
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">No webhook attempts recorded yet.</div>'
        )

    html_parts = []
    for a in attempts:
        tenant_name = tenants.get(a.get("tenant_hash") or "", "Unknown")
        success_badge = (
            '<span class="px-2 py-1 text-xs bg-green-500/20 text-green-400 rounded">Success</span>'
            if a.get("success")
            else '<span class="px-2 py-1 text-xs bg-red-500/20 text-red-400 rounded">Failed</span>'
        )
        created_at = a.get("created_at")
        if created_at:
            if isinstance(created_at, datetime):
                timestamp = created_at.strftime("%Y-%m-%d %H:%M:%S")
            elif isinstance(created_at, str):
                timestamp = datetime.fromisoformat(created_at).strftime(
                    "%Y-%m-%d %H:%M:%S"
                )
            else:
                timestamp = str(created_at)
        else:
            timestamp = "-"
        latency = f"{a.get('latency_ms')}ms" if a.get("latency_ms") else "-"
        status_code = a.get("status_code", "-")

        html_parts.append(f"""
<div class="p-4 hover:bg-gray-700/50 transition">
    <div class="flex items-start justify-between gap-4">
        <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 flex-wrap">
                <span class="font-medium">{tenant_name}</span>
                {success_badge}
                <span class="text-xs text-gray-500">HTTP {status_code}</span>
                <span class="text-xs text-gray-500">{latency}</span>
            </div>
            <div class="text-sm text-gray-400 truncate mt-1">{a.get("url", "-")}</div>
            <div class="text-xs text-gray-500 mt-1">Event: {a.get("event_type", "-")}</div>
            {"<div class='text-xs text-red-400 mt-1'>" + a.get("error_message", "") + "</div>" if a.get("error_message") else ""}
        </div>
        <div class="text-xs text-gray-500 whitespace-nowrap">{timestamp}</div>
    </div>
</div>
""")

    return HTMLResponse(content="".join(html_parts))


@fragments_router.get("/blocked-ips", response_class=HTMLResponse)
async def get_blocked_ips_fragment(session_id: str = Depends(require_admin_session)):
    blocked_ips = rate_limiter.get_blocked_ips()

    if not blocked_ips:
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">No blocked IPs</div>'
        )

    html_parts = []
    for ip_data in blocked_ips:
        html_parts.append(f"""
<div class="p-4 hover:bg-gray-700/50 transition">
    <div class="flex items-center justify-between">
        <div>
            <span class="font-mono text-lg">{ip_data.get("ip", "-")}</span>
            <div class="text-sm text-gray-400 mt-1">Reason: {ip_data.get("reason", "-")}</div>
        </div>
        <button hx-delete="/admin/api/rate-limit/block?ip={ip_data.get("ip")}" 
                hx-on="htmx:afterRequest: htmx.trigger('#blocked-ips', 'load')"
                class="px-3 py-1 text-sm text-gray-400 hover:text-white hover:bg-gray-600 rounded transition">
            Unblock
        </button>
    </div>
</div>
""")

    return HTMLResponse(content="".join(html_parts))


@fragments_router.get("/chatwoot/config", response_class=HTMLResponse)
async def get_chatwoot_config_fragment(
    session_id: str = Depends(require_admin_session),
):
    saved_config = None
    if tenant_manager._db:
        saved_config = await tenant_manager._db.get_global_config("chatwoot")

    url_value = saved_config.get("url", "") if saved_config else ""
    token_value = saved_config.get("token", "") if saved_config else ""
    account_id_value = saved_config.get("account_id", "") if saved_config else ""

    return HTMLResponse(
        content=f"""
<div class="space-y-4">
    <div class="grid grid-cols-2 gap-4">
        <div>
            <label class="block text-sm font-medium text-gray-300 mb-2">Chatwoot URL</label>
            <input type="url" id="chatwoot-url" placeholder="https://chatwoot.example.com" 
                   value="{url_value}"
                   class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-whatsapp">
        </div>
        <div>
            <label class="block text-sm font-medium text-gray-300 mb-2">Account ID</label>
            <input type="text" id="chatwoot-account-id" placeholder="1" 
                   value="{account_id_value}"
                   class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-whatsapp">
        </div>
    </div>
    <div>
        <label class="block text-sm font-medium text-gray-300 mb-2">API Token</label>
        <input type="password" id="chatwoot-token" placeholder="Your Chatwoot API token" 
               value="{token_value}"
               class="w-full px-4 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white focus:outline-none focus:ring-2 focus:ring-whatsapp">
    </div>
    <div class="flex items-center gap-4 pt-2">
        <button onclick="saveChatwootConfig()" class="px-4 py-2 bg-whatsapp hover:bg-whatsappDark text-white rounded-lg transition">
            Save Configuration
        </button>
        <span id="chatwoot-config-status" class="text-sm text-gray-400"></span>
    </div>
</div>
<script>
async function saveChatwootConfig() {{
    const url = document.getElementById('chatwoot-url').value;
    const token = document.getElementById('chatwoot-token').value;
    const accountId = document.getElementById('chatwoot-account-id').value;
    const status = document.getElementById('chatwoot-config-status');
    
    if (!url || !token || !accountId) {{
        status.textContent = 'Please fill all fields';
        status.className = 'text-sm text-red-400';
        return;
    }}
    
    status.textContent = 'Saving...';
    status.className = 'text-sm text-gray-400';
    
    try {{
        const response = await fetch('/admin/api/chatwoot/config', {{
            method: 'POST',
            headers: {{'Content-Type': 'application/json'}},
            body: JSON.stringify({{
                url: url,
                token: token,
                account_id: accountId,
                enabled: true
            }})
        }});
        
        const data = await response.json();
        
        if (response.ok) {{
            status.textContent = 'Configuration saved!';
            status.className = 'text-sm text-green-400';
            htmx.trigger('#chatwoot-tenants', 'load');
        }} else {{
            status.textContent = data.detail || 'Failed to save';
            status.className = 'text-sm text-red-400';
        }}
    }} catch (e) {{
        status.textContent = 'Error: ' + e.message;
        status.className = 'text-sm text-red-400';
    }}
}}
</script>
"""
    )


@fragments_router.get("/chatwoot/tenants", response_class=HTMLResponse)
async def get_chatwoot_tenants_fragment(
    session_id: str = Depends(require_admin_session),
):
    tenants = tenant_manager.list_tenants()

    if not tenants:
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">No tenants configured</div>'
        )

    html_parts = []
    for tenant in tenants:
        config = getattr(tenant, "chatwoot_config", None) or {}
        enabled = config.get("enabled", False)
        status_badge = (
            '<span class="px-2 py-1 text-xs bg-green-500/20 text-green-400 rounded">Enabled</span>'
            if enabled
            else '<span class="px-2 py-1 text-xs bg-gray-500/20 text-gray-400 rounded">Disabled</span>'
        )

        html_parts.append(f"""
<div class="p-4 hover:bg-gray-700/50 transition">
    <div class="flex items-center justify-between">
        <div class="flex items-center gap-3">
            <div class="w-10 h-10 bg-gray-600 rounded-full flex items-center justify-center">
                <span class="text-lg font-semibold">{tenant.name[0].upper()}</span>
            </div>
            <div>
                <div class="flex items-center gap-2">
                    <span class="font-medium">{tenant.name}</span>
                    {status_badge}
                </div>
                <div class="text-sm text-gray-400">
                    {config.get("url", "Not configured") if config.get("url") else "Not configured"}
                </div>
            </div>
        </div>
        <div class="flex items-center gap-2">
            <button onclick="toggleChatwootForTenant('{tenant.api_key_hash[:16]}', {str(enabled).lower()})"
                    class="px-3 py-1 text-sm {"text-yellow-400 hover:bg-yellow-500/20" if enabled else "text-green-400 hover:bg-green-500/20"} rounded transition">
                {"Disable" if enabled else "Enable"}
            </button>
            <button onclick="showChatwootTenantConfig('{tenant.api_key_hash[:16]}')"
                    class="px-3 py-1 text-sm text-gray-400 hover:text-white hover:bg-gray-600 rounded transition">
                Configure
            </button>
            {"<button onclick=\"syncChatwootContacts('" + tenant.api_key_hash[:16] + '\')" class="px-3 py-1 text-sm text-blue-400 hover:bg-blue-500/20 rounded transition">Sync Contacts</button>' + ("<button onclick=\"syncChatwootMessages('" + tenant.api_key_hash[:16] + '\')" class="px-3 py-1 text-sm text-green-400 hover:bg-green-500/20 rounded transition">Sync Messages</button>' if config.get("import_messages") else "") if enabled else ""}
        </div>
    </div>
</div>
""")

    return HTMLResponse(content="".join(html_parts))


@fragments_router.get("/failed-auth", response_class=HTMLResponse)
async def get_failed_auth_fragment(session_id: str = Depends(require_admin_session)):
    result = rate_limiter.get_failed_auth_attempts()
    failed = result.get("ips_with_failures", {})

    if not failed:
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">No failed auth attempts recorded</div>'
        )

    html_parts = []
    for ip, count in failed.items():
        bar_width = min(count / 5 * 100, 100)
        bar_color = (
            "bg-red-500"
            if count >= 5
            else "bg-yellow-500"
            if count >= 3
            else "bg-gray-500"
        )
        html_parts.append(f"""
<div class="p-4 hover:bg-gray-700/50 transition">
    <div class="flex items-center justify-between">
        <div class="flex-1">
            <div class="flex items-center gap-3">
                <span class="font-mono">{ip}</span>
                <span class="text-sm text-gray-400">{count} attempt{"s" if count != 1 else ""}</span>
                {"<span class='px-2 py-1 text-xs bg-red-500/20 text-red-400 rounded'>BLOCKED</span>" if count >= 5 else ""}
            </div>
            <div class="mt-2 h-2 bg-gray-700 rounded-full overflow-hidden">
                <div class="h-full {bar_color} rounded-full transition-all" style="width: {bar_width}%"></div>
            </div>
        </div>
        <button hx-delete="/admin/api/rate-limit/failed-auth?ip={ip}" 
                hx-on="htmx:afterRequest: htmx.trigger('#failed-auth', 'load')"
                class="ml-4 px-3 py-1 text-sm text-gray-400 hover:text-white hover:bg-gray-600 rounded transition">
            Clear
        </button>
    </div>
</div>
""")

    return HTMLResponse(content="".join(html_parts))


@fragments_router.get("/tenant-panel/{tenant_hash}", response_class=HTMLResponse)
async def get_tenant_panel_fragment(
    tenant_hash: str,
    session_id: str = Depends(require_admin_session),
):
    tenant = tenant_manager._tenants.get(tenant_hash)
    if not tenant:
        return HTMLResponse(
            content='<div class="p-4 text-red-400">Tenant not found</div>'
        )

    db = tenant_manager._db
    messages = []
    recent_chats = []

    if db:
        messages, _ = await db.list_messages(tenant_hash=tenant_hash, limit=50)
        recent_chats = await db.get_recent_chats(tenant_hash, limit=20)

    messages_html = ""
    if messages:
        for msg in reversed(messages):
            is_inbound = msg.get("direction") != "outbound"
            text = msg.get("text") or ""
            ts = msg.get("timestamp")
            if ts:
                if ts > 1e12:
                    ts = ts / 1000
                timestamp = datetime.fromtimestamp(ts).strftime("%H:%M")
            else:
                timestamp = ""

            push_name = msg.get("push_name") or ""
            if not push_name:
                from_jid = msg.get("from_jid") or ""
                phone = from_jid.split("@")[0] if "@" in from_jid else from_jid
                push_name = phone if phone else "Unknown"

            if is_inbound:
                messages_html += f"""
<div class="flex gap-2 mb-3">
    <div class="max-w-[80%] bg-gray-700 rounded-2xl rounded-tl-sm px-4 py-2">
        <div class='text-xs text-whatsapp mb-1'>{push_name}</div>
        <div class="text-sm text-gray-100">{text}</div>
        <div class="text-xs text-gray-400 mt-1 text-right">{timestamp}</div>
    </div>
</div>"""
            else:
                chat_jid = msg.get("chat_jid") or ""
                recipient_phone = (
                    chat_jid.split("@")[0] if "@" in chat_jid else chat_jid
                )
                recipient_name = push_name if push_name else recipient_phone
                recipient_display = (
                    f"{recipient_name} ({recipient_phone})"
                    if push_name
                    else recipient_phone
                )

                messages_html += f"""
<div class="flex gap-2 mb-3 justify-end">
    <div class="max-w-[80%] bg-whatsapp/20 rounded-2xl rounded-tr-sm px-4 py-2">
        <div class='text-xs text-whatsapp/70 mb-1'>To: {recipient_display}</div>
        <div class="text-sm text-gray-100">{text}</div>
        <div class="text-xs text-gray-400 mt-1 text-right">{timestamp}</div>
    </div>
</div>"""

    chats_options = ""
    for chat in recent_chats:
        push_name = chat.get("push_name") or ""
        chat_jid = chat.get("chat_jid", "")
        phone = chat.get("phone") or (
            chat_jid.split("@")[0] if "@" in chat_jid else chat_jid
        )
        is_group = chat.get("is_group")

        if push_name:
            label = f"{push_name} ({phone})"
        else:
            label = phone
        if is_group:
            label += " [Group]"

        chats_options += f'<option value="{chat_jid}">{label}</option>'

    html = f"""
<div class="border-t border-gray-700 bg-gray-900/50">
    <div class="p-4">
        <div class="flex items-center justify-between mb-3">
            <h4 class="font-medium text-whatsapp">Messages</h4>
            <span class="text-xs text-gray-400">{len(messages)} messages</span>
        </div>
        <div class="max-h-64 overflow-y-auto mb-4 bg-gray-800/50 rounded-lg p-3">
            {messages_html}
        </div>
        <div class="space-y-3">
            <div>
                <label class="block text-xs text-gray-400 mb-1">To:</label>
                <div class="flex gap-2">
                    <select id="chat-select-{tenant_hash}" class="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-whatsapp">
                        <option value="">Select chat...</option>
                        {chats_options}
                    </select>
                    <input type="text" id="manual-jid-{tenant_hash}" placeholder="or enter phone" class="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-whatsapp">
                </div>
            </div>
            <div>
                <label class="block text-xs text-gray-400 mb-1">Message:</label>
                <div class="flex gap-2">
                    <input type="text" id="msg-text-{tenant_hash}" placeholder="Type your message..." class="flex-1 px-3 py-2 bg-gray-700 border border-gray-600 rounded-lg text-white text-sm focus:outline-none focus:ring-2 focus:ring-whatsapp" onkeypress="if(event.key==='Enter')sendMsgAsTenant('{tenant_hash}')">
                    <button onclick="sendMsgAsTenant('{tenant_hash}')" class="px-4 py-2 bg-whatsapp hover:bg-whatsappDark text-white rounded-lg text-sm font-medium">Send</button>
                </div>
            </div>
        </div>
    </div>
</div>
"""
    return HTMLResponse(content=html)


@fragments_router.get("/tenant-messages/{tenant_hash}", response_class=HTMLResponse)
async def get_tenant_messages_fragment(
    tenant_hash: str,
    limit: int = Query(100, ge=1, le=500),
    session_id: str = Depends(require_admin_session),
):
    tenant = tenant_manager._tenants.get(tenant_hash)
    if not tenant:
        return HTMLResponse(
            content='<div class="p-6 text-center text-red-400">Tenant not found</div>'
        )

    db = tenant_manager._db
    if not db:
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">Database not available</div>'
        )

    messages, total = await db.list_messages(tenant_hash=tenant_hash, limit=limit)

    if not messages:
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">No messages yet</div>'
        )

    html_parts = []
    for msg in reversed(messages):  # Show oldest to newest
        is_inbound = msg.get("direction") != "outbound"
        text = msg.get("text") or "<i class='text-gray-500'>No text</i>"
        ts = msg.get("timestamp")

        if ts:
            if ts > 1e12:
                ts = ts / 1000
            timestamp = datetime.fromtimestamp(ts).strftime("%H:%M")
        else:
            timestamp = ""

        push_name = msg.get("push_name") or ""
        if not push_name:
            from_jid = msg.get("from_jid") or ""
            phone = from_jid.split("@")[0] if "@" in from_jid else from_jid
            push_name = phone if phone else "Unknown"

        if is_inbound:
            html_parts.append(f"""
<div class="flex gap-2 mb-3 px-4">
    <div class="max-w-[80%] bg-gray-700 rounded-2xl rounded-tl-sm px-4 py-2">
        <div class='text-xs text-whatsapp mb-1'>{push_name}</div>
        <div class="text-sm text-gray-100">{text}</div>
        <div class="text-xs text-gray-400 mt-1 text-right">{timestamp}</div>
    </div>
</div>""")
        else:
            chat_jid = msg.get("chat_jid") or ""
            recipient_phone = chat_jid.split("@")[0] if "@" in chat_jid else chat_jid
            recipient_name = push_name if push_name else recipient_phone
            recipient_display = (
                f"{recipient_name} ({recipient_phone})"
                if push_name
                else recipient_phone
            )

            html_parts.append(f"""
<div class="flex gap-2 mb-3 justify-end px-4">
    <div class="max-w-[80%] bg-whatsapp/20 rounded-2xl rounded-tr-sm px-4 py-2">
        <div class='text-xs text-whatsapp/70 mb-1'>To: {recipient_display}</div>
        <div class="text-sm text-gray-100">{text}</div>
        <div class="text-xs text-gray-400 mt-1 text-right">{timestamp}</div>
    </div>
</div>""")

    return HTMLResponse(content="".join(html_parts))


@fragments_router.get("/tenant-contacts/{tenant_hash}", response_class=HTMLResponse)
async def get_tenant_contacts_fragment(
    tenant_hash: str,
    limit: int = Query(100, ge=1, le=500),
    session_id: str = Depends(require_admin_session),
):
    tenant = tenant_manager._tenants.get(tenant_hash)
    if not tenant:
        return HTMLResponse(
            content='<div class="p-6 text-center text-red-400">Tenant not found</div>'
        )

    db = tenant_manager._db
    if not db:
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">Database not available</div>'
        )

    contacts = await db.get_recent_chats(tenant_hash, limit=limit)

    if not contacts:
        return HTMLResponse(
            content='<div class="p-6 text-center text-gray-500">No contacts yet</div>'
        )

    html_parts = []
    for contact in contacts:
        chat_jid = contact.get("chat_jid", "")
        push_name = contact.get("push_name") or ""
        phone = contact.get("phone") or (
            chat_jid.split("@")[0] if "@" in chat_jid else chat_jid
        )
        is_group = contact.get("is_group", False)
        message_count = contact.get("message_count", 0)
        last_message_at = contact.get("last_message_at")

        if push_name:
            display_name = push_name
            subtitle = phone
        else:
            display_name = phone
            subtitle = ""

        if last_message_at:
            if isinstance(last_message_at, datetime):
                last_time = last_message_at.strftime("%Y-%m-%d %H:%M")
            else:
                last_time = str(last_message_at)
        else:
            last_time = ""

        if is_group:
            icon_svg = '<svg class="w-6 h-6 text-blue-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M17 20h5v-2a3 3 0 00-5.356-1.857M17 20H7m10 0v-2c0-.656-.126-1.283-.356-1.857M7 20H2v-2a3 3 0 015.356-1.857M7 20v-2c0-.656.126-1.283.356-1.857m0 0a5.002 5.002 0 019.288 0M15 7a3 3 0 11-6 0 3 3 0 016 0zm6 3a2 2 0 11-4 0 2 2 0 014 0zM7 10a2 2 0 11-4 0 2 2 0 014 0z"></path></svg>'
            badge = '<span class="ml-2 px-2 py-1 text-xs bg-blue-500/20 text-blue-400 rounded">Group</span>'
        else:
            icon_svg = '<svg class="w-6 h-6 text-whatsapp" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z"></path></svg>'
            badge = ""

        display_name_escaped = display_name.replace("'", "'")

        contact_html = f"""
<div class="p-4 hover:bg-gray-700/50 transition cursor-pointer" onclick="selectContact('{chat_jid}', '{display_name_escaped}')">
    <div class="flex items-center justify-between">
        <div class="flex items-center gap-3 flex-1">
            <div class="w-10 h-10 bg-gray-700 rounded-full flex items-center justify-center flex-shrink-0">
                {icon_svg}
            </div>
            <div class="flex-1 min-w-0">
                <div class="flex items-center gap-2">
                    <span class="font-medium truncate">{display_name}</span>
                    {badge}
                </div>
                <div class="text-sm text-gray-400 truncate">{subtitle}</div>
            </div>
        </div>
        <div class="text-right flex-shrink-0 ml-4">
            <div class="text-sm text-gray-400">{message_count} messages</div>
            <div class="text-xs text-gray-500 mt-1">{last_time}</div>
        </div>
    </div>
</div>"""
        html_parts.append(contact_html)

    header = f'<div class="px-6 py-3 bg-gray-700/50 border-b border-gray-700"><span class="text-sm text-gray-400">{len(contacts)} contacts</span></div>'
    html_parts.insert(0, header)

    return HTMLResponse(content="".join(html_parts))


@fragments_router.get("/recent-chats/{tenant_hash}")
async def get_recent_chats_fragment(
    tenant_hash: str,
    session_id: str = Depends(require_admin_session),
):
    db = tenant_manager._db
    if not db:
        return {"chats": []}

    chats = await db.get_recent_chats(tenant_hash, limit=50)
    return {"chats": chats}


# JSON API Routes


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


@api_router.get("/websockets")
async def list_websockets_api(session_id: str = Depends(require_admin_session)):
    return {
        "count": admin_ws_manager.get_connection_count(),
        "connections": admin_ws_manager.get_connections_info(),
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
    name: str = Form(...),
    session_id: str = Depends(require_admin_session),
):
    tenant, api_key = await tenant_manager.create_tenant(name)
    return {
        "status": "created",
        "tenant": {
            "name": tenant.name,
            "api_key": api_key,
            "api_key_hash": tenant.api_key_hash,
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

    deleted = await tenant_manager.delete_tenant_by_hash(tenant_hash)
    return {"status": "deleted" if deleted else "not_found"}


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


class ToggleEnabledRequest(BaseModel):
    enabled: bool


@api_router.patch("/tenants/{tenant_hash}/enabled")
async def toggle_tenant_enabled(
    tenant_hash: str,
    request: ToggleEnabledRequest,
    session_id: str = Depends(require_admin_session),
):
    tenant = tenant_manager._tenants.get(tenant_hash)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    db = tenant_manager._db
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    await db.update_tenant_enabled(tenant_hash, request.enabled)
    tenant.enabled = request.enabled

    if not request.enabled and tenant.bridge:
        await tenant.bridge.stop()
        tenant.connection_state = "disconnected"

    return {"status": "updated", "enabled": request.enabled}


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
                "tenant_name": tenants.get(msg.get("tenant_hash") or "", "Unknown"),
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
                "tenant_name": tenants.get(a.get("tenant_hash") or "", "Unknown"),
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

    if not is_safe_webhook_url(data.url):
        raise HTTPException(
            status_code=400,
            detail="Webhook URL points to internal or blocked address",
        )

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


class AdminSendMessage(BaseModel):
    to: str
    text: str


@api_router.post("/tenants/{tenant_hash}/send")
async def admin_send_message(
    tenant_hash: str,
    data: AdminSendMessage,
    session_id: str = Depends(require_admin_session),
):
    tenant = tenant_manager._tenants.get(tenant_hash)
    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    if not tenant.has_auth:
        raise HTTPException(status_code=400, detail="Tenant is not connected")

    if not data.to:
        raise HTTPException(status_code=400, detail="Recipient is required")

    if not data.text:
        raise HTTPException(status_code=400, detail="Message text is required")

    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_message(to=data.to, text=data.text)
        return {
            "status": "sent",
            "message_id": result.get("message_id"),
            "to": result.get("to", data.to),
        }
    except Exception as e:
        logger.error(f"Admin send message failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


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
    rate_limiter.clear_failed_auth(ip)
    return {"status": "cleared"}


# Bulk Operations


class BulkOperationRequest(BaseModel):
    items: list[str] = Field(..., max_length=50)


class BulkTenantReconnectRequest(BaseModel):
    tenant_hashes: list[str] = Field(..., max_length=50)


class BulkMessageDeleteRequest(BaseModel):
    message_ids: list[int] = Field(..., max_length=50)


@api_router.post("/tenants/bulk/reconnect")
async def bulk_reconnect_tenants(
    data: BulkTenantReconnectRequest,
    session_id: str = Depends(require_admin_session),
):
    """Bulk reconnect multiple tenants (max 50)"""
    results = []

    for hash in data.tenant_hashes:
        try:
            tenant = tenant_manager._tenants.get(hash)
            if not tenant:
                results.append({"hash": hash, "status": "not_found"})
                continue

            if tenant.bridge:
                await tenant.bridge.stop()

            bridge = await tenant_manager.get_or_create_bridge(tenant)
            await bridge.login()
            results.append({"hash": hash, "status": "success"})
        except Exception as e:
            results.append({"hash": hash, "status": "error", "error": str(e)})

    return {
        "processed": len(results),
        "successful": sum(1 for r in results if r["status"] == "success"),
        "failed": sum(1 for r in results if r["status"] != "success"),
        "results": results,
    }


@api_router.delete("/tenants/bulk")
async def bulk_delete_tenants(
    data: BulkTenantReconnectRequest,
    session_id: str = Depends(require_admin_session),
):
    """Bulk delete multiple tenants (max 50)"""
    results = []

    for hash in data.tenant_hashes:
        try:
            tenant = tenant_manager._tenants.get(hash)
            if not tenant:
                results.append({"hash": hash, "status": "not_found"})
                continue

            deleted = await tenant_manager.delete_tenant_by_hash(hash)
            results.append({"hash": hash, "status": "deleted" if deleted else "failed"})
        except Exception as e:
            results.append({"hash": hash, "status": "error", "error": str(e)})

    return {
        "processed": len(results),
        "deleted": sum(1 for r in results if r["status"] == "deleted"),
        "failed": sum(1 for r in results if r["status"] != "deleted"),
        "results": results,
    }


@api_router.delete("/messages/bulk")
async def bulk_delete_messages(
    data: BulkMessageDeleteRequest,
    session_id: str = Depends(require_admin_session),
):
    """Bulk delete multiple messages (max 50)"""
    db = tenant_manager._db
    if not db:
        raise HTTPException(status_code=503, detail="Database not available")

    deleted = []
    failed = []

    for msg_id in data.message_ids:
        try:
            if await db.delete_message(msg_id):
                deleted.append(msg_id)
            else:
                failed.append(msg_id)
        except Exception as e:
            failed.append(msg_id)

    return {
        "requested": len(data.message_ids),
        "deleted": len(deleted),
        "failed": len(failed),
        "deleted_ids": deleted,
        "failed_ids": failed,
    }


@api_router.post("/webhooks/bulk/test")
async def bulk_test_webhooks(
    data: BulkOperationRequest,
    session_id: str = Depends(require_admin_session),
):
    """Bulk test webhook URLs (max 50)"""
    import httpx
    import asyncio

    results = []

    async def test_webhook(url: str):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.post(
                    url,
                    json={"test": True, "timestamp": datetime.now(UTC).isoformat()},
                    headers={"Content-Type": "application/json"},
                )
                return {
                    "url": url,
                    "success": response.status_code in [200, 201, 202, 204],
                    "status_code": response.status_code,
                }
        except Exception as e:
            return {"url": url, "success": False, "error": str(e)}

    # Test all webhooks in parallel
    tasks = [test_webhook(url) for url in data.items]
    results = await asyncio.gather(*tasks)

    return {
        "total": len(results),
        "successful": sum(1 for r in results if r["success"]),
        "failed": sum(1 for r in results if not r["success"]),
        "results": results,
    }


class ChatwootConfigRequest(BaseModel):
    url: str
    token: str
    account_id: str
    enabled: bool = True


class ChatwootTenantConfigRequest(BaseModel):
    enabled: bool = True
    sign_messages: bool = True
    reopen_conversation: bool = True


@api_router.post("/chatwoot/config")
async def set_chatwoot_global_config(
    data: ChatwootConfigRequest,
    session_id: str = Depends(require_admin_session),
):
    from ..chatwoot import ChatwootConfig, ChatwootClient, ChatwootAPIError

    config = ChatwootConfig(
        enabled=data.enabled,
        url=data.url.rstrip("/"),
        token=data.token,
        account_id=data.account_id,
    )

    client = ChatwootClient(config)
    try:
        await client.list_inboxes()
        connected = True
    except ChatwootAPIError as e:
        logger.error(f"Chatwoot connection error: {e.message}")
        raise HTTPException(
            status_code=400, detail=f"Chatwoot connection error: {e.message}"
        )
    except Exception as e:
        logger.error(f"Unexpected Chatwoot error: {e}")
        raise HTTPException(status_code=400, detail=f"Unexpected error: {str(e)}")
    finally:
        await client.close()

    if tenant_manager._db:
        await tenant_manager._db.save_global_config(
            "chatwoot",
            {
                "url": data.url.rstrip("/"),
                "token": data.token,
                "account_id": data.account_id,
                "enabled": data.enabled,
            },
        )

    return {"status": "configured", "connected": connected}


@api_router.get("/chatwoot/tenants")
async def list_chatwoot_tenants_api(session_id: str = Depends(require_admin_session)):
    tenants = tenant_manager.list_tenants()
    result = []
    for tenant in tenants:
        config = getattr(tenant, "chatwoot_config", None) or {}
        result.append(
            {
                "tenant_hash": tenant.api_key_hash[:16],
                "tenant_name": tenant.name,
                "chatwoot_enabled": config.get("enabled", False),
                "chatwoot_url": config.get("url"),
                "chatwoot_inbox_id": config.get("inbox_id"),
            }
        )
    return {"tenants": result}


@api_router.post("/tenants/{tenant_hash}/chatwoot")
async def set_tenant_chatwoot_config(
    tenant_hash: str,
    data: ChatwootTenantConfigRequest,
    session_id: str = Depends(require_admin_session),
):
    from ..chatwoot import ChatwootConfig, ChatwootClient, ChatwootAPIError

    tenant = None
    for t in tenant_manager.list_tenants():
        if t.api_key_hash == tenant_hash:
            tenant = t
            break

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    existing_config = getattr(tenant, "chatwoot_config", None) or {}

    if data.enabled:
        global_config = None
        if tenant_manager._db:
            global_config = await tenant_manager._db.get_global_config("chatwoot")

        if not global_config:
            raise HTTPException(
                status_code=400,
                detail="Chatwoot global configuration not found. Please configure Chatwoot first.",
            )

        cw_config = ChatwootConfig(
            enabled=True,
            url=global_config["url"],
            token=global_config["token"],
            account_id=global_config["account_id"],
        )

        client = ChatwootClient(cw_config)
        try:
            inbox_name = f"WhatsApp - {tenant.name}"
            webhook_url = f"{settings.base_url.rstrip('/')}/webhooks/chatwoot/{tenant.api_key_hash[:16]}/outgoing"

            existing_inbox_id = existing_config.get("inbox_id")
            if not existing_inbox_id:
                inboxes = await client.list_inboxes()
                existing_inbox = None
                for inbox in inboxes:
                    if inbox.name == inbox_name:
                        existing_inbox = inbox
                        break

                if existing_inbox:
                    inbox_id = existing_inbox.id
                else:
                    inbox = await client.create_inbox(inbox_name, webhook_url)
                    inbox_id = inbox.id
            else:
                inbox_id = existing_inbox_id

            new_config = {
                **existing_config,
                "enabled": True,
                "sign_messages": data.sign_messages,
                "reopen_conversation": data.reopen_conversation,
                "inbox_id": inbox_id,
                "url": global_config["url"],
                "account_id": global_config["account_id"],
            }

        except ChatwootAPIError as e:
            logger.error(f"Failed to create Chatwoot inbox: {e.message}")
            raise HTTPException(
                status_code=400, detail=f"Failed to create Chatwoot inbox: {e.message}"
            )
        finally:
            await client.close()
    else:
        new_config = {
            **existing_config,
            "enabled": False,
            "sign_messages": data.sign_messages,
            "reopen_conversation": data.reopen_conversation,
        }

    tenant.chatwoot_config = new_config

    if tenant_manager._db:
        await tenant_manager._db.save_chatwoot_config(tenant.api_key_hash, new_config)

    return {"status": "updated", "config": new_config}


@api_router.post("/tenants/{tenant_hash}/chatwoot/sync-contacts")
async def sync_tenant_chatwoot_contacts(
    tenant_hash: str,
    session_id: str = Depends(require_admin_session),
):
    from ..chatwoot import ChatwootConfig, ChatwootClient

    tenant = None
    for t in tenant_manager.list_tenants():
        if t.api_key_hash == tenant_hash:
            tenant = t
            break

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    config = getattr(tenant, "chatwoot_config", None)
    if not config or not config.get("enabled"):
        raise HTTPException(
            status_code=400, detail="Chatwoot not enabled for this tenant"
        )

    if not tenant_manager._db:
        raise HTTPException(status_code=400, detail="Database not available")

    global_config = await tenant_manager._db.get_global_config("chatwoot")
    if not global_config:
        raise HTTPException(status_code=400, detail="Chatwoot global config not found")

    chats = await tenant_manager._db.get_recent_chats(tenant.api_key_hash, limit=1000)

    cw_config = ChatwootConfig(
        enabled=True,
        url=config.get("url", global_config["url"]),
        token=global_config["token"],
        account_id=config.get("account_id", global_config["account_id"]),
        inbox_id=config.get("inbox_id"),
    )

    client = ChatwootClient(cw_config)
    created = 0
    updated = 0
    skipped = 0

    try:
        for chat in chats:
            if chat.get("is_group"):
                skipped += 1
                continue

            chat_jid = chat.get("chat_jid", "")
            if not chat_jid:
                skipped += 1
                continue

            phone = chat_jid.split("@")[0] if "@" in chat_jid else chat_jid
            name = chat.get("push_name") or phone

            try:
                existing = await client.find_contact_by_phone(phone)
                if existing:
                    if name and name != existing.name:
                        await client.update_contact(existing.id, name=name)
                        updated += 1
                    else:
                        skipped += 1
                else:
                    await client.create_contact(phone_number=phone, name=name)
                    created += 1
            except Exception as e:
                logger.warning(f"Failed to sync contact {phone}: {e}")
                skipped += 1

    finally:
        await client.close()

    return {"created": created, "updated": updated, "skipped": skipped}


@api_router.post("/tenants/{tenant_hash}/chatwoot/sync-messages")
async def sync_tenant_chatwoot_messages(
    tenant_hash: str,
    session_id: str = Depends(require_admin_session),
):
    from ..chatwoot import ChatwootConfig, ChatwootSyncService

    tenant = None
    for t in tenant_manager.list_tenants():
        if t.api_key_hash == tenant_hash:
            tenant = t
            break

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    config = getattr(tenant, "chatwoot_config", None)
    if not config or not config.get("enabled"):
        raise HTTPException(
            status_code=400, detail="Chatwoot not enabled for this tenant"
        )

    if not config.get("import_messages", False):
        raise HTTPException(
            status_code=400,
            detail="Message import not enabled. Enable 'import_messages' in Chatwoot config.",
        )

    if not tenant_manager._db:
        raise HTTPException(status_code=400, detail="Database not available")

    global_config = await tenant_manager._db.get_global_config("chatwoot")
    if not global_config:
        raise HTTPException(status_code=400, detail="Chatwoot global config not found")

    cw_config = ChatwootConfig(
        enabled=True,
        url=config.get("url", global_config["url"]),
        token=global_config["token"],
        account_id=config.get("account_id", global_config["account_id"]),
        inbox_id=config.get("inbox_id"),
        days_limit_import=config.get("days_limit_import", 3),
        reopen_conversation=config.get("reopen_conversation", True),
        merge_brazil_contacts=config.get("merge_brazil_contacts", True),
    )

    sync_service = ChatwootSyncService(cw_config, tenant, tenant_manager._db)

    try:
        result = await sync_service.sync_message_history()
        return result
    except Exception as e:
        logger.error(f"Failed to sync messages for tenant {tenant.name}: {e}")
        raise HTTPException(
            status_code=500, detail=f"Failed to sync messages: {str(e)}"
        )
    finally:
        await sync_service.close()


@api_router.delete("/tenants/{tenant_hash}/chatwoot")
async def disable_tenant_chatwoot(
    tenant_hash: str,
    session_id: str = Depends(require_admin_session),
):
    tenant = None
    for t in tenant_manager.list_tenants():
        if t.api_key_hash == tenant_hash:
            tenant = t
            break

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    tenant.chatwoot_config = None

    if tenant_manager._db:
        await tenant_manager._db.save_chatwoot_config(tenant.api_key_hash, None)

    return {"status": "disabled"}


@api_router.get("/session-id")
async def get_session_id(
    request: Request,
    session_id: str = Depends(require_admin_session),
):
    """Get current admin session ID for WebSocket connection"""
    return {"session_id": session_id}
