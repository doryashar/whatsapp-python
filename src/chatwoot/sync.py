import asyncio
from collections import defaultdict
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from .models import ChatwootConfig, ChatwootContact, ChatwootConversation
from .client import ChatwootClient, ChatwootAPIError
from ..telemetry import get_logger

if TYPE_CHECKING:
    from ..tenant import Tenant
    from ..store.database import Database

logger = get_logger("whatsapp.chatwoot.sync")


class ChatwootSyncService:
    def __init__(self, config: ChatwootConfig, tenant: "Tenant", db: "Database"):
        self._config = config
        self._tenant = tenant
        self._client = ChatwootClient(config)
        self._db = db
        self._contact_cache: dict[str, ChatwootContact] = {}
        self._conversation_cache: dict[int, ChatwootConversation] = {}

    async def close(self):
        await self._client.close()

    async def sync_message_history(
        self,
        days_limit: Optional[int] = None,
    ) -> dict:
        synced = 0
        skipped = 0
        errors = 0
        error_details = []

        if days_limit is None:
            days_limit = self._config.days_limit_import

        logger.info(
            f"Starting Chatwoot message sync for tenant {self._tenant.name}: "
            f"days_limit={days_limit}"
        )

        try:
            messages = await self._db.get_unsynced_messages_for_chatwoot(
                tenant_hash=self._tenant.api_key_hash,
                days_limit=days_limit,
                limit=1000,
            )

            logger.info(f"Found {len(messages)} unsynced messages to process")

            if not messages:
                return {
                    "synced": 0,
                    "skipped": 0,
                    "errors": 0,
                    "error_details": [],
                    "message": "No messages to sync",
                }

            messages_by_contact = defaultdict(list)
            for msg in messages:
                chat_jid = msg.get("chat_jid")
                if chat_jid:
                    messages_by_contact[chat_jid].append(msg)

            for contact_jid, contact_messages in messages_by_contact.items():
                try:
                    result = await self._sync_contact_messages(
                        contact_jid, contact_messages
                    )
                    synced += result["synced"]
                    skipped += result["skipped"]
                    errors += result["errors"]
                    error_details.extend(result.get("error_details", []))
                except Exception as e:
                    logger.error(
                        f"Failed to sync messages for contact {contact_jid}: {e}",
                        exc_info=True,
                    )
                    errors += len(contact_messages)
                    error_details.append(f"Contact {contact_jid}: {str(e)}")

            logger.info(
                f"Chatwoot message sync complete for tenant {self._tenant.name}: "
                f"synced={synced}, skipped={skipped}, errors={errors}"
            )

            return {
                "synced": synced,
                "skipped": skipped,
                "errors": errors,
                "error_details": error_details[:10],
            }

        except Exception as e:
            logger.error(
                f"Failed to sync message history for tenant {self._tenant.name}: {e}",
                exc_info=True,
            )
            raise

    async def _sync_contact_messages(
        self, contact_jid: str, messages: list[dict]
    ) -> dict:
        synced = 0
        skipped = 0
        errors = 0
        error_details = []

        phone_number = self._extract_phone(contact_jid)
        if not phone_number:
            logger.warning(f"Could not extract phone from jid: {contact_jid}")
            return {
                "synced": 0,
                "skipped": len(messages),
                "errors": 0,
                "error_details": [],
            }

        contact_name = messages[0].get("push_name") if messages else phone_number

        try:
            contact = await self._get_or_create_contact(phone_number, contact_name)
        except Exception as e:
            logger.error(f"Failed to create contact for {phone_number}: {e}")
            return {
                "synced": 0,
                "skipped": 0,
                "errors": len(messages),
                "error_details": [f"Failed to create contact: {str(e)}"],
            }

        try:
            conversation = await self._get_or_create_conversation(contact)
        except Exception as e:
            logger.error(f"Failed to create conversation for contact {contact.id}: {e}")
            return {
                "synced": 0,
                "skipped": 0,
                "errors": len(messages),
                "error_details": [f"Failed to create conversation: {str(e)}"],
            }

        for msg in messages:
            try:
                success = await self._sync_single_message(conversation.id, msg)
                if success:
                    synced += 1
                    await self._db.mark_message_chatwoot_synced(msg["id"])
                else:
                    skipped += 1
            except Exception as e:
                logger.warning(f"Failed to sync message {msg.get('id')}: {e}")
                errors += 1
                error_details.append(f"Message {msg.get('id')}: {str(e)}")

        return {
            "synced": synced,
            "skipped": skipped,
            "errors": errors,
            "error_details": error_details[:5],
        }

    async def _get_or_create_contact(
        self, phone_number: str, name: Optional[str] = None
    ) -> ChatwootContact:
        if phone_number in self._contact_cache:
            return self._contact_cache[phone_number]

        contact = await self._client.find_or_create_contact(
            phone_number=phone_number,
            name=name or phone_number,
        )
        self._contact_cache[phone_number] = contact
        return contact

    async def _get_or_create_conversation(
        self, contact: ChatwootContact
    ) -> ChatwootConversation:
        if contact.id in self._conversation_cache:
            return self._conversation_cache[contact.id]

        conversation = await self._client.get_or_create_conversation(contact=contact)
        self._conversation_cache[contact.id] = conversation
        return conversation

    async def _sync_single_message(self, conversation_id: int, message: dict) -> bool:
        content = message.get("text", "")
        msg_type = message.get("msg_type", "text")
        direction = message.get("direction", "inbound")
        media_url = message.get("media_url")

        if not content and msg_type == "text":
            return False

        message_type = "incoming" if direction == "inbound" else "outgoing"

        attachments = None
        if media_url and msg_type != "text":
            attachments = await self._prepare_attachment(media_url, msg_type, message)

        if not content:
            content = f"[{msg_type}]"

        try:
            await self._client.create_message(
                conversation_id=conversation_id,
                content=content,
                message_type=message_type,
                attachments=attachments,
            )
            return True
        except ChatwootAPIError as e:
            logger.warning(f"Chatwoot API error syncing message: {e.message}")
            raise

    async def _prepare_attachment(
        self, media_url: str, msg_type: str, message: dict
    ) -> Optional[list[dict]]:
        mimetype_map = {
            "image": "image/jpeg",
            "video": "video/mp4",
            "audio": "audio/ogg",
            "document": "application/pdf",
            "sticker": "image/webp",
        }

        mimetype = mimetype_map.get(msg_type, "application/octet-stream")

        return [{"file_type": mimetype, "file_url": media_url}]

    def _extract_phone(self, jid: str) -> Optional[str]:
        if not jid:
            return None

        phone = jid.split("@")[0]
        phone = phone.split(":")[0]

        if not phone.isdigit():
            return None

        return "+" + phone if not phone.startswith("+") else phone
