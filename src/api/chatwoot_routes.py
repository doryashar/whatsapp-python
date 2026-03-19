import json
from typing import Optional, List
from fastapi import APIRouter, HTTPException, Header, Request, Depends
from pydantic import BaseModel, Field

from ..tenant import tenant_manager
from ..chatwoot import (
    ChatwootConfig,
    ChatwootClient,
    ChatwootIntegration,
    ChatwootWebhookHandler,
    ChatwootAPIError,
)
from ..telemetry import get_logger

logger = get_logger("whatsapp.chatwoot.routes")

router = APIRouter(prefix="/api/chatwoot", tags=["chatwoot"])
webhook_router = APIRouter(tags=["chatwoot-webhook"])


class ChatwootConfigRequest(BaseModel):
    enabled: bool = True
    url: str
    token: str
    account_id: str
    inbox_name: str = "WhatsApp"
    sign_messages: bool = True
    sign_delimiter: str = "\n"
    reopen_conversation: bool = True
    conversation_pending: bool = False
    import_contacts: bool = True
    import_messages: bool = False
    days_limit_import: int = 3
    merge_brazil_contacts: bool = True
    bot_contact_enabled: bool = True
    bot_name: str = "Bot"
    bot_avatar_url: Optional[str] = None
    ignore_jids: List[str] = Field(default_factory=list)
    number: Optional[str] = None
    auto_create: bool = True
    organization: Optional[str] = None
    logo: Optional[str] = None
    message_delete_enabled: bool = True
    mark_read_on_reply: bool = True
    group_messages_enabled: bool = True


class ChatwootSetupRequest(BaseModel):
    inbox_name: str = "WhatsApp"


class ChatwootStatusResponse(BaseModel):
    enabled: bool
    connected: bool = False
    url: Optional[str] = None
    account_id: Optional[str] = None
    inbox_id: Optional[int] = None


def get_tenant(api_key: str = Header(None, alias="X-API-Key")):
    if not api_key:
        raise HTTPException(status_code=401, detail="API key required")

    tenant = tenant_manager.get_tenant_by_key(api_key)
    if not tenant:
        raise HTTPException(status_code=401, detail="Invalid API key")

    return tenant


@router.get("/config")
async def get_config(tenant=Depends(get_tenant)):
    config = getattr(tenant, "chatwoot_config", None)

    if not config:
        return {"enabled": False}

    return {
        "enabled": config.get("enabled", False),
        "url": config.get("url"),
        "account_id": config.get("account_id"),
        "inbox_id": config.get("inbox_id"),
        "inbox_name": config.get("inbox_name", "WhatsApp"),
        "sign_messages": config.get("sign_messages", True),
        "reopen_conversation": config.get("reopen_conversation", True),
    }


@router.post("/config")
async def set_config(request: ChatwootConfigRequest, tenant=Depends(get_tenant)):
    existing = getattr(tenant, "chatwoot_config", {}) or {}

    config = ChatwootConfig(
        enabled=request.enabled,
        url=request.url,
        token=request.token,
        account_id=request.account_id,
        inbox_id=existing.get("inbox_id"),
        inbox_name=request.inbox_name,
        hmac_token=existing.get("hmac_token"),
        sign_messages=request.sign_messages,
        sign_delimiter=request.sign_delimiter,
        reopen_conversation=request.reopen_conversation,
        conversation_pending=request.conversation_pending,
        import_contacts=request.import_contacts,
        import_messages=request.import_messages,
        days_limit_import=request.days_limit_import,
        merge_brazil_contacts=request.merge_brazil_contacts,
        bot_contact_enabled=request.bot_contact_enabled,
        bot_name=request.bot_name,
        bot_avatar_url=request.bot_avatar_url,
        ignore_jids=request.ignore_jids,
        number=request.number,
        auto_create=request.auto_create,
        organization=request.organization,
        logo=request.logo,
        message_delete_enabled=request.message_delete_enabled,
        mark_read_on_reply=request.mark_read_on_reply,
        group_messages_enabled=request.group_messages_enabled,
    )

    client = ChatwootClient(config)
    try:
        is_connected = await client.verify_connection()
        if not is_connected:
            raise HTTPException(status_code=400, detail="Failed to connect to Chatwoot")
    except ChatwootAPIError as e:
        raise HTTPException(status_code=400, detail=f"Chatwoot connection error: {e}")
    finally:
        await client.close()

    tenant.chatwoot_config = config.model_dump()

    if tenant_manager._db:
        await tenant_manager._db.save_chatwoot_config(
            tenant.api_key_hash,
            config.model_dump(),
        )

    logger.info(f"Chatwoot config updated for tenant: {tenant.name}")

    return {
        "status": "configured",
        "enabled": config.enabled,
        "connected": is_connected,
    }


