import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock
from tests.conftest import ADMIN_PASSWORD


@pytest.mark.asyncio
async def test_messages_fragment_shows_inbound_direction_correctly(
    setup_tenant_manager,
):
    from src.main import app
    from src.tenant import tenant_manager

    tenant, api_key = await tenant_manager.create_tenant("Test Tenant")

    mock_messages = [
        {
            "id": 1,
            "tenant_hash": tenant.api_key_hash,
            "message_id": "msg1",
            "from_jid": "1234567890@s.whatsapp.net",
            "chat_jid": "1234567890@s.whatsapp.net",
            "is_group": False,
            "push_name": "Test User",
            "text": "Hello inbound",
            "msg_type": "text",
            "timestamp": 1234567890,
            "direction": "inbound",
            "created_at": "2024-01-01 12:00:00",
        }
    ]

    setup_tenant_manager._db.list_messages = AsyncMock(return_value=(mock_messages, 1))

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

            response = await client.get("/admin/fragments/messages")
            assert response.status_code == 200
            content = response.text

            assert "bg-blue-500/20 text-blue-400" in content
            assert "In" in content
            assert "Hello inbound" in content
    finally:
        await tenant_manager.delete_tenant(api_key)


@pytest.mark.asyncio
async def test_messages_fragment_shows_outbound_direction_correctly(
    setup_tenant_manager,
):
    from src.main import app
    from src.tenant import tenant_manager

    tenant, api_key = await tenant_manager.create_tenant("Test Tenant")

    mock_messages = [
        {
            "id": 1,
            "tenant_hash": tenant.api_key_hash,
            "message_id": "msg1",
            "from_jid": "1234567890@s.whatsapp.net",
            "chat_jid": "1234567890@s.whatsapp.net",
            "is_group": False,
            "push_name": "Test User",
            "text": "Hello outbound",
            "msg_type": "text",
            "timestamp": 1234567890,
            "direction": "outbound",
            "created_at": "2024-01-01 12:00:00",
        }
    ]

    setup_tenant_manager._db.list_messages = AsyncMock(return_value=(mock_messages, 1))

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

            response = await client.get("/admin/fragments/messages")
            assert response.status_code == 200
            content = response.text

            assert "bg-purple-500/20 text-purple-400" in content
            assert "Out" in content
            assert "Hello outbound" in content
    finally:
        await tenant_manager.delete_tenant(api_key)


@pytest.mark.asyncio
async def test_messages_page_has_correct_filter_values(setup_tenant_manager):
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

        response = await client.get("/admin/messages")
        assert response.status_code == 200
        content = response.text

        assert 'value="inbound"' in content
        assert 'value="outbound"' in content
        assert "Inbound</option>" in content
        assert "Outbound</option>" in content


@pytest.mark.asyncio
async def test_outbound_label_has_to_prefix(setup_tenant_manager):
    from src.main import app
    from src.tenant import tenant_manager

    tenant, api_key = await tenant_manager.create_tenant("Test Tenant")

    mock_messages = [
        {
            "id": 1,
            "tenant_hash": tenant.api_key_hash,
            "message_id": "msg_out_to",
            "from_jid": "9876543210@s.whatsapp.net",
            "chat_jid": "5551234567@s.whatsapp.net",
            "is_group": False,
            "push_name": "",
            "text": "Outbound to test",
            "msg_type": "text",
            "timestamp": 1234567890,
            "direction": "outbound",
            "created_at": "2024-01-01 12:00:00",
        }
    ]

    setup_tenant_manager._db.list_messages = AsyncMock(return_value=(mock_messages, 1))
    setup_tenant_manager._db.get_contact_names_for_chats = AsyncMock(return_value={})

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

            response = await client.get("/admin/fragments/messages")
            assert response.status_code == 200
            content = response.text

            assert "To: 5551234567" in content
            assert "From:" not in content
    finally:
        await tenant_manager.delete_tenant(api_key)


@pytest.mark.asyncio
async def test_outbound_label_with_contact_name(setup_tenant_manager):
    from src.main import app
    from src.tenant import tenant_manager

    tenant, api_key = await tenant_manager.create_tenant("Test Tenant")

    mock_messages = [
        {
            "id": 1,
            "tenant_hash": tenant.api_key_hash,
            "message_id": "msg_out_name",
            "from_jid": "9876543210@s.whatsapp.net",
            "chat_jid": "5551234567@s.whatsapp.net",
            "is_group": False,
            "push_name": "",
            "text": "Outbound named",
            "msg_type": "text",
            "timestamp": 1234567890,
            "direction": "outbound",
            "created_at": "2024-01-01 12:00:00",
        }
    ]

    setup_tenant_manager._db.list_messages = AsyncMock(return_value=(mock_messages, 1))
    setup_tenant_manager._db.get_contact_names_for_chats = AsyncMock(
        return_value={
            (tenant.api_key_hash, "5551234567@s.whatsapp.net"): {
                "name": "Jane Smith",
                "is_group": False,
            }
        }
    )

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

            response = await client.get("/admin/fragments/messages")
            assert response.status_code == 200
            content = response.text

            assert "To: Jane Smith" in content
            assert "From:" not in content
    finally:
        await tenant_manager.delete_tenant(api_key)


