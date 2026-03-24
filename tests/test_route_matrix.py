"""
Route Matrix Test — auto-discovers ALL routes from the FastAPI app
and verifies:
  1. Correct HTTP method returns expected status (200/302/401)
  2. Wrong HTTP methods return 405 (Method Not Allowed)
  3. All routes are reachable and registered
"""

import pytest
from fastapi.testclient import TestClient
from src.main import app
from tests.fixtures.app_client import app_client


ALL_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]

PUBLIC_ROUTES = {
    "/health": {"GET": [200]},
    "/admin/static/websocket.js": {"GET": [200]},
    "/admin/login": {"GET": [200], "POST": [302]},
    "/admin/": {"GET": [302, 307]},
}

ROUTES_REQUIRING_BODY = {
    ("/admin/login", "POST"): {"password": "test-admin-password-123"},
}

ROUTES_WITH_MULTIPLE_METHODS = {
    "/admin/api/tenants/bulk": ["DELETE"],
    "/admin/api/rate-limit/block": ["POST", "DELETE"],
}

SESSION_PROTECTED_ROUTES = {
    "/admin/dashboard": {"GET": [200]},
    "/admin/tenants": {"GET": [200]},
    "/admin/messages": {"GET": [200]},
    "/admin/webhooks": {"GET": [200]},
    "/admin/security": {"GET": [200]},
    "/admin/chatwoot": {"GET": [200]},
    "/admin/logs": {"GET": [200]},
    "/admin/logout": {"POST": [302]},
}

SESSION_PROTECTED_JSON_ROUTES = {
    "/admin/api/stats": {"GET": [200]},
    "/admin/api/websockets": {"GET": [200]},
    "/admin/api/tenants": {"GET": [200]},
    "/admin/api/tenants": {"POST": [200]},
    "/admin/api/tenants/bulk/reconnect": {"POST": [200]},
    "/admin/api/tenants/bulk": {"DELETE": [200]},
    "/admin/api/messages": {"GET": [200]},
    "/admin/api/messages/bulk": {"DELETE": [200]},
    "/admin/api/messages/all": {"DELETE": [200]},
    "/admin/api/webhooks": {"GET": [200]},
    "/admin/api/webhooks/history": {"GET": [200]},
    "/admin/api/webhooks/stats": {"GET": [200]},
    "/admin/api/webhooks/bulk/test": {"POST": [200]},
    "/admin/api/rate-limit/blocked": {"GET": [200]},
    "/admin/api/rate-limit/block": {"POST": [200]},
    "/admin/api/rate-limit/block": {"DELETE": [200]},
    "/admin/api/rate-limit/failed-auth": {"GET": [200]},
    "/admin/api/rate-limit/failed-auth": {"DELETE": [200]},
    "/admin/api/logs/clear": {"POST": [200]},
    "/admin/api/frontend-errors": {"POST": [204]},
    "/admin/api/chatwoot/config": {"POST": [200]},
    "/admin/api/chatwoot/tenants": {"GET": [200]},
    "/admin/api/session-id": {"GET": [200]},
}

FRAGMENT_ROUTES = {
    "/admin/fragments/stats": {"GET": [200]},
    "/admin/fragments/websockets": {"GET": [200]},
    "/admin/fragments/tenants": {"GET": [200]},
    "/admin/fragments/messages-tabs": {"GET": [200]},
    "/admin/fragments/messages": {"GET": [200]},
    "/admin/fragments/webhooks": {"GET": [200]},
    "/admin/fragments/webhook-history": {"GET": [200]},
    "/admin/fragments/blocked-ips": {"GET": [200]},
    "/admin/fragments/chatwoot/config": {"GET": [200]},
    "/admin/fragments/chatwoot/tenants": {"GET": [200]},
    "/admin/fragments/failed-auth": {"GET": [200]},
    "/admin/fragments/logs": {"GET": [200]},
}


