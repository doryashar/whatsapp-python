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
    media_url: Optional[str] = None
    mimetype: Optional[str] = None
    filename: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    location_name: Optional[str] = None
    location_address: Optional[str] = None

    model_config = {"populate_by_name": True}


class SendMessageRequest(BaseModel):
    to: str
    text: str
    media_url: Optional[str] = None


class SendMessageResponse(BaseModel):
    message_id: Optional[str] = None
    to: Optional[str] = None


class SendReactionRequest(BaseModel):
    chat: str
    message_id: str
    emoji: str
    from_me: bool = False


class SendReactionResponse(BaseModel):
    status: Optional[str] = None
    chat: Optional[str] = None
    message_id: Optional[str] = None
    emoji: Optional[str] = None


class LoginResponse(BaseModel):
    status: Optional[str] = None
    qr: Optional[str] = None
    qr_data_url: Optional[str] = None
    connection_state: Optional[str] = None
    jid: Optional[str] = None
    phone: Optional[str] = None
    name: Optional[str] = None


class StatusResponse(BaseModel):
    connection_state: Optional[str] = None
    self_info: Optional[SelfInfo] = None
    has_qr: bool = False


class LogoutResponse(BaseModel):
    status: Optional[str] = None


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
    status: Optional[str] = None
    url: Optional[str] = None


class SendPollRequest(BaseModel):
    to: str
    name: str
    values: list[str]
    selectable_count: int = 1


class SendPollResponse(BaseModel):
    message_id: Optional[str] = None
    to: Optional[str] = None


class SendTypingResponse(BaseModel):
    status: Optional[str] = None
    to: Optional[str] = None


class AuthExistsResponse(BaseModel):
    exists: Optional[bool] = None


class AuthAgeResponse(BaseModel):
    age_ms: Optional[int] = None


class SelfIdResponse(BaseModel):
    jid: Optional[str] = None
    e164: Optional[str] = None
    name: Optional[str] = None
