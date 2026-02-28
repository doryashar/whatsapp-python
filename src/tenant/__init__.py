import secrets
import hashlib
import asyncio
import json
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime

from ..config import settings, logger
from ..bridge.client import BaileysBridge
from ..store.messages import MessageStore
from ..store.database import Database


@dataclass
class Tenant:
    api_key_hash: str
    name: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    bridge: Optional[BaileysBridge] = None
    message_store: MessageStore = field(
        default_factory=lambda: MessageStore(max_messages=settings.max_messages)
    )
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

    def get_auth_dir(self, base_dir: Path) -> Path:
        auth_dir = (
            base_dir / hashlib.sha256(self.api_key_hash.encode()).hexdigest()[:16]
        )
        auth_dir.mkdir(parents=True, exist_ok=True)
        return auth_dir

    def has_valid_auth(self) -> bool:
        return self.has_auth or self.creds_json is not None


class TenantManager:
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
                message_store=MessageStore(max_messages=settings.max_messages),
                webhook_urls=data.get("webhook_urls", []),
                connection_state=data.get("connection_state", "disconnected"),
                self_jid=data.get("self_jid"),
                self_phone=data.get("self_phone"),
                self_name=data.get("self_name"),
                last_connected_at=data.get("last_connected_at"),
                last_disconnected_at=data.get("last_disconnected_at"),
                has_auth=data.get("has_auth", False),
                creds_json=data.get("creds_json"),
            )
            self._tenants[tenant.api_key_hash] = tenant
            logger.debug(
                f"Loaded tenant: {tenant.name}, has_auth={tenant.has_auth}, has_creds={tenant.creds_json is not None}"
            )

        self._initialized = True
        logger.info(f"TenantManager initialized with {len(self._tenants)} tenants")

    def _restore_creds_to_filesystem(self, tenant: Tenant) -> bool:
        if not tenant.creds_json:
            return False

        auth_dir = tenant.get_auth_dir(self._base_auth_dir)
        creds_file = auth_dir / "creds.json"

        try:
            with open(creds_file, "w") as f:
                json.dump(tenant.creds_json, f)
            logger.info(f"Restored credentials to filesystem for tenant: {tenant.name}")
            return True
        except Exception as e:
            logger.error(f"Failed to restore credentials for {tenant.name}: {e}")
            return False

    async def restore_sessions(self) -> None:
        logger.info(
            "Restoring WhatsApp sessions for tenants with stored credentials..."
        )
        restored = 0
        for tenant in self._tenants.values():
            if tenant.creds_json:
                logger.info(f"Restoring session for tenant: {tenant.name}")
                self._restore_creds_to_filesystem(tenant)
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

    async def save_creds(self, tenant: Tenant, creds_json: dict) -> None:
        tenant.creds_json = creds_json
        tenant.has_auth = True
        if self._db:
            await self._db.save_creds(tenant.api_key_hash, creds_json)
            logger.info(f"Credentials saved to database for tenant: {tenant.name}")

    async def clear_creds(self, tenant: Tenant) -> None:
        tenant.creds_json = None
        tenant.has_auth = False
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
            message_store=MessageStore(max_messages=settings.max_messages),
        )
        tenant._raw_api_key = raw_key
        self._tenants[key_hash] = tenant

        if self._db:
            await self._db.save_tenant(
                tenant.api_key_hash,
                tenant.name,
                tenant.created_at,
                tenant.webhook_urls,
            )

        logger.info(f"Tenant created: {name}, api_key={raw_key[:20]}...")
        return tenant, raw_key

    def get_tenant_by_key(self, api_key: str) -> Optional[Tenant]:
        key_hash = self.hash_api_key(api_key)
        tenant = self._tenants.get(key_hash)
        logger.debug(f"Lookup tenant by key: found={tenant is not None}")
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
                self._restore_creds_to_filesystem(tenant)
            auth_dir = tenant.get_auth_dir(self._base_auth_dir)
            tenant.bridge = BaileysBridge(
                bridge_path=settings.bridge_path,
                auth_dir=auth_dir,
                tenant_id=tenant.api_key_hash,
                auto_login=True,
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
            tenant.last_connected_at = datetime.utcnow()
        elif connection_state == "disconnected":
            tenant.last_disconnected_at = datetime.utcnow()

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


tenant_manager = TenantManager()
