import uuid
from datetime import datetime, timezone
from src.store.messages import StoredMessage


def make_stored_message(**overrides) -> StoredMessage:
    defaults = {
        "id": str(uuid.uuid4()),
        "from_jid": "1234567890@s.whatsapp.net",
        "chat_jid": "1234567890@s.whatsapp.net",
        "is_group": False,
        "push_name": "Test User",
        "text": "Hello world",
        "msg_type": "text",
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
        "direction": "inbound",
    }
    defaults.update(overrides)
    return StoredMessage(**defaults)


def make_group_message(**overrides) -> StoredMessage:
    return make_stored_message(
        chat_jid="1203631234567@g.us",
        is_group=True,
        chat_name="Test Group",
        **overrides,
    )


def make_media_message(msg_type: str = "image", **overrides) -> StoredMessage:
    return make_stored_message(
        msg_type=msg_type,
        media_url=f"https://example.com/media/{uuid.uuid4()}.jpg",
        mimetype="image/jpeg",
        filename="test.jpg",
        **overrides,
    )


def make_outbound_message(**overrides) -> StoredMessage:
    return make_stored_message(
        direction="outbound",
        from_jid="9876543210@s.whatsapp.net",
        to_jid="1234567890@s.whatsapp.net",
        **overrides,
    )


def make_bridge_event(event_type: str = "message", **overrides) -> dict:
    defaults = {
        "id": str(uuid.uuid4()),
        "from": "1234567890@s.whatsapp.net",
        "chat_jid": "1234567890@s.whatsapp.net",
        "push_name": "Test User",
        "text": "Hello world",
        "type": "text",
        "timestamp": int(datetime.now(timezone.utc).timestamp()),
    }
    defaults.update(overrides)
    return defaults


def make_tenant_dict(**overrides) -> dict:
    defaults = {
        "name": "Test Tenant",
        "api_key_hash": "abc123hash456",
        "connection_state": "disconnected",
        "webhook_urls": [],
        "chatwoot_config": None,
        "self_jid": None,
        "self_phone": None,
        "self_name": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    defaults.update(overrides)
    return defaults
