import asyncio
import re
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
    from ..bridge.client import BaileysBridge

logger = get_logger("whatsapp.chatwoot.integration")


class ChatwootIntegration:
    def __init__(
        self,
        config: ChatwootConfig,
        tenant: "Tenant",
        bridge: Optional["BaileysBridge"] = None,
    ):
        self._config = config
        self._tenant = tenant
        self._bridge = bridge
        self._client = ChatwootClient(config)
        self._contact_cache: dict[str, ChatwootContact] = {}
        self._conversation_cache: dict[int, ChatwootConversation] = {}
        self._profile_picture_cache: dict[str, str] = {}

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    @property
    def config(self) -> ChatwootConfig:
        return self._config

    async def close(self):
        await self._client.close()

    async def handle_message(self, event_data: dict, is_outgoing: bool = False) -> bool:
        if not self._config.enabled:
            logger.debug("Chatwoot integration disabled, skipping message")
            return False

        try:
            from_jid = event_data.get("from", "")
            chat_jid = event_data.get("chat_jid", "")
            to_jid = event_data.get("to", "")
            text = event_data.get("text", "")
            msg_type = event_data.get("type", "text")
            push_name = event_data.get("push_name")
            is_group = event_data.get("is_group", False)
            message_id = event_data.get("id")
            is_edited = event_data.get("is_edited", False)

            logger.info(f"handle_message full data: {event_data}")

            logger.debug(
                f"handle_message: from={from_jid}, chat={chat_jid}, to={to_jid}, text={text[:50] if text else ''}, type={msg_type}, is_group={is_group}, is_outgoing={is_outgoing}"
            )

            if self._is_ignored(chat_jid):
                logger.debug(f"Skipping ignored JID: {chat_jid}")
                return False

            if msg_type == "empty":
                logger.debug(
                    f"Skipping empty/status message for tenant {self._tenant.name}"
                )
                return False

            if msg_type == "text" and (not text or text.strip() == ""):
                logger.debug(
                    f"Skipping empty text message for tenant {self._tenant.name}"
                )
                return False

            if is_group:
                if not self._config.group_messages_enabled:
                    logger.debug(
                        f"Group messages disabled, skipping for tenant {self._tenant.name}"
                    )
                    return False
                return await self._handle_group_message(event_data, is_outgoing)

            return await self._handle_direct_message(event_data, is_outgoing)

        except ChatwootAPIError as e:
            logger.error(f"Chatwoot API error handling message: {e}", exc_info=True)
            return False
        except Exception as e:
            logger.error(
                f"Unexpected error handling message for Chatwoot: {e}", exc_info=True
            )
            return False

    async def _handle_direct_message(self, event_data: dict, is_outgoing: bool) -> bool:
        from_jid = event_data.get("from", "")
        chat_jid = event_data.get("chat_jid", "")
        to_jid = event_data.get("to", "")
        text = event_data.get("text", "")
        msg_type = event_data.get("type", "text")
        push_name = event_data.get("push_name")
        message_id = event_data.get("id")
        is_edited = event_data.get("is_edited", False)

        if is_outgoing:
            phone_number = self._extract_phone(to_jid)
            if not phone_number:
                logger.debug(
                    f"Could not extract phone from 'to' jid: {to_jid}, trying chat_jid"
                )
                phone_number = self._extract_phone(chat_jid)
        else:
            phone_number = self._extract_phone(from_jid)
            if not phone_number:
                logger.debug(
                    f"Could not extract phone from 'from' jid: {from_jid}, trying chat_jid"
                )
                phone_number = self._extract_phone(chat_jid)

        if not phone_number:
            logger.warning(
                f"Could not extract phone from jid: {from_jid}, {to_jid}, or {chat_jid}"
            )
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
        logger.debug(f"Contact resolved: id={contact.id}, phone={contact.phone_number}")

        if self._bridge and chat_jid:
            await self._sync_profile_picture(contact, chat_jid)

        logger.debug(f"Getting or creating conversation for contact {contact.id}")
        conversation = await self._client.get_or_create_conversation(
            contact=contact,
            source_id=chat_jid,
        )
        logger.debug(
            f"Conversation resolved: id={conversation.id}, status={conversation.status}"
        )

        content = self._prepare_message_content(event_data, is_edited)
        attachments = None
        source_id = f"WAID:{message_id}"
        source_reply_id = None
        content_attributes = {}

        quoted_message_id = event_data.get("quoted_message_id")
        if quoted_message_id:
            source_reply_id = f"WAID:{quoted_message_id}"
            quoted_text = event_data.get("quoted_text", "")
            if quoted_text:
                content_attributes = {"in_reply_to": quoted_text[:100]}

        if (
            msg_type
            not in ("text", "location", "contact", "list", "listResponse", "viewOnce")
            and "media_url" in event_data
        ):
            attachments = await self._prepare_attachments(event_data)

        logger.debug(
            f"Creating message in conversation {conversation.id}: content={content[:50] if content else ''}"
        )
        message = await self._client.create_message(
            conversation_id=conversation.id,
            content=content or f"[{msg_type}]",
            message_type="outgoing" if is_outgoing else "incoming",
            attachments=attachments,
            source_id=source_id,
            source_reply_id=source_reply_id,
            content_attributes=content_attributes if content_attributes else None,
        )
        logger.info(
            f"Message sent to Chatwoot: tenant={self._tenant.name}, "
            f"conversation={conversation.id}, message={message.id}"
        )

        return True

    async def _handle_group_message(self, event_data: dict, is_outgoing: bool) -> bool:
        from_jid = event_data.get("from", "")
        chat_jid = event_data.get("chat_jid", "")
        to_jid = event_data.get("to", "")
        text = event_data.get("text", "")
        msg_type = event_data.get("type", "text")
        push_name = event_data.get("push_name")
        message_id = event_data.get("id")
        is_edited = event_data.get("is_edited", False)
        participant_jid = event_data.get("participant", "") or from_jid

        group_phone = self._extract_group_id(chat_jid)
        if not group_phone:
            logger.warning(f"Could not extract group ID from jid: {chat_jid}")
            return False

        group_name = event_data.get("group_name", group_phone)
        group_contact_name = f"{group_name} (GROUP)"

        logger.debug(
            f"Finding or creating group contact: phone={group_phone}, name={group_contact_name}"
        )
        group_contact = await self._client.find_or_create_contact(
            phone_number=group_phone,
            name=group_contact_name,
            identifier=chat_jid,
        )
        logger.debug(
            f"Group contact resolved: id={group_contact.id}, phone={group_contact.phone_number}"
        )

        if self._bridge and chat_jid:
            await self._sync_profile_picture(group_contact, chat_jid)

        logger.debug(f"Getting or creating conversation for group {group_contact.id}")
        conversation = await self._client.get_or_create_conversation(
            contact=group_contact,
            source_id=chat_jid,
        )
        logger.debug(
            f"Group conversation resolved: id={conversation.id}, status={conversation.status}"
        )

        content = self._prepare_message_content(event_data, is_edited)

        participant_name = (
            push_name or self._extract_phone(participant_jid) or "Unknown"
        )
        if content:
            content = f"[{participant_name}]: {content}"

        attachments = None
        source_id = f"WAID:{message_id}"
        source_reply_id = None
        content_attributes = {}

        quoted_message_id = event_data.get("quoted_message_id")
        if quoted_message_id:
            source_reply_id = f"WAID:{quoted_message_id}"
            quoted_text = event_data.get("quoted_text", "")
            if quoted_text:
                content_attributes = {"in_reply_to": quoted_text[:100]}

        if (
            msg_type
            not in ("text", "location", "contact", "list", "listResponse", "viewOnce")
            and "media_url" in event_data
        ):
            attachments = await self._prepare_attachments(event_data)

        logger.debug(
            f"Creating group message in conversation {conversation.id}: content={content[:50] if content else ''}"
        )
        message = await self._client.create_message(
            conversation_id=conversation.id,
            content=content or f"[{msg_type}]",
            message_type="outgoing" if is_outgoing else "incoming",
            attachments=attachments,
            source_id=source_id,
            source_reply_id=source_reply_id,
            content_attributes=content_attributes if content_attributes else None,
        )
        logger.info(
            f"Group message sent to Chatwoot: tenant={self._tenant.name}, "
            f"conversation={conversation.id}, message={message.id}"
        )

        return True

    def _prepare_message_content(
        self, event_data: dict, is_edited: bool = False
    ) -> Optional[str]:
        msg_type = event_data.get("type", "text")
        text = event_data.get("text", "")

        content = None

        if msg_type == "text":
            content = self._convert_wa_to_cw_markdown(text) if text else None
        elif msg_type in ("location", "liveLocation"):
            content = self._format_location_message(event_data)
        elif msg_type == "contact":
            content = self._format_contact_message(event_data)
        elif msg_type in ("list", "listResponse"):
            content = self._format_list_message(event_data)
        elif msg_type == "viewOnce":
            content = self._format_view_once_message(event_data)
        else:
            content = text if text else None

        if is_edited and content:
            edited_text = event_data.get("edited_text", content)
            content = f"Edited: {edited_text}"

        return content

    def _convert_wa_to_cw_markdown(self, content: str) -> str:
        """Convert WhatsApp markdown to Chatwoot markdown."""
        if not content:
            return content

        def replace_italic(match):
            return "\x00ITALICSTART\x00" + match.group(1) + "\x00ITALICEND\x00"

        content = re.sub(r"```([^`]+)```", r"`\1`", content)
        content = re.sub(r"(?<!~)~([^~]+)~(?!~)", r"~~\1~~", content)
        content = re.sub(r"(?<!_)_([^_]+)_(?!_)", replace_italic, content)
        content = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"**\1**", content)
        content = content.replace("\x00ITALICSTART\x00", "*").replace(
            "\x00ITALICEND\x00", "*"
        )
        return content

    def _format_location_message(self, event_data: dict) -> str:
        lat = event_data.get("latitude")
        lon = event_data.get("longitude")
        name = event_data.get("location_name", "")
        address = event_data.get("location_address", "")

        if lat and lon:
            parts = [f"Location: https://maps.google.com/?q={lat},{lon}"]
            if name:
                parts.append(f"Name: {name}")
            if address:
                parts.append(f"Address: {address}")
            return "\n".join(parts)
        return "[Location]"

    def _format_contact_message(self, event_data: dict) -> str:
        contacts = event_data.get("contacts", [])
        if not contacts:
            contact_name = event_data.get("contact_name", "")
            contact_phone = event_data.get("contact_phone", "")
            if contact_name or contact_phone:
                contacts = [
                    {
                        "name": contact_name,
                        "phones": [contact_phone] if contact_phone else [],
                    }
                ]

        if not contacts:
            return "[Contact]"

        parts = ["Contact(s):"]
        for contact in contacts:
            name = contact.get("name", "Unknown")
            phones = contact.get("phones", [])
            if phones:
                for phone in phones:
                    parts.append(f"  {name}: {phone}")
            else:
                parts.append(f"  {name}")
        return "\n".join(parts)

    def _format_list_message(self, event_data: dict) -> str:
        title = event_data.get("list_title", "")
        description = event_data.get("list_description", "")
        button_text = event_data.get("button_text", "")
        selected_id = event_data.get("selected_id", "")
        selected_text = event_data.get("selected_text", "")

        if selected_text:
            return f"Selected: {selected_text}"

        parts = []
        if title:
            parts.append(title)
        if description:
            parts.append(description)
        if button_text:
            parts.append(f"Button: {button_text}")

        return "\n".join(parts) if parts else "[List Message]"

    def _format_view_once_message(self, event_data: dict) -> str:
        media_type = event_data.get("media_type", "media")
        return f"View Once {media_type.title()} (cannot be displayed)"

    def _extract_group_id(self, jid: str) -> Optional[str]:
        if not jid:
            return None

        if "@g.us" not in jid:
            return None

        group_id = jid.split("@")[0]
        group_id = group_id.split(":")[0]

        if not group_id:
            return None

        return "+" + group_id if not group_id.startswith("+") else group_id

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

    async def handle_qr(self, event_data: dict) -> bool:
        if not self._config.enabled:
            return False

        if not self._config.bot_contact_enabled:
            return False

        try:
            qr_data_url = event_data.get("qr_data_url")
            if not qr_data_url:
                return False

            bot_contact = await self._client.find_or_create_bot_contact(
                bot_name=self._config.bot_name,
                bot_avatar_url=self._config.bot_avatar_url,
            )
            conversation = await self._client.get_or_create_bot_conversation(
                bot_contact
            )

            await self._client.create_message(
                conversation_id=conversation.id,
                content="Scan this QR code to connect your WhatsApp:",
                message_type="incoming",
                attachments=[{"file_type": "image/png", "file_url": qr_data_url}],
            )

            logger.info(
                f"QR code sent to Chatwoot bot conversation for tenant {self._tenant.name}"
            )
            return True
        except Exception as e:
            logger.error(f"Error sending QR code to Chatwoot: {e}")
            return False

    def _extract_phone(self, jid: str) -> Optional[str]:
        if not jid:
            return None

        if "@lid" in jid:
            logger.debug(f"Skipping LID address: {jid}")
            return None

        if "@g.us" in jid:
            return None

        phone = jid.split("@")[0]
        phone = phone.split(":")[0]

        if not phone.isdigit():
            return None

        if len(phone) < 10 or len(phone) > 15:
            logger.debug(f"Invalid phone number length: {phone}")
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
        self._profile_picture_cache.clear()

    def _is_ignored(self, jid: Optional[str]) -> bool:
        if not jid:
            return False
        ignore_list = self._config.ignore_jids or []
        for ignored in ignore_list:
            if jid == ignored or jid.startswith(ignored):
                return True
        return False

    async def _sync_profile_picture(self, contact: ChatwootContact, jid: str) -> None:
        if not self._bridge:
            return

        try:
            cached_url = self._profile_picture_cache.get(jid)
            if cached_url:
                return

            result = await self._bridge.get_profile_picture(jid)
            profile_url = result.get("url")

            if not profile_url:
                return

            self._profile_picture_cache[jid] = profile_url

            current_thumbnail = contact.thumbnail or ""
            wa_filename = profile_url.split("#")[0].split("?")[0].split("/")[-1]
            cw_filename = current_thumbnail.split("#")[0].split("?")[0].split("/")[-1]

            if wa_filename and wa_filename != cw_filename:
                logger.debug(
                    f"Updating profile picture for contact {contact.id}: {wa_filename}"
                )
                await self._client.update_contact(
                    contact_id=contact.id,
                    avatar_url=profile_url,
                )
                contact.thumbnail = profile_url
        except Exception as e:
            logger.debug(f"Failed to sync profile picture for {jid}: {e}")
