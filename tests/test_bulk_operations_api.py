import pytest
from unittest.mock import AsyncMock, patch, Mock
from fastapi.testclient import TestClient
from fastapi import FastAPI
from src.tenant import Tenant
from src.admin.auth import require_admin_session


class TestBulkDeleteEndpoint:
    @pytest.mark.asyncio
    async def test_bulk_delete_returns_correct_response_shape(self):
        tenant = Tenant(
            api_key_hash="test_bulk_del_hash",
            name="bulk_del_test",
            has_auth=False,
        )

        with patch("src.admin.routes.tenant_manager") as mock_mgr:
            mock_mgr._tenants = {tenant.api_key_hash: tenant}
            mock_mgr.delete_tenant_by_hash = AsyncMock(return_value=True)
            mock_mgr._db = None
            mock_ws = AsyncMock()

            with patch(
                "src.admin.routes.require_admin_session", return_value="session"
            ):
                with patch("src.admin.routes.admin_ws_manager", mock_ws):
                    from src.admin.routes import bulk_delete_tenants
                    from src.admin.routes import BulkTenantReconnectRequest

                    data = BulkTenantReconnectRequest(
                        tenant_hashes=[tenant.api_key_hash]
                    )
                    result = await bulk_delete_tenants(data, "session")

                    assert "deleted" in result
                    assert "failed" in result
                    assert result["deleted"] == 1
                    assert result["failed"] == 0
                    assert "detail" not in result

    @pytest.mark.asyncio
    async def test_bulk_delete_not_found_counts_as_failed(self):
        with patch("src.admin.routes.tenant_manager") as mock_mgr:
            mock_mgr._tenants = {}
            mock_mgr._db = None
            mock_ws = AsyncMock()

            with patch(
                "src.admin.routes.require_admin_session", return_value="session"
            ):
                with patch("src.admin.routes.admin_ws_manager", mock_ws):
                    from src.admin.routes import bulk_delete_tenants
                    from src.admin.routes import BulkTenantReconnectRequest

                    data = BulkTenantReconnectRequest(
                        tenant_hashes=["nonexistent_hash"]
                    )
                    result = await bulk_delete_tenants(data, "session")

                    assert "deleted" in result
                    assert "failed" in result
                    assert result["deleted"] == 0
                    assert result["failed"] == 1
                    assert result["results"][0]["status"] == "not_found"

    def test_bulk_delete_route_reaches_bulk_handler_not_single_tenant_handler(self):
        """
        If DELETE /admin/api/tenants/bulk is shadowed by
        DELETE /admin/api/tenants/{tenant_hash}, the single-tenant handler
        runs with tenant_hash='bulk', finds no tenant, returns 404.

        The bulk handler returns 200 with {'deleted': N, 'failed': N}.
        """
        app = FastAPI()
        from src.admin.routes import api_router

        app.include_router(api_router)
        app.dependency_overrides[require_admin_session] = lambda: "session"

        try:
            with patch("src.admin.routes.tenant_manager") as mock_mgr:
                mock_mgr._tenants = {}
                mock_mgr._db = None
                mock_mgr.delete_tenant_by_hash = AsyncMock(return_value=False)
                mock_ws = AsyncMock()
                mock_ws.broadcast = AsyncMock()

                with patch("src.admin.routes.admin_ws_manager", mock_ws):
                    client = TestClient(app, raise_server_exceptions=False)
                    response = client.request(
                        "DELETE",
                        "/admin/api/tenants/bulk",
                        json={"tenant_hashes": ["nonexistent"]},
                    )

            assert response.status_code == 200, (
                f"Expected 200 from bulk handler, got {response.status_code} "
                f"— route may be shadowed by /tenants/{{tenant_hash}}. "
                f"Response: {response.json()}"
            )
            data = response.json()
            assert "deleted" in data, (
                f"Response missing 'deleted' key — hit wrong handler. Got: {data}"
            )
            assert "failed" in data, (
                f"Response missing 'failed' key — hit wrong handler. Got: {data}"
            )
        finally:
            app.dependency_overrides.clear()


class TestBulkReconnectEndpoint:
    @pytest.mark.asyncio
    async def test_bulk_reconnect_returns_correct_response_shape(self):
        tenant = Tenant(
            api_key_hash="test_bulk_recon_hash",
            name="bulk_recon_test",
            has_auth=False,
        )

        mock_bridge = Mock()
        mock_bridge.login = AsyncMock(return_value={"status": "connecting"})

        with patch("src.admin.routes.tenant_manager") as mock_mgr:
            mock_mgr._tenants = {tenant.api_key_hash: tenant}
            tenant.bridge = None
            mock_mgr.get_or_create_bridge = AsyncMock(return_value=mock_bridge)

            with patch(
                "src.admin.routes.require_admin_session", return_value="session"
            ):
                from src.admin.routes import bulk_reconnect_tenants
                from src.admin.routes import BulkTenantReconnectRequest

                data = BulkTenantReconnectRequest(tenant_hashes=[tenant.api_key_hash])
                result = await bulk_reconnect_tenants(data, "session")

                assert "successful" in result
                assert "failed" in result
                assert result["successful"] == 1
                assert result["failed"] == 0

    def test_bulk_reconnect_route_reaches_bulk_handler_not_single_tenant_handler(self):
        """
        If POST /admin/api/tenants/bulk/reconnect is shadowed by
        POST /admin/api/tenants/{tenant_hash}/reconnect, the single-tenant
        handler runs with tenant_hash='bulk', finds no tenant, returns 404.

        The bulk handler returns 200 with {'successful': N, 'failed': N}.
        """
        app = FastAPI()
        from src.admin.routes import api_router

        app.include_router(api_router)
        app.dependency_overrides[require_admin_session] = lambda: "session"

        try:
            with patch("src.admin.routes.tenant_manager") as mock_mgr:
                mock_mgr._tenants = {}
                mock_mgr.get_or_create_bridge = AsyncMock()

                client = TestClient(app, raise_server_exceptions=False)
                response = client.post(
                    "/admin/api/tenants/bulk/reconnect",
                    json={"tenant_hashes": ["nonexistent"]},
                )

            assert response.status_code == 200, (
                f"Expected 200 from bulk handler, got {response.status_code} "
                f"— route may be shadowed by /tenants/{{tenant_hash}}/reconnect. "
                f"Response: {response.json()}"
            )
            data = response.json()
            assert "successful" in data, (
                f"Response missing 'successful' key — hit wrong handler. Got: {data}"
            )
            assert "failed" in data, (
                f"Response missing 'failed' key — hit wrong handler. Got: {data}"
            )
        finally:
            app.dependency_overrides.clear()
