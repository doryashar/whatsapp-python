"""
Redirect Chain Tests — verify all admin redirects with follow_redirects=False
to catch 303 vs 302 issues, wrong redirect targets, and method preservation bugs.
"""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from tests.fixtures.app_client import app_client


@pytest.fixture
def client(app_client):
    raw_client, _tm = app_client
    yield raw_client


class TestAdminRootRedirect:
    """Test GET /admin/ → /admin/dashboard redirect."""

    def test_admin_root_redirects_to_dashboard(self, client):
        resp = client.get(
            "/admin/", follow_redirects=False, headers={"Accept": "text/html"}
        )
        assert resp.status_code in (302, 307), f"Expected 3xx, got {resp.status_code}"
        location = resp.headers.get("location", "")
        assert "/admin/dashboard" in location, (
            f"Expected /admin/dashboard in Location, got {location}"
        )

    def test_admin_root_redirects_with_302_not_307(self, client):
        resp = client.get("/admin/", follow_redirects=False)
        assert resp.status_code == 302, f"Expected 302 redirect, got {resp.status_code}"
        location = resp.headers.get("location", "")
        assert "/admin/dashboard" in location

    def test_admin_root_without_trailing_slash_redirects(self, client):
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code in (302, 303, 307, 404, 200)


class TestAdminLoginRedirects:
    """Test login form redirect behavior."""

    def test_valid_login_redirects_to_dashboard(self, client):
        resp = client.post(
            "/admin/login",
            data={"password": "test-admin-password-123"},
            follow_redirects=False,
        )
        assert resp.status_code == 302, f"Expected 302, got {resp.status_code}"
        location = resp.headers.get("location", "")
        assert location == "/admin/dashboard", (
            f"Expected Location: /admin/dashboard, got {location}"
        )

    def test_invalid_login_redirects_to_login_with_error(self, client):
        resp = client.post(
            "/admin/login",
            data={"password": "wrong-password"},
            follow_redirects=False,
        )
        assert resp.status_code == 302, f"Expected 302, got {resp.status_code}"
        location = resp.headers.get("location", "")
        assert "/admin/login" in location, (
            f"Expected redirect to /admin/login, got {location}"
        )
        assert "error" in location, f"Expected error param in redirect, got {location}"

    def test_login_redirect_is_302(self, client):
        resp = client.post(
            "/admin/login",
            data={"password": "test-admin-password-123"},
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            f"Login redirect should use 302, got {resp.status_code}. "
            f"303 or 307 could cause issues."
        )

    def test_admin_root_redirects_with_302_not_303(self, client):
        resp = client.get("/admin/", follow_redirects=False)
        assert resp.status_code in (302, 303, 307), (
            f"Expected 3xx redirect, got {resp.status_code}"
        )
        if resp.status_code == 307:
            pytest.fail(
                "GET /admin/ returns 307 which preserves method — "
                "if a POST hits /admin/, the redirect to /admin/dashboard "
                "will be a POST (causing 405). Use 302 or 303 instead."
            )

    def test_admin_root_without_trailing_slash_redirects(self, client):
        resp = client.get("/admin", follow_redirects=False)
        assert resp.status_code in (302, 303, 307, 404, 200)


class TestAdminLoginRedirects:
    """Test login form redirect behavior."""

    def test_valid_login_redirects_to_dashboard(self, client):
        resp = client.post(
            "/admin/login",
            data={"password": "test-admin-password-123"},
            follow_redirects=False,
        )
        assert resp.status_code == 302, f"Expected 302, got {resp.status_code}"
        location = resp.headers.get("location", "")
        assert location == "/admin/dashboard", (
            f"Expected Location: /admin/dashboard, got {location}"
        )

    def test_invalid_login_redirects_to_login_with_error(self, client):
        resp = client.post(
            "/admin/login",
            data={"password": "wrong-password"},
            follow_redirects=False,
        )
        assert resp.status_code == 302, f"Expected 302, got {resp.status_code}"
        location = resp.headers.get("location", "")
        assert "/admin/login" in location, (
            f"Expected redirect to /admin/login, got {location}"
        )
        assert "error" in location, f"Expected error param in redirect, got {location}"

    def test_login_redirect_is_302(self, client):
        resp = client.post(
            "/admin/login",
            data={"password": "test-admin-password-123"},
            follow_redirects=False,
        )
        assert resp.status_code == 302, (
            f"Login redirect should use 302, got {resp.status_code}. "
            f"303 or 307 could cause issues."
        )


