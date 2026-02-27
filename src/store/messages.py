from collections import deque
from typing import Optional
from ..config import settings


class InboundMessage:
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
    ):
        self.id = id
        self.from_jid = from_jid
        self.chat_jid = chat_jid
        self.is_group = is_group
        self.push_name = push_name
        self.text = text
        self.type = msg_type
        self.timestamp = timestamp

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "from": self.from_jid,
            "chat_jid": self.chat_jid,
            "is_group": self.is_group,
            "push_name": self.push_name,
            "text": self.text,
            "type": self.type,
            "timestamp": self.timestamp,
        }


class MessageStore:
    def __init__(self, max_messages: int = 1000):
        self.max_messages = max_messages
        self._messages: deque[InboundMessage] = deque(maxlen=max_messages)

    def add(self, msg: InboundMessage) -> None:
        self._messages.append(msg)

    def list(self, limit: int = 100, offset: int = 0) -> tuple[list[dict], int]:
        total = len(self._messages)
        messages = list(self._messages)
        end = offset + limit
        return [m.to_dict() for m in messages[offset:end]], total

    def clear(self) -> None:
        self._messages.clear()


message_store = MessageStore(max_messages=settings.max_messages)
