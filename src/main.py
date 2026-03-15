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


def create_task_with_logging(coro, name: str = "unnamed") -> asyncio.Task:
    """Create an asyncio task with exception logging."""
    task = asyncio.create_task(coro)

    def _handle_task_exception(t: asyncio.Task) -> None:
        try:
            if t.cancelled():
                return
            exc = t.exception()
            if exc:
                logger.error(
                    f"Background task '{name}' failed: {exc}",
                    exc_info=exc,
                    extra={"task_name": name},
                )
        except asyncio.CancelledError:
            pass
        except asyncio.InvalidStateError:
            pass

    task.add_done_callback(_handle_task_exception)
    return task


async def _restart_bridge(tenant, reason: str = "restart") -> bool:
    if not tenant.has_valid_auth():
        logger.warning(
            f"No valid auth for {tenant.name}, cannot restart",
            extra={"tenant": tenant.name},
        )
        return False

    if not tenant_manager.can_restart(tenant):
        logger.error(
            f"Cannot restart bridge for {tenant.name} - rate limit exceeded",
            extra={"tenant": tenant.name},
        )
        return False

    if tenant.bridge:
        try:
            await tenant.bridge.stop()
        except Exception as e:
            logger.warning(f"Error stopping bridge for {tenant.name}: {e}")

    try:
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
        tenant_manager.record_restart(tenant, reason)
        tenant_manager.reset_health_failures(tenant)

        logger.info(
            f"Bridge restarted successfully for {tenant.name}",
            extra={
                "tenant": tenant.name,
                "new_pid": new_bridge._process.pid if new_bridge._process else None,
            },
        )
        return True

    except Exception as e:
        logger.error(
            f"Failed to restart bridge for {tenant.name}: {e}",
            extra={"tenant": tenant.name},
            exc_info=True,
        )
        return False


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

    success = await _restart_bridge(tenant, "process_crash")
    if not success:
        await tenant_manager.update_session_state(tenant, "disconnected")


async def trigger_bridge_reconnect(tenant):
    logger.info(
        f"Triggering bridge reconnection for {tenant.name}",
        extra={"tenant": tenant.name},
    )
    await _restart_bridge(tenant, "disconnect_reconnect")


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


async def handle_history_sync(tenant: "Tenant", chats_data: dict[str, Any]):
    """Sync chat history from WhatsApp to database"""
    from .utils.history import store_chat_messages

    if not tenant_manager._db:
        logger.debug(f"No database available for history sync: tenant={tenant.name}")
        return

    if not tenant.message_store:
        logger.warning(f"No message store for tenant {tenant.name}")
        return

    chats = chats_data.get("chats", [])
    total_messages = chats_data.get("total_messages", 0)

    logger.info(
        f"Starting history sync for tenant {tenant.name}: {len(chats)} chats, {total_messages} messages"
    )

    stats = await store_chat_messages(tenant, chats_data, tenant_manager._db)

    logger.info(
        f"History sync complete for tenant {tenant.name}: "
        f"stored={stats['stored']}, duplicates={stats['duplicates']}, errors={stats['errors']}",
        extra={
            "tenant": tenant.name,
            **stats,
        },
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
                f"Processing Chatwoot sent message for tenant {tenant.name}: to={params.get('to')}, text={params.get('text', '')[:50]}"
            )
            result = await integration.handle_message(params, is_outgoing=True)
            logger.info(f"Chatwoot sent message result: {result}")
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


def _handle_qr_event(
    event_type: str, tenant: "Tenant", tenant_id: str, params: dict[str, Any]
) -> None:
    logger.info(f"QR code generated for tenant {tenant.name}")
    create_task_with_logging(
        admin_ws_manager.broadcast(
            "qr_generated",
            {
                "tenant_hash": tenant_id,
                "tenant_name": tenant.name,
                "qr": params.get("qr"),
                "qr_data_url": params.get("qr_data_url"),
            },
        ),
        name="broadcast_qr",
    )
    config = getattr(tenant, "chatwoot_config", None)
    if config and config.get("enabled"):
        create_task_with_logging(
            handle_chatwoot_event(tenant, "qr", params), name="chatwoot_qr"
        )


def _handle_connected_event(
    event_type: str, tenant: "Tenant", tenant_id: str, params: dict[str, Any]
) -> None:
    logger.info(
        f"Tenant {tenant.name} connected: jid={params.get('jid')}, phone={params.get('phone')}"
    )
    create_task_with_logging(
        tenant_manager.update_session_state(
            tenant,
            "connected",
            self_jid=params.get("jid"),
            self_phone=params.get("phone"),
            self_name=params.get("name"),
            has_auth=True,
        ),
        name="update_session_connected",
    )


