import hashlib
import hmac
import json
import re
from typing import Optional, TYPE_CHECKING

from .models import ChatwootWebhookPayload, ChatwootMessage, ChatwootConfig
from .client import ChatwootAPIError, ChatwootClient
from ..telemetry import get_logger

if TYPE_CHECKING:
    from ..tenant import Tenant
    from ..bridge.client import BaileysBridge

logger = get_logger("whatsapp.chatwoot.webhook")

BOT_PHONE = "123456"


class ChatwootWebhookHandler:
    def __init__(
        self,
        tenant: "Tenant",
        bridge: "BaileysBridge",
        config: ChatwootConfig,
        hmac_token: Optional[str] = None,
    ):
        self._tenant = tenant
        self._bridge = bridge
        self._config = config
        self._hmac_token = hmac_token
        self._chatwoot_client: Optional[ChatwootClient] = None

    def verify_signature(self, payload: bytes, signature: str) -> bool:
        if not self._hmac_token:
            return True

        expected = hmac.new(
            self._hmac_token.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()

        provided = (
            signature.replace("sha256=", "")
            if signature.startswith("sha256=")
            else signature
        )

        return hmac.compare_digest(expected, provided)

    async def handle_webhook(self, payload: dict) -> dict:
        event = payload.get("event", "")

        logger.debug(
            f"Chatwoot webhook received for tenant {self._tenant.name}: event={event}"
        )

        if event == "message_created":
            return await self._handle_message_created(payload)
        elif event == "message_updated":
            return await self._handle_message_updated(payload)
        elif event == "conversation_status_changed":
            return await self._handle_status_changed(payload)
        elif event == "conversation_created":
            return await self._handle_conversation_created(payload)
        else:
            logger.debug(f"Unhandled Chatwoot webhook event: {event}")
            return {"status": "ignored", "event": event}

    async def _handle_message_created(self, payload: dict) -> dict:
        message_data = payload.get("message", {})
        conversation_data = payload.get("conversation", {})
        meta = conversation_data.get("meta", {})
        meta_sender = meta.get("sender", {})
        contact_data = meta_sender or payload.get("contact", {})
        sender_data = message_data.get("sender", {}) or payload.get("sender", {})

        message_type = message_data.get("message_type") or payload.get(
            "message_type", "incoming"
        )

        if message_type not in ("outgoing", 1, "outgoing"):
            logger.debug(
                f"Ignoring non-outgoing message from Chatwoot (type={message_type})"
            )
            return {"status": "ignored", "reason": "not outgoing"}

        private = message_data.get("private", False) or payload.get("private", False)
        if private:
            logger.debug("Ignoring private message from Chatwoot")
            return {"status": "ignored", "reason": "private"}

        content = message_data.get("content", "") or payload.get("content", "")
        attachments = message_data.get("attachments", [])

        contact_phone = contact_data.get("phone_number", "")
        if not contact_phone:
            logger.warning("No phone number in Chatwoot webhook contact")
            return {"status": "error", "reason": "no phone number"}

        phone = self._normalize_phone(contact_phone)

        if self._is_bot_contact(phone):
            return await self._handle_bot_command(content, conversation_data)

        sender_name = (
            sender_data.get("available_name")
            or sender_data.get("name")
            or contact_data.get("name")
        )

        formatted_content = self._format_message(content, sender_name)

        try:
            if attachments:
                for attachment in attachments:
                    file_url = attachment.get("file_url", "")
                    if file_url:
                        await self._bridge.send_message(
                            to=phone,
                            text=formatted_content or "",
                            media_url=file_url,
                        )
            else:
                await self._bridge.send_message(
                    to=phone,
                    text=formatted_content,
                )

            if self._config.mark_read_on_reply:
                try:
                    await self._bridge.mark_read(to=phone, message_ids=[])
                except Exception as e:
                    logger.debug(f"Failed to mark messages as read: {e}")

            logger.info(
                f"Message sent to WhatsApp via Chatwoot webhook: "
                f"tenant={self._tenant.name}, to={phone}"
            )

            return {"status": "sent", "to": phone}

        except Exception as e:
            logger.error(f"Failed to send message from Chatwoot webhook: {e}")
            await self._create_error_private_note(conversation_data, str(e))
            return {"status": "error", "reason": str(e)}

    async def _handle_message_updated(self, payload: dict) -> dict:
        message_data = payload.get("message", {})
        content = message_data.get("content", "")

        if content:
            return {"status": "acknowledged", "reason": "content updated"}

        if not self._config.message_delete_enabled:
            return {"status": "ignored", "reason": "deletion disabled"}

        source_id = message_data.get("source_id", "")
        if source_id and source_id.startswith("WAID:"):
            wa_message_id = source_id.replace("WAID:", "")

            contact_data = payload.get("sender", {}) or payload.get("contact", {})
            contact_phone = contact_data.get("phone_number", "")
            if contact_phone:
                phone = self._normalize_phone(contact_phone)

                try:
                    await self._bridge.delete_message(
                        to=phone,
                        message_id=wa_message_id,
                        from_me=False,
                    )
                    logger.info(
                        f"Message deleted in WhatsApp via Chatwoot webhook: "
                        f"tenant={self._tenant.name}, message_id={wa_message_id}"
                    )
                    return {"status": "deleted", "message_id": wa_message_id}
                except Exception as e:
                    logger.error(f"Failed to delete message from Chatwoot webhook: {e}")
                    return {"status": "error", "reason": str(e)}

        return {"status": "acknowledged"}

    def _is_bot_contact(self, phone: str) -> bool:
        normalized = phone.replace("+", "").replace("-", "")
        return normalized == BOT_PHONE

    def _convert_markdown_formatting(self, content: str) -> str:
        def replace_bold(match):
            return "\x00BOLDSTART\x00" + match.group(1) + "\x00BOLDEND\x00"

        content = re.sub(r"\*\*([^*]+)\*\*", replace_bold, content)
        content = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"_\1_", content)
        content = content.replace("\x00BOLDSTART\x00", "*").replace(
            "\x00BOLDEND\x00", "*"
        )
        content = re.sub(r"~~([^~]+)~~", r"~\1~", content)
        content = re.sub(r"`([^`]+)`", r"```\1```", content)
        return content

    def _format_message(self, content: str, sender_name: Optional[str]) -> str:
        content = self._convert_markdown_formatting(content)

        if not sender_name or not self._config.sign_messages:
            return content

        delimiter = self._config.sign_delimiter or "\n"
        delimiter = delimiter.replace("\\n", "\n")

        return f"*{sender_name}:*{delimiter}{content}"

    async def _handle_bot_command(self, content: str, conversation_data: dict) -> dict:
        if not self._config.bot_contact_enabled:
            logger.debug("Bot contact disabled, ignoring command")
            return {"status": "ignored", "reason": "bot disabled"}

        command = content.strip().lower().replace("/", "")

        logger.info(f"Bot command received: {command}")

        response = None

        if command in ("init", "iniciar"):
            response = await self._handle_init_command(command)
        elif command.startswith("init:"):
            number = command.split(":", 1)[1].strip()
            response = await self._handle_init_command(command, number)
        elif command in ("disconnect", "desconectar"):
            response = await self._handle_disconnect_command()
        elif command == "status":
            response = await self._handle_status_command()
        elif command == "clearcache":
            response = await self._handle_clearcache_command()
        else:
            logger.debug(f"Unknown bot command: {command}")
            return {"status": "ignored", "reason": "unknown command"}

        if response:
            await self._send_bot_response(response, conversation_data)

        return {"status": "command_executed", "command": command}

    async def _handle_init_command(
        self, command: str, number: Optional[str] = None
    ) -> str:
        try:
            status = await self._bridge.get_status()
            state = status.get("connection_state", "unknown")

            if state == "connected":
                return f"Already connected to WhatsApp."

            if number:
                await self._bridge.login()
                return f"Initiating connection with number {number}..."
            else:
                await self._bridge.login()
                return (
                    "Initiating WhatsApp connection... Please scan QR code if prompted."
                )
        except Exception as e:
            logger.error(f"Init command error: {e}")
            return f"Failed to initiate connection: {str(e)}"

    async def _handle_disconnect_command(self) -> str:
        try:
            await self._bridge.logout()
            return "Disconnected from WhatsApp successfully."
        except Exception as e:
            logger.error(f"Disconnect command error: {e}")
            return f"Failed to disconnect: {str(e)}"

    async def _handle_status_command(self) -> str:
        try:
            status = await self._bridge.get_status()
            state = status.get("connection_state", "unknown")
            self_info = status.get("self", {})

            if state == "connected":
                phone = self_info.get("phone", "unknown")
                name = self_info.get("name", "unknown")
                return f"Connected to WhatsApp as {name} ({phone})"
            elif state == "pending_qr":
                return "Waiting for QR code scan..."
            elif state == "connecting":
                return "Connecting to WhatsApp..."
            else:
                return f"Disconnected from WhatsApp. Status: {state}"
        except Exception as e:
            logger.error(f"Status command error: {e}")
            return f"Failed to get status: {str(e)}"

    async def _handle_clearcache_command(self) -> str:
        try:
            if hasattr(self._tenant, "chatwoot_integration"):
                integration = getattr(self._tenant, "chatwoot_integration", None)
                if integration:
                    integration.clear_cache()
            return "Chatwoot cache cleared successfully."
        except Exception as e:
            logger.error(f"Clearcache command error: {e}")
            return f"Failed to clear cache: {str(e)}"

    async def _send_bot_response(self, message: str, conversation_data: dict) -> None:
        client = None
        try:
            if not self._chatwoot_client:
                self._chatwoot_client = ChatwootClient(self._config)

            client = self._chatwoot_client

            bot_contact = await self._chatwoot_client.find_or_create_bot_contact()
            conversation = await self._chatwoot_client.get_or_create_bot_conversation(
                bot_contact
            )

            await self._chatwoot_client.create_message(
                conversation_id=conversation.id,
                content=message,
                message_type="incoming",
            )

            logger.info(f"Bot response sent: {message[:50]}...")
        except Exception as e:
            logger.error(f"Failed to send bot response: {e}")

    async def _handle_status_changed(self, payload: dict) -> dict:
        conversation_data = payload.get("conversation", {})
        status = conversation_data.get("status", "")

        logger.debug(
            f"Chatwoot conversation status changed: "
            f"conversation_id={conversation_data.get('id')}, status={status}"
        )

        return {"status": "acknowledged"}

    async def _handle_conversation_created(self, payload: dict) -> dict:
        conversation_data = payload.get("conversation", {})

        logger.debug(
            f"Chatwoot conversation created: "
            f"conversation_id={conversation_data.get('id')}"
        )

        return {"status": "acknowledged"}

    async def _create_error_private_note(
        self, conversation_data: dict, error_message: str
    ) -> None:
        if not conversation_data:
            return

        conversation_id = conversation_data.get("id")
        if not conversation_id:
            return

        try:
            if not self._chatwoot_client:
                self._chatwoot_client = ChatwootClient(self._config)

            await self._chatwoot_client.create_message(
                conversation_id=conversation_id,
                content=f"Failed to send to WhatsApp: {error_message}",
                private=True,
            )
            logger.debug(
                f"Created error private note in conversation {conversation_id}"
            )
        except Exception as e:
            logger.warning(f"Failed to create error private note: {e}")

    def _normalize_phone(self, phone: str) -> str:
        cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
        if not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        return cleaned

    async def close(self) -> None:
        """Clean up resources."""
        if self._chatwoot_client:
            await self._chatwoot_client.close()
            self._chatwoot_client = None
