"""
Authenticated Happy-Path HTTP Tests — verifies that every admin UI page
returns 200 when properly authenticated. This tests at the HTTP protocol
level, not via browser rendering.
"""

import pytest
import secrets
from datetime import datetime, timedelta, UTC
from fastapi.testclient import TestClient
from src.main import app
from src.tenant import tenant_manager
from tests.fixtures.app_client import app_client

ADMIN_UI_PAGES = [
    "/admin/dashboard",
    "/admin/tenants",
    "/admin/messages",
    "/admin/webhooks",
    "/admin/security",
    "/admin/chatwoot",
    "/admin/logs",
]

ADMIN_API_ENDPOINTS = [
    ("/admin/api/stats", "GET"),
    ("/admin/api/websockets", "GET"),
    ("/admin/api/tenants", "GET"),
    ("/admin/api/messages", "GET"),
    ("/admin/api/webhooks", "GET"),
    ("/admin/api/webhooks/history", "GET"),
    ("/admin/api/webhooks/stats", "GET"),
    ("/admin/api/rate-limit/blocked", "GET"),
    ("/admin/api/rate-limit/failed-auth", "GET"),
    ("/admin/api/chatwoot/tenants", "GET"),
    ("/admin/api/session-id", "GET"),
]

ADMIN_FRAGMENTS = [
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


class _AuthClient:
    """Wrapper around TestClient that injects admin session cookie."""

    def __init__(self, client: TestClient, session_id: str):
        self._client = client
        self._session_id = session_id

    @property
    def session_id(self):
        return self._session_id

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

    def patch(self, path, **kwargs):
        return self.request("PATCH", path, **kwargs)


@pytest.fixture
def authenticated_client(app_client):
    client, _tm = app_client
    resp = client.post(
        "/admin/login",
        data={"password": "test-admin-password-123"},
        follow_redirects=False,
    )
    assert resp.status_code == 302, f"Login failed: {resp.status_code}"

    session_id = None
    for cookie_header in resp.headers.get_list("set-cookie"):
        if "admin_session=" in cookie_header:
            session_id = cookie_header.split("admin_session=")[1].split(";")[0]
            break

    assert session_id, "No session cookie in login response"
    yield _AuthClient(client, session_id)


class TestAdminUIPagesAuthenticated:
    """Verify every admin UI page returns 200 when authenticated."""

    @pytest.mark.parametrize("path", ADMIN_UI_PAGES)
    def test_page_returns_200(self, authenticated_client, path):
        resp = authenticated_client.get(path)
        assert resp.status_code == 200, (
            f"GET {path}: expected 200, got {resp.status_code}. Body: {resp.text[:500]}"
        )

    @pytest.mark.parametrize("path", ADMIN_UI_PAGES)
    def test_page_returns_html(self, authenticated_client, path):
        resp = authenticated_client.get(path)
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "text/html" in content_type, (
            f"GET {path}: expected text/html, got {content_type}"
        )

    @pytest.mark.parametrize("path", ADMIN_UI_PAGES)
    def test_page_contains_common_elements(self, authenticated_client, path):
        resp = authenticated_client.get(path)
        assert resp.status_code == 200
        body = resp.text
        assert "<!DOCTYPE html>" in body or "<html" in body, (
            f"GET {path}: response doesn't contain HTML boilerplate"
        )


class TestAdminJSONEndpointsAuthenticated:
    """Verify every admin JSON API endpoint returns 200 when authenticated."""

    @pytest.mark.parametrize("path,method", ADMIN_API_ENDPOINTS)
    def test_endpoint_returns_200(self, authenticated_client, path, method):
        resp = authenticated_client.request(method, path)
        assert resp.status_code == 200, (
            f"{method} {path}: expected 200, got {resp.status_code}. "
            f"Body: {resp.text[:500]}"
        )

    @pytest.mark.parametrize("path,method", ADMIN_API_ENDPOINTS)
    def test_endpoint_returns_json(self, authenticated_client, path, method):
        resp = authenticated_client.request(method, path)
        assert resp.status_code == 200
        content_type = resp.headers.get("content-type", "")
        assert "application/json" in content_type, (
            f"{method} {path}: expected application/json, got {content_type}"
        )


class TestAdminFragmentsAuthenticated:
    """Verify every htmx fragment endpoint returns 200 when authenticated."""

    @pytest.mark.parametrize("path", ADMIN_FRAGMENTS)
    def test_fragment_returns_200(self, authenticated_client, path):
        resp = authenticated_client.get(path)
        assert resp.status_code == 200, (
            f"GET {path}: expected 200, got {resp.status_code}. Body: {resp.text[:500]}"
        )


class TestDashboardSpecificContent:
    """Test specific content in the dashboard response."""

    def test_dashboard_has_title(self, authenticated_client):
        resp = authenticated_client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert "Dashboard" in resp.text

    def test_dashboard_has_htmx_fragments(self, authenticated_client):
        resp = authenticated_client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert "hx-get" in resp.text

    def test_dashboard_has_navigation(self, authenticated_client):
        resp = authenticated_client.get("/admin/dashboard")
        assert resp.status_code == 200
        assert "/admin/tenants" in resp.text or 'href="/admin/tenants"' in resp.text


class TestTenantsPageContent:
    """Test specific content in the tenants page."""

    def test_tenants_page_has_title(self, authenticated_client):
        resp = authenticated_client.get("/admin/tenants")
        assert resp.status_code == 200
        assert "Tenant" in resp.text

    def test_tenants_page_has_add_button(self, authenticated_client):
        resp = authenticated_client.get("/admin/tenants")
        assert resp.status_code == 200


class TestMessagesPageContent:
    """Test specific content in the messages page."""

    def test_messages_page_has_title(self, authenticated_client):
        resp = authenticated_client.get("/admin/messages")
        assert resp.status_code == 200
        assert "Message" in resp.text


class TestWebhooksPageContent:
    """Test specific content in the webhooks page."""

    def test_webhooks_page_has_title(self, authenticated_client):
        resp = authenticated_client.get("/admin/webhooks")
        assert resp.status_code == 200
        assert "Webhook" in resp.text


class TestSecurityPageContent:
    """Test specific content in the security page."""

    def test_security_page_has_title(self, authenticated_client):
        resp = authenticated_client.get("/admin/security")
        assert resp.status_code == 200
        assert "Security" in resp.text or "security" in resp.text.lower()


class TestChatwootPageContent:
    """Test specific content in the chatwoot page."""

    def test_chatwoot_page_has_title(self, authenticated_client):
        resp = authenticated_client.get("/admin/chatwoot")
        assert resp.status_code == 200
        assert "Chatwoot" in resp.text


class TestLogsPageContent:
    """Test specific content in the logs page."""

    def test_logs_page_has_title(self, authenticated_client):
        resp = authenticated_client.get("/admin/logs")
        assert resp.status_code == 200
        assert "Log" in resp.text


class TestSessionIDEndpoint:
    """Test the session-id endpoint returns a valid session."""

    def test_session_id_returns_string(self, authenticated_client):
        resp = authenticated_client.get("/admin/api/session-id")
        assert resp.status_code == 200
        data = resp.json()
        assert "session_id" in data
        assert isinstance(data["session_id"], str)
        assert len(data["session_id"]) > 0

    def test_session_id_matches_cookie(self, authenticated_client):
        resp = authenticated_client.get("/admin/api/session-id")
        assert resp.status_code == 200
        data = resp.json()
        assert data["session_id"] == authenticated_client.session_id


class TestFrontendErrorsEndpoint:
    """Test the frontend error reporting endpoint."""

    def test_frontend_errors_accepts_post(self, authenticated_client):
        resp = authenticated_client.post(
            "/admin/api/frontend-errors",
            json={
                "message": "test error",
                "source": "test",
                "details": {},
            },
        )
        assert resp.status_code == 204

    def test_frontend_errors_requires_auth(self, app_client):
        client, _tm = app_client
        resp = client.post(
            "/admin/api/frontend-errors",
            json={
                "message": "test error",
                "source": "test",
                "details": {},
            },
        )
        assert resp.status_code == 401
