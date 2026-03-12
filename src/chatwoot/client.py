import asyncio
import time
from typing import Optional, Any, Tuple
import httpx

from .models import (
    ChatwootConfig,
    ChatwootContact,
    ChatwootConversation,
    ChatwootMessage,
    ChatwootInbox,
    CreateContactRequest,
    CreateConversationRequest,
    CreateMessageRequest,
)
from ..telemetry import get_logger

logger = get_logger("whatsapp.chatwoot.client")


class ChatwootAPIError(Exception):
    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        response: Optional[dict] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.response = response
        super().__init__(self.message)


class ChatwootClient:
    CACHE_TTL = 1800

    def __init__(self, config: ChatwootConfig, timeout: int = 30):
        self._config = config
        self._timeout = timeout
        self._base_url = config.url.rstrip("/")
        self._token = config.token
        self._account_id = config.account_id
        self._client: Optional[httpx.AsyncClient] = None
        self._conversation_cache: dict[int, Tuple[ChatwootConversation, float]] = {}

    def _get_headers(self) -> dict:
        return {
            "api_access_token": self._token,
            "Content-Type": "application/json",
        }

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        endpoint: str,
        data: Optional[dict] = None,
        params: Optional[dict] = None,
    ) -> dict:
        client = await self._ensure_client()
        url = f"{self._base_url}{endpoint}"
        headers = self._get_headers()

        logger.info(f"Chatwoot API request: {method} {url}")

        try:
            response = await client.request(
                method,
                url,
                json=data,
                params=params,
                headers=headers,
            )

            logger.info(f"Chatwoot API response: {response.status_code}")

            if response.status_code >= 400:
                try:
                    error_data = response.json()
                    error_msg = error_data.get(
                        "error", error_data.get("message", str(error_data))
                    )
                except Exception:
                    error_data = {"error": response.text}
                    error_msg = response.text[:500]

                logger.error(f"Chatwoot API error {response.status_code}: {error_msg}")
                raise ChatwootAPIError(
                    f"{error_msg}",
                    status_code=response.status_code,
                    response=error_data,
                )

            return response.json()
        except httpx.TimeoutException:
            raise ChatwootAPIError(f"Timeout calling Chatwoot API: {endpoint}")
        except httpx.ConnectError as e:
            raise ChatwootAPIError(f"Connection error to Chatwoot: {e}")

    async def find_contact_by_phone(
        self, phone_number: str
    ) -> Optional[ChatwootContact]:
        endpoint = f"/api/v1/accounts/{self._account_id}/contacts"
        params = {"search": phone_number}

        try:
            result = await self._request("GET", endpoint, params=params)
            payload = result.get("payload", result)
            contacts = (
                payload if isinstance(payload, list) else payload.get("contacts", [])
            )

            for contact_data in contacts:
                if isinstance(contact_data, dict):
                    contact_phone = contact_data.get("phone_number", "")
                    if contact_phone and self._normalize_phone(
                        contact_phone
                    ) == self._normalize_phone(phone_number):
                        return ChatwootContact(**contact_data)

            return None
        except ChatwootAPIError:
            return None

    async def find_contact_by_identifier(
        self, identifier: str
    ) -> Optional[ChatwootContact]:
        endpoint = f"/api/v1/accounts/{self._account_id}/contacts"
        params = {"search": identifier}

        try:
            result = await self._request("GET", endpoint, params=params)
            payload = result.get("payload", result)
            contacts = (
                payload if isinstance(payload, list) else payload.get("contacts", [])
            )

            for contact_data in contacts:
                if isinstance(contact_data, dict):
                    if contact_data.get("identifier") == identifier:
                        return ChatwootContact(**contact_data)

            return None
        except ChatwootAPIError:
            return None

    async def create_contact(
        self,
        phone_number: str,
        name: Optional[str] = None,
        identifier: Optional[str] = None,
        custom_attributes: Optional[dict] = None,
    ) -> ChatwootContact:
        endpoint = f"/api/v1/accounts/{self._account_id}/contacts"

        if not self._config.inbox_id:
            raise ChatwootAPIError("inbox_id not configured")

        data = {
            "inbox_id": int(self._config.inbox_id),
            "phone_number": phone_number,
        }

        if name:
            data["name"] = name
        if identifier:
            data["identifier"] = identifier
        if custom_attributes:
            data["custom_attributes"] = custom_attributes

        result = await self._request("POST", endpoint, data=data)
        payload = result.get("payload", result)
        contact_data = (
            payload.get("contact", payload) if isinstance(payload, dict) else payload
        )

        return ChatwootContact(**contact_data)

    async def update_contact(
        self,
        contact_id: int,
        name: Optional[str] = None,
        phone_number: Optional[str] = None,
        avatar_url: Optional[str] = None,
        identifier: Optional[str] = None,
        custom_attributes: Optional[dict] = None,
    ) -> ChatwootContact:
        endpoint = f"/api/v1/accounts/{self._account_id}/contacts/{contact_id}"

        data = {}
        if name:
            data["name"] = name
        if phone_number:
            data["phone_number"] = phone_number
        if avatar_url is not None:
            data["avatar_url"] = avatar_url
        if identifier is not None:
            data["identifier"] = identifier
        if custom_attributes:
            data["custom_attributes"] = custom_attributes

        result = await self._request("PATCH", endpoint, data=data)
        return ChatwootContact(**result)

    async def find_or_create_contact(
        self,
        phone_number: str,
        name: Optional[str] = None,
        identifier: Optional[str] = None,
    ) -> ChatwootContact:
        phone_normalized = self._normalize_phone(phone_number)

        contact = await self.find_contact_by_phone(phone_normalized)
        if contact:
            if name and name != contact.name and name != phone_normalized:
                try:
                    updated_contact = await self.update_contact(
                        contact_id=contact.id,
                        name=name,
                    )
                    logger.info(
                        f"Updated contact name from '{contact.name}' to '{name}' for phone {phone_normalized}"
                    )
                    return updated_contact
                except ChatwootAPIError as e:
                    logger.warning(f"Failed to update contact name: {e}")
            return contact

        if self._config.merge_brazil_contacts and phone_normalized.startswith("55"):
            alt_phone = self._try_brazil_number_variants(phone_normalized)
            if alt_phone:
                contact = await self.find_contact_by_phone(alt_phone)
                if contact:
                    if name and name != contact.name and name != phone_normalized:
                        try:
                            updated_contact = await self.update_contact(
                                contact_id=contact.id,
                                name=name,
                            )
                            logger.info(
                                f"Updated contact name from '{contact.name}' to '{name}' for phone {alt_phone}"
                            )
                            return updated_contact
                        except ChatwootAPIError as e:
                            logger.warning(f"Failed to update contact name: {e}")
                    return contact

        return await self.create_contact(
            phone_number=phone_normalized,
            name=name,
            identifier=identifier,
        )

    async def create_conversation(
        self,
        contact_id: int,
        source_id: Optional[str] = None,
    ) -> ChatwootConversation:
        if not self._config.inbox_id:
            raise ChatwootAPIError("inbox_id not configured")

        endpoint = f"/api/v1/accounts/{self._account_id}/conversations"

        data: dict[str, Any] = {
            "contact_id": contact_id,
            "inbox_id": int(self._config.inbox_id),
        }

        if source_id:
            data["source_id"] = source_id

        result = await self._request("POST", endpoint, data=data)
        return ChatwootConversation(**result)

    async def find_conversation_by_contact(
        self, contact_id: int
    ) -> Optional[ChatwootConversation]:
        endpoint = f"/api/v1/accounts/{self._account_id}/conversations"
        params = {"contact_id": contact_id, "status": "all", "assignee_type": "all"}

        try:
            result = await self._request("GET", endpoint, params=params)
            data_wrapper = result.get("data", result)
            payload = data_wrapper.get("payload", data_wrapper)
            conversations = (
                payload
                if isinstance(payload, list)
                else payload.get("conversations", [])
            )

            for conv_data in conversations:
                if isinstance(conv_data, dict):
                    status = conv_data.get("status", "")
                    if status in ("open", "pending", "resolved", "closed", "snoozed"):
                        return ChatwootConversation(**conv_data)

            return None
        except ChatwootAPIError:
            return None

    async def toggle_conversation_status(
        self, conversation_id: int, status: str
    ) -> ChatwootConversation:
        endpoint = f"/api/v1/accounts/{self._account_id}/conversations/{conversation_id}/toggle_status"
        data = {"status": status}
        result = await self._request("POST", endpoint, data=data)
        return ChatwootConversation(**result)

    async def create_message(
        self,
        conversation_id: int,
        content: str,
        message_type: str = "incoming",
        attachments: Optional[list] = None,
        source_id: Optional[str] = None,
        source_reply_id: Optional[str] = None,
        content_attributes: Optional[dict] = None,
        private: bool = False,
    ) -> ChatwootMessage:
        endpoint = f"/api/v1/accounts/{self._account_id}/conversations/{conversation_id}/messages"

        data: dict[str, Any] = {
            "content": content,
            "message_type": message_type,
            "private": private,
        }

        if attachments:
            data["attachments"] = attachments
        if source_id:
            data["source_id"] = source_id
        if source_reply_id:
            data["source_reply_id"] = source_reply_id
        if content_attributes:
            data["content_attributes"] = content_attributes

        result = await self._request("POST", endpoint, data=data)
        return ChatwootMessage(**result)

    async def get_or_create_conversation(
        self,
        contact: ChatwootContact,
        source_id: Optional[str] = None,
    ) -> ChatwootConversation:
        cached = self._get_cached_conversation(contact.id)
        if cached:
            return cached

        if self._config.reopen_conversation:
            existing = await self.find_conversation_by_contact(contact.id)
            if existing:
                if existing.status in ("resolved", "closed"):
                    await self.toggle_conversation_status(existing.id, "open")
                self._cache_conversation(contact.id, existing)
                return existing

        conv = await self.create_conversation(
            contact_id=contact.id, source_id=source_id
        )
        self._cache_conversation(contact.id, conv)
        return conv

    def _get_cached_conversation(
        self, contact_id: int
    ) -> Optional[ChatwootConversation]:
        if contact_id in self._conversation_cache:
            conv, timestamp = self._conversation_cache[contact_id]
            if time.time() - timestamp < self.CACHE_TTL:
                return conv
            else:
                del self._conversation_cache[contact_id]
        return None

    def _cache_conversation(self, contact_id: int, conv: ChatwootConversation) -> None:
        self._conversation_cache[contact_id] = (conv, time.time())

    def clear_cache(self) -> None:
        self._conversation_cache.clear()

    async def create_inbox(self, name: str, webhook_url: str) -> ChatwootInbox:
        endpoint = f"/api/v1/accounts/{self._account_id}/inboxes"

        data = {
            "name": name,
            "channel": {
                "type": "api",
                "webhook_url": webhook_url,
            },
        }

        result = await self._request("POST", endpoint, data=data)
        return ChatwootInbox(**result)

    async def list_inboxes(self) -> list[ChatwootInbox]:
        endpoint = f"/api/v1/accounts/{self._account_id}/inboxes"
        result = await self._request("GET", endpoint)
        inboxes = result if isinstance(result, list) else result.get("payload", [])
        return [ChatwootInbox(**inbox) for inbox in inboxes]

    async def verify_connection(self) -> bool:
        try:
            await self.list_inboxes()
            return True
        except ChatwootAPIError:
            return False

    async def delete_message(self, conversation_id: int, message_id: int) -> bool:
        endpoint = f"/api/v1/accounts/{self._account_id}/conversations/{conversation_id}/messages/{message_id}"

        try:
            await self._request("DELETE", endpoint)
            return True
        except ChatwootAPIError as e:
            if e.status_code == 404:
                logger.debug(f"Message {message_id} not found in Chatwoot")
                return False
            raise

    async def update_last_seen(self, conversation_id: int) -> None:
        endpoint = f"/api/v1/accounts/{self._account_id}/conversations/{conversation_id}/last_seen"

        try:
            await self._request("POST", endpoint)
        except ChatwootAPIError as e:
            logger.debug(
                f"Failed to update last seen for conversation {conversation_id}: {e}"
            )

    async def find_or_create_bot_contact(
        self,
        bot_name: Optional[str] = None,
        bot_avatar_url: Optional[str] = None,
    ) -> ChatwootContact:
        bot_phone = "+123456"
        bot_identifier = "123456"

        contact = await self.find_contact_by_phone(bot_phone)
        if contact:
            return contact

        return await self.create_contact(
            phone_number=bot_phone,
            name=bot_name or self._config.bot_name or "WhatsApp Bot",
            identifier=bot_identifier,
            custom_attributes={"is_bot": True},
        )

    async def find_bot_conversation(
        self,
        bot_contact: ChatwootContact,
    ) -> Optional[ChatwootConversation]:
        return await self.find_conversation_by_contact(bot_contact.id)

    async def create_bot_conversation(
        self,
        bot_contact: ChatwootContact,
    ) -> ChatwootConversation:
        return await self.create_conversation(
            contact_id=bot_contact.id,
        )

    async def get_or_create_bot_conversation(
        self,
        bot_contact: ChatwootContact,
    ) -> ChatwootConversation:
        existing = await self.find_bot_conversation(bot_contact)
        if existing:
            if existing.status in ("resolved", "closed"):
                await self.toggle_conversation_status(existing.id, "open")
            return existing
        return await self.create_bot_conversation(bot_contact)

    async def send_bot_message(
        self,
        conversation_id: int,
        content: str,
    ) -> ChatwootMessage:
        return await self.create_message(
            conversation_id=conversation_id,
            content=content,
            message_type="incoming",
        )

    def _normalize_phone(self, phone: str) -> str:
        cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
        if not cleaned.startswith("+") and len(cleaned) >= 10:
            cleaned = "+" + cleaned
        return cleaned

    def _try_brazil_number_variants(self, phone: str) -> Optional[str]:
        phone = phone.replace("+", "")

        if not phone.startswith("55") or len(phone) < 12:
            return None

        if len(phone) == 13 and phone[4] == "9":
            return "+" + phone[:4] + phone[5:]
        elif len(phone) == 12:
            ddd = phone[2:4]
            number = phone[4:]
            return "+55" + ddd + "9" + number

        return None
