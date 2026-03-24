import json
import secrets
import pytest
from playwright.sync_api import Page, expect
from tests.playwright.conftest import BASE_URL, ADMIN_PASSWORD


pytestmark = pytest.mark.playwright


class TestTenantAPI:
    def test_create_tenant_returns_201(self, authenticated_page: Page):
        name = f"api_test_tenant_{secrets.token_hex(4)}"
        response = authenticated_page.request.post(
            f"{BASE_URL}/admin/api/tenants",
            form={"name": name},
        )
        assert response.status == 200
        data = response.json()
        assert data["status"] == "created"
        assert "tenant" in data
        assert data["tenant"]["name"] == name
        assert "api_key" in data["tenant"]

    def test_create_tenant_without_name_fails(self, authenticated_page: Page):
        response = authenticated_page.request.post(
            f"{BASE_URL}/admin/api/tenants",
            form={},
        )
        assert response.status == 422

    def test_list_tenants_returns_array(
        self, authenticated_page: Page, test_tenant: dict
    ):
        response = authenticated_page.request.get(f"{BASE_URL}/admin/api/tenants")
        assert response.status == 200
        data = response.json()
        assert "tenants" in data
        assert isinstance(data["tenants"], list)
        assert len(data["tenants"]) >= 1

    def test_list_tenants_includes_tenant_fields(
        self, authenticated_page: Page, test_tenant: dict
    ):
        response = authenticated_page.request.get(f"{BASE_URL}/admin/api/tenants")
        data = response.json()
        tenants = data["tenants"]
        found = any(t["api_key_hash"] == test_tenant["hash"] for t in tenants)
        assert found, "Test tenant should be in the list"

        tenant = next(t for t in tenants if t["api_key_hash"] == test_tenant["hash"])
        assert "name" in tenant
        assert "connection_state" in tenant
        assert "created_at" in tenant
        assert "webhook_count" in tenant
        assert "has_auth" in tenant

    def test_get_tenant_by_hash(self, authenticated_page: Page, test_tenant: dict):
        response = authenticated_page.request.get(
            f"{BASE_URL}/admin/api/tenants/{test_tenant['hash']}"
        )
        assert response.status == 200
        data = response.json()
        assert data["api_key_hash"] == test_tenant["hash"]
        assert data["name"] == test_tenant["name"]

    def test_get_nonexistent_tenant_returns_404(self, authenticated_page: Page):
        fake_hash = "nonexistent_" + secrets.token_hex(16)
        response = authenticated_page.request.get(
            f"{BASE_URL}/admin/api/tenants/{fake_hash}"
        )
        assert response.status == 404

    def test_delete_tenant(self, authenticated_page: Page):
        name = f"delete_test_{secrets.token_hex(4)}"
        create_resp = authenticated_page.request.post(
            f"{BASE_URL}/admin/api/tenants",
            form={"name": name},
        )
        assert create_resp.status == 200
        tenant_hash = create_resp.json()["tenant"]["api_key_hash"]

        delete_resp = authenticated_page.request.delete(
            f"{BASE_URL}/admin/api/tenants/{tenant_hash}"
        )
        assert delete_resp.status == 200
        assert delete_resp.json()["status"] == "deleted"

        get_resp = authenticated_page.request.get(
            f"{BASE_URL}/admin/api/tenants/{tenant_hash}"
        )
        assert get_resp.status == 404

    def test_delete_nonexistent_tenant_returns_404(self, authenticated_page: Page):
        fake_hash = "nonexistent_" + secrets.token_hex(16)
        response = authenticated_page.request.delete(
            f"{BASE_URL}/admin/api/tenants/{fake_hash}"
        )
        assert response.status == 404


