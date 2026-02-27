import secrets
import hashlib
import asyncio
from pathlib import Path
from typing import Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime

from ..config import settings
from ..bridge.client import BaileysBridge
from ..store.messages import MessageStore


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

    def get_auth_dir(self, base_dir: Path) -> Path:
        auth_dir = (
            base_dir / hashlib.sha256(self.api_key_hash.encode()).hexdigest()[:16]
        )
        auth_dir.mkdir(parents=True, exist_ok=True)
        return auth_dir


class TenantManager:
    def __init__(self, base_auth_dir: Optional[Path] = None):
        self._tenants: dict[str, Tenant] = {}
        self._base_auth_dir = base_auth_dir or settings.auth_dir
        self._base_auth_dir.mkdir(parents=True, exist_ok=True)
        self._event_handler: Optional[
            Callable[[str, dict[str, Any], Optional[str]], None]
        ] = None

    def on_event(
        self, handler: Callable[[str, dict[str, Any], Optional[str]], None]
    ) -> None:
        self._event_handler = handler

    @staticmethod
    def hash_api_key(api_key: str) -> str:
        return hashlib.sha256(api_key.encode()).hexdigest()

    def create_tenant(self, name: str) -> tuple[Tenant, str]:
        raw_key = f"wa_{secrets.token_urlsafe(32)}"
        key_hash = self.hash_api_key(raw_key)

        tenant = Tenant(
            api_key_hash=key_hash,
            name=name,
            message_store=MessageStore(max_messages=settings.max_messages),
        )
        tenant._raw_api_key = raw_key
        self._tenants[key_hash] = tenant

        return tenant, raw_key

    def get_tenant_by_key(self, api_key: str) -> Optional[Tenant]:
        key_hash = self.hash_api_key(api_key)
        return self._tenants.get(key_hash)

    def get_tenant_by_name(self, name: str) -> Optional[Tenant]:
        for tenant in self._tenants.values():
            if tenant.name == name:
                return tenant
        return None

    def list_tenants(self) -> list[Tenant]:
        return list(self._tenants.values())

    def delete_tenant(self, api_key: str) -> bool:
        key_hash = self.hash_api_key(api_key)
        tenant = self._tenants.get(key_hash)
        if tenant:
            if tenant.bridge:
                asyncio.create_task(tenant.bridge.stop())
            del self._tenants[key_hash]
            return True
        return False

    async def get_or_create_bridge(self, tenant: Tenant) -> BaileysBridge:
        if tenant.bridge is None:
            auth_dir = tenant.get_auth_dir(self._base_auth_dir)
            tenant.bridge = BaileysBridge(
                bridge_path=settings.bridge_path,
                auth_dir=auth_dir,
                tenant_id=tenant.api_key_hash,
            )
            if self._event_handler:
                tenant.bridge.on_event(self._event_handler)
            await tenant.bridge.start()
        return tenant.bridge

    def add_webhook(self, tenant: Tenant, url: str) -> None:
        if url not in tenant.webhook_urls:
            tenant.webhook_urls.append(url)

    def remove_webhook(self, tenant: Tenant, url: str) -> bool:
        try:
            tenant.webhook_urls.remove(url)
            return True
        except ValueError:
            return False


tenant_manager = TenantManager()