def _handle_disconnected_event(
    event_type: str, tenant: "Tenant", tenant_id: str, params: dict[str, Any]
) -> None:
    reason = params.get("reason")
    reason_name = params.get("reason_name", "unknown")
    error = params.get("error", "")
    should_reconnect = params.get("should_reconnect", True)

    logger.warning(
        f"Tenant {tenant.name} disconnected: reason={reason} ({reason_name}), "
        f"error={error}, should_reconnect={should_reconnect}"
    )

    if reason_name == "loggedOut":
        create_task_with_logging(
            tenant_manager.update_session_state(tenant, "disconnected", has_auth=False),
            name="update_session_disconnected",
        )
        create_task_with_logging(tenant_manager.clear_creds(tenant), name="clear_creds")
        logger.info(f"Cleared credentials for logged out tenant: {tenant.name}")
    elif reason_name == "banned":
        create_task_with_logging(
            tenant_manager.update_session_state(tenant, "disconnected"),
            name="update_session_banned",
        )
        logger.error(f"Tenant {tenant.name} is banned from WhatsApp")
    else:
        create_task_with_logging(
            tenant_manager.update_session_state(tenant, "disconnected"),
            name="update_session_disconnected",
        )
        if should_reconnect:
            logger.info(f"Scheduling reconnection for tenant {tenant.name}")
            create_task_with_logging(
                trigger_bridge_reconnect(tenant), name="trigger_reconnect"
            )


def _handle_state_event(
    event_type: str, tenant: "Tenant", tenant_id: str, params: dict[str, Any]
) -> None:
    if event_type == "reconnecting":
        logger.info(f"Tenant {tenant.name} reconnecting: reason={params.get('reason')}")
    elif event_type == "reconnect_failed":
        logger.error(f"Tenant {tenant.name} reconnect failed: {params.get('error')}")
        return
    elif event_type == "connecting":
        logger.info(f"Tenant {tenant.name} connecting to WhatsApp...")

    create_task_with_logging(
        tenant_manager.update_session_state(tenant, "connecting"),
        name=f"update_session_{event_type}",
    )


def _handle_auth_update_event(
    event_type: str, tenant: "Tenant", tenant_id: str, params: dict[str, Any]
) -> None:
    if params:
        create_task_with_logging(
            tenant_manager.save_auth_state(tenant, params),
            name="save_auth_state",
        )


def _handle_sync_event(
    event_type: str, tenant: "Tenant", tenant_id: str, params: dict[str, Any]
) -> None:
    if event_type == "contacts":
        logger.info(
            f"Received contacts for tenant {tenant.name}: count={len(params.get('contacts', []))}"
        )
        create_task_with_logging(
            handle_contacts_sync(tenant, params.get("contacts", [])),
            name="contacts_sync",
        )
    elif event_type == "chats_history":
        logger.info(
            f"Received chat history for tenant {tenant.name}: chats={len(params.get('chats', []))}, messages={params.get('total_messages', 0)}"
        )
        create_task_with_logging(
            handle_history_sync(tenant, params), name="history_sync"
        )


def _handle_message_log_event(
    event_type: str, tenant: "Tenant", tenant_id: str, params: dict[str, Any]
) -> None:
    if event_type == "message":
        logger.debug(
            f"Message received for tenant {tenant.name}: from={params.get('from')}"
        )
    elif event_type == "sent":
        logger.debug(
            f"Message sent by tenant {tenant.name}: to={params.get('to')}, params={params}"
        )


def _handle_chatwoot_message_event(
    event_type: str, tenant: "Tenant", tenant_id: str, params: dict[str, Any]
) -> None:
    chatwoot_config = getattr(tenant, "chatwoot_config", None)
    if not chatwoot_config or not chatwoot_config.get("enabled"):
        return

    if event_type == "message_deleted":
        logger.info(
            f"Message deleted for tenant {tenant.name}: message_id={params.get('message_id')}"
        )
    elif event_type == "message_read":
        logger.debug(
            f"Messages marked as read for tenant {tenant.name}: chat={params.get('chat_jid')}"
        )

    create_task_with_logging(
        handle_chatwoot_event(tenant, event_type, params),
        name=f"chatwoot_{event_type}",
    )


