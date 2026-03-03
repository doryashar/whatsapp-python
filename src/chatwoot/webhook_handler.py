import hashlib
import hmac
import json
from typing import Optional, TYPE_CHECKING

from .models import ChatwootWebhookPayload, ChatwootMessage
from .client import ChatwootAPIError
from ..telemetry import get_logger

if TYPE_CHECKING:
    from ..tenant import Tenant
    from ..bridge.client import BaileysBridge

logger = get_logger("whatsapp.chatwoot.webhook")


class ChatwootWebhookHandler:
    def __init__(
        self,
        tenant: "Tenant",
        bridge: "BaileysBridge",
        hmac_token: Optional[str] = None,
    ):
        self._tenant = tenant
        self._bridge = bridge
        self._hmac_token = hmac_token

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
        contact_data = payload.get("sender", {}) or payload.get("contact", {})

        message_type = message_data.get("message_type", "outgoing")

        if message_type != "outgoing":
            logger.debug("Ignoring non-outgoing message from Chatwoot")
            return {"status": "ignored", "reason": "not outgoing"}

        private = message_data.get("private", False)
        if private:
            logger.debug("Ignoring private message from Chatwoot")
            return {"status": "ignored", "reason": "private"}

        content = message_data.get("content", "")
        attachments = message_data.get("attachments", [])

        contact_phone = contact_data.get("phone_number", "")
        if not contact_phone:
            logger.warning("No phone number in Chatwoot webhook contact")
            return {"status": "error", "reason": "no phone number"}

        phone = self._normalize_phone(contact_phone)

        try:
            if attachments:
                for attachment in attachments:
                    file_url = attachment.get("file_url", "")
                    if file_url:
                        await self._bridge.send_message(
                            to=phone,
                            text=content or "",
                            media_url=file_url,
                        )
            else:
                await self._bridge.send_message(
                    to=phone,
                    text=content,
                )

            logger.info(
                f"Message sent to WhatsApp via Chatwoot webhook: "
                f"tenant={self._tenant.name}, to={phone}"
            )

            return {"status": "sent", "to": phone}

        except Exception as e:
            logger.error(f"Failed to send message from Chatwoot webhook: {e}")
            return {"status": "error", "reason": str(e)}

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

    def _normalize_phone(self, phone: str) -> str:
        cleaned = "".join(c for c in phone if c.isdigit() or c == "+")
        if not cleaned.startswith("+"):
            cleaned = "+" + cleaned
        return cleaned
