import secrets
import hashlib
import asyncio
import json
import shutil
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime, timedelta, UTC

from ..config import settings
from ..telemetry import get_logger
from ..bridge.client import BaileysBridge
from ..store.messages import MessageStore
from ..store.database import Database

logger = get_logger("whatsapp.tenant")


@dataclass
class Tenant:
    api_key_hash: str
    name: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    bridge: Optional[BaileysBridge] = None
    message_store: Optional[MessageStore] = None
    webhook_urls: list[str] = field(default_factory=list)
    _raw_api_key: Optional[str] = None
    connection_state: str = "disconnected"
    self_jid: Optional[str] = None
    self_phone: Optional[str] = None
    self_name: Optional[str] = None
    last_connected_at: Optional[datetime] = None
    last_disconnected_at: Optional[datetime] = None
    has_auth: bool = False
    creds_json: Optional[dict] = None
    chatwoot_config: Optional[dict] = None
    health_check_failures: int = 0
    last_health_check: Optional[datetime] = None
    last_successful_health_check: Optional[datetime] = None
    total_restarts: int = 0
    last_restart_at: Optional[datetime] = None
    last_restart_reason: Optional[str] = None
    enabled: bool = True
    settings: Optional[dict] = None
    _restarting: bool = False
    _restart_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)

    def get_auto_mark_read(self) -> bool:
        return self.settings is None or self.settings.get("auto_mark_read", True)

    def __post_init__(self):
        if self.message_store is None:
            self.message_store = MessageStore(max_messages=settings.max_messages)

    def get_auth_dir(self, base_dir: Path) -> Path:
        auth_dir = (
            base_dir / hashlib.sha256(self.api_key_hash.encode()).hexdigest()[:16]
        )
        auth_dir.mkdir(parents=True, exist_ok=True)
        return auth_dir

    def has_valid_auth(self) -> bool:
        return self.has_auth or self.creds_json is not None


