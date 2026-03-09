from __future__ import annotations

from collections import deque
from typing import Optional, TYPE_CHECKING

from ..config import settings

if TYPE_CHECKING:
    from .database import Database


class StoredMessage:
    def __init__(
        self,
        id: str,
        from_jid: str,
        chat_jid: str,
        is_group: bool = False,
        push_name: Optional[str] = None,
        text: str = "",
        msg_type: str = "text",
        timestamp: int = 0,
        direction: str = "inbound",
        media_url: Optional[str] = None,
        db_id: Optional[int] = None,
    ):
        self.id = id
        self.from_jid = from_jid
        self.chat_jid = chat_jid
        self.is_group = is_group
        self.push_name = push_name
        self.text = text
        self.type = msg_type
        self.timestamp = timestamp
        self.direction = direction
        self.media_url = media_url
        self.db_id = db_id

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from_jid": self.from_jid,
            "chat_jid": self.chat_jid,
            "is_group": self.is_group,
            "push_name": self.push_name,
            "text": self.text,
            "type": self.type,
            "timestamp": self.timestamp,
            "direction": self.direction,
            "media_url": self.media_url,
            "db_id": self.db_id,
        }


class MessageStore:
    def __init__(
        self,
        max_messages: int = 1000,
        tenant_hash: Optional[str] = None,
        db: Optional["Database"] = None,
    ):
        self.max_messages = max_messages
        self.tenant_hash = tenant_hash
        self.db = db
        self._messages: deque[StoredMessage] = deque(maxlen=max_messages)

    def add(self, msg: StoredMessage) -> None:
        self._messages.append(msg)

    async def add_with_persist(self, msg: StoredMessage) -> Optional[int]:
        from ..telemetry import get_logger

        logger = get_logger("whatsapp.messages")

        self._messages.append(msg)
        if self.db and self.tenant_hash:
            try:
                db_id = await self.db.save_message(
                    tenant_hash=self.tenant_hash,
                    message_id=msg.id,
                    from_jid=msg.from_jid,
                    chat_jid=msg.chat_jid,
                    is_group=msg.is_group,
                    push_name=msg.push_name,
                    text=msg.text,
                    msg_type=msg.type,
                    timestamp=msg.timestamp,
                    direction=getattr(msg, "direction", "inbound"),
                    media_url=getattr(msg, "media_url", None),
                )
                msg.db_id = db_id
                logger.debug(f"Message persisted to DB with db_id={db_id}")
                return db_id
            except Exception as e:
                logger.error(f"Failed to persist message to DB: {e}", exc_info=True)
        return None

    def list(self, limit: int = 100, offset: int = 0) -> tuple[list[dict], int]:
        total = len(self._messages)
        messages = list(self._messages)
        end = offset + limit
        return [m.to_dict() for m in messages[offset:end]], total

    async def list_from_db(
        self,
        limit: int = 100,
        offset: int = 0,
        chat_jid: Optional[str] = None,
        direction: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        if self.db and self.tenant_hash:
            messages, total = await self.db.list_messages(
                tenant_hash=self.tenant_hash,
                chat_jid=chat_jid,
                direction=direction,
                search=search,
                limit=limit,
                offset=offset,
            )
            return messages, total
        return self.list(limit=limit, offset=offset)

    def clear(self) -> None:
        self._messages.clear()


message_store = MessageStore(max_messages=settings.max_messages)
