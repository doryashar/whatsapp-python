from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional
from enum import Enum


class MessageType(str, Enum):
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    DOCUMENT = "document"
    STICKER = "sticker"
    LOCATION = "location"
    CONTACT = "contact"
    EMPTY = "empty"
    UNKNOWN = "unknown"


class ConnectionState(str, Enum):
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    PENDING_QR = "pending_qr"


class SelfInfo(BaseModel):
    jid: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None


class InboundMessage(BaseModel):
    id: str
    from_jid: str = Field(..., alias="from")
    chat_jid: str
    is_group: bool = False
    push_name: Optional[str] = None
    text: str
    type: MessageType = MessageType.TEXT
    timestamp: int

    model_config = {"populate_by_name": True}


class SendMessageRequest(BaseModel):
    to: str
    text: str
    media_url: Optional[str] = None


class SendMessageResponse(BaseModel):
    message_id: str
    to: str


class SendReactionRequest(BaseModel):
    chat: str
    message_id: str
    emoji: str


class SendReactionResponse(BaseModel):
    status: str
    chat: str
    message_id: str
    emoji: str


class LoginResponse(BaseModel):
    status: str
    qr: Optional[str] = None
    qr_data_url: Optional[str] = None
    connection_state: Optional[str] = None
    jid: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None


class StatusResponse(BaseModel):
    connection_state: str
    self_info: Optional[SelfInfo] = None
    has_qr: bool = False


class LogoutResponse(BaseModel):
    status: str


class MessageListResponse(BaseModel):
    messages: list[InboundMessage]
    total: int
    limit: int
    offset: int


class AddWebhookRequest(BaseModel):
    url: str


class WebhookListResponse(BaseModel):
    urls: list[str]


class WebhookOperationResponse(BaseModel):
    status: str
    url: Optional[str] = None