class TenantManager:
    RESTART_HISTORY_CLEANUP_INTERVAL = 3600

    def __init__(
        self, base_auth_dir: Optional[Path] = None, database: Optional[Database] = None
    ):
        self._tenants: dict[str, Tenant] = {}
        self._base_auth_dir = base_auth_dir or settings.auth_dir
        self._base_auth_dir.mkdir(parents=True, exist_ok=True)
        self._event_handler: Optional[
            Callable[[str, dict[str, Any], Optional[str]], None]
        ] = None
        self._db = database
        self._initialized = False
        self._restart_history: dict[str, list[datetime]] = {}
        self._last_cleanup: datetime = datetime.now(UTC)
        logger.debug("TenantManager initialized")

    def set_database(self, database: Database) -> None:
        logger.debug("Setting database for TenantManager")
        self._db = database

    async def initialize(self) -> None:
        if self._initialized or not self._db:
            logger.debug(
                f"TenantManager initialize skipped: initialized={self._initialized}, has_db={self._db is not None}"
            )
            return

        logger.info("Initializing TenantManager from database")
        await self._db.connect()
        tenants_data = await self._db.load_tenants()

        for data in tenants_data:
            tenant = Tenant(
                api_key_hash=data["api_key_hash"],
                name=data["name"],
                created_at=data["created_at"],
                message_store=MessageStore(
                    max_messages=settings.max_messages,
                    tenant_hash=data["api_key_hash"],
                    db=self._db,
                ),
                webhook_urls=data.get("webhook_urls", []),
                connection_state=data.get("connection_state", "disconnected"),
                self_jid=data.get("self_jid"),
                self_phone=data.get("self_phone"),
                self_name=data.get("self_name"),
                last_connected_at=data.get("last_connected_at"),
                last_disconnected_at=data.get("last_disconnected_at"),
                has_auth=data.get("has_auth", False),
                creds_json=data.get("creds_json"),
                chatwoot_config=data.get("chatwoot_config"),
                enabled=data.get("enabled", True),
                settings=data.get("settings"),
            )
            self._tenants[tenant.api_key_hash] = tenant
            logger.debug(
                f"Loaded tenant: {tenant.name}, has_auth={tenant.has_auth}, has_creds={tenant.creds_json is not None}"
            )

        self._initialized = True
        logger.info(f"TenantManager initialized with {len(self._tenants)} tenants")

    def _restore_auth_to_filesystem(self, tenant: Tenant) -> bool:
        if not tenant.creds_json:
            return False

        auth_dir = tenant.get_auth_dir(self._base_auth_dir)
        auth_data = tenant.creds_json

        try:
            if "creds" in auth_data:
                creds_file = auth_dir / "creds.json"
                with open(creds_file, "w") as f:
                    json.dump(auth_data["creds"], f)
                logger.debug(f"Restored creds.json for tenant: {tenant.name}")
            elif isinstance(auth_data, dict) and "noiseKey" in auth_data:
                creds_file = auth_dir / "creds.json"
                with open(creds_file, "w") as f:
                    json.dump(auth_data, f)
                logger.debug(f"Restored legacy creds.json for tenant: {tenant.name}")

            if "keys" in auth_data and isinstance(auth_data["keys"], dict):
                keys_dir = auth_dir / "keys"
                keys_dir.mkdir(parents=True, exist_ok=True)
                for filename, content in auth_data["keys"].items():
                    key_file = keys_dir / filename
                    if isinstance(content, bytes):
                        with open(key_file, "wb") as f:
                            f.write(content)
                    else:
                        with open(key_file, "w") as f:
                            f.write(content)
                logger.debug(
                    f"Restored {len(auth_data['keys'])} key files for tenant: {tenant.name}"
                )

            logger.info(f"Restored auth state to filesystem for tenant: {tenant.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore auth state for {tenant.name}: {e}")
            return False

    async def restore_sessions(self) -> None:
        logger.info(
            "Restoring WhatsApp sessions for tenants with stored credentials..."
        )
        restored = 0
        for tenant in self._tenants.values():
            if tenant.creds_json:
                logger.info(f"Restoring session for tenant: {tenant.name}")
                self._restore_auth_to_filesystem(tenant)
                try:
                    bridge = await self.get_or_create_bridge(tenant)
                    result = await bridge.login()
                    status = result.get("status", "unknown")
                    if status in ("already_connected", "connected"):
                        restored += 1
                        logger.info(f"Session restored for tenant: {tenant.name}")
                    elif status == "qr_ready":
                        logger.info(f"Tenant {tenant.name} needs QR scan")
                except Exception as e:
                    logger.error(f"Failed to restore session for {tenant.name}: {e}")
            else:
                logger.debug(f"No stored credentials for tenant: {tenant.name}")

        logger.info(f"Session restoration complete: {restored} sessions restored")

    async def save_auth_state(self, tenant: Tenant, auth_data: dict) -> None:
        tenant.creds_json = auth_data
        tenant.has_auth = True
        if self._db:
            await self._db.save_creds(tenant.api_key_hash, auth_data)
            key_count = (
                len(auth_data.get("keys", {})) if isinstance(auth_data, dict) else 0
            )
            logger.info(
                f"Auth state saved to database for tenant: {tenant.name} (keys: {key_count})"
            )

    async def clear_creds(self, tenant: Tenant) -> None:
        tenant.creds_json = None
        tenant.has_auth = False

        auth_dir = tenant.get_auth_dir(self._base_auth_dir)
        if auth_dir.exists():
            try:
                shutil.rmtree(auth_dir)
                logger.info(f"Auth directory deleted for tenant: {tenant.name}")
            except Exception as e:
                logger.error(f"Failed to delete auth directory for {tenant.name}: {e}")

        if self._db:
            await self._db.clear_creds(tenant.api_key_hash)
            logger.info(f"Credentials cleared from database for tenant: {tenant.name}")

    async def close(self) -> None:
        if self._db:
            logger.debug("Closing TenantManager database connection")
            await self._db.close()

    def on_event(
        self, handler: Callable[[str, dict[str, Any], Optional[str]], None]
    ) -> None:
        logger.debug("Registering event handler")
        self._event_handler = handler

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()

    async def create_tenant(self, name: str) -> tuple[Tenant, str]:
        logger.info(f"Creating tenant: {name}")
        raw_key = f"wa_{secrets.token_urlsafe(32)}"
        key_hash = self.hash_api_key(raw_key)

        tenant = Tenant(
            api_key_hash=key_hash,
            name=name,
            message_store=MessageStore(
                max_messages=settings.max_messages,
                tenant_hash=key_hash,
                db=self._db,
            ),
        )
        tenant._raw_api_key = raw_key

        if self._db:
            await self._db.save_tenant(
                tenant.api_key_hash,
                tenant.name,
                tenant.created_at,
                tenant.webhook_urls,
            )

        self._tenants[key_hash] = tenant

        logger.info(
            f"Tenant created: {name}, api_key_hash={tenant.api_key_hash[:16]}..."
        )
        return tenant, raw_key

    def get_tenant_by_key(self, api_key: str) -> Optional[Tenant]:
        key_hash = self.hash_api_key(api_key)
        tenant = self._tenants.get(key_hash)
        logger.debug(f"Lookup tenant by key: found={tenant is not None}")
        return tenant

    def get_tenant_by_hash(self, api_key_hash: str) -> Optional[Tenant]:
        tenant = self._tenants.get(api_key_hash)
        logger.debug(f"Lookup tenant by hash: found={tenant is not None}")
        return tenant

    def get_tenant_by_name(self, name: str) -> Optional[Tenant]:
        for tenant in self._tenants.values():
            if tenant.name == name:
                logger.debug(f"Found tenant by name: {name}")
                return tenant
        logger.debug(f"Tenant not found by name: {name}")
        return None

    def list_tenants(self) -> list[Tenant]:
        logger.debug(f"Listing {len(self._tenants)} tenants")
        return list(self._tenants.values())

    async def delete_tenant(self, api_key: str) -> bool:
        key_hash = self.hash_api_key(api_key)
        return await self.delete_tenant_by_hash(key_hash)

    async def delete_tenant_by_hash(self, key_hash: str) -> bool:
        tenant = self._tenants.get(key_hash)
        if tenant:
            logger.info(f"Deleting tenant: {tenant.name}")
            if tenant.bridge:
                await tenant.bridge.stop()
            del self._tenants[key_hash]

            if self._db:
                await self._db.delete_tenant(key_hash)

            return True
        logger.debug(f"Tenant not found for deletion")
        return False

    async def get_or_create_bridge(self, tenant: Tenant) -> BaileysBridge:
        if tenant.bridge is None:
            logger.debug(f"Creating bridge for tenant: {tenant.name}")
            if tenant.creds_json:
                self._restore_auth_to_filesystem(tenant)
            auth_dir = tenant.get_auth_dir(self._base_auth_dir)
            tenant.bridge = BaileysBridge(
                bridge_path=settings.bridge_path,
                auth_dir=auth_dir,
                tenant_id=tenant.api_key_hash,
                auto_login=settings.auto_login,
                auto_mark_read=tenant.get_auto_mark_read(),
            )
            if self._event_handler:
                tenant.bridge.on_event(self._event_handler)
            await tenant.bridge.start()
            logger.info(f"Bridge started for tenant: {tenant.name}")
        return tenant.bridge

    async def update_session_state(
        self,
        tenant: Tenant,
        connection_state: str,
        self_jid: Optional[str] = None,
        self_phone: Optional[str] = None,
        self_name: Optional[str] = None,
        has_auth: Optional[bool] = None,
    ) -> None:
        tenant.connection_state = connection_state
        if self_jid:
            tenant.self_jid = self_jid
        if self_phone:
            tenant.self_phone = self_phone
        if self_name:
            tenant.self_name = self_name
        if has_auth is not None:
            tenant.has_auth = has_auth

        if connection_state == "connected":
            tenant.last_connected_at = datetime.now(UTC)
        elif connection_state == "disconnected":
            tenant.last_disconnected_at = datetime.now(UTC)

        if self._db:
            await self._db.update_session_state(
                tenant.api_key_hash,
                connection_state,
                self_jid,
                self_phone,
                self_name,
                has_auth,
            )
            logger.debug(f"Session state persisted for tenant: {tenant.name}")

    async def add_webhook(self, tenant: Tenant, url: str) -> None:
        if url not in tenant.webhook_urls:
            logger.info(f"Adding webhook for tenant {tenant.name}: {url}")
            tenant.webhook_urls.append(url)
            if self._db:
                await self._db.update_webhooks(tenant.api_key_hash, tenant.webhook_urls)

    async def remove_webhook(self, tenant: Tenant, url: str) -> bool:
        try:
            logger.info(f"Removing webhook for tenant {tenant.name}: {url}")
            tenant.webhook_urls.remove(url)
            if self._db:
                await self._db.update_webhooks(tenant.api_key_hash, tenant.webhook_urls)
            return True
        except ValueError:
            logger.debug(f"Webhook not found: {url}")
            return False

    async def update_tenant_settings(
        self, tenant: Tenant, settings_update: dict
    ) -> tuple[bool, bool]:
        old_auto_mark_read = tenant.get_auto_mark_read()

        current_settings = tenant.settings or {}
        new_settings = {**current_settings, **settings_update}
        tenant.settings = new_settings

        if self._db:
            await self._db.save_settings(tenant.api_key_hash, new_settings)

        logger.info(f"Updated settings for tenant {tenant.name}: {settings_update}")

        new_auto_mark_read = tenant.get_auto_mark_read()
        needs_restart = (
            old_auto_mark_read != new_auto_mark_read and tenant.bridge is not None
        )

        if needs_restart:
            logger.info(
                f"Auto mark read setting changed for tenant {tenant.name}, "
                f"restarting bridge to apply changes"
            )
            try:
                if tenant.bridge:
                    await tenant.bridge.stop()
                tenant.bridge = None
                await self.get_or_create_bridge(tenant)
                logger.info(f"Bridge restarted for tenant {tenant.name}")
            except Exception as e:
                logger.error(f"Failed to restart bridge for {tenant.name}: {e}")

        return True, needs_restart

    def reset_health_failures(self, tenant: Tenant) -> None:
        tenant.health_check_failures = 0
        tenant.last_successful_health_check = datetime.now(UTC)
        logger.debug(f"Health check failures reset for tenant: {tenant.name}")

    def increment_health_failures(self, tenant: Tenant) -> int:
        tenant.health_check_failures += 1
        tenant.last_health_check = datetime.now(UTC)
        logger.warning(
            f"Health check failure incremented for {tenant.name}: "
            f"{tenant.health_check_failures}/{settings.max_health_check_failures}"
        )
        return tenant.health_check_failures

    def _cleanup_restart_history(self) -> None:
        now = datetime.now(UTC)
        if (
            now - self._last_cleanup
        ).total_seconds() < self.RESTART_HISTORY_CLEANUP_INTERVAL:
            return

        cutoff = now - timedelta(seconds=settings.restart_window_seconds)
        active_tenant_hashes = set(self._tenants.keys())

        for tenant_hash in list(self._restart_history.keys()):
            if tenant_hash not in active_tenant_hashes:
                del self._restart_history[tenant_hash]
            else:
                self._restart_history[tenant_hash] = [
                    ts for ts in self._restart_history[tenant_hash] if ts > cutoff
                ]
                if not self._restart_history[tenant_hash]:
                    del self._restart_history[tenant_hash]

        self._last_cleanup = now
        logger.debug(
            f"Restart history cleanup completed, {len(self._restart_history)} tenants tracked"
        )

    def can_restart(self, tenant: Tenant) -> bool:
        self._cleanup_restart_history()

        if not settings.auto_restart_bridge:
            logger.debug(f"Auto-restart disabled for {tenant.name}")
            return False

        history = self._restart_history.get(tenant.api_key_hash, [])
        cutoff = datetime.now(UTC) - timedelta(seconds=settings.restart_window_seconds)
        history = [ts for ts in history if ts > cutoff]
        self._restart_history[tenant.api_key_hash] = history

        if len(history) >= settings.max_restart_attempts:
            logger.warning(
                f"Restart rate limit exceeded for {tenant.name}: "
                f"{len(history)} attempts in {settings.restart_window_seconds}s"
            )
            return False

        return True

    def record_restart(self, tenant: Tenant, reason: str) -> None:
        if tenant.api_key_hash not in self._restart_history:
            self._restart_history[tenant.api_key_hash] = []
        self._restart_history[tenant.api_key_hash].append(datetime.now(UTC))
        tenant.total_restarts += 1
        tenant.last_restart_at = datetime.now(UTC)
        tenant.last_restart_reason = reason
        logger.info(
            f"Restart recorded for {tenant.name}: reason={reason}, "
            f"total_restarts={tenant.total_restarts}"
        )


tenant_manager = TenantManager()
