import asyncio
from typing import Optional, TYPE_CHECKING
from dataclasses import dataclass, field
from datetime import datetime

from .models import (
    ChatwootConfig,
    ChatwootContact,
    ChatwootConversation,
    ChatwootMessage,
)
from .client import ChatwootClient, ChatwootAPIError
from ..telemetry import get_logger

if TYPE_CHECKING:
    from ..tenant import Tenant

logger = get_logger("whatsapp.chatwoot.integration")


class ChatwootIntegration:
    def __init__(self, config: ChatwootConfig, tenant: "Tenant"):
        self._config = config
        self._tenant = tenant
        self._client = ChatwootClient(config)
        self._contact_cache: dict[str, ChatwootContact] = {}
        self._conversation_cache: dict[int, ChatwootConversation] = {}

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def config(self) -> ChatwootConfig:
        return self._config

    async def close(self):
        await self._client.close()

    async def handle_message(self, event_data: dict) -> bool:
        if not self._config.enabled:
            logger.debug("Chatwoot integration disabled, skipping message")
            return False

        try:
            from_jid = event_data.get("from", "")
            chat_jid = event_data.get("chat_jid", "")
            text = event_data.get("text", "")
            msg_type = event_data.get("type", "text")
            push_name = event_data.get("push_name")
            is_group = event_data.get("is_group", False)
            message_id = event_data.get("id")

            logger.debug(
                f"handle_message: from={from_jid}, chat={chat_jid}, text={text[:50] if text else ''}, type={msg_type}, is_group={is_group}"
            )

            if is_group:
                logger.debug(f"Skipping group message for tenant {self._tenant.name}")
                return False

            phone_number = self._extract_phone(from_jid)
            if not phone_number:
                logger.warning(f"Could not extract phone from jid: {from_jid}")
                return False

            logger.debug(f"Extracted phone: {phone_number}")

            contact_name = push_name or phone_number

            logger.debug(
                f"Finding or creating contact: phone={phone_number}, name={contact_name}"
            )
            contact = await self._client.find_or_create_contact(
                phone_number=phone_number,
                name=contact_name,
                identifier=from_jid,
            )
            logger.debug(
                f"Contact resolved: id={contact.id}, phone={contact.phone_number}"
            )

            logger.debug(f"Getting or creating conversation for contact {contact.id}")
            conversation = await self._client.get_or_create_conversation(
                contact=contact,
                source_id=chat_jid,
            )
            logger.debug(
                f"Conversation resolved: id={conversation.id}, status={conversation.status}"
            )

            content = text
            attachments = None

            if msg_type != "text" and "media_url" in event_data:
                attachments = await self._prepare_attachments(event_data)

            logger.debug(
                f"Creating message in conversation {conversation.id}: content={content[:50] if content else ''}"
            )
            message = await self._client.create_message(
                conversation_id=conversation.id,
                content=content or f"[{msg_type}]",
                message_type="incoming",
                attachments=attachments,
            )
            logger.info(
                f"Message sent to Chatwoot: tenant={self._tenant.name}, "
                f"conversation={conversation.id}, message={message.id}"
            )

            return True

        except ChatwootAPIError as e:
            logger.error(f"Chatwoot API error handling message: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error handling message for Chatwoot: {e}", exc_info=True
            )
            return False

    async def handle_connected(self, event_data: dict) -> bool:
        if not self._config.enabled:
            return False

        try:
            self_phone = event_data.get("phone")
            logger.info(
                f"Chatwoot integration connected for tenant {self._tenant.name}: phone={self_phone}"
            )
            return True
        except Exception as e:
            logger.error(f"Error handling connected event: {e}")
            return False

    async def handle_disconnected(self, event_data: dict) -> bool:
        if not self._config.enabled:
            return False

        logger.info(f"Chatwoot integration disconnected for tenant {self._tenant.name}")
        return True

    def _extract_phone(self, jid: str) -> Optional[str]:
        if not jid:
            return None

        phone = jid.split("@")[0]
        phone = phone.split(":")[0]

        if not phone.isdigit():
            return None

        return "+" + phone if not phone.startswith("+") else phone

    async def _prepare_attachments(self, event_data: dict) -> list:
        attachments = []

        media_url = event_data.get("media_url")
        media_type = event_data.get("type", "image")
        mimetype = event_data.get("mimetype", "application/octet-stream")
        filename = event_data.get("filename", "attachment")

        if media_url:
            attachments.append(
                {
                    "file_type": mimetype,
                    "file_url": media_url,
                }
            )

        return attachments

    def clear_cache(self):
        self._contact_cache.clear()
        self._conversation_cache.clear()
