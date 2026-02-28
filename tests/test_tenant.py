import pytest
from unittest.mock import patch, AsyncMock
from httpx import ASGITransport, AsyncClient

from src.tenant import TenantManager, tenant_manager


@pytest.fixture
def fresh_tenant_manager():
    manager = TenantManager()
    return manager


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
    from src.config import settings

    with patch.object(settings, "admin_api_key", "test_admin_key"):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/admin/tenants",
                params={"name": "new_user"},
                headers={"X-API-Key": "test_admin_key"},
            )
            assert response.status_code == 200
            data = response.json()
            assert data["name"] == "new_user"
            assert "api_key" in data


@pytest.mark.asyncio
async def test_admin_list_tenants():
    from src.main import app
    from src.config import settings
    from src.tenant import tenant_manager

    await tenant_manager.create_tenant("list_test_user")

    with patch.object(settings, "admin_api_key", "test_admin_key"):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/admin/tenants", headers={"X-API-Key": "test_admin_key"}
            )
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
        response = await client.post("/admin/tenants", params={"name": "new_user"})
        assert response.status_code == 401
