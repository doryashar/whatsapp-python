from typing import Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class ChatwootConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    url: str = ""
    token: str = ""
    account_id: str = ""
    inbox_id: Optional[str] = None
    inbox_name: str = "WhatsApp"
    webhook_url: Optional[str] = None
    hmac_token: Optional[str] = None

    sign_messages: bool = True
    sign_delimiter: str = "\n"
    reopen_conversation: bool = True
    conversation_pending: bool = False
    import_contacts: bool = True
    import_messages: bool = False
    days_limit_import: int = 3
    merge_brazil_contacts: bool = True

    bot_name: str = "Bot"
    bot_avatar_url: Optional[str] = None


class ChatwootContact(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    name: str = ""
    phone_number: Optional[str] = None
    identifier: Optional[str] = None
    email: Optional[str] = None
    thumbnail: Optional[str] = None
    custom_attributes: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatwootConversation(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    account_id: int
    inbox_id: int
    contact_id: int
    status: str = "open"
    uuid: Optional[str] = None
    custom_attributes: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatwootMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    content: str = ""
    message_type: str = "incoming"
    content_type: str = "text"
    private: bool = False
    sender_id: Optional[int] = None
    conversation_id: int
    account_id: int
    attachments: List[dict] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChatwootInbox(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    name: str
    channel_type: str
    account_id: int
    webhook_url: Optional[str] = None


class ChatwootWebhookPayload(BaseModel):
    model_config = ConfigDict(extra="allow")

    event: str
    account: Optional[dict] = None
    conversation: Optional[ChatwootConversation] = None
    contact: Optional[ChatwootContact] = None
    message: Optional[ChatwootMessage] = None
    inbox: Optional[ChatwootInbox] = None


class CreateContactRequest(BaseModel):
    inbox_id: int
    name: Optional[str] = None
    phone_number: Optional[str] = None
    identifier: Optional[str] = None
    email: Optional[str] = None
    custom_attributes: dict = Field(default_factory=dict)


class CreateConversationRequest(BaseModel):
    source_id: Optional[str] = None
    contact_id: int
    inbox_id: int
    status: str = "open"
    custom_attributes: dict = Field(default_factory=dict)


class CreateMessageRequest(BaseModel):
    content: str
    message_type: str = "incoming"
    private: bool = False
    content_type: str = "text"
    attachments: List[dict] = Field(default_factory=list)
