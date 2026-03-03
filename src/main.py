import asyncio
import json
from typing import Any, Optional, TYPE_CHECKING
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from .config import settings
from .telemetry import setup_telemetry, instrument_app, get_logger
from .api import router, admin_router
from .api.chatwoot_routes import (
    router as chatwoot_router,
    webhook_router as chatwoot_webhook_router,
)
from .admin import (
    router as admin_ui_router,
    api_router as admin_api_router,
    fragments_router as admin_fragments_router,
    admin_ws_manager,
)
from .middleware import RateLimitMiddleware, rate_limiter
from .tenant import tenant_manager
from .store.database import Database
from .webhooks import WebhookSender
from .store.messages import StoredMessage
from .chatwoot import ChatwootConfig, ChatwootIntegration

if TYPE_CHECKING:
    from .tenant import Tenant

setup_telemetry(
    service_name=settings.service_name,
    service_version=settings.service_version,
    otlp_endpoint=settings.otlp_endpoint if settings.otlp_endpoint else None,
    debug=settings.debug,
)
logger = get_logger()


async def connection_health_check():
    while True:
        try:
            await asyncio.sleep(30)

            for tenant in tenant_manager.list_tenants():
                if tenant.bridge and tenant.connection_state == "connected":
                    if not tenant.bridge.is_alive():
                        logger.warning(
                            f"Bridge process died for tenant {tenant.name}, marking as disconnected"
                        )
                        await tenant_manager.update_session_state(
                            tenant, "disconnected"
                        )
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Health check error: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(
        "Starting WhatsApp API",
        extra={"service": settings.service_name, "version": settings.service_version},
    )
    db = Database(settings.database_url, settings.data_dir)
    tenant_manager.set_database(db)
    await tenant_manager.initialize()
    await tenant_manager.restore_sessions()

    health_task = asyncio.create_task(connection_health_check())

    logger.info("WhatsApp API ready")
    yield

    health_task.cancel()
    try:
        await health_task
    except asyncio.CancelledError:
        pass

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