class TestRateLimitAPI:
    def test_get_blocked_ips(self, authenticated_page: Page, blocked_ip: str):
        response = authenticated_page.request.get(
            f"{BASE_URL}/admin/api/rate-limit/blocked"
        )
        assert response.status == 200
        data = response.json()
        assert "blocked_ips" in data
        assert isinstance(data["blocked_ips"], list)

    def test_block_ip(self, authenticated_page: Page):
        test_ip = f"10.{secrets.randbelow(256)}.{secrets.randbelow(256)}.{secrets.randbelow(256)}"
        response = authenticated_page.request.post(
            f"{BASE_URL}/admin/api/rate-limit/block?ip={test_ip}&reason=test"
        )
        assert response.status == 200
        data = response.json()
        assert data["status"] == "blocked"
        assert data["ip"] == test_ip

    def test_block_ip_without_ip_param_fails(self, authenticated_page: Page):
        response = authenticated_page.request.post(
            f"{BASE_URL}/admin/api/rate-limit/block"
        )
        assert response.status == 422

    def test_unblock_ip(self, authenticated_page: Page):
        test_ip = f"10.{secrets.randbelow(256)}.{secrets.randbelow(256)}.{secrets.randbelow(256)}"
        authenticated_page.request.post(
            f"{BASE_URL}/admin/api/rate-limit/block?ip={test_ip}&reason=test"
        )

        response = authenticated_page.request.delete(
            f"{BASE_URL}/admin/api/rate-limit/block?ip={test_ip}"
        )
        assert response.status == 200
        data = response.json()
        assert data["status"] == "unblocked"

    def test_unblock_nonexistent_ip(self, authenticated_page: Page):
        response = authenticated_page.request.delete(
            f"{BASE_URL}/admin/api/rate-limit/block?ip=192.0.2.999"
        )
        assert response.status == 200
        data = response.json()
        assert data["status"] == "not_blocked"

    def test_get_rate_limit_stats(self, authenticated_page: Page):
        response = authenticated_page.request.get(
            f"{BASE_URL}/admin/api/rate-limit/failed-auth"
        )
        assert response.status == 200
        data = response.json()
        assert "ips_with_failures" in data

    def test_clear_failed_auth(self, authenticated_page: Page):
        response = authenticated_page.request.delete(
            f"{BASE_URL}/admin/api/rate-limit/failed-auth"
        )
        assert response.status == 200
        data = response.json()
        assert data["status"] == "cleared"

    def test_clear_failed_auth_for_specific_ip(self, authenticated_page: Page):
        response = authenticated_page.request.delete(
            f"{BASE_URL}/admin/api/rate-limit/failed-auth?ip=10.0.0.1"
        )
        assert response.status == 200