def _store_message(event_type: str, tenant: "Tenant", params: dict[str, Any]) -> None:
    if tenant.message_store is None:
        logger.warning(f"Message store not initialized for tenant {tenant.name}")
        return

    if event_type == "sent":
        from_jid = tenant.self_jid or params.get("from", "")
        chat_jid = params.get("to", "")
        is_outbound = True
    else:
        from_jid = params.get("from", "")
        chat_jid = params.get("chat_jid") or params.get("from", "")
        is_outbound = tenant.self_jid and from_jid == tenant.self_jid
    direction = "outbound" if is_outbound else "inbound"

    msg = StoredMessage(
        id=params.get("id") or params.get("message_id", ""),
        from_jid=from_jid or "",
        chat_jid=chat_jid,
        is_group=params.get("is_group", False),
        push_name=params.get("push_name"),
        text=params.get("text", ""),
        msg_type=params.get("type", "text"),
        timestamp=params.get("timestamp", 0),
        direction=direction,
        media_url=params.get("media_url"),
    )
    if hasattr(tenant.message_store, "add_with_persist"):
        create_task_with_logging(
            tenant.message_store.add_with_persist(msg), name="store_message"
        )
    else:
        tenant.message_store.add(msg)


def _broadcast_to_websockets(
    event_type: str, tenant: "Tenant", tenant_id: str, params: dict[str, Any]
) -> None:
    create_task_with_logging(
        manager.broadcast(tenant_id, event_type, params), name="broadcast_event"
    )

    if event_type in ["connected", "disconnected", "connecting", "reconnecting"]:
        create_task_with_logging(
            admin_ws_manager.broadcast(
                "tenant_state_changed",
                {
                    "tenant_hash": tenant_id,
                    "tenant_name": tenant.name,
                    "event": event_type,
                    "params": params,
                },
            ),
            name="admin_broadcast_state",
        )
    elif event_type in ["message", "sent"]:
        create_task_with_logging(
            admin_ws_manager.broadcast(
                "new_message",
                {
                    "tenant_hash": tenant_id,
                    "tenant_name": tenant.name,
                    "message": params,
                },
            ),
            name="admin_broadcast_message",
        )


def _send_webhook(event_type: str, tenant: "Tenant", params: dict[str, Any]) -> None:
    if not tenant.webhook_urls:
        return

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
    create_task_with_logging(sender.send(event_type, params), name="webhook_send")


def _handle_chatwoot_integration(
    event_type: str, tenant: "Tenant", params: dict[str, Any]
) -> None:
    chatwoot_config = getattr(tenant, "chatwoot_config", None)
    if not chatwoot_config or not chatwoot_config.get("enabled"):
        return

    if event_type in [
        "message",
        "sent",
        "connected",
        "disconnected",
        "status_instance",
    ]:
        create_task_with_logging(
            handle_chatwoot_event(tenant, event_type, params),
            name="chatwoot_event",
        )


EVENT_HANDLERS = {
    "qr": _handle_qr_event,
    "connected": _handle_connected_event,
    "disconnected": _handle_disconnected_event,
    "reconnecting": _handle_state_event,
    "reconnect_failed": _handle_state_event,
    "connecting": _handle_state_event,
    "auth.update": _handle_auth_update_event,
    "contacts": _handle_sync_event,
    "chats_history": _handle_sync_event,
    "message": _handle_message_log_event,
    "sent": _handle_message_log_event,
    "message_deleted": _handle_chatwoot_message_event,
    "message_read": _handle_chatwoot_message_event,
}


def handle_bridge_event(
    event_type: str, params: dict[str, Any], tenant_id: Optional[str] = None
):
    logger.debug(
        f"Bridge event received: type={event_type}, tenant={tenant_id[:16] if tenant_id else 'none'}..."
    )

    if not tenant_id:
        logger.debug("Event has no tenant_id, ignoring")
        return

    tenant = tenant_manager.get_tenant_by_hash(tenant_id)

    if not tenant:
        logger.debug(f"Tenant not found for event: {tenant_id[:16]}...")
        return

    logger.info(f"Bridge event for tenant {tenant.name}: type={event_type}")

    handler = EVENT_HANDLERS.get(event_type)
    if handler:
        handler(event_type, tenant, tenant_id, params)
    else:
        logger.debug(f"Unknown event type arrived: {event_type} with params: {params}")

    if event_type in ["message", "sent"]:
        _store_message(event_type, tenant, params)

    _broadcast_to_websockets(event_type, tenant, tenant_id, params)
    _send_webhook(event_type, tenant, params)
    _handle_chatwoot_integration(event_type, tenant, params)


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
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "X-API-Key", "Cookie"],
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
