import pytest
import tempfile
import os
import hashlib
from pathlib import Path

from src.store.database import Database
from src.tenant import TenantManager
from datetime import datetime, UTC


@pytest.mark.asyncio
async def test_sqlite_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant(
            "hash1", "tenant1", datetime.now(UTC), ["https://example.com/hook"]
        )
        await db.save_tenant("hash2", "tenant2", datetime.now(UTC), [])

        tenants = await db.load_tenants()
        assert len(tenants) == 2
        names = [t["name"] for t in tenants]
        assert "tenant1" in names
        assert "tenant2" in names

        for t in tenants:
            if t["api_key_hash"] == "hash1":
                assert t["webhook_urls"] == ["https://example.com/hook"]

        await db.delete_tenant("hash1")
        tenants = await db.load_tenants()
        assert len(tenants) == 1
        assert tenants[0]["name"] == "tenant2"

        await db.close()


@pytest.mark.asyncio
async def test_tenant_manager_with_database():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        auth_dir = Path(tmpdir) / "auth"

        db = Database("", data_dir)
        manager = TenantManager(base_auth_dir=auth_dir, database=db)
        await manager.initialize()

        tenant, api_key = await manager.create_tenant("test_user")
        await manager.add_webhook(tenant, "https://example.com/webhook")

        await db.close()

        db2 = Database("", data_dir)
        manager2 = TenantManager(base_auth_dir=auth_dir, database=db2)
        await manager2.initialize()

        loaded_tenant = manager2.get_tenant_by_key(api_key)
        assert loaded_tenant is not None
        assert loaded_tenant.name == "test_user"
        assert "https://example.com/webhook" in loaded_tenant.webhook_urls

        await db2.close()


@pytest.mark.asyncio
async def test_update_webhooks_persists():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant("hash1", "tenant1", datetime.now(UTC), [])

        await db.update_webhooks("hash1", ["https://hook1.com", "https://hook2.com"])

        tenants = await db.load_tenants()
        assert tenants[0]["webhook_urls"] == ["https://hook1.com", "https://hook2.com"]

        await db.close()


@pytest.mark.asyncio
async def test_auth_state_with_keys_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        auth_dir = Path(tmpdir) / "auth"

        db = Database("", data_dir)
        manager = TenantManager(base_auth_dir=auth_dir, database=db)
        await manager.initialize()

        tenant, api_key = await manager.create_tenant("test_user")

        auth_data = {
            "creds": {"me": {"id": "12345@s.whatsapp.net"}, "noiseKey": "abc123"},
            "keys": {
                "app-state-sync-key-1.json": '{"key": "data1"}',
                "session-1.json": '{"session": "data2"}',
            },
        }
        await manager.save_auth_state(tenant, auth_data)

        await db.close()

        db2 = Database("", data_dir)
        manager2 = TenantManager(base_auth_dir=auth_dir, database=db2)
        await manager2.initialize()

        loaded_tenant = manager2.get_tenant_by_key(api_key)
        assert loaded_tenant is not None
        assert loaded_tenant.creds_json is not None
        assert loaded_tenant.creds_json["creds"]["me"]["id"] == "12345@s.whatsapp.net"
        assert "keys" in loaded_tenant.creds_json
        assert "app-state-sync-key-1.json" in loaded_tenant.creds_json["keys"]

        manager2._restore_auth_to_filesystem(loaded_tenant)

        keys_dir = (
            auth_dir
            / hashlib.sha256(loaded_tenant.api_key_hash.encode()).hexdigest()[:16]
            / "keys"
        )
        assert keys_dir.exists()
        assert (keys_dir / "app-state-sync-key-1.json").exists()
        assert (keys_dir / "session-1.json").exists()

        await db2.close()


@pytest.mark.asyncio
async def test_credential_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant("hash1", "tenant1", datetime.now(UTC), [])

        creds = {"me": {"id": "12345@s.whatsapp.net"}, "noiseKey": "abc123"}
        await db.save_creds("hash1", creds)

        loaded_creds = await db.load_creds("hash1")
        assert loaded_creds is not None
        assert loaded_creds["me"]["id"] == "12345@s.whatsapp.net"

        tenants = await db.load_tenants()
        assert tenants[0]["has_auth"] is True
        assert tenants[0]["creds_json"] is not None

        await db.clear_creds("hash1")
        loaded_creds = await db.load_creds("hash1")
        assert loaded_creds is None

        tenants = await db.load_tenants()
        assert tenants[0]["has_auth"] is False
        assert tenants[0]["creds_json"] is None

        await db.close()


@pytest.mark.asyncio
async def test_session_state_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant("hash1", "tenant1", datetime.now(UTC), [])

        await db.update_session_state(
            "hash1",
            "connected",
            self_jid="123456789@s.whatsapp.net",
            self_phone="123456789",
            self_name="Test User",
            has_auth=True,
        )

        tenants = await db.load_tenants()
        assert tenants[0]["connection_state"] == "connected"
        assert tenants[0]["self_jid"] == "123456789@s.whatsapp.net"
        assert tenants[0]["self_phone"] == "123456789"
        assert tenants[0]["self_name"] == "Test User"
        assert tenants[0]["has_auth"] is True

        await db.close()
