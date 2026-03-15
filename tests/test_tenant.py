import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from httpx import ASGITransport, AsyncClient

from src.tenant import TenantManager, tenant_manager


@pytest.fixture
def fresh_tenant_manager():
    manager = TenantManager()
    return manager


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
        return_value={
            "id": "test-session-id",
            "expires_at": "2099-01-01",
            "user_agent": "test",
            "ip_address": "127.0.0.1",
        }
    )
    db.save_tenant = AsyncMock()
    db.delete_tenant = AsyncMock()
    return db


@pytest.fixture(autouse=True)
def setup_admin_api_key(monkeypatch, mock_db):
    """Set admin password for all tests in this module"""
    from src import config
    from src.admin import auth as admin_auth
    from src.tenant import tenant_manager

    # Patch in both places
    monkeypatch.setattr(config.settings, "admin_password", "test_admin_key")
    monkeypatch.setattr(admin_auth.settings, "admin_password", "test_admin_key")
    monkeypatch.setattr(config.settings, "debug", True)

    # Setup mock database
    original_db = tenant_manager._db
    tenant_manager._db = mock_db

    yield

    monkeypatch.setattr(config.settings, "admin_password", None)
    monkeypatch.setattr(admin_auth.settings, "admin_password", None)
    monkeypatch.setattr(config.settings, "debug", False)
    tenant_manager._db = original_db


class TestTenantManager:
    @pytest.mark.asyncio
    async def test_create_tenant(self, fresh_tenant_manager):
        tenant, api_key = await fresh_tenant_manager.create_tenant("test_user")

        assert tenant.name == "test_user"
        assert api_key.startswith("wa_")
        assert len(api_key) > 10

    @pytest.mark.asyncio
    async def test_get_tenant_by_key(self, fresh_tenant_manager):
        tenant, api_key = await fresh_tenant_manager.create_tenant("test_user")

        retrieved = fresh_tenant_manager.get_tenant_by_key(api_key)
        assert retrieved is not None
        assert retrieved.name == "test_user"

    def test_get_tenant_by_invalid_key(self, fresh_tenant_manager):
        retrieved = fresh_tenant_manager.get_tenant_by_key("invalid_key")
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_tenant(self, fresh_tenant_manager):
        tenant, api_key = await fresh_tenant_manager.create_tenant("test_user")

        result = await fresh_tenant_manager.delete_tenant(api_key)
        assert result is True

        retrieved = fresh_tenant_manager.get_tenant_by_key(api_key)
        assert retrieved is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent_tenant(self, fresh_tenant_manager):
        result = await fresh_tenant_manager.delete_tenant("invalid_key")
        assert result is False

    @pytest.mark.asyncio
    async def test_list_tenants(self, fresh_tenant_manager):
        await fresh_tenant_manager.create_tenant("user1")
        await fresh_tenant_manager.create_tenant("user2")

        tenants = fresh_tenant_manager.list_tenants()
        assert len(tenants) == 2
        names = [t.name for t in tenants]
        assert "user1" in names
        assert "user2" in names

    @pytest.mark.asyncio
    async def test_add_webhook(self, fresh_tenant_manager):
        tenant, _ = await fresh_tenant_manager.create_tenant("test_user")

        await fresh_tenant_manager.add_webhook(tenant, "https://example.com/hook")
        assert "https://example.com/hook" in tenant.webhook_urls

    @pytest.mark.asyncio
    async def test_remove_webhook(self, fresh_tenant_manager):
        tenant, _ = await fresh_tenant_manager.create_tenant("test_user")
        await fresh_tenant_manager.add_webhook(tenant, "https://example.com/hook")

        result = await fresh_tenant_manager.remove_webhook(
            tenant, "https://example.com/hook"
        )
        assert result is True
        assert "https://example.com/hook" not in tenant.webhook_urls

    @pytest.mark.asyncio
    async def test_message_store_isolated(self, fresh_tenant_manager):
        from src.store.messages import StoredMessage

        tenant1, _ = await fresh_tenant_manager.create_tenant("user1")
        tenant2, _ = await fresh_tenant_manager.create_tenant("user2")

        msg = StoredMessage(
            id="msg1",
            from_jid="12345",
            chat_jid="12345",
            text="hello",
            timestamp=12345,
        )
        tenant1.message_store.add(msg)

        _, total1 = tenant1.message_store.list()
        _, total2 = tenant2.message_store.list()

        assert total1 == 1
        assert total2 == 0