@pytest.mark.asyncio
async def test_inbound_label_has_from_prefix(setup_tenant_manager):
    from src.main import app
    from src.tenant import tenant_manager

    tenant, api_key = await tenant_manager.create_tenant("Test Tenant")

    mock_messages = [
        {
            "id": 1,
            "tenant_hash": tenant.api_key_hash,
            "message_id": "msg_in_from",
            "from_jid": "5551234567@s.whatsapp.net",
            "chat_jid": "5551234567@s.whatsapp.net",
            "is_group": False,
            "push_name": "Bob",
            "text": "Inbound from test",
            "msg_type": "text",
            "timestamp": 1234567890,
            "direction": "inbound",
            "created_at": "2024-01-01 12:00:00",
        }
    ]

    setup_tenant_manager._db.list_messages = AsyncMock(return_value=(mock_messages, 1))

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

            response = await client.get("/admin/fragments/messages")
            assert response.status_code == 200
            content = response.text

            assert "From: Bob" in content
            assert "To:" not in content
    finally:
        await tenant_manager.delete_tenant(api_key)


@pytest.mark.asyncio
async def test_mixed_directions_correct_labels(setup_tenant_manager):
    from src.main import app
    from src.tenant import tenant_manager

    tenant, api_key = await tenant_manager.create_tenant("Test Tenant")

    mock_messages = [
        {
            "id": 1,
            "tenant_hash": tenant.api_key_hash,
            "message_id": "msg_in",
            "from_jid": "5551111111@s.whatsapp.net",
            "chat_jid": "5551111111@s.whatsapp.net",
            "is_group": False,
            "push_name": "Sender In",
            "text": "Inbound",
            "msg_type": "text",
            "timestamp": 1234567890,
            "direction": "inbound",
            "created_at": "2024-01-01 12:00:00",
        },
        {
            "id": 2,
            "tenant_hash": tenant.api_key_hash,
            "message_id": "msg_out",
            "from_jid": "9876543210@s.whatsapp.net",
            "chat_jid": "5552222222@s.whatsapp.net",
            "is_group": False,
            "push_name": "",
            "text": "Outbound",
            "msg_type": "text",
            "timestamp": 1234567891,
            "direction": "outbound",
            "created_at": "2024-01-01 12:00:01",
        },
    ]

    setup_tenant_manager._db.list_messages = AsyncMock(return_value=(mock_messages, 2))
    setup_tenant_manager._db.get_contact_names_for_chats = AsyncMock(return_value={})

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

            response = await client.get("/admin/fragments/messages")
            assert response.status_code == 200
            content = response.text

            assert "From: Sender In" in content
            assert "To: 5552222222" in content
            assert "bg-blue-500/20 text-blue-400" in content
            assert "bg-purple-500/20 text-purple-400" in content
    finally:
        await tenant_manager.delete_tenant(api_key)


@pytest.mark.asyncio
async def test_phone_and_chat_id_displayed(setup_tenant_manager):
    from src.main import app
    from src.tenant import tenant_manager

    tenant, api_key = await tenant_manager.create_tenant("Test Tenant")

    mock_messages = [
        {
            "id": 1,
            "tenant_hash": tenant.api_key_hash,
            "message_id": "msg_meta",
            "from_jid": "5551234567@s.whatsapp.net",
            "chat_jid": "5551234567@s.whatsapp.net",
            "is_group": False,
            "push_name": "Meta Test",
            "text": "Check meta",
            "msg_type": "text",
            "timestamp": 1234567890,
            "direction": "inbound",
            "created_at": "2024-01-01 12:00:00",
        }
    ]

    setup_tenant_manager._db.list_messages = AsyncMock(return_value=(mock_messages, 1))

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

            response = await client.get("/admin/fragments/messages")
            assert response.status_code == 200
            content = response.text

            assert "text-gray-600" in content
            assert "5551234567@s.whatsapp.net" in content
            assert ">5551234567<" in content
    finally:
        await tenant_manager.delete_tenant(api_key)
