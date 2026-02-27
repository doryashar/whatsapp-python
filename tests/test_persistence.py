import pytest
import tempfile
import os
from pathlib import Path

from src.store.database import Database
from src.tenant import TenantManager
from datetime import datetime


@pytest.mark.asyncio
async def test_sqlite_persistence():
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir)
        db = Database("", data_dir)
        await db.connect()

        await db.save_tenant(
            "hash1", "tenant1", datetime.utcnow(), ["https://example.com/hook"]
        )
        await db.save_tenant("hash2", "tenant2", datetime.utcnow(), [])

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

        await db.save_tenant("hash1", "tenant1", datetime.utcnow(), [])

        await db.update_webhooks("hash1", ["https://hook1.com", "https://hook2.com"])

        tenants = await db.load_tenants()
        assert tenants[0]["webhook_urls"] == ["https://hook1.com", "https://hook2.com"]

        await db.close()
