from fastapi import APIRouter, HTTPException, Query
from ..bridge import bridge, BridgeError
from ..store.messages import message_store, InboundMessage
from ..webhooks import webhook_sender
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

router = APIRouter(prefix="/api", tags=["WhatsApp"])


@router.get("/status", response_model=StatusResponse)
async def get_status():
    try:
        result = await bridge.get_status()
        return StatusResponse(
            connection_state=result.get("connection_state", "disconnected"),
            self_info=SelfInfo(**result["self"]) if result.get("self") else None,
            has_qr=result.get("has_qr", False),
        )
    except BridgeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login", response_model=LoginResponse)
async def login():
    try:
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
async def logout():
    try:
        result = await bridge.logout()
        return LogoutResponse(status=result.get("status", "logged_out"))
    except BridgeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/messages", response_model=MessageListResponse)
async def list_messages(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    messages, total = message_store.list(limit=limit, offset=offset)
    return MessageListResponse(
        messages=[InboundMessage(**m) for m in messages],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.delete("/messages")
async def clear_messages():
    message_store.clear()
    return {"status": "cleared"}


@router.post("/send", response_model=SendMessageResponse)
async def send_message(request: SendMessageRequest):
    try:
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
async def send_reaction(request: SendReactionRequest):
    try:
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
async def list_webhooks():
    return WebhookListResponse(urls=webhook_sender.urls)


@router.post("/webhooks", response_model=WebhookOperationResponse)
async def add_webhook(request: AddWebhookRequest):
    if not request.url.startswith(("http://", "https://")):
        raise HTTPException(
            status_code=400, detail="URL must start with http:// or https://"
        )
    webhook_sender.add_url(request.url)
    return WebhookOperationResponse(status="added", url=request.url)


@router.delete("/webhooks", response_model=WebhookOperationResponse)
async def remove_webhook(url: str = Query(..., description="Webhook URL to remove")):
    if webhook_sender.remove_url(url):
        return WebhookOperationResponse(status="removed", url=url)
    raise HTTPException(status_code=404, detail="Webhook URL not found")
