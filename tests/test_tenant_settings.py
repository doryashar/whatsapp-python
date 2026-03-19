import pytest
from datetime import datetime, UTC

from src.tenant import Tenant, TenantManager
from src.store.database import Database
from src.bridge.client import BaileysBridge


class TestTenantSettings:
    def test_tenant_default_settings_is_none(self):
        tenant = Tenant(api_key_hash="test_hash", name="Test Tenant")
        assert tenant.settings is None

    def test_tenant_get_auto_mark_read_default_true(self):
        tenant = Tenant(api_key_hash="test_hash", name="Test Tenant")
        assert tenant.get_auto_mark_read() is True

    def test_tenant_get_auto_mark_read_explicit_true(self):
        tenant = Tenant(
            api_key_hash="test_hash",
            name="Test Tenant",
            settings={"auto_mark_read": True},
        )
        assert tenant.get_auto_mark_read() is True

    def test_tenant_get_auto_mark_read_explicit_false(self):
        tenant = Tenant(
            api_key_hash="test_hash",
            name="Test Tenant",
            settings={"auto_mark_read": False},
        )
        assert tenant.get_auto_mark_read() is False

    def test_tenant_get_auto_mark_read_missing_key_returns_true(self):
        tenant = Tenant(
            api_key_hash="test_hash",
            name="Test Tenant",
            settings={"other_setting": "value"},
        )
        assert tenant.get_auto_mark_read() is True

    def test_tenant_get_auto_mark_read_empty_settings(self):
        tenant = Tenant(api_key_hash="test_hash", name="Test Tenant", settings={})
        assert tenant.get_auto_mark_read() is True


class TestTenantSettingsUpdate:
    @pytest.fixture
    async def tenant_manager_with_db(self, tmp_path):
        db_path = tmp_path / "test.db"
        db = Database(f"sqlite://{db_path}", tmp_path)
        manager = TenantManager(base_auth_dir=tmp_path, database=db)
        await manager.initialize()
        yield manager
        await db.close()

    @pytest.mark.asyncio
    async def test_update_tenant_settings(self, tenant_manager_with_db):
        tenant = Tenant(api_key_hash="test_hash", name="Test")
        tenant_manager_with_db._tenants["test_hash"] = tenant

        success, needs_restart = await tenant_manager_with_db.update_tenant_settings(
            tenant, {"auto_mark_read": False}
        )

        assert success is True
        assert tenant.settings == {"auto_mark_read": False}
        assert tenant.get_auto_mark_read() is False
        assert needs_restart is False

    @pytest.mark.asyncio
    async def test_update_settings_merges_with_existing(self, tenant_manager_with_db):
        tenant = Tenant(
            api_key_hash="test_hash",
            name="Test",
            settings={"existing_setting": "value"},
        )
        tenant_manager_with_db._tenants["test_hash"] = tenant

        await tenant_manager_with_db.update_tenant_settings(
            tenant, {"auto_mark_read": False}
        )

        assert tenant.settings == {"existing_setting": "value", "auto_mark_read": False}

    @pytest.mark.asyncio
    async def test_update_settings_needs_restart_when_bridge_exists(
        self, tenant_manager_with_db
    ):
        from unittest.mock import MagicMock, AsyncMock, patch

        tenant = Tenant(api_key_hash="test_hash", name="Test")
        mock_bridge = MagicMock()
        mock_bridge.stop = AsyncMock()
        tenant.bridge = mock_bridge
        tenant_manager_with_db._tenants["test_hash"] = tenant

        with patch.object(
            tenant_manager_with_db, "get_or_create_bridge", new_callable=AsyncMock
        ) as mock_create:
            (
                success,
                needs_restart,
            ) = await tenant_manager_with_db.update_tenant_settings(
                tenant, {"auto_mark_read": False}
            )

        assert success is True
        assert needs_restart is True
        mock_bridge.stop.assert_called_once()
        mock_create.assert_called_once_with(tenant)


class TestBridgeAutoMarkRead:
    def test_bridge_default_auto_mark_read_true(self):
        bridge = BaileysBridge(tenant_id="test")
        assert bridge.auto_mark_read is True

    def test_bridge_auto_mark_read_false(self):
        bridge = BaileysBridge(tenant_id="test", auto_mark_read=False)
        assert bridge.auto_mark_read is False

    def test_bridge_auto_mark_read_true_explicit(self):
        bridge = BaileysBridge(tenant_id="test", auto_mark_read=True)
        assert bridge.auto_mark_read is True


class TestDatabaseSettings:
    @pytest.fixture
    async def db(self, tmp_path):
        db = Database("sqlite:///:memory:", tmp_path)
        await db.connect()
        return db

    @pytest.mark.asyncio
    async def test_save_settings(self, db):
        await db.save_tenant("hash1", "Test", datetime.now(UTC), [])
        await db.save_settings("hash1", {"auto_mark_read": False})

        tenants = await db.load_tenants()
        assert len(tenants) == 1
        assert tenants[0]["settings"] == {"auto_mark_read": False}

    @pytest.mark.asyncio
    async def test_save_settings_none_clears(self, db):
        await db.save_tenant("hash1", "Test", datetime.now(UTC), [])
        await db.save_settings("hash1", {"auto_mark_read": False})
        await db.save_settings("hash1", None)

        tenants = await db.load_tenants()
        assert tenants[0]["settings"] is None

    @pytest.mark.asyncio
    async def test_load_tenants_includes_settings(self, db):
        await db.save_tenant("hash1", "Test", datetime.now(UTC), [])
        await db.save_settings("hash1", {"auto_mark_read": True, "other": "value"})

        tenants = await db.load_tenants()
        assert tenants[0]["settings"]["auto_mark_read"] is True
        assert tenants[0]["settings"]["other"] == "value"
