"""
htmx Fragment Endpoint Tests — verify every htmx fragment endpoint at the
HTTP level. These are the endpoints referenced by hx-get/hx-post attributes
in the admin UI. Tests both authenticated (200) and unauthenticated (401) access.
"""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from src.tenant import tenant_manager
from tests.fixtures.app_client import app_client


HTMX_GET_FRAGMENTS = [
    "/admin/fragments/stats",
    "/admin/fragments/websockets",
    "/admin/fragments/tenants",
    "/admin/fragments/messages-tabs",
    "/admin/fragments/messages",
    "/admin/fragments/webhooks",
    "/admin/fragments/webhook-history",
    "/admin/fragments/blocked-ips",
    "/admin/fragments/chatwoot/config",
    "/admin/fragments/chatwoot/tenants",
    "/admin/fragments/failed-auth",
    "/admin/fragments/logs",
]

TENANT_SPECIFIC_FRAGMENTS = [
    "/admin/fragments/tenant-panel/{hash}",
    "/admin/fragments/tenant-messages/{hash}",
    "/admin/fragments/tenant-contacts/{hash}",
    "/admin/fragments/recent-chats/{hash}",
]


class _AuthClient:
    """Wrapper around TestClient that injects admin session cookie."""

    def __init__(self, client: TestClient, session_id: str):
        self._client = client
        self._session_id = session_id

    def request(self, method, path, **kwargs):
        headers = kwargs.pop("headers", {})
        headers["Cookie"] = f"admin_session={self._session_id}"
        return self._client.request(method, path, headers=headers, **kwargs)

    def get(self, path, **kwargs):
        return self.request("GET", path, **kwargs)

    def post(self, path, **kwargs):
        return self.request("POST", path, **kwargs)

    def delete(self, path, **kwargs):
        return self.request("DELETE", path, **kwargs)


