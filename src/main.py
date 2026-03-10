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
from .bridge.client import BaileysBridge
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


async def handle_bridge_crash(tenant):
    logger.error(
        f"Bridge process crashed for {tenant.name}",
        extra={
            "tenant": tenant.name,
            "exit_code": tenant.bridge._process.returncode
            if tenant.bridge and tenant.bridge._process
            else None,
        },
    )

    await tenant_manager.update_session_state(tenant, "connecting")

    if tenant.bridge:
        try:
            await tenant.bridge.stop()
        except Exception as e:
            logger.debug(f"Error stopping dead bridge for {tenant.name}: {e}")

    if not tenant.has_valid_auth():
        logger.warning(
            f"No valid auth for {tenant.name}, cannot auto-restart",
            extra={"tenant": tenant.name},
        )
        await tenant_manager.update_session_state(
            tenant, "disconnected", has_auth=False
        )
        return

    if not tenant_manager.can_restart(tenant):
        logger.error(
            f"Cannot restart bridge for {tenant.name} - rate limit exceeded",
            extra={"tenant": tenant.name},
        )
        await tenant_manager.update_session_state(tenant, "disconnected")
        return

    try:
        logger.info(f"Auto-restarting bridge for {tenant.name}")
        await asyncio.sleep(settings.restart_cooldown_seconds)

        auth_dir = tenant.get_auth_dir(settings.auth_dir)
        new_bridge = BaileysBridge(
            auth_dir=auth_dir,
            auto_login=True,
            tenant_id=tenant.api_key_hash,
        )

        if tenant_manager._event_handler:
            new_bridge.on_event(tenant_manager._event_handler)

        await new_bridge.start()

        tenant.bridge = new_bridge
        tenant_manager.record_restart(tenant, "process_crash")
        tenant_manager.reset_health_failures(tenant)

        logger.info(
            f"Bridge auto-restarted successfully for {tenant.name}",
            extra={
                "tenant": tenant.name,
                "new_pid": new_bridge._process.pid if new_bridge._process else None,
            },
        )

        await tenant_manager.update_session_state(tenant, "connecting")

    except Exception as e:
        logger.error(
            f"Failed to auto-restart bridge for {tenant.name}: {e}",
            extra={"tenant": tenant.name},
            exc_info=True,
        )
        await tenant_manager.update_session_state(tenant, "disconnected")


async def connection_health_check():
    while True:
        try:
            await asyncio.sleep(settings.health_check_interval_seconds)

            for tenant in tenant_manager.list_tenants():
                if not tenant.bridge or tenant.connection_state != "connected":
                    continue

                try:
                    if not tenant.bridge.is_alive():
                        logger.warning(
                            f"Bridge process died for {tenant.name}",
                            extra={"tenant": tenant.name},
                        )
                        await handle_bridge_crash(tenant)
                        continue

                    try:
                        status = await asyncio.wait_for(
                            tenant.bridge.get_status(),
                            timeout=settings.health_check_timeout_seconds,
                        )

                        if status.get("connection_state") == "connected":
                            tenant_manager.reset_health_failures(tenant)
                            logger.debug(
                                f"Health check passed for {tenant.name}",
                                extra={
                                    "tenant": tenant.name,
                                    "pid": tenant.bridge._process.pid
                                    if tenant.bridge._process
                                    else None,
                                    "whatsapp_jid": tenant.self_jid,
                                },
                            )
                        else:
                            failures = tenant_manager.increment_health_failures(tenant)
                            logger.warning(
                                f"WhatsApp reports disconnected for {tenant.name} "
                                f"({failures}/{settings.max_health_check_failures})",
                                extra={
                                    "tenant": tenant.name,
                                    "failure_count": failures,
                                    "status": status,
                                },
                            )

                            if failures >= settings.max_health_check_failures:
                                logger.error(
                                    f"Max health check failures reached for {tenant.name}, marking offline",
                                    extra={"tenant": tenant.name},
                                )
                                await tenant_manager.update_session_state(
                                    tenant, "disconnected"
                                )

                    except asyncio.TimeoutError:
                        failures = tenant_manager.increment_health_failures(tenant)
                        logger.warning(
                            f"Health check timeout for {tenant.name} "
                            f"({failures}/{settings.max_health_check_failures})",
                            extra={
                                "tenant": tenant.name,
                                "failure_count": failures,
                            },
                        )

                        if failures >= settings.max_health_check_failures:
                            logger.error(
                                f"Max health check failures reached for {tenant.name}, marking offline",
                                extra={"tenant": tenant.name},
                            )
                            await tenant_manager.update_session_state(
                                tenant, "disconnected"
                            )

                except Exception as e:
                    logger.error(
                        f"Health check error for {tenant.name}: {e}",
                        extra={"tenant": tenant.name},
                        exc_info=True,
                    )

        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Health check loop error: {e}", exc_info=True)


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