@router.delete("/config")
async def disable_config(tenant=Depends(get_tenant)):
    tenant.chatwoot_config = None

    if tenant_manager._db:
        await tenant_manager._db.save_chatwoot_config(
            tenant.api_key_hash,
            None,
        )

    logger.info(f"Chatwoot integration disabled for tenant: {tenant.name}")

    return {"status": "disabled"}


@router.post("/setup")
async def setup_inbox(request: ChatwootSetupRequest, tenant=Depends(get_tenant)):
    config = getattr(tenant, "chatwoot_config", None)

    if not config or not config.get("enabled"):
        raise HTTPException(status_code=400, detail="Chatwoot not configured")

    chatwoot_config = ChatwootConfig(**config)

    if chatwoot_config.inbox_id:
        return {
            "status": "already_setup",
            "inbox_id": chatwoot_config.inbox_id,
        }

    client = ChatwootClient(chatwoot_config)

    try:
        import secrets

        webhook_token = secrets.token_urlsafe(32)

        base_url = getattr(tenant_manager, "_webhook_base_url", "http://localhost:8080")
        webhook_url = f"{base_url}/webhooks/chatwoot/{tenant.api_key_hash}/outgoing"

        inbox = await client.create_inbox(
            name=request.inbox_name,
            webhook_url=webhook_url,
        )

        chatwoot_config.inbox_id = inbox.id
        chatwoot_config.webhook_url = webhook_url
        chatwoot_config.hmac_token = webhook_token

        tenant.chatwoot_config = chatwoot_config.model_dump()

        if tenant_manager._db:
            await tenant_manager._db.save_chatwoot_config(
                tenant.api_key_hash,
                chatwoot_config.model_dump(),
            )

        logger.info(
            f"Chatwoot inbox created for tenant {tenant.name}: inbox_id={inbox.id}"
        )

        return {
            "status": "created",
            "inbox_id": inbox.id,
            "webhook_url": webhook_url,
        }

    except ChatwootAPIError as e:
        raise HTTPException(status_code=400, detail=f"Failed to create inbox: {e}")
    finally:
        await client.close()


@router.get("/status", response_model=ChatwootStatusResponse)
async def get_status(tenant=Depends(get_tenant)):
    config = getattr(tenant, "chatwoot_config", None)

    if not config or not config.get("enabled"):
        return ChatwootStatusResponse(enabled=False)

    chatwoot_config = ChatwootConfig(**config)
    client = ChatwootClient(chatwoot_config)

    try:
        connected = await client.verify_connection()
    except ChatwootAPIError:
        connected = False
    finally:
        await client.close()

    return ChatwootStatusResponse(
        enabled=True,
        connected=connected,
        url=chatwoot_config.url,
        account_id=chatwoot_config.account_id,
        inbox_id=chatwoot_config.inbox_id,
    )


@webhook_router.post("/webhooks/chatwoot/{tenant_hash}/outgoing")
async def handle_outgoing(
    tenant_hash: str,
    request: Request,
    x_webhook_signature: Optional[str] = Header(None),
):
    tenant = tenant_manager._tenants.get(tenant_hash)

    if not tenant:
        raise HTTPException(status_code=404, detail="Tenant not found")

    config = getattr(tenant, "chatwoot_config", None)
    if not config or not config.get("enabled"):
        raise HTTPException(status_code=400, detail="Chatwoot not enabled for tenant")

    body = await request.body()
    payload = json.loads(body)

    chatwoot_config = ChatwootConfig(**config)

    bridge = await tenant_manager.get_or_create_bridge(tenant)

    handler = ChatwootWebhookHandler(
        tenant=tenant,
        bridge=bridge,
        config=chatwoot_config,
        hmac_token=chatwoot_config.hmac_token,
    )

    try:
        if chatwoot_config.hmac_token:
            if not x_webhook_signature:
                raise HTTPException(status_code=401, detail="Missing signature")
            if not handler.verify_signature(body, x_webhook_signature):
                raise HTTPException(status_code=401, detail="Invalid signature")

        result = await handler.handle_webhook(payload)

        logger.debug(
            f"Chatwoot webhook processed for tenant {tenant.name}: result={result}"
        )

        return result
    finally:
        await handler.close()
