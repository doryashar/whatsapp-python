from fastapi import APIRouter, HTTPException, Query, Depends
from ..bridge import BridgeError
from ..tenant import Tenant, tenant_manager
from ..store.messages import InboundMessage
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
)
from .auth import get_tenant, get_admin_key

router = APIRouter(prefix="/api", tags=["WhatsApp"])
admin_router = APIRouter(prefix="/admin", tags=["Admin"])


@router.get("/status", response_model=StatusResponse)
async def get_status(tenant: Tenant = Depends(get_tenant)):
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.get_status()
        return StatusResponse(
            connection_state=result.get("connection_state", "disconnected"),
            self_info=SelfInfo(**result["self"]) if result.get("self") else None,
            has_qr=result.get("has_qr", False),
        )
    except BridgeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login", response_model=LoginResponse)
async def login(tenant: Tenant = Depends(get_tenant)):
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.login()
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
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/logout", response_model=LogoutResponse)
async def logout(tenant: Tenant = Depends(get_tenant)):
    try:
        if tenant.bridge:
            result = await tenant.bridge.logout()
            return LogoutResponse(status=result.get("status", "logged_out"))
        return LogoutResponse(status="not_connected")
    except BridgeError as e:
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
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_message(
            to=request.to,
            text=request.text,
            media_url=request.media_url,
        )
        return SendMessageResponse(
            message_id=result.get("message_id", "unknown"),
            to=result.get("to", request.to),
        )
    except BridgeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/react", response_model=SendReactionResponse)
async def send_reaction(
    request: SendReactionRequest,
    tenant: Tenant = Depends(get_tenant),
):
    try:
        bridge = await tenant_manager.get_or_create_bridge(tenant)
        result = await bridge.send_reaction(
            chat=request.chat,
            message_id=request.message_id,
            emoji=request.emoji,
        )
        return SendReactionResponse(
            status=result.get("status", "reacted"),
            chat=result.get("chat", request.chat),
            message_id=request.message_id,
            emoji=request.emoji,
        )
    except BridgeError as e:
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
