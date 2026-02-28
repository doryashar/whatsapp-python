import asyncio
import json
from typing import Any, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings, logger
from .api import router, admin_router
from .tenant import tenant_manager
from .store.database import Database
from .webhooks import WebhookSender
from .store.messages import StoredMessage


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting WhatsApp API...")
    db = Database(settings.database_url, settings.data_dir)
    tenant_manager.set_database(db)
    await tenant_manager.initialize()
    await tenant_manager.restore_sessions()
    logger.info("WhatsApp API ready")
    yield
    logger.info("Shutting down WhatsApp API...")
    await tenant_manager.close()
    logger.info("Shutdown complete")


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
    logger.debug(
        f"Bridge event received: type={event_type}, tenant={tenant_id[:16] if tenant_id else 'none'}..."
    )

    if not tenant_id:
        logger.debug("Event has no tenant_id, ignoring")
        return

    tenant = None
    for t in tenant_manager.list_tenants():
        if t.api_key_hash == tenant_id:
            tenant = t
            break

    if not tenant:
        logger.debug(f"Tenant not found for event: {tenant_id[:16]}...")
        return

    logger.info(f"Bridge event for tenant {tenant.name}: type={event_type}")

    if event_type == "qr":
        logger.info(f"QR code generated for tenant {tenant.name}")
    elif event_type == "connected":
        logger.info(
            f"Tenant {tenant.name} connected: jid={params.get('jid')}, phone={params.get('phone')}"
        )
        asyncio.create_task(
            tenant_manager.update_session_state(
                tenant,
                "connected",
                self_jid=params.get("jid"),
                self_phone=params.get("phone"),
                self_name=params.get("name"),
                has_auth=True,
            )
        )
    elif event_type == "disconnected":
        reason = params.get("reason")
        reason_name = params.get("reason_name", "unknown")
        error = params.get("error", "")
        should_reconnect = params.get("should_reconnect", True)
        logger.warning(
            f"Tenant {tenant.name} disconnected: reason={reason} ({reason_name}), "
            f"error={error}, should_reconnect={should_reconnect}"
        )
        if reason_name == "loggedOut":
            asyncio.create_task(
                tenant_manager.update_session_state(
                    tenant, "disconnected", has_auth=False
                )
            )
        else:
            asyncio.create_task(
                tenant_manager.update_session_state(tenant, "disconnected")
            )
    elif event_type == "reconnecting":
        logger.info(f"Tenant {tenant.name} reconnecting: reason={params.get('reason')}")
        asyncio.create_task(tenant_manager.update_session_state(tenant, "connecting"))
    elif event_type == "reconnect_failed":
        logger.error(f"Tenant {tenant.name} reconnect failed: {params.get('error')}")
    elif event_type == "connecting":
        logger.info(f"Tenant {tenant.name} connecting to WhatsApp...")
        asyncio.create_task(tenant_manager.update_session_state(tenant, "connecting"))
    elif event_type == "message":
        logger.debug(
            f"Message received for tenant {tenant.name}: from={params.get('from')}"
        )

    if event_type == "message":
        msg = StoredMessage(
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
        logger.debug(
            f"Sending webhook for event {event_type} to {len(tenant.webhook_urls)} URLs"
        )
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
    lifespan=lifespan,
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
    logger.debug(
        f"WebSocket connection attempt: api_key={api_key[:20] if api_key else 'none'}..."
    )
    if not api_key:
        logger.warning("WebSocket rejected: no API key")
        await websocket.close(code=1008, reason="API key required")
        return

    tenant = tenant_manager.get_tenant_by_key(api_key)
    if not tenant:
        logger.warning("WebSocket rejected: invalid API key")
        await websocket.close(code=1008, reason="Invalid API key")
        return

    logger.info(f"WebSocket connected for tenant: {tenant.name}")
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
        logger.info(f"WebSocket disconnected for tenant: {tenant.name}")
        manager.disconnect(tenant.api_key_hash, websocket)
    except Exception as e:
        logger.debug(f"WebSocket error for tenant {tenant.name}: {e}")
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
