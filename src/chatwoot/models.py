from typing import Optional, List, Any
from pydantic import BaseModel, Field, ConfigDict
from datetime import datetime


class ChatwootConfig(BaseModel):
    model_config = ConfigDict(extra="allow")

    enabled: bool = False
    url: str = ""
    token: str = ""
    account_id: str = ""
    inbox_id: Optional[int] = None
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

    bot_contact_enabled: bool = True
    bot_name: str = "Bot"
    bot_avatar_url: Optional[str] = None

    ignore_jids: List[str] = Field(default_factory=list)

    number: Optional[str] = None
    auto_create: bool = True
    organization: Optional[str] = None
    logo: Optional[str] = None
    message_delete_enabled: bool = True
    mark_read_on_reply: bool = True
    group_messages_enabled: bool = True


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
    contact_id: int = 0
    status: str = "open"
    uuid: Optional[str] = None
    custom_attributes: dict = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def __init__(self, **data):
        if (
            "meta" in data
            and isinstance(data["meta"], dict)
            and "sender" in data["meta"]
        ):
            sender = data["meta"]["sender"]
            if isinstance(sender, dict) and (
                "contact_id" not in data or data.get("contact_id") is None
            ):
                sender_id = sender.get("id")
                if sender_id is not None:
                    data["contact_id"] = sender_id
        super().__init__(**data)


class ChatwootMessage(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    content: str = ""
    message_type: int = 0
    content_type: str = "text"
    private: bool = False
    sender_id: Optional[int] = None
    conversation_id: int
    account_id: Optional[int] = None
    inbox_id: Optional[int] = None
    attachments: List[dict] = Field(default_factory=list)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    sender: Optional[dict] = None


class ChatwootInbox(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: int
    name: str
    channel_type: str
    account_id: Optional[int] = None
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
    source_id: Optional[str] = None
    source_reply_id: Optional[str] = None
    content_attributes: dict = Field(default_factory=dict)