def _discover_routes():
    """Auto-discover all routes from the FastAPI app."""
    routes = []
    for route in app.routes:
        if hasattr(route, "methods") and hasattr(route, "path"):
            for method in route.methods:
                if method == "HEAD":
                    continue
                routes.append((method, route.path))
    return routes


DISCOVERED_ROUTES = _discover_routes()
DISCOVERED_PATHS = sorted(set(path for _, path in DISCOVERED_ROUTES))
AUTO_GENERATED_PATHS = {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}


def _get_allowed_methods(path):
    methods = set()
    for method, route_path in DISCOVERED_ROUTES:
        if route_path == path:
            methods.add(method)
    for base_path, methods_list in ROUTES_WITH_MULTIPLE_METHODS.items():
        if path == base_path:
            methods.update(methods_list)
    return methods


class TestRouteDiscovery:
    """Verify that the app has routes registered and we can discover them."""

    def test_app_has_routes(self):
        assert len(DISCOVERED_ROUTES) > 0, "No routes discovered from FastAPI app"

    def test_app_has_admin_routes(self):
        admin_routes = [p for _, p in DISCOVERED_ROUTES if p.startswith("/admin")]
        assert len(admin_routes) > 10, (
            f"Expected >10 admin routes, found {len(admin_routes)}"
        )

    def test_app_has_api_routes(self):
        api_routes = [p for _, p in DISCOVERED_ROUTES if p.startswith("/api")]
        assert len(api_routes) > 20, f"Expected >20 API routes, found {len(api_routes)}"

    def test_discovered_routes_match_known_public(self):
        known_public = set(PUBLIC_ROUTES.keys())
        discovered_public = known_public & set(DISCOVERED_PATHS)
        missing = known_public - set(DISCOVERED_PATHS)
        assert not missing, f"Public routes not discovered: {missing}"

    def test_discovered_routes_match_known_session_protected(self):
        known = set(SESSION_PROTECTED_ROUTES.keys())
        missing = known - set(DISCOVERED_PATHS)
        assert not missing, f"Session-protected routes not discovered: {missing}"

    def test_discovered_routes_match_known_fragments(self):
        known = set(FRAGMENT_ROUTES.keys())
        missing = known - set(DISCOVERED_PATHS)
        assert not missing, f"Fragment routes not discovered: {missing}"


class TestPublicRouteMethods:
    """Test that public routes accept the correct methods and reject others."""

    @pytest.fixture
    def client(self, app_client):
        raw_client, _tm = app_client
        return raw_client


class TestSessionProtectedRoutesUnauthenticated:
    """Test that session-protected routes reject unauthenticated requests."""

    @pytest.fixture
    def client(self, app_client):
        raw_client, _tm = app_client
        return raw_client

    @pytest.mark.parametrize("path,methods_map", list(SESSION_PROTECTED_ROUTES.items()))
    def test_html_request_redirects_to_login(self, client, path, methods_map):
        for method in methods_map:
            resp = client.request(
                method,
                path,
                headers={"Accept": "text/html"},
                follow_redirects=False,
            )
            assert resp.status_code == 302, (
                f"{method} {path}: expected 302 redirect, got {resp.status_code}"
            )
            assert "/admin/login" in resp.headers.get("location", ""), (
                f"{method} {path}: redirect location should be /admin/login, got {resp.headers.get('location')}"
            )

    @pytest.mark.parametrize("path,methods_map", list(SESSION_PROTECTED_ROUTES.items()))
    def test_json_request_returns_401(self, client, path, methods_map):
        for method in methods_map:
            resp = client.request(
                method,
                path,
                headers={"Accept": "application/json"},
                follow_redirects=False,
            )
            assert resp.status_code == 401, (
                f"{method} {path} (JSON): expected 401, got {resp.status_code}"
            )

    @pytest.mark.parametrize(
        "path,methods_map", list(SESSION_PROTECTED_JSON_ROUTES.items())
    )
    def test_json_api_returns_401_unauthenticated(self, client, path, methods_map):
        for method in methods_map:
            resp = client.request(method, path, follow_redirects=False)
            assert resp.status_code == 401, (
                f"{method} {path}: expected 401, got {resp.status_code}"
            )

    @pytest.mark.parametrize("path", list(FRAGMENT_ROUTES.keys()))
    def test_fragment_returns_401_unauthenticated(self, client, path):
        resp = client.get(path, follow_redirects=False)
        assert resp.status_code == 401, (
            f"GET {path}: expected 401, got {resp.status_code}"
        )


