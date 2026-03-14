import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from src.store.messages import StoredMessage


@pytest.mark.asyncio
async def test_sent_event_creates_outbound_message():
    from src.main import handle_bridge_event
    from src.tenant import Tenant, tenant_manager
    from src.store.messages import MessageStore

    mock_db = MagicMock()
    mock_db.save_message = AsyncMock(return_value=1)
    mock_db.list_messages = AsyncMock(return_value=([], 0))

    tenant = Tenant(
        api_key_hash="test_hash_sent",
        name="Test Tenant",
        message_store=MessageStore(
            max_messages=100,
            tenant_hash="test_hash_sent",
            db=mock_db,
        ),
    )
    tenant.self_jid = "972555077668:11@s.whatsapp.net"
    tenant_manager._tenants["test_hash_sent"] = tenant

    params = {
        "id": "sent_msg_123",
        "to": "1234567890@s.whatsapp.net",
        "text": "היי",
        "type": "text",
        "timestamp": 1234567890,
        "chat_jid": "1234567890@s.whatsapp.net",
    }

    handle_bridge_event("sent", params, "test_hash_sent")

    await asyncio.sleep(0.1)

    messages, total = tenant.message_store.list(limit=10)
    assert total == 1
    assert messages[0]["direction"] == "outbound"
    assert messages[0]["text"] == "היי"
    assert messages[0]["from_jid"] == "1234567890@s.whatsapp.net"

    del tenant_manager._tenants["test_hash_sent"]


@pytest.mark.asyncio
async def test_message_event_inbound_direction():
    from src.main import handle_bridge_event
    from src.tenant import Tenant, tenant_manager
    from src.store.messages import MessageStore

    mock_db = MagicMock()
    mock_db.save_message = AsyncMock(return_value=1)
    mock_db.list_messages = AsyncMock(return_value=([], 0))

    tenant = Tenant(
        api_key_hash="test_hash_inbound",
        name="Test Tenant",
        message_store=MessageStore(
            max_messages=100,
            tenant_hash="test_hash_inbound",
            db=mock_db,
        ),
    )
    tenant.self_jid = "972555077668:11@s.whatsapp.net"
    tenant_manager._tenants["test_hash_inbound"] = tenant

    params = {
        "id": "inbound_msg_456",
        "from": "1234567890@s.whatsapp.net",
        "chat_jid": "1234567890@s.whatsapp.net",
        "text": "Hello",
        "type": "text",
        "timestamp": 1234567890,
    }

    handle_bridge_event("message", params, "test_hash_inbound")

    await asyncio.sleep(0.1)

    messages, total = tenant.message_store.list(limit=10)
    assert total == 1
    assert messages[0]["direction"] == "inbound"
    assert messages[0]["text"] == "Hello"

    del tenant_manager._tenants["test_hash_inbound"]


@pytest.mark.asyncio
async def test_message_event_outbound_when_from_self():
    from src.main import handle_bridge_event
    from src.tenant import Tenant, tenant_manager
    from src.store.messages import MessageStore

    mock_db = MagicMock()
    mock_db.save_message = AsyncMock(return_value=1)
    mock_db.list_messages = AsyncMock(return_value=([], 0))

    tenant = Tenant(
        api_key_hash="test_hash_outbound_from_self",
        name="Test Tenant",
        message_store=MessageStore(
            max_messages=100,
            tenant_hash="test_hash_outbound_from_self",
            db=mock_db,
        ),
    )
    tenant.self_jid = "972555077668:11@s.whatsapp.net"
    tenant_manager._tenants["test_hash_outbound_from_self"] = tenant

    params = {
        "id": "outbound_msg_789",
        "from": "972555077668:11@s.whatsapp.net",
        "chat_jid": "1234567890@s.whatsapp.net",
        "text": "Reply",
        "type": "text",
        "timestamp": 1234567890,
    }

    handle_bridge_event("message", params, "test_hash_outbound_from_self")

    await asyncio.sleep(0.1)

    messages, total = tenant.message_store.list(limit=10)
    assert total == 1
    assert messages[0]["direction"] == "outbound"
    assert messages[0]["text"] == "Reply"

    del tenant_manager._tenants["test_hash_outbound_from_self"]
