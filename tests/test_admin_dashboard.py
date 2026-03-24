import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock
import asyncio

from tests.conftest import ADMIN_PASSWORD


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
    db.update_admin_session_expiry = AsyncMock()
    return db


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
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/admin/login?error=1" in response.headers["location"]


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


class TestAdminSessionRefresh:
    @pytest.mark.asyncio
    async def test_validate_session_refreshes_expiry(self, mock_db):
        from src.admin.auth import AdminSession
        from datetime import datetime, timedelta, UTC

        near_expiry = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        mock_db.get_admin_session = AsyncMock(
            return_value={"id": "test-session-id", "expires_at": near_expiry}
        )
        mock_db.update_admin_session_expiry = AsyncMock()
        session = AdminSession(mock_db)

        result = await session.validate_session("test-session-id")

        assert result is True
        mock_db.update_admin_session_expiry.assert_called_once()
        call_args = mock_db.update_admin_session_expiry.call_args
        assert call_args[0][0] == "test-session-id"
        assert isinstance(call_args[0][1], datetime)

    @pytest.mark.asyncio
    async def test_validate_session_returns_false_for_invalid(self, mock_db):
        from src.admin.auth import AdminSession

        mock_db.get_admin_session = AsyncMock(return_value=None)
        mock_db.update_admin_session_expiry = AsyncMock()
        session = AdminSession(mock_db)

        result = await session.validate_session("invalid-session")

        assert result is False
        mock_db.update_admin_session_expiry.assert_not_called()

    @pytest.mark.asyncio
    async def test_session_duration_constant(self, mock_db):
        from src.admin.auth import AdminSession

        assert AdminSession.SESSION_DURATION_HOURS == 24

    @pytest.mark.asyncio
    async def test_create_session_uses_duration_constant(self, mock_db):
        from src.admin.auth import AdminSession
        from unittest.mock import MagicMock
        from datetime import datetime, timedelta, UTC

        session = AdminSession(mock_db)
        request = MagicMock()
        request.client.host = "127.0.0.1"
        request.headers.get = lambda x: "test-agent"

        await session.create_session(request, ADMIN_PASSWORD)

        call_args = mock_db.create_admin_session.call_args
        expires_at = call_args.kwargs["expires_at"]
        expected_delta = timedelta(hours=AdminSession.SESSION_DURATION_HOURS)
        actual_delta = expires_at - datetime.now(UTC)
        tolerance = timedelta(seconds=5)
        assert abs(expected_delta - actual_delta) < tolerance


class TestSQLiteTenantTransaction:
    @pytest.mark.asyncio
    async def test_save_tenant_uses_transaction_on_sqlite(self, tmp_path):
        from src.store.database import Database
        from datetime import datetime, UTC

        db_path = tmp_path / "test.db"
        db = Database(f"sqlite://{db_path}", tmp_path)
        await db.connect()

        try:
            await db.save_tenant(
                api_key_hash="test_hash_123",
                name="Test Tenant",
                created_at=datetime.now(UTC),
                webhook_urls=["https://example.com/webhook"],
            )

            tenants = await db.load_tenants()
            assert len(tenants) == 1
            assert tenants[0]["name"] == "Test Tenant"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_save_tenant_rollback_on_error(self, tmp_path):
        from src.store.database import Database
        from datetime import datetime, UTC
        from unittest.mock import patch, AsyncMock

        db_path = tmp_path / "test.db"
        db = Database(f"sqlite://{db_path}", tmp_path)
        await db.connect()

        try:
            await db.save_tenant(
                api_key_hash="existing_tenant",
                name="Existing Tenant",
                created_at=datetime.now(UTC),
                webhook_urls=[],
            )

            original_execute = db._pool.execute
            call_count = [0]

            async def failing_execute(query, *args):
                call_count[0] += 1
                if "INSERT OR REPLACE" in query:
                    raise Exception("Simulated error")
                return await original_execute(query, *args)

            with patch.object(db._pool, "execute", side_effect=failing_execute):
                with pytest.raises(Exception, match="Simulated error"):
                    await db.save_tenant(
                        api_key_hash="new_tenant",
                        name="New Tenant",
                        created_at=datetime.now(UTC),
                        webhook_urls=[],
                    )

            tenants = await db.load_tenants()
            assert len(tenants) == 1
            assert tenants[0]["api_key_hash"] == "existing_tenant"
        finally:
            await db.close()

    @pytest.mark.asyncio
    async def test_save_tenant_preserves_existing_fields_on_update(self, tmp_path):
        from src.store.database import Database
        from datetime import datetime, UTC

        db_path = tmp_path / "test.db"
        db = Database(f"sqlite://{db_path}", tmp_path)
        await db.connect()

        try:
            await db.save_tenant(
                api_key_hash="preserve_test",
                name="Original Name",
                created_at=datetime.now(UTC),
                webhook_urls=["https://example.com/webhook"],
            )

            await db.update_session_state(
                "preserve_test",
                "connected",
                "test_jid",
                "test_phone",
                "test_name",
                True,
            )

            await db.save_tenant(
                api_key_hash="preserve_test",
                name="Updated Name",
                created_at=datetime.now(UTC),
                webhook_urls=["https://example.com/new_webhook"],
            )

            tenants = await db.load_tenants()
            tenant = [t for t in tenants if t["api_key_hash"] == "preserve_test"][0]
            assert tenant["name"] == "Updated Name"
            assert tenant["connection_state"] == "connected"
            assert tenant["self_jid"] == "test_jid"
            assert tenant["self_phone"] == "test_phone"
            assert tenant["self_name"] == "test_name"
            assert tenant["has_auth"] is True
        finally:
            await db.close()