@pytest.mark.asyncio
async def test_admin_create_tenant():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Login first to get session cookie
        login_response = await client.post(
            "/admin/login", data={"password": "test_admin_key"}, follow_redirects=False
        )
        assert login_response.status_code == 302

        # Now make the authenticated request
        response = await client.post(
            "/admin/api/tenants",
            data={"name": "new_user"},
        )
        if response.status_code != 200:
            print(f"Status: {response.status_code}, Body: {response.text}")
        assert response.status_code == 200
        data = response.json()
        assert data["tenant"]["name"] == "new_user"
        assert "api_key" in data["tenant"]


@pytest.mark.asyncio
async def test_admin_list_tenants():
    from src.main import app
    from src.tenant import tenant_manager

    await tenant_manager.create_tenant("list_test_user")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Login first to get session cookie
        login_response = await client.post(
            "/admin/login", data={"password": "test_admin_key"}, follow_redirects=False
        )
        assert login_response.status_code == 302

        # Now make the authenticated request
        response = await client.get("/admin/api/tenants")
        assert response.status_code == 200
        data = response.json()
        assert "tenants" in data
        names = [t["name"] for t in data["tenants"]]
        assert "list_test_user" in names


@pytest.mark.asyncio
async def test_admin_requires_key():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Try to access without logging in
        response = await client.post("/admin/api/tenants", params={"name": "new_user"})
        assert response.status_code == 401


class TestBinaryKeyFileHandling:
    @pytest.mark.asyncio
    async def test_binary_key_file_written_correctly(self, tmp_path):
        from src.tenant import TenantManager, Tenant
        from unittest.mock import patch

        manager = TenantManager()
        db = AsyncMock()
        manager.set_database(db)

        auth_dir = tmp_path / "auth"
        auth_dir.mkdir(parents=True, exist_ok=True)

        auth_data = {
            "creds": {"noiseKey": "test"},
            "keys": {
                "app-state-sync-key-1.json": b"\x00\x01\x02\x03",
                "session.json": '{"key": "value"}',
            },
        }

        tenant = Tenant(
            name="test_tenant",
            api_key_hash="test_hash",
        )
        tenant.creds_json = auth_data

        with patch.object(tenant, "get_auth_dir", return_value=auth_dir):
            success = manager._restore_auth_to_filesystem(tenant)

        assert success is True

        binary_file = auth_dir / "keys" / "app-state-sync-key-1.json"
        assert binary_file.exists()
        with open(binary_file, "rb") as f:
            content = f.read()
        assert content == b"\x00\x01\x02\x03"

        text_file = auth_dir / "keys" / "session.json"
        assert text_file.exists()
        with open(text_file, "r") as f:
            content = f.read()
        assert content == '{"key": "value"}'

    @pytest.mark.asyncio
    async def test_text_key_file_written_correctly(self, tmp_path):
        from src.tenant import TenantManager, Tenant
        from unittest.mock import patch

        manager = TenantManager()
        db = AsyncMock()
        manager.set_database(db)

        auth_dir = tmp_path / "auth"
        auth_dir.mkdir(parents=True, exist_ok=True)

        auth_data = {
            "creds": {"noiseKey": "test"},
            "keys": {
                "test-key.json": '{"data": "string content"}',
            },
        }

        tenant = Tenant(
            name="test_tenant",
            api_key_hash="test_hash",
        )
        tenant.creds_json = auth_data

        with patch.object(tenant, "get_auth_dir", return_value=auth_dir):
            success = manager._restore_auth_to_filesystem(tenant)

        assert success is True

        key_file = auth_dir / "keys" / "test-key.json"
        assert key_file.exists()
        with open(key_file, "r") as f:
            content = f.read()
        assert content == '{"data": "string content"}'


class TestRestartHistoryCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_removes_deleted_tenant_entries(self, fresh_tenant_manager):
        from datetime import datetime, UTC, timedelta

        fresh_tenant_manager._restart_history["deleted_hash"] = [
            datetime.now(UTC) - timedelta(seconds=60)
        ]
        fresh_tenant_manager._last_cleanup = datetime.now(UTC) - timedelta(seconds=7200)

        fresh_tenant_manager._cleanup_restart_history()

        assert "deleted_hash" not in fresh_tenant_manager._restart_history

    @pytest.mark.asyncio
    async def test_cleanup_removes_expired_timestamps(self, fresh_tenant_manager):
        from datetime import datetime, UTC, timedelta
        from src import config

        tenant, _ = await fresh_tenant_manager.create_tenant("test_cleanup")

        old_ts = datetime.now(UTC) - timedelta(
            seconds=config.settings.restart_window_seconds + 100
        )
        recent_ts = datetime.now(UTC) - timedelta(seconds=60)

        fresh_tenant_manager._restart_history[tenant.api_key_hash] = [old_ts, recent_ts]
        fresh_tenant_manager._last_cleanup = datetime.now(UTC) - timedelta(seconds=7200)

        fresh_tenant_manager._cleanup_restart_history()

        assert len(fresh_tenant_manager._restart_history[tenant.api_key_hash]) == 1
        assert (
            fresh_tenant_manager._restart_history[tenant.api_key_hash][0] == recent_ts
        )

    @pytest.mark.asyncio
    async def test_cleanup_removes_empty_entries(self, fresh_tenant_manager):
        from datetime import datetime, UTC, timedelta
        from src import config

        tenant, _ = await fresh_tenant_manager.create_tenant("test_empty")

        old_ts = datetime.now(UTC) - timedelta(
            seconds=config.settings.restart_window_seconds + 100
        )
        fresh_tenant_manager._restart_history[tenant.api_key_hash] = [old_ts]
        fresh_tenant_manager._last_cleanup = datetime.now(UTC) - timedelta(seconds=7200)

        fresh_tenant_manager._cleanup_restart_history()

        assert tenant.api_key_hash not in fresh_tenant_manager._restart_history

    def test_cleanup_skipped_when_interval_not_elapsed(self, fresh_tenant_manager):
        from datetime import datetime, UTC

        fresh_tenant_manager._last_cleanup = datetime.now(UTC)
        fresh_tenant_manager._restart_history["old_entry"] = [datetime.now(UTC)]

        fresh_tenant_manager._cleanup_restart_history()

        assert "old_entry" in fresh_tenant_manager._restart_history

    @pytest.mark.asyncio
    async def test_can_restart_triggers_cleanup(
        self, fresh_tenant_manager, monkeypatch
    ):
        from datetime import datetime, UTC, timedelta
        from src import config

        monkeypatch.setattr(config.settings, "auto_restart_bridge", True)

        tenant, _ = await fresh_tenant_manager.create_tenant("test_trigger")
        fresh_tenant_manager._restart_history["deleted_tenant"] = [datetime.now(UTC)]
        fresh_tenant_manager._last_cleanup = datetime.now(UTC) - timedelta(seconds=7200)

        fresh_tenant_manager.can_restart(tenant)

        assert "deleted_tenant" not in fresh_tenant_manager._restart_history

    def test_cleanup_updates_last_cleanup_timestamp(self, fresh_tenant_manager):
        from datetime import datetime, UTC, timedelta

        old_cleanup = datetime.now(UTC) - timedelta(seconds=7200)
        fresh_tenant_manager._last_cleanup = old_cleanup

        fresh_tenant_manager._cleanup_restart_history()

        assert fresh_tenant_manager._last_cleanup > old_cleanup
