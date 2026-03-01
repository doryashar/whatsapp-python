from fastapi import APIRouter, HTTPException, Query, Depends
from typing import Optional
from ..bridge import BridgeError
from ..tenant import Tenant, tenant_manager
from ..telemetry import get_logger
from ..middleware import rate_limiter
from ..models import (
    SendMessageRequest,
    SendMessageResponse,
    SendReactionRequest,
    SendReactionResponse,
    LoginResponse,
    StatusResponse,
    LogoutResponse,
    MessageListResponse,
    SelfInfo,
    AddWebhookRequest,
    WebhookListResponse,
    WebhookOperationResponse,
    InboundMessage,
    SendPollRequest,
    SendPollResponse,
    SendTypingResponse,
    AuthExistsResponse,
    AuthAgeResponse,
    SelfIdResponse,
)
from .auth import get_tenant, get_admin_key

logger = get_logger("whatsapp.api")

router = APIRouter(prefix="/api", tags=["WhatsApp"])
admin_router = APIRouter(prefix="/admin/v1", tags=["Admin"])


@router.get("/status", response_model=StatusResponse)
async def get_status(tenant: Tenant = Depends(get_tenant)):
    logger.debug(f"Status check for tenant: {tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.get_status()
        logger.debug(
            f"Status result: state={result.get('connection_state')}, has_qr={result.get('has_qr')}"
        )
        return StatusResponse(
            connection_state=result.get("connection_state", "disconnected"),
            self_info=SelfInfo(**result["self"]) if result.get("self") else None,
            has_qr=result.get("has_qr", False),
        )
    except BridgeError as e:
        logger.error(f"Status check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login", response_model=LoginResponse)
async def login(tenant: Tenant = Depends(get_tenant)):
    logger.info(f"Login requested for tenant: {tenant.name}")
    try:
        logger.debug(f"Getting/creating bridge for tenant: {tenant.name}")
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        logger.debug(f"Calling bridge.login()")
        result = await bridge.login()
        logger.info(
            f"Login result: status={result.get('status')}, state={result.get('connection_state')}, jid={result.get('jid')}"
        )
        return LoginResponse(
            status=result.get("status", "unknown"),
            qr=result.get("qr"),
            qr_data_url=result.get("qr_data_url"),
            connection_state=result.get("connection_state"),
            jid=result.get("jid"),
            phone=result.get("phone"),
            name=result.get("name"),
        )
    except BridgeError as e:
        logger.error(f"Login failed for tenant {tenant.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logout", response_model=LogoutResponse)
async def logout(tenant: Tenant = Depends(get_tenant)):
    logger.info(f"Logout requested for tenant: {tenant.name}")
    try:
        if tenant.bridge:
            result = await tenant.bridge.logout()
            logger.info(f"Logout result: {result.get('status')}")
            return LogoutResponse(status=result.get("status", "logged_out"))
        logger.debug(f"No bridge for tenant {tenant.name}, returning not_connected")
        return LogoutResponse(status="not_connected")
    except BridgeError as e:
        logger.error(f"Logout failed for tenant {tenant.name}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages", response_model=MessageListResponse)
async def list_messages(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    tenant: Tenant = Depends(get_tenant),
):
    messages, total = tenant.message_store.list(limit=limit, offset=offset)
    return MessageListResponse(
        messages=[InboundMessage(**m) for m in messages],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/messages")
async def clear_messages(tenant: Tenant = Depends(get_tenant)):
    tenant.message_store.clear()
    return {"status": "cleared"}


@router.post("/send", response_model=SendMessageResponse)
async def send_message(
    request: SendMessageRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(f"Send message requested: tenant={tenant.name}, to={request.to}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_message(
            to=request.to,
            text=request.text,
            media_url=request.media_url,
        )
        logger.info(
            f"Message sent: message_id={result.get('message_id')}, to={result.get('to')}"
        )
        return SendMessageResponse(
            message_id=result.get("message_id", "unknown"),
            to=result.get("to", request.to),
        )
    except BridgeError as e:
        logger.error(f"Send message failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/react", response_model=SendReactionResponse)
async def send_reaction(
    request: SendReactionRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(
        f"Send reaction: tenant={tenant.name}, chat={request.chat}, emoji={request.emoji}"
    )
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_reaction(
            chat=request.chat,
            message_id=request.message_id,
            emoji=request.emoji,
            from_me=request.from_me,
        )
        logger.debug(f"Reaction result: {result.get('status')}")
        return SendReactionResponse(
            status=result.get("status", "reacted"),
            chat=result.get("chat", request.chat),
            message_id=request.message_id,
            emoji=request.emoji,
        )
    except BridgeError as e:
        logger.error(f"Send reaction failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/poll", response_model=SendPollResponse)
async def send_poll(
    request: SendPollRequest,
    tenant: Tenant = Depends(get_tenant),
):
    logger.info(
        f"Send poll: tenant={tenant.name}, to={request.to}, name={request.name}"
    )
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_poll(
            to=request.to,
            name=request.name,
            values=request.values,
            selectable_count=request.selectable_count,
        )
        logger.info(
            f"Poll sent: message_id={result.get('message_id')}, to={result.get('to')}"
        )
        return SendPollResponse(
            message_id=result.get("message_id", "unknown"),
            to=result.get("to", request.to),
        )
    except BridgeError as e:
        logger.error(f"Send poll failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/typing", response_model=SendTypingResponse)
async def send_typing(
    to: str = Query(..., description="Recipient phone number or JID"),
    tenant: Tenant = Depends(get_tenant),
):
    logger.debug(f"Send typing: tenant={tenant.name}, to={to}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_typing(to=to)
        return SendTypingResponse(
            status=result.get("status", "typing"),
            to=result.get("to", to),
        )
    except BridgeError as e:
        logger.error(f"Send typing failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/exists", response_model=AuthExistsResponse)
async def check_auth_exists(tenant: Tenant = Depends(get_tenant)):
    logger.debug(f"Check auth exists: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.auth_exists()
        return AuthExistsResponse(exists=result.get("exists", False))
    except BridgeError as e:
        logger.error(f"Check auth exists failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/age", response_model=AuthAgeResponse)
async def get_auth_age(tenant: Tenant = Depends(get_tenant)):
    logger.debug(f"Get auth age: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.auth_age()
        return AuthAgeResponse(age_ms=result.get("age_ms"))
    except BridgeError as e:
        logger.error(f"Get auth age failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/auth/self", response_model=SelfIdResponse)
async def get_self_id(tenant: Tenant = Depends(get_tenant)):
    logger.debug(f"Get self ID: tenant={tenant.name}")
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.self_id()
        return SelfIdResponse(
            jid=result.get("jid"),
            e164=result.get("e164"),
            name=result.get("name"),
        )
    except BridgeError as e:
        logger.error(f"Get self ID failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/webhooks", response_model=WebhookListResponse)
async def list_webhooks(tenant: Tenant = Depends(get_tenant)):
    return WebhookListResponse(urls=tenant.webhook_urls)


@router.post("/webhooks", response_model=WebhookOperationResponse)
async def add_webhook(
    request: AddWebhookRequest,
    tenant: Tenant = Depends(get_tenant),
):
    if not request.url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400, detail="URL must start with http:// or https://"
        )
    await tenant_manager.add_webhook(tenant, request.url)
    return WebhookOperationResponse(status="added", url=request.url)


@router.delete("/webhooks", response_model=WebhookOperationResponse)
async def remove_webhook(
    url: str = Query(..., description="Webhook URL to remove"),
    tenant: Tenant = Depends(get_tenant),
):
    if await tenant_manager.remove_webhook(tenant, url):
        return WebhookOperationResponse(status="removed", url=url)
    raise HTTPException(status_code=404, detail="Webhook URL not found")


class CreateTenantRequest:
    def __init__(self, name: str):
        self.name = name


class TenantResponse:
    def __init__(self, name: str, api_key: str, created_at: str):
        self.name = name
        self.api_key = api_key
        self.created_at = created_at


class TenantListResponse:
    def __init__(self, tenants: list[dict]):
        self.tenants = tenants


@admin_router.post("/tenants")
async def create_tenant(
    name: str = Query(..., description="Tenant name"),
    _: str = Depends(get_admin_key),
):
    tenant, api_key = await tenant_manager.create_tenant(name)
    return {
        "name": tenant.name,
        "api_key": api_key,
        "created_at": tenant.created_at.isoformat(),
    }


@admin_router.get("/tenants")
async def list_tenants(_: str = Depends(get_admin_key)):
    tenants = []
    for t in tenant_manager.list_tenants():
        tenants.append(
            {
                "name": t.name,
                "created_at": t.created_at.isoformat(),
                "webhook_count": len(t.webhook_urls),
            }
        )
    return {"tenants": tenants}


@admin_router.delete("/tenants")
async def delete_tenant(
    api_key: str = Query(..., description="Tenant API key to delete"),
    _: str = Depends(get_admin_key),
):
    if await tenant_manager.delete_tenant(api_key):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Tenant not found")


@admin_router.get("/rate-limit/blocked")
async def list_blocked_ips(_: str = Depends(get_admin_key)):
    return {"blocked_ips": rate_limiter.get_blocked_ips()}


@admin_router.post("/rate-limit/block")
async def block_ip(
    ip: str = Query(..., description="IP address to block"),
    _: str = Depends(get_admin_key),
):
    rate_limiter.block_ip(ip, reason="admin")
    return {"status": "blocked", "ip": ip}


@admin_router.delete("/rate-limit/block")
async def unblock_ip(
    ip: str = Query(..., description="IP address to unblock"),
    _: str = Depends(get_admin_key),
):
    if rate_limiter.unblock_ip(ip):
        return {"status": "unblocked", "ip": ip}
    raise HTTPException(status_code=404, detail="IP not found in block list")


@admin_router.get("/rate-limit/stats")
async def rate_limit_stats(
    _: str = Depends(get_admin_key),
    ip: Optional[str] = Query(None, description="Get stats for specific IP"),
):
    return rate_limiter.get_stats(ip)


@admin_router.get("/rate-limit/failed-auth")
async def list_failed_auth_attempts(
    _: str = Depends(get_admin_key),
    ip: Optional[str] = Query(
        None, description="Get failed auth attempts for specific IP"
    ),
):
    return rate_limiter.get_failed_auth_attempts(ip)


@admin_router.delete("/rate-limit/failed-auth")
async def clear_failed_auth_attempts(
    ip: str = Query(..., description="IP address to clear failed attempts for"),
    _: str = Depends(get_admin_key),
):
    rate_limiter.clear_failed_auth(ip)
    return {"status": "cleared", "ip": ip}