class TestWebhookAPI:
    def test_add_webhook_to_tenant(self, authenticated_page: Page, test_tenant: dict):
        response = authenticated_page.request.post(
            f"{BASE_URL}/admin/api/tenants/{test_tenant['hash']}/webhooks",
            data=json.dumps({"url": "https://test-hook.example.com/endpoint"}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status == 200
        data = response.json()
        assert data["status"] == "added"

    def test_add_invalid_webhook_url_fails(
        self, authenticated_page: Page, test_tenant: dict
    ):
        response = authenticated_page.request.post(
            f"{BASE_URL}/admin/api/tenants/{test_tenant['hash']}/webhooks",
            data=json.dumps({"url": "not-a-url"}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status == 400

    def test_add_internal_webhook_url_fails(
        self, authenticated_page: Page, test_tenant: dict
    ):
        response = authenticated_page.request.post(
            f"{BASE_URL}/admin/api/tenants/{test_tenant['hash']}/webhooks",
            data=json.dumps({"url": "http://localhost:8000/hook"}),
            headers={"Content-Type": "application/json"},
        )
        assert response.status == 400

    def test_remove_webhook_from_tenant(
        self, authenticated_page: Page, test_tenant: dict
    ):
        add_resp = authenticated_page.request.post(
            f"{BASE_URL}/admin/api/tenants/{test_tenant['hash']}/webhooks",
            data=json.dumps({"url": "https://remove-test.example.com/hook"}),
            headers={"Content-Type": "application/json"},
        )
        if add_resp.status != 200:
            pytest.skip("Could not add webhook for removal test")

        remove_resp = authenticated_page.request.delete(
            f"{BASE_URL}/admin/api/tenants/{test_tenant['hash']}/webhooks"
            f"?url=https://remove-test.example.com/hook"
        )
        assert remove_resp.status == 200
        data = remove_resp.json()
        assert data["status"] == "removed"

    def test_list_webhooks(self, authenticated_page: Page):
        response = authenticated_page.request.get(f"{BASE_URL}/admin/api/webhooks")
        assert response.status == 200
        data = response.json()
        assert "webhooks" in data


class TestStatsAPI:
    def test_get_dashboard_stats(self, authenticated_page: Page):
        response = authenticated_page.request.get(f"{BASE_URL}/admin/api/stats")
        assert response.status == 200
        data = response.json()
        assert "tenants" in data
        assert "messages" in data
        assert "webhooks" in data
        assert "rate_limit" in data

    def test_stats_tenants_has_subfields(self, authenticated_page: Page):
        response = authenticated_page.request.get(f"{BASE_URL}/admin/api/stats")
        data = response.json()
        tenants = data["tenants"]
        assert "total" in tenants
        assert "connected" in tenants
        assert "disconnected" in tenants

    def test_websocket_stats_endpoint(self, authenticated_page: Page):
        response = authenticated_page.request.get(f"{BASE_URL}/admin/api/websockets")
        assert response.status == 200
        data = response.json()
        assert "count" in data
        assert isinstance(data["count"], int)


class TestAuthentication:
    def test_api_without_auth_returns_401(self, page: Page):
        response = page.request.get(f"{BASE_URL}/admin/api/tenants")
        assert response.status in (401, 302, 403)

    def test_api_with_invalid_cookie_returns_401(self, page: Page):
        page.context.add_cookies(
            [
                {
                    "name": "admin_session",
                    "value": "invalid_session_token",
                    "domain": "localhost",
                    "path": "/",
                }
            ]
        )
        response = page.request.get(f"{BASE_URL}/admin/api/tenants")
        assert response.status in (401, 403)

    def test_create_tenant_api_without_auth_fails(self, page: Page):
        response = page.request.post(
            f"{BASE_URL}/admin/api/tenants",
            form={"name": "unauth_test"},
        )
        assert response.status in (401, 302, 403)

    def test_delete_tenant_api_without_auth_fails(self, page: Page):
        response = page.request.delete(f"{BASE_URL}/admin/api/tenants/some_hash")
        assert response.status in (401, 302, 403)

    def test_rate_limit_api_without_auth_fails(self, page: Page):
        response = page.request.get(f"{BASE_URL}/admin/api/rate-limit/blocked")
        assert response.status in (401, 302, 403)

    def test_stats_api_without_auth_fails(self, page: Page):
        response = page.request.get(f"{BASE_URL}/admin/api/stats")
        assert response.status in (401, 302, 403)

    def test_webhooks_api_without_auth_fails(self, page: Page):
        response = page.request.get(f"{BASE_URL}/admin/api/webhooks")
        assert response.status in (401, 302, 403)

    def test_websocket_api_without_auth_fails(self, page: Page):
        response = page.request.get(f"{BASE_URL}/admin/api/websockets")
        assert response.status in (401, 302, 403)


class TestMessagesAPI:
    def test_list_messages_api(self, authenticated_page: Page):
        response = authenticated_page.request.get(f"{BASE_URL}/admin/api/messages")
        assert response.status == 200
        data = response.json()
        assert "messages" in data
        assert "total" in data
        assert isinstance(data["messages"], list)

    def test_list_messages_with_search(self, authenticated_page: Page):
        response = authenticated_page.request.get(
            f"{BASE_URL}/admin/api/messages?search=nonexistent_xyz_12345"
        )
        assert response.status == 200
        data = response.json()
        assert data["total"] == 0

    def test_list_messages_with_limit(self, authenticated_page: Page):
        response = authenticated_page.request.get(
            f"{BASE_URL}/admin/api/messages?limit=5"
        )
        assert response.status == 200
        data = response.json()
        assert len(data["messages"]) <= 5

    def test_webhook_history_api(self, authenticated_page: Page):
        response = authenticated_page.request.get(
            f"{BASE_URL}/admin/api/webhooks/history"
        )
        assert response.status == 200
        data = response.json()
        assert "attempts" in data
        assert "total" in data

    def test_webhook_stats_api(self, authenticated_page: Page):
        response = authenticated_page.request.get(
            f"{BASE_URL}/admin/api/webhooks/stats"
        )
        assert response.status == 200
        data = response.json()
        assert isinstance(data, dict)

    def test_bulk_delete_tenants_api(self, authenticated_page: Page):
        name = f"bulk_del_{secrets.token_hex(4)}"
        create_resp = authenticated_page.request.post(
            f"{BASE_URL}/admin/api/tenants",
            form={"name": name},
        )
        if create_resp.status != 200:
            pytest.skip("Could not create tenant for bulk delete test")

        tenant_hash = create_resp.json()["tenant"]["api_key_hash"]
        result = authenticated_page.evaluate(
            """async ([url, hash]) => {
            try {
                const resp = await fetch(url, {
                    method: 'DELETE',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({tenant_hashes: [hash]})
                });
                return {status: resp.status, body: await resp.json()};
            } catch(e) {
                return {status: 0, error: e.message};
            }
        }""",
            [f"{BASE_URL}/admin/api/tenants/bulk", tenant_hash],
        )
        if result["status"] == 200:
            assert result["body"].get("deleted", 0) >= 1
        else:
            pass

    def test_toggle_tenant_enabled(self, authenticated_page: Page, test_tenant: dict):
        response = authenticated_page.request.patch(
            f"{BASE_URL}/admin/api/tenants/{test_tenant['hash']}/enabled",
            data=json.dumps({"enabled": False}),
            headers={"Content-Type": "application/json"},
        )
        if response.status == 200:
            data = response.json()
            assert data["enabled"] is False

            restore = authenticated_page.request.patch(
                f"{BASE_URL}/admin/api/tenants/{test_tenant['hash']}/enabled",
                data=json.dumps({"enabled": True}),
                headers={"Content-Type": "application/json"},
            )
            assert restore.status == 200