class TestAdminLogoutRedirect:
    """Test logout redirect behavior."""

    def test_logout_redirects_to_login(self, client):
        resp = client.post(
            "/admin/login",
            data={"password": "test-admin-password-123"},
            follow_redirects=False,
        )
        session_id = None
        for h in resp.headers.get_list("set-cookie"):
            if "admin_session=" in h:
                session_id = h.split("admin_session=")[1].split(";")[0]
                break
        assert session_id

        resp = client.post(
            "/admin/logout",
            follow_redirects=False,
            headers={"Cookie": f"admin_session={session_id}"},
        )
        assert resp.status_code == 302, f"Expected 302, got {resp.status_code}"
        location = resp.headers.get("location", "")
        assert location == "/admin/login", (
            f"Expected Location: /admin/login, got {location}"
        )

    def test_logout_clears_cookie(self, client):
        resp = client.post(
            "/admin/login",
            data={"password": "test-admin-password-123"},
            follow_redirects=False,
        )
        session_id = None
        for h in resp.headers.get_list("set-cookie"):
            if "admin_session=" in h:
                session_id = h.split("admin_session=")[1].split(";")[0]
                break
        assert session_id

        resp = client.post(
            "/admin/logout",
            follow_redirects=False,
            headers={"Cookie": f"admin_session={session_id}"},
        )
        cookies = resp.headers.get_list("set-cookie")
        cookie_headers = " ".join(cookies).lower()
        assert "admin_session" in cookie_headers, (
            "Logout should set cookie header for admin_session"
        )


class TestAPIEndpointRedirects:
    """Test that admin API endpoints don't redirect — they return 401."""

    API_ENDPOINTS = [
        ("/admin/api/stats", "GET"),
        ("/admin/api/tenants", "GET"),
        ("/admin/api/messages", "GET"),
        ("/admin/api/webhooks", "GET"),
    ]

    @pytest.mark.parametrize("path,method", API_ENDPOINTS)
    def test_api_returns_401_not_302(self, client, path, method):
        resp = client.request(method, path, follow_redirects=False)
        assert resp.status_code == 401, (
            f"{method} {path}: expected 401, got {resp.status_code}. "
            f"API endpoints should return 401, not redirect."
        )


class TestFragmentEndpointRedirects:
    """Test that htmx fragment endpoints return 401, not 302."""

    FRAGMENT_ENDPOINTS = [
        "/admin/fragments/stats",
        "/admin/fragments/websockets",
        "/admin/fragments/tenants",
        "/admin/fragments/messages-tabs",
        "/admin/fragments/messages",
        "/admin/fragments/webhooks",
        "/admin/fragments/logs",
    ]

    @pytest.mark.parametrize("path", FRAGMENT_ENDPOINTS)
    def test_fragment_returns_401_not_302(self, client, path):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 401, (
            f"GET {path}: expected 401 for htmx request, got {resp.status_code}. "
            f"htmx requests should get 401 so the JS can handle it, not a 302 redirect."
        )


class TestRedirectMethodPreservation:
    """Test that POST redirects don't preserve method (which would cause 405s)."""

    def test_post_to_admin_root_gets_405(self, client):
        resp = client.post("/admin/", follow_redirects=False)
        assert resp.status_code == 405

    def test_post_to_dashboard_gets_405(self, client):
        resp = client.post("/admin/dashboard", follow_redirects=False)
        assert resp.status_code == 405

    def test_post_to_tenants_page_gets_405(self, client):
        resp = client.post("/admin/tenants", follow_redirects=False)
        assert resp.status_code == 405

    def test_delete_to_dashboard_gets_405(self, client):
        resp = client.delete("/admin/dashboard", follow_redirects=False)
        assert resp.status_code == 405

    def test_put_to_tenants_page_gets_405(self, client):
        resp = client.put("/admin/tenants", follow_redirects=False)
        assert resp.status_code == 405

    def test_patch_to_dashboard_gets_405(self, client):
        resp = client.patch("/admin/dashboard", follow_redirects=False)
        assert resp.status_code == 405