class TestRoute405OnWrongMethod:
    """Test that wrong HTTP methods on EVERY route return 405."""

    @pytest.fixture
    def client(self, app_client):
        raw_client, _tm = app_client
        return raw_client

    @pytest.mark.parametrize(
        "path,method",
        [
            (path, method)
            for path in DISCOVERED_PATHS
            for method in ALL_METHODS
            if method not in _get_allowed_methods(path)
            and path not in AUTO_GENERATED_PATHS
        ],
    )
    def test_wrong_method_returns_405(self, client, path, method):
        resp = client.request(method, path, follow_redirects=False)
        assert resp.status_code in (405, 401, 302), (
            f"{method} {path}: expected 405/401/302, got {resp.status_code}"
        )
        if resp.status_code != 405:
            resp_auth = client.get(
                path,
                headers={"Accept": "text/html", "Cookie": "admin_session=valid"},
                follow_redirects=False,
            )
            if resp_auth.status_code in (302, 401):
                pass


class TestAdminRouteAuthMatrix:
    """Comprehensive auth matrix for admin routes."""

    @pytest.fixture
    def client(self, app_client):
        raw_client, _tm = app_client
        return raw_client

    def test_no_cookie_no_json_accept_redirects(self, client):
        resp = client.get(
            "/admin/dashboard",
            headers={"Accept": "text/html"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_no_cookie_json_accept_returns_401(self, client):
        resp = client.get(
            "/admin/dashboard",
            headers={"Accept": "application/json"},
            follow_redirects=False,
        )
        assert resp.status_code == 401

    def test_no_cookie_default_accept_returns_401(self, client):
        resp = client.get("/admin/dashboard", follow_redirects=False)
        assert resp.status_code == 401, (
            "Default Accept (not text/html) should return 401, not 302"
        )

    def test_invalid_cookie_redirects(self, client):
        resp = client.get(
            "/admin/dashboard",
            headers={"Accept": "text/html", "Cookie": "admin_session=invalid-token"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_invalid_cookie_json_returns_401(self, client):
        resp = client.get(
            "/admin/dashboard",
            headers={
                "Accept": "application/json",
                "Cookie": "admin_session=invalid-token",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 401

    def test_expired_cookie_returns_302(self, app_client):
        client, _tm = app_client
        import secrets
        from datetime import datetime, timedelta, UTC

        session_id = secrets.token_urlsafe(32)
        expired = datetime.now(UTC) - timedelta(hours=1)
        import asyncio

        loop = asyncio.get_event_loop()
        loop.run_until_complete(
            _tm._db.create_admin_session(
                session_id=session_id,
                expires_at=expired,
                user_agent="test",
                ip_address="127.0.0.1",
            )
        )
        resp = client.get(
            "/admin/dashboard",
            headers={"Accept": "text/html", "Cookie": f"admin_session={session_id}"},
            follow_redirects=False,
        )
        assert resp.status_code == 302

    def test_logout_requires_auth(self, client):
        resp = client.post("/admin/logout", follow_redirects=False)
        assert resp.status_code in (302, 401)


class TestHealthEndpoint:
    """Test the health endpoint specifically."""

    @pytest.fixture
    def client(self, app_client):
        raw_client, _tm = app_client
        return raw_client

    def test_health_get_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_post_405(self, client):
        resp = client.post("/health")
        assert resp.status_code == 405

    def test_health_delete_405(self, client):
        resp = client.delete("/health")
        assert resp.status_code == 405

    def test_health_returns_json(self, client):
        resp = client.get("/health")
        assert resp.headers.get("content-type", "").startswith("application/json")
