import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock


ADMIN_PASSWORD = "test-admin-password-123"


@pytest.fixture(autouse=True)
def setup_admin_password(monkeypatch):
    from src import config

    monkeypatch.setattr(config.settings, "admin_password", ADMIN_PASSWORD)
    yield
    monkeypatch.setattr(config.settings, "admin_password", None)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db.list_messages = AsyncMock(return_value=([], 0))
    db.get_recent_chats = AsyncMock(return_value=[])
    db.get_webhook_stats = AsyncMock(
        return_value={"total": 0, "success_count": 0, "fail_count": 0}
    )
    db.create_admin_session = AsyncMock(return_value="test-session-id")
    db.get_admin_session = AsyncMock(
        return_value={"id": "test-session-id", "expires_at": "2099-01-01"}
    )
    db.save_tenant = AsyncMock(return_value=None)
    db.load_tenants = AsyncMock(return_value=[])
    db.delete_tenant = AsyncMock(return_value=True)
    return db


@pytest.fixture
async def setup_tenant_manager(mock_db, monkeypatch):
    from src.tenant import tenant_manager
    from src.store.database import Database

    original_db = tenant_manager._db
    original_tenants = tenant_manager._tenants.copy()

    tenant_manager._db = mock_db
    tenant_manager._tenants.clear()

    yield tenant_manager

    tenant_manager._db = original_db
    tenant_manager._tenants = original_tenants


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
