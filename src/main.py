import asyncio
import json
from typing import Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .api import router, admin_router
from .tenant import tenant_manager
from .webhooks import WebhookSender
from .store.messages import InboundMessage


class ConnectionManager:
    def __init__(self):
        self._connections: dict[str, list[WebSocket]] = {}

    async def connect(self, api_key_hash: str, websocket: WebSocket):
        await websocket.accept()
        if api_key_hash not in self._connections:
            self._connections[api_key_hash] = []
        self._connections[api_key_hash].append(websocket)

    def disconnect(self, api_key_hash: str, websocket: WebSocket):
        if api_key_hash in self._connections:
            if websocket in self._connections[api_key_hash]:
                self._connections[api_key_hash].remove(websocket)

    async def broadcast(self, api_key_hash: str, event_type: str, data: dict[str, Any]):
        if api_key_hash not in self._connections:
            return
        message = json.dumps({"type": event_type, "data": data})
        for connection in self._connections[api_key_hash][:]:
            try:
                await connection.send_text(message)
            except Exception:
                pass


manager = ConnectionManager()


def handle_bridge_event(
    event_type: str, params: dict[str, Any], tenant_id: Optional[str] = None
):
    if not tenant_id:
        return

    tenant = None
    for t in tenant_manager.list_tenants():
        if t.api_key_hash == tenant_id:
            tenant = t
            break

    if not tenant:
        return

    if event_type == "message":
        msg = InboundMessage(
            id=params["id"],
            from_jid=params["from"],
            chat_jid=params["chat_jid"],
            is_group=params.get("is_group", False),
            push_name=params.get("push_name"),
            text=params.get("text", ""),
            msg_type=params.get("type", "text"),
            timestamp=params.get("timestamp", 0),
        )
        tenant.message_store.add(msg)

    asyncio.create_task(manager.broadcast(tenant_id, event_type, params))

    if tenant.webhook_urls:
        sender = WebhookSender(
            urls=tenant.webhook_urls,
            secret=settings.webhook_secret,
            timeout=settings.webhook_timeout,
            max_retries=settings.webhook_retries,
        )
        asyncio.create_task(sender.send(event_type, params))


tenant_manager.on_event(handle_bridge_event)

app = FastAPI(
    title="WhatsApp API",
    description="WhatsApp Web API with FastAPI and Baileys bridge - Multi-tenant",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(admin_router)


@app.get("/health")
async def health():
    return {"status": "healthy"}


@app.websocket("/ws/events")
async def ws_events(
    websocket: WebSocket,
    api_key: Optional[str] = Query(None),
):
    if not api_key:
        await websocket.close(code=1008, reason="API key required")
        return

    tenant = tenant_manager.get_tenant_by_key(api_key)
    if not tenant:
        await websocket.close(code=1008, reason="Invalid API key")
        return

    await manager.connect(tenant.api_key_hash, websocket)

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                if msg.get("type") == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
            except json.JSONDecodeError:
                pass
    except WebSocketDisconnect:
        manager.disconnect(tenant.api_key_hash, websocket)
    except Exception:
        manager.disconnect(tenant.api_key_hash, websocket)


def main():
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )


if __name__ == "__main__":
    main()
