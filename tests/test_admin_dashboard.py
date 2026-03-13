import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio


ADMIN_PASSWORD = "test-admin-password-123"


@pytest.fixture(autouse=True)
def setup_admin_password(monkeypatch):
    from src import config

    monkeypatch.setattr(config.settings, "admin_password", ADMIN_PASSWORD)
    monkeypatch.setattr(config.settings, "debug", True)
    yield
    monkeypatch.setattr(config.settings, "admin_password", None)
    monkeypatch.setattr(config.settings, "debug", False)


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
    db.save_tenant = AsyncMock()
    db.delete_tenant = AsyncMock()
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
async def test_admin_login_page():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/admin/login")
        assert response.status_code == 200
        assert "Admin Login" in response.text


@pytest.mark.asyncio
async def test_admin_login_success(setup_tenant_manager):
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/admin/login", data={"password": ADMIN_PASSWORD}, follow_redirects=False
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/admin/dashboard"
        assert "admin_session" in response.cookies


@pytest.mark.asyncio
async def test_admin_login_failure(setup_tenant_manager):
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/admin/login",
            data={"password": "wrong-password"},
        )
        assert response.status_code == 401


@pytest.mark.asyncio
async def test_admin_dashboard_requires_auth():
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            "/admin/dashboard", follow_redirects=False, headers={"Accept": "text/html"}
        )
        assert response.status_code == 302
        assert response.headers["location"] == "/admin/login"


@pytest.mark.asyncio
async def test_admin_api_stats(setup_tenant_manager):
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        login_response = await client.post(
            "/admin/login", data={"password": ADMIN_PASSWORD}
        )
        assert login_response.status_code == 302

        response = await client.get("/admin/api/stats")
        assert response.status_code == 200
        data = response.json()
        assert "tenants" in data
        assert "messages" in data
        assert "webhooks" in data


@pytest.mark.asyncio
async def test_admin_fragments_tenants(setup_tenant_manager):
    from src.main import app

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

        response = await client.get("/admin/fragments/tenants")
        assert response.status_code == 200
        assert "No tenants yet" in response.text or "tenant-row" in response.text


@pytest.mark.asyncio
async def test_expandable_tenant_ui(setup_tenant_manager):
    from src.admin.routes import get_tenants_fragment
    from src.tenant import tenant_manager

    tenant, api_key = await tenant_manager.create_tenant("Expandable Test")

    try:
        html = await get_tenants_fragment(session_id="test")
        content = html.body.decode()

        assert "toggleTenantPanel" in content
        assert f"toggleTenantPanel('{tenant.api_key_hash}')" in content
        assert f"chevron-{tenant.api_key_hash}" in content
        assert f"tenant-panel-{tenant.api_key_hash}" in content
        assert "cursor-pointer" in content
    finally:
        await tenant_manager.delete_tenant(api_key)


@pytest.mark.asyncio
async def test_tenant_panel_has_send_form(setup_tenant_manager):
    from src.admin.routes import get_tenant_panel_fragment
    from src.tenant import tenant_manager

    tenant, api_key = await tenant_manager.create_tenant("Panel Send Test")

    try:
        html = await get_tenant_panel_fragment(tenant.api_key_hash, session_id="test")
        content = html.body.decode()

        assert "chat-select-" in content
        assert "manual-jid-" in content
        assert "msg-text-" in content
        assert "sendMsgAsTenant" in content
        assert "Send" in content
    finally:
        await tenant_manager.delete_tenant(api_key)


@pytest.mark.asyncio
async def test_create_tenant_with_form_data(setup_tenant_manager):
    from src.main import app
    from src.tenant import tenant_manager

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

        response = await client.post(
            "/admin/api/tenants",
            data={"name": "Form Test Tenant"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "created"
        assert data["tenant"]["name"] == "Form Test Tenant"
        assert "api_key" in data["tenant"]

        await tenant_manager.delete_tenant(data["tenant"]["api_key"])


@pytest.mark.asyncio
async def test_delete_tenant_without_raw_key(setup_tenant_manager):
    from src.main import app
    from src.tenant import tenant_manager

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post("/admin/login", data={"password": ADMIN_PASSWORD})

        response = await client.post(
            "/admin/api/tenants",
            data={"name": "Delete Test Tenant"},
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert response.status_code == 200
        data = response.json()
        tenant_hash = data["tenant"]["api_key_hash"]

        tenant = tenant_manager._tenants.get(tenant_hash)
        assert tenant is not None

        tenant._raw_api_key = None

        delete_response = await client.delete(f"/admin/api/tenants/{tenant_hash}")
        assert delete_response.status_code == 200
        assert delete_response.json()["status"] == "deleted"

        assert tenant_manager._tenants.get(tenant_hash) is None
