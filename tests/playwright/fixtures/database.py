import hashlib
import secrets
from datetime import datetime
from typing import Optional

from src.store.database import Database
from src.store.messages import MessageStore, StoredMessage
from src.tenant import tenant_manager, Tenant


class DatabaseFactory:
    def __init__(self, db: Database):
        self.db = db
        self._created_tenants: list[str] = []
        self._created_messages: list[str] = []

    async def create_tenant(
        self,
        name: Optional[str] = None,
        connection_state: str = "connected",
        jid: Optional[str] = None,
        webhook_urls: Optional[list[str]] = None,
    ) -> dict:
        tenant_name = name or f"tenant_{secrets.token_hex(4)}"
        raw_key = f"wa_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        tenant = Tenant(
            api_key_hash=key_hash,
            name=tenant_name,
            message_store=MessageStore(
                max_messages=1000,
                tenant_hash=key_hash,
                db=self.db,
            ),
        )

        tenant.connection_state = connection_state
        if jid:
            tenant._jid = jid
        if webhook_urls:
            tenant.webhook_urls = webhook_urls

        tenant_manager._tenants[key_hash] = tenant

        await self.db.save_tenant(
            tenant.api_key_hash,
            tenant.name,
            tenant.created_at,
            tenant.webhook_urls,
        )

        self._created_tenants.append(key_hash)

        return {
            "tenant": tenant,
            "api_key": raw_key,
            "hash": key_hash,
            "name": tenant_name,
        }

    async def create_message(
        self,
        tenant_hash: str,
        text: Optional[str] = None,
        direction: str = "inbound",
        push_name: Optional[str] = None,
        from_jid: Optional[str] = None,
        chat_jid: Optional[str] = None,
    ) -> StoredMessage:
        msg_id = f"msg_{secrets.token_hex(8)}"
        phone = secrets.randbelow(9000000000) + 1000000000

        msg = StoredMessage(
            id=msg_id,
            from_jid=from_jid or f"{phone}@s.whatsapp.net",
            chat_jid=chat_jid or f"{phone}@s.whatsapp.net",
            is_group=False,
            push_name=push_name or f"Contact {secrets.randbelow(100)}",
            text=text or f"Test message {secrets.token_hex(4)}",
            msg_type="text",
            timestamp=int(datetime.now().timestamp() * 1000),
            direction=direction,
        )

        await self.db.save_message(tenant_hash, msg)
        self._created_messages.append(msg_id)

        return msg

    async def cleanup(self):
        for tenant_hash in self._created_tenants:
            if tenant_hash in tenant_manager._tenants:
                del tenant_manager._tenants[tenant_hash]
            try:
                await self.db.delete_tenant(tenant_hash)
            except Exception:
                pass
        self._created_tenants.clear()
        self._created_messages.clear()


async def create_preseeded_database() -> tuple[Database, DatabaseFactory, dict]:
    db = Database(":memory:")
    await db.init()

    factory = DatabaseFactory(db)

    tenant_data = await factory.create_tenant(
        name="Alice Business",
        connection_state="connected",
        jid="1111111111@s.whatsapp.net",
        webhook_urls=["https://webhook.example.com/hook"],
    )

    messages = []
    for i in range(5):
        msg = await factory.create_message(
            tenant_hash=tenant_data["hash"],
            text=f"Test message {i}",
            direction="inbound" if i % 2 == 0 else "outbound",
            push_name=f"Contact {i}",
        )
        messages.append(msg)

    tenant_data["messages"] = messages

    return db, factory, tenant_data