async def handle_contacts_sync(tenant: "Tenant", contacts: list[dict]):
    """Sync contacts from WhatsApp to database"""
    if not tenant_manager._db:
        logger.debug(f"No database available for contact sync: tenant={tenant.name}")
        return

    from .utils.phone import normalize_phone

    synced_count = 0
    for contact in contacts:
        try:
            phone = contact.get("phone")
            jid = contact.get("jid")
            if not phone or not jid:
                continue

            normalized_phone = normalize_phone(phone)
            if not normalized_phone:
                continue

            await tenant_manager._db.upsert_contact(
                tenant_hash=tenant.api_key_hash,
                phone=normalized_phone,
                name=contact.get("name"),
                chat_jid=jid,
                is_group=contact.get("is_group", False),
            )
            synced_count += 1
        except Exception as e:
            logger.error(
                f"Failed to sync contact for tenant {tenant.name}: {e}",
                exc_info=True,
            )

    logger.info(
        f"Synced {synced_count} contacts for tenant {tenant.name}",
        extra={"tenant": tenant.name, "count": synced_count},
    )


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

    integration = None
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
        integration = ChatwootIntegration(config, tenant, db=tenant_manager._db)

        if event_type == "message":
            logger.info(
                f"Processing Chatwoot message for tenant {tenant.name}: from={params.get('from')}, text={params.get('text', '')[:50]}"
            )
            result = await integration.handle_message(params, is_outgoing=False)
            logger.info(f"Chatwoot message result: {result}")
        elif event_type == "sent":
            logger.info(
                f"Processing Chatwoot outgoing message for tenant {tenant.name}: to={params.get('to')}, text={params.get('text', '')[:50]}"
            )
            result = await integration.handle_message(params, is_outgoing=True)
            logger.info(f"Chatwoot outgoing message result: {result}")
        elif event_type == "connected":
            await integration.handle_connected(params)
        elif event_type == "disconnected":
            await integration.handle_disconnected(params)
        elif event_type == "qr":
            await integration.handle_qr(params)
        elif event_type == "message_deleted":
            await integration.handle_message_deleted(params)
        elif event_type == "message_read":
            await integration.handle_message_read(params)
        elif event_type == "status_instance":
            await integration.handle_status_instance(params)
    except Exception as e:
        logger.error(
            f"Chatwoot integration error for tenant {tenant.name}: {e}", exc_info=True
        )
    finally:
        if integration:
            await integration.close()


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
        asyncio.create_task(
            admin_ws_manager.broadcast(
                "qr_generated",
                {
                    "tenant_hash": tenant_id,
                    "tenant_name": tenant.name,
                    "qr": params.get("qr"),
                    "qr_data_url": params.get("qr_data_url"),
                },
            )
        )
        config = getattr(tenant, "chatwoot_config", None)
        if config and config.get("enabled"):
            asyncio.create_task(handle_chatwoot_event(tenant, "qr", params))
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
    elif event_type == "contacts":
        logger.info(
            f"Received contacts for tenant {tenant.name}: count={len(params.get('contacts', []))}"
        )
        asyncio.create_task(handle_contacts_sync(tenant, params.get("contacts", [])))
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
    elif event_type == "sent":
        logger.debug(
            f"Message sent by tenant {tenant.name}: to={params.get('to')}, params={params}"
        )
    elif event_type == "message_deleted":
        logger.info(
            f"Message deleted for tenant {tenant.name}: message_id={params.get('message_id')}"
        )
        chatwoot_config = getattr(tenant, "chatwoot_config", None)
        if chatwoot_config and chatwoot_config.get("enabled"):
            asyncio.create_task(
                handle_chatwoot_event(tenant, "message_deleted", params)
            )
    elif event_type == "message_read":
        logger.debug(
            f"Messages marked as read for tenant {tenant.name}: chat={params.get('chat_jid')}"
        )
        chatwoot_config = getattr(tenant, "chatwoot_config", None)
        if chatwoot_config and chatwoot_config.get("enabled"):
            asyncio.create_task(handle_chatwoot_event(tenant, "message_read", params))
    else:
        logger.debug(f"Unknown event type arrived: {event_type} with params: {params}")

    if event_type in ["message", "sent"]:
        if tenant.message_store is None:
            logger.warning(f"Message store not initialized for tenant {tenant.name}")
            return
        # Determine message direction: outbound if from tenant or if it's a "sent" event, inbound otherwise
        from_jid = params.get("from") or params.get(
            "to", ""
        )  # sent events have "to", message events have "from"
        is_outbound = event_type == "sent" or (
            tenant.self_jid and from_jid == tenant.self_jid
        )
        direction = "outbound" if is_outbound else "inbound"

        msg = StoredMessage(
            id=params.get("id") or params.get("message_id", ""),
            from_jid=from_jid or "",
            chat_jid=params.get("chat_jid") or params.get("to", ""),
            is_group=params.get("is_group", False),
            push_name=params.get("push_name"),
            text=params.get("text", ""),
            msg_type=params.get("type", "text"),
            timestamp=params.get("timestamp", 0),
            direction=direction,
            media_url=params.get("media_url"),
        )
        if hasattr(tenant.message_store, "add_with_persist"):
            asyncio.create_task(tenant.message_store.add_with_persist(msg))
        else:
            tenant.message_store.add(msg)

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
    elif event_type in ["message", "sent"]:
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
        if event_type in [
            "message",
            "sent",
            "connected",
            "disconnected",
            "status_instance",
        ]:
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
    allow_origins=settings.cors_origins,
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
        f"WebSocket connection attempt: api_key_hash={hash(api_key) if api_key else 'none'}"
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
        f"Admin WebSocket connection attempt: session_hash={hash(session_id) if session_id else 'none'}"
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
