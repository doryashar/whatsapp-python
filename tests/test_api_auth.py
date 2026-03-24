import pytest
from unittest.mock import MagicMock, patch
from fastapi import FastAPI, Depends, Request, Header
from fastapi.testclient import TestClient
from fastapi import HTTPException

from src.api.auth import get_api_key, get_tenant, get_admin_key
from src.tenant import Tenant


def _make_request(client_ip: str = "1.2.3.4") -> Request:
    scope = {
        "type": "http",
        "method": "GET",
        "headers": [],
        "query_string": b"",
        "path": "/test",
    }
    request = Request(scope)
    request._client = MagicMock()
    request._client.host = client_ip
    return request


class TestGetApiKey:
    def test_x_api_key_header(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_rl.is_blocked.return_value = False
            result = get_api_key(request, x_api_key="my-key", authorization=None)
        assert result == "my-key"

    def test_bearer_token(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_rl.is_blocked.return_value = False
            result = get_api_key(request, x_api_key=None, authorization="Bearer my-key")
        assert result == "my-key"

    def test_bearer_token_case_mismatch_rejected(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_rl.is_blocked.return_value = False
            with pytest.raises(HTTPException) as exc_info:
                get_api_key(request, x_api_key=None, authorization="bearer my-key")
        assert exc_info.value.status_code == 401

    def test_x_api_key_takes_precedence_over_bearer(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_rl.is_blocked.return_value = False
            result = get_api_key(
                request, x_api_key="x-key", authorization="Bearer b-key"
            )
        assert result == "x-key"

    def test_missing_key_returns_401(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_rl.is_blocked.return_value = False
            with pytest.raises(HTTPException) as exc_info:
                get_api_key(request, x_api_key=None, authorization=None)
        assert exc_info.value.status_code == 401
        assert "API key required" in exc_info.value.detail
        mock_rl.record_failed_auth.assert_called_once_with("1.2.3.4")

    def test_blocked_ip_returns_429(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_rl.is_blocked.return_value = True
            with pytest.raises(HTTPException) as exc_info:
                get_api_key(request, x_api_key="my-key", authorization=None)
        assert exc_info.value.status_code == 429
        assert "blocked" in exc_info.value.detail

    def test_bearer_without_prefix_ignored(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_rl.is_blocked.return_value = False
            with pytest.raises(HTTPException) as exc_info:
                get_api_key(request, x_api_key=None, authorization="NotBearer token")
        assert exc_info.value.status_code == 401

    def test_empty_bearer_returns_401(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_rl.is_blocked.return_value = False
            with pytest.raises(HTTPException) as exc_info:
                get_api_key(request, x_api_key=None, authorization="Bearer ")
        assert exc_info.value.status_code == 401

    def test_uses_get_client_ip(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="10.0.0.1") as mock_ip,
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_rl.is_blocked.return_value = False
            get_api_key(request, x_api_key="k", authorization=None)
        mock_ip.assert_called_once_with(request)


class TestGetTenant:
    @pytest.fixture
    def mock_tenant(self):
        t = MagicMock(spec=Tenant)
        t.name = "TestTenant"
        return t

    def test_valid_key(self, mock_tenant):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.tenant_manager") as mock_tm,
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_tm.get_tenant_by_key.return_value = mock_tenant
            result = get_tenant(request, api_key="valid-key")
        assert result is mock_tenant
        mock_tm.get_tenant_by_key.assert_called_once_with("valid-key")
        mock_rl.clear_failed_auth.assert_called_once_with("1.2.3.4")

    def test_invalid_key_returns_401(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.tenant_manager") as mock_tm,
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_tm.get_tenant_by_key.return_value = None
            mock_rl.record_failed_auth.return_value = (3, False)
            with pytest.raises(HTTPException) as exc_info:
                get_tenant(request, api_key="bad-key")
        assert exc_info.value.status_code == 401
        assert "Invalid API key" in exc_info.value.detail
        assert "3/" in exc_info.value.detail

    def test_invalid_key_blocks_after_max_attempts(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.tenant_manager") as mock_tm,
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_tm.get_tenant_by_key.return_value = None
            mock_rl.record_failed_auth.return_value = (5, True)
            with pytest.raises(HTTPException) as exc_info:
                get_tenant(request, api_key="bad-key")
        assert exc_info.value.status_code == 401
        assert "blocked" in exc_info.value.detail

    def test_blocked_ip_returns_401(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.tenant_manager") as mock_tm,
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_tm.get_tenant_by_key.return_value = None
            mock_rl.record_failed_auth.return_value = (10, True)
            with pytest.raises(HTTPException) as exc_info:
                get_tenant(request, api_key="bad-key")
        assert exc_info.value.status_code == 401

    def test_clears_failed_auth_on_success(self, mock_tenant):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.tenant_manager") as mock_tm,
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_tm.get_tenant_by_key.return_value = mock_tenant
            get_tenant(request, api_key="valid-key")
        mock_rl.clear_failed_auth.assert_called_once_with("1.2.3.4")


class TestGetAdminKey:
    def test_valid_admin_key(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
            patch("src.api.auth.settings") as mock_settings,
        ):
            mock_rl.is_blocked.return_value = False
            mock_settings.admin_api_key = "super-secret-admin-key"
            result = get_admin_key(
                request, x_api_key="super-secret-admin-key", authorization=None
            )
        assert result == "super-secret-admin-key"
        mock_rl.clear_failed_auth.assert_called_once_with("1.2.3.4")

    def test_valid_admin_key_via_bearer(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
            patch("src.api.auth.settings") as mock_settings,
        ):
            mock_rl.is_blocked.return_value = False
            mock_settings.admin_api_key = "super-secret-admin-key"
            result = get_admin_key(
                request, x_api_key=None, authorization="Bearer super-secret-admin-key"
            )
        assert result == "super-secret-admin-key"

    def test_invalid_admin_key_returns_401(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
            patch("src.api.auth.settings") as mock_settings,
        ):
            mock_rl.is_blocked.return_value = False
            mock_settings.admin_api_key = "correct-key"
            mock_rl.record_failed_auth.return_value = (2, False)
            with pytest.raises(HTTPException) as exc_info:
                get_admin_key(request, x_api_key="wrong-key", authorization=None)
        assert exc_info.value.status_code == 401
        assert "Invalid admin API key" in exc_info.value.detail

    def test_missing_key_returns_401(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_rl.is_blocked.return_value = False
            with pytest.raises(HTTPException) as exc_info:
                get_admin_key(request, x_api_key=None, authorization=None)
        assert exc_info.value.status_code == 401
        assert "Admin API key required" in exc_info.value.detail
        mock_rl.record_failed_auth.assert_called_once_with("1.2.3.4")

    def test_no_admin_key_configured_returns_503(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
            patch("src.api.auth.settings") as mock_settings,
        ):
            mock_rl.is_blocked.return_value = False
            mock_settings.admin_api_key = ""
            with pytest.raises(HTTPException) as exc_info:
                get_admin_key(request, x_api_key="some-key", authorization=None)
        assert exc_info.value.status_code == 503
        assert "not configured" in exc_info.value.detail

    def test_blocked_ip_returns_429(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
        ):
            mock_rl.is_blocked.return_value = True
            with pytest.raises(HTTPException) as exc_info:
                get_admin_key(request, x_api_key="admin-key", authorization=None)
        assert exc_info.value.status_code == 429

    def test_failed_auth_tracking(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
            patch("src.api.auth.settings") as mock_settings,
        ):
            mock_rl.is_blocked.return_value = False
            mock_settings.admin_api_key = "correct-key"
            mock_rl.record_failed_auth.return_value = (4, False)
            with pytest.raises(HTTPException):
                get_admin_key(request, x_api_key="wrong-key", authorization=None)
        mock_rl.record_failed_auth.assert_called_once_with("1.2.3.4")

    def test_blocked_after_max_failed_auth(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
            patch("src.api.auth.settings") as mock_settings,
        ):
            mock_rl.is_blocked.return_value = False
            mock_settings.admin_api_key = "correct-key"
            mock_rl.record_failed_auth.return_value = (5, True)
            with pytest.raises(HTTPException) as exc_info:
                get_admin_key(request, x_api_key="wrong-key", authorization=None)
        assert exc_info.value.status_code == 401
        assert "blocked" in exc_info.value.detail

    def test_clears_failed_auth_on_success(self):
        request = _make_request()
        with (
            patch("src.api.auth.get_client_ip", return_value="1.2.3.4"),
            patch("src.api.auth.rate_limiter") as mock_rl,
            patch("src.api.auth.settings") as mock_settings,
        ):
            mock_rl.is_blocked.return_value = False
            mock_settings.admin_api_key = "admin-key"
            get_admin_key(request, x_api_key="admin-key", authorization=None)
        mock_rl.clear_failed_auth.assert_called_once_with("1.2.3.4")


class TestDependencyOverride:
    def test_override_get_api_key_in_app(self):
        from src.api.auth import get_api_key as original_get_api_key
        from src.tenant import Tenant as RealTenant

        app = FastAPI()
        app.dependency_overrides[original_get_api_key] = lambda: "overridden-key"

        @app.get("/test-api-key")
        async def ep(key: str = Depends(original_get_api_key)):
            return {"key": key}

        client = TestClient(app)
        resp = client.get("/test-api-key")
        assert resp.status_code == 200
        assert resp.json() == {"key": "overridden-key"}

    def test_override_get_tenant_in_app(self):
        from src.api.auth import get_tenant as original_get_tenant

        mock_t = MagicMock(spec=Tenant)
        mock_t.name = "Overridden"

        app = FastAPI()
        app.dependency_overrides[original_get_tenant] = lambda: mock_t

        @app.get("/test-tenant")
        async def ep(tenant: Tenant = Depends(original_get_tenant)):
            return {"name": tenant.name}

        client = TestClient(app)
        resp = client.get("/test-tenant")
        assert resp.status_code == 200
        assert resp.json() == {"name": "Overridden"}

    def test_override_get_admin_key_in_app(self):
        from src.api.auth import get_admin_key as original_get_admin_key

        app = FastAPI()
        app.dependency_overrides[original_get_admin_key] = lambda: "admin-override"

        @app.get("/test-admin")
        async def ep(key: str = Depends(original_get_admin_key)):
            return {"key": key}

        client = TestClient(app)
        resp = client.get("/test-admin")
        assert resp.status_code == 200
        assert resp.json() == {"key": "admin-override"}
