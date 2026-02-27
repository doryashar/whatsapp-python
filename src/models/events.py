from pydantic import BaseModel
from typing import Any, Optional
from enum import Enum


class EventType(str, Enum):
    READY = "ready"
    QR = "qr"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    MESSAGE = "message"
    SENT = "sent"
    ERROR = "error"


class BridgeEvent(BaseModel):
    jsonrpc: str = "2.0"
    method: str
    params: dict[str, Any]


class QREventData(BaseModel):
    qr: str
    qr_data_url: Optional[str] = None


class ConnectedEventData(BaseModel):
    jid: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None


class DisconnectedEventData(BaseModel):
    reason: Optional[int] = None
    should_reconnect: bool = False


class MessageEventData(BaseModel):
    id: str
    from_jid: str
    chat_jid: str
    is_group: bool
    push_name: Optional[str] = None
    text: str
    type: str
    timestamp: int


class SentEventData(BaseModel):
    message_id: str
    to: str