async def handle_chatwoot_event(
    tenant: "Tenant", event_type: str, params: dict[str, Any]
):
    """Handle Chatwoot integration for events."""
    chatwoot_config = getattr(tenant, "chatwoot_config", None)
    logger.debug(
        f"Chatwoot event check: tenant={tenant.name}, enabled={chatwoot_config.get('enabled') if chatwoot_config else None}"
    )

    if not chatwoot_config or not chatwoot_config.get("enabled"):
        logger.debug(
            f"Chatwoot skipped for tenant {tenant.name}: config={chatwoot_config}"
        )
        return

    try:
        if tenant_manager._db:
            global_config = await tenant_manager._db.get_global_config("chatwoot")
            logger.debug(f"Global Chatwoot config: {global_config}")
        else:
            global_config = None

        if global_config:
            merged_config = {
                **global_config,
                **chatwoot_config,
            }
        else:
            merged_config = chatwoot_config

        logger.info(
            f"Creating ChatwootConfig with: url={merged_config.get('url')}, account_id={merged_config.get('account_id')}, inbox_id={merged_config.get('inbox_id')}"
        )

        config = ChatwootConfig(**merged_config)
        integration = ChatwootIntegration(config, tenant)

        if event_type == "message":
            logger.info(
                f"Processing Chatwoot message for tenant {tenant.name}: from={params.get('from')}, text={params.get('text', '')[:50]}"
            )
            result = await integration.handle_message(params)
            logger.info(f"Chatwoot message result: {result}")
        elif event_type == "connected":
            await integration.handle_connected(params)
        elif event_type == "disconnected":
            await integration.handle_disconnected(params)
    except Exception as e:
        logger.error(
            f"Chatwoot integration error for tenant {tenant.name}: {e}", exc_info=True
        )


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
            asyncio.create_task(tenant_manager.clear_creds(tenant))
            logger.info(f"Cleared credentials for logged out tenant: {tenant.name}")
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
    elif event_type == "auth.update":
        auth_data = params
        if auth_data:
            asyncio.create_task(tenant_manager.save_auth_state(tenant, auth_data))
    elif event_type == "message":
        logger.debug(
            f"Message received for tenant {tenant.name}: from={params.get('from')}"
        )
    else:
        logger.debug(f"Unknown event type arrived: {event_type} with params: {params}")

    if event_type == "message":
        # Determine message direction: outbound if from tenant, inbound otherwise
        from_jid = params["from"]
        is_outbound = tenant.self_jid and from_jid == tenant.self_jid
        direction = "outbound" if is_outbound else "inbound"
        
        msg = StoredMessage(
            id=params["id"],
            from_jid=from_jid,
            chat_jid=params["chat_jid"],
            is_group=params.get("is_group", False),
            push_name=params.get("push_name"),
            text=params.get("text", ""),
            msg_type=params.get("type", "text"),
            timestamp=params.get("timestamp", 0),
            direction=direction,
        )
        tenant.message_store.add(msg)
        if hasattr(tenant.message_store, "add_with_persist"):
            asyncio.create_task(tenant.message_store.add_with_persist(msg))

    asyncio.create_task(manager.broadcast(tenant_id, event_type, params))

    # Broadcast to admin dashboard
    if event_type in ["connected", "disconnected", "connecting", "reconnecting"]:
        asyncio.create_task(
            admin_ws_manager.broadcast(
                "tenant_state_changed",
                {
                    "tenant_hash": tenant_id,
                    "tenant_name": tenant.name,
                    "event": event_type,
                    "params": params,
                },
            )
        )
    elif event_type == "message":
        asyncio.create_task(
            admin_ws_manager.broadcast(
                "new_message",
                {
                    "tenant_hash": tenant_id,
                    "tenant_name": tenant.name,
                    "message": params,
                },
            )
        )

    if tenant.webhook_urls:
        logger.debug(
            f"Sending webhook for event {event_type} to {len(tenant.webhook_urls)} URLs"
        )
        sender = WebhookSender(
            urls=tenant.webhook_urls,
            secret=settings.webhook_secret,
            timeout=settings.webhook_timeout,
            max_retries=settings.webhook_retries,
            tenant_hash=tenant.api_key_hash,
            db=tenant_manager._db,
        )
        asyncio.create_task(sender.send(event_type, params))

    chatwoot_config = getattr(tenant, "chatwoot_config", None)
    if chatwoot_config and chatwoot_config.get("enabled"):
        asyncio.create_task(handle_chatwoot_event(tenant, event_type, params))


tenant_manager.on_event(handle_bridge_event)

app = FastAPI(
    title="WhatsApp API",
    description="WhatsApp Web API with FastAPI and Baileys bridge - Multi-tenant",
    version="2.0.0",
    lifespan=lifespan,
)

instrument_app(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)

app.include_router(router)
app.include_router(admin_router)
app.include_router(admin_ui_router)
app.include_router(admin_api_router)
app.include_router(admin_fragments_router)
app.include_router(chatwoot_router)
app.include_router(chatwoot_webhook_router)


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


@app.websocket("/admin/ws")
async def admin_ws_events(
    websocket: WebSocket,
    session_id: Optional[str] = Query(None),
):
    """WebSocket endpoint for admin dashboard real-time updates"""
    logger.debug(
        f"Admin WebSocket connection attempt: session={session_id[:16] if session_id else 'none'}..."
    )

    if not session_id:
        logger.warning("Admin WebSocket rejected: no session ID")
        await websocket.close(code=1008, reason="Session ID required")
        return

    # Validate session
    db = tenant_manager._db
    if not db:
        logger.warning("Admin WebSocket rejected: database not available")
        await websocket.close(code=1011, reason="Database not available")
        return

    from .admin.auth import AdminSession

    admin_session = AdminSession(db)
    session_data = await admin_session.get_session(session_id)

    if not session_data:
        logger.warning("Admin WebSocket rejected: invalid session")
        await websocket.close(code=1008, reason="Invalid session")
        return

    logger.info(f"Admin WebSocket connected: session={session_id[:16]}...")
    await admin_ws_manager.connect(websocket, session_id)

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
        logger.info(f"Admin WebSocket disconnected: session={session_id[:16]}...")
        await admin_ws_manager.disconnect(websocket)
    except Exception as e:
        logger.debug(f"Admin WebSocket error: {e}")
        await admin_ws_manager.disconnect(websocket)


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
