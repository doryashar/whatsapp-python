from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from ..tenant import Tenant
    from ..store.database import Database

from ..store.messages import StoredMessage
from ..telemetry import get_logger

logger = get_logger("whatsapp.history")


async def store_chat_messages(
    tenant: "Tenant",
    chats_data: dict[str, Any],
    db: "Database",
) -> dict[str, int]:
    """
    Store chat messages from WhatsApp history sync.

    Returns:
        dict with 'stored', 'duplicates', 'errors' counts
    """
    chats = chats_data.get("chats", [])
    stats = {"stored": 0, "duplicates": 0, "errors": 0}

    for chat in chats:
        chat_jid = chat.get("jid", "")
        is_group = chat.get("is_group", False)
        messages = chat.get("messages", [])

        for msg in messages:
            try:
                msg_id = msg.get("id", "")
                if not msg_id:
                    continue

                from_me = msg.get("from_me", False)
                from_jid = msg.get("from", "")
                text = msg.get("text", "")
                msg_type = msg.get("type", "text")
                timestamp = msg.get("timestamp", 0)
                push_name = msg.get("push_name")

                direction = "outbound" if from_me else "inbound"

                stored_msg = StoredMessage(
                    id=msg_id,
                    from_jid=from_jid or "",
                    chat_jid=chat_jid,
                    is_group=is_group,
                    push_name=push_name,
                    text=text,
                    msg_type=msg_type,
                    timestamp=timestamp,
                    direction=direction,
                )

                if hasattr(tenant.message_store, "add_with_persist"):
                    db_id = await tenant.message_store.add_with_persist(stored_msg)
                    if db_id:
                        stats["stored"] += 1
                    else:
                        stats["duplicates"] += 1
                else:
                    tenant.message_store.add(stored_msg)
                    stats["stored"] += 1

            except Exception as e:
                stats["errors"] += 1
                logger.error(
                    f"Failed to sync message for tenant {tenant.name}: {e}",
                    exc_info=True,
                )

    return stats