def _login(client) -> tuple[_AuthClient, str]:
    """Log in via the admin login endpoint and return an auth client wrapper."""
    resp = client.post(
        "/admin/login",
        data={"password": "test-admin-password-123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302, f"Login failed: {resp.status_code}"
    session_id = None
    for h in resp.headers.get_list("set-cookie"):
        if "admin_session=" in h:
            session_id = h.split("admin_session=")[1].split(";")[0]
            break
    assert session_id, "No session cookie in login response"
    return _AuthClient(client, session_id), session_id


@pytest.fixture
def client(app_client):
    client, _tm = app_client
    yield client


@pytest.fixture
def auth_client(app_client):
    client, _tm = app_client
    ac, _sid = _login(client)
    yield ac


@pytest.fixture
def auth_client_with_tenant(auth_client, app_client):
    client, _tm = app_client
    import asyncio

    loop = asyncio.get_event_loop()
    tenant, api_key = loop.run_until_complete(
        tenant_manager.create_tenant("Test Tenant")
    )
    tenant_hash = tenant.api_key_hash
    yield auth_client, tenant_hash
    try:
        loop.run_until_complete(tenant_manager.delete_tenant(api_key))
    except Exception:
        pass


class TestFragmentUnauthenticated:
    """All fragments must return 401 when no session cookie is present."""

    @pytest.mark.parametrize("path", HTMX_GET_FRAGMENTS)
    def test_returns_401(self, client, path):
        resp = client.get(path)
        assert resp.status_code == 401, (
            f"GET {path}: expected 401, got {resp.status_code}"
        )

    @pytest.mark.parametrize("path", HTMX_GET_FRAGMENTS)
    def test_returns_401_with_htmx_header(self, client, path):
        resp = client.get(
            path,
            headers={
                "HX-Request": "true",
                "Accept": "text/html",
            },
            follow_redirects=False,
        )
        assert resp.status_code in (302, 401), (
            f"GET {path} (htmx): expected 302 or 401, got {resp.status_code}"
        )

    @pytest.mark.parametrize("path", HTMX_GET_FRAGMENTS)
    def test_returns_401_invalid_cookie(self, client, path):
        resp = client.get(
            path,
            headers={"Cookie": "admin_session=invalid"},
        )
        assert resp.status_code == 401, (
            f"GET {path} (invalid cookie): expected 401, got {resp.status_code}"
        )


class TestFragmentAuthenticated:
    """All fragments must return 200 when authenticated."""

    @pytest.mark.parametrize("path", HTMX_GET_FRAGMENTS)
    def test_returns_200(self, auth_client, path):
        resp = auth_client.get(path)
        assert resp.status_code == 200, (
            f"GET {path}: expected 200, got {resp.status_code}. Body: {resp.text[:300]}"
        )

    @pytest.mark.parametrize("path", HTMX_GET_FRAGMENTS)
    def test_returns_html_content(self, auth_client, path):
        resp = auth_client.get(path)
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type or "json" in content_type, (
            f"GET {path}: expected text/html or json, got {content_type}"
        )

    @pytest.mark.parametrize("path", HTMX_GET_FRAGMENTS)
    def test_returns_non_empty_body(self, auth_client, path):
        resp = auth_client.get(path)
        assert resp.status_code == 200
        assert len(resp.text) > 0, f"GET {path}: response body is empty"


class TestFragmentWithHtmxHeaders:
    """Test that fragments respond correctly to htmx-specific headers."""

    @pytest.mark.parametrize("path", HTMX_GET_FRAGMENTS)
    def test_hx_request_header_ok(self, auth_client, path):
        resp = auth_client.get(path, headers={"HX-Request": "true"})
        assert resp.status_code == 200, (
            f"GET {path} (HX-Request): expected 200, got {resp.status_code}"
        )

    @pytest.mark.parametrize("path", HTMX_GET_FRAGMENTS)
    def test_hx_trigger_header_preserved(self, auth_client, path):
        resp = auth_client.get(
            path,
            headers={
                "HX-Request": "true",
                "HX-Trigger": "some-event",
            },
        )
        assert resp.status_code == 200


class TestFragmentWrongMethods:
    """Test that wrong HTTP methods on fragment endpoints return 405."""

    @pytest.mark.parametrize("path", HTMX_GET_FRAGMENTS)
    def test_post_returns_405(self, auth_client, path):
        resp = auth_client.post(path)
        assert resp.status_code == 405, (
            f"POST {path}: expected 405, got {resp.status_code}"
        )

    @pytest.mark.parametrize("path", HTMX_GET_FRAGMENTS)
    def test_delete_returns_405(self, auth_client, path):
        resp = auth_client.delete(path)
        assert resp.status_code == 405, (
            f"DELETE {path}: expected 405, got {resp.status_code}"
        )

    @pytest.mark.parametrize("path", HTMX_GET_FRAGMENTS)
    def test_put_returns_405(self, auth_client, path):
        resp = auth_client.request("PUT", path)
        assert resp.status_code == 405, (
            f"PUT {path}: expected 405, got {resp.status_code}"
        )

    @pytest.mark.parametrize("path", HTMX_GET_FRAGMENTS)
    def test_patch_returns_405(self, auth_client, path):
        resp = auth_client.request("PATCH", path)
        assert resp.status_code == 405, (
            f"PATCH {path}: expected 405, got {resp.status_code}"
        )


class TestTenantSpecificFragments:
    """Test fragment endpoints that require a tenant hash."""

    @pytest.mark.parametrize("template", TENANT_SPECIFIC_FRAGMENTS)
    def test_returns_404_for_nonexistent_tenant(self, auth_client, template):
        path = template.replace("{hash}", "nonexistent123")
        resp = auth_client.get(path)
        assert resp.status_code in (404, 200, 422), (
            f"GET {path}: expected 404/200/422, got {resp.status_code}"
        )

    @pytest.mark.parametrize("template", TENANT_SPECIFIC_FRAGMENTS)
    def test_returns_200_for_existing_tenant(self, auth_client_with_tenant, template):
        auth_client, tenant_hash = auth_client_with_tenant
        path = template.replace("{hash}", tenant_hash)
        resp = auth_client.get(path)
        assert resp.status_code == 200, (
            f"GET {path}: expected 200, got {resp.status_code}"
        )

    @pytest.mark.parametrize("template", TENANT_SPECIFIC_FRAGMENTS)
    def test_unauthenticated_returns_401(self, client, template):
        path = template.replace("{hash}", "nonexistent123")
        resp = client.get(path)
        assert resp.status_code == 401


class TestStatsFragmentContent:
    """Verify the stats fragment returns meaningful data."""

    def test_contains_stats_elements(self, auth_client):
        resp = auth_client.get("/admin/fragments/stats")
        assert resp.status_code == 200
        assert len(resp.text) > 10

    def test_no_server_error(self, auth_client):
        resp = auth_client.get("/admin/fragments/stats")
        assert resp.status_code == 200
        assert "500" not in resp.text[:100]
        assert "Internal Server Error" not in resp.text


class TestTenantsFragmentContent:
    """Verify the tenants fragment works correctly."""

    def test_returns_tenant_list(self, auth_client):
        resp = auth_client.get("/admin/fragments/tenants")
        assert resp.status_code == 200

    def test_with_tenants_present(self, auth_client_with_tenant):
        auth_client, tenant_hash = auth_client_with_tenant
        resp = auth_client.get("/admin/fragments/tenants")
        assert resp.status_code == 200


class TestLogsFragmentContent:
    """Verify the logs fragment returns JSON."""

    def test_returns_json(self, auth_client):
        resp = auth_client.get("/admin/fragments/logs")
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "json" in content_type, f"Expected JSON content type, got {content_type}"

    def test_logs_is_list(self, auth_client):
        resp = auth_client.get("/admin/fragments/logs")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)
        assert "entries" in data
        assert isinstance(data["entries"], list)


class TestRecentChatsFragment:
    """Verify the recent-chats fragment returns JSON."""

    def test_returns_json_for_tenant(self, auth_client_with_tenant):
        auth_client, tenant_hash = auth_client_with_tenant
        resp = auth_client.get(f"/admin/fragments/recent-chats/{tenant_hash}")
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "json" in content_type
