import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timezone
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from src.api.routes import router, admin_router
from src.api.auth import get_tenant, get_admin_key
from src.bridge import BridgeError
from src.tenant import Tenant
from tests.fixtures.bridge_mock import MockBridge

MOCK_API_KEY = "test-api-key-123"
MOCK_ADMIN_KEY = "test-admin-key-456"


def _make_tenant():
    t = MagicMock(spec=Tenant)
    t.name = "TestTenant"
    t.api_key_hash = "abc123"
    t.webhook_urls = []
    t.bridge = None
    t.message_store = None
    return t


def _make_app(tenant=None, admin_key=None):
    from src.main import app

    if tenant is not None:
        app.dependency_overrides[get_tenant] = lambda: tenant

    if admin_key is not None:
        app.dependency_overrides[get_admin_key] = lambda: admin_key

    return app


def _make_app_clean():
    """Create a fresh minimal app for tests that need isolation from the full app."""
    app = FastAPI()
    app.include_router(router)
    app.include_router(admin_router)
    return app


def _mock_bridge():
    return MockBridge()


def _patch_get_bridge(mock_bridge):
    return patch(
        "src.api.routes.tenant_manager.get_or_create_bridge",
        new_callable=AsyncMock,
        return_value=mock_bridge,
    )


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    from src.middleware import rate_limiter
    from src.main import app

    rate_limiter._blocked_ips.clear()
    rate_limiter._failed_auth_attempts.clear()
    yield
    rate_limiter._blocked_ips.clear()
    rate_limiter._failed_auth_attempts.clear()
    app.dependency_overrides.clear()


class TestCoreEndpoints:
    def test_get_status_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "get_status",
            {
                "connection_state": "connected",
                "self": {"jid": "123@s.whatsapp.net", "phone": "+123", "name": "Test"},
                "has_qr": False,
            },
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get("/api/status", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        data = resp.json()
        assert data["connection_state"] == "connected"
        assert data["has_qr"] is False

    def test_get_status_bridge_error(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_error("get_status", BridgeError("connection lost"))
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get("/api/status", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 500
        assert "connection lost" in resp.json()["detail"]

    def test_post_login_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "login",
            {"status": "qr_ready", "qr": "qr-data", "connection_state": "connecting"},
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post("/api/login", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["status"] == "qr_ready"
        assert resp.json()["qr"] == "qr-data"

    def test_post_login_bridge_error(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_error("login", BridgeError("login failed"))
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post("/api/login", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 500

    def test_post_logout_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("logout", {"status": "logged_out"})
        tenant.bridge = bridge
        app = _make_app(tenant)
        with TestClient(app) as client:
            resp = client.post("/api/logout", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["status"] == "logged_out"

    def test_post_logout_no_bridge(self):
        tenant = _make_tenant()
        tenant.bridge = None
        app = _make_app(tenant)
        with TestClient(app) as client:
            resp = client.post("/api/logout", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["status"] == "not_connected"

    def test_get_messages_success(self):
        tenant = _make_tenant()
        ms = MagicMock()
        ms.list.return_value = (
            [
                {
                    "id": "msg1",
                    "from_jid": "a",
                    "chat_jid": "b",
                    "text": "hi",
                    "timestamp": 1000,
                    "direction": "inbound",
                    "msg_type": "text",
                }
            ],
            1,
        )
        tenant.message_store = ms
        app = _make_app(tenant)
        with TestClient(app) as client:
            resp = client.get("/api/messages", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["total"] == 1

    def test_get_messages_no_store(self):
        tenant = _make_tenant()
        tenant.message_store = None
        app = _make_app(tenant)
        with TestClient(app) as client:
            resp = client.get("/api/messages", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 500
        assert "not initialized" in resp.json()["detail"]

    def test_delete_messages_success(self):
        tenant = _make_tenant()
        ms = MagicMock()
        tenant.message_store = ms
        app = _make_app(tenant)
        with TestClient(app) as client:
            resp = client.delete("/api/messages", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        ms.clear.assert_called_once()

    def test_post_send_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "send_message", {"message_id": "m1", "to": "123@s.whatsapp.net"}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/send",
                json={"to": "123@s.whatsapp.net", "text": "hello"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["message_id"] == "m1"

    def test_post_send_ssrf_rejected(self):
        tenant = _make_tenant()
        app = _make_app(tenant)
        with TestClient(app) as client:
            resp = client.post(
                "/api/send",
                json={
                    "to": "123",
                    "text": "hi",
                    "media_url": "http://169.254.169.254/secret",
                },
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 400
        assert "SSRF" in resp.json()["detail"]

    def test_post_send_bridge_error(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_error("send_message", BridgeError("send failed"))
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/send",
                json={"to": "123", "text": "hi"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 500

    def test_post_react_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("send_reaction", {"status": "reacted"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/react",
                json={"chat": "g@g", "message_id": "m1", "emoji": "thumbsup"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["emoji"] == "thumbsup"

    def test_post_poll_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("send_poll", {"message_id": "p1", "to": "g@g"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/poll",
                json={"to": "g@g", "name": "Poll", "values": ["A", "B"]},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["message_id"] == "p1"

    def test_post_typing_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "send_typing", {"status": "typing", "to": "123@s.whatsapp.net"}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/typing?to=123@s.whatsapp.net", headers={"X-API-Key": MOCK_API_KEY}
            )
        assert resp.status_code == 200
        assert resp.json()["to"] == "123@s.whatsapp.net"


class TestAuthEndpoints:
    def test_auth_exists_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("auth_exists", {"exists": True})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get("/api/auth/exists", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["exists"] is True

    def test_auth_age_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("auth_age", {"age_ms": 3600000})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get("/api/auth/age", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["age_ms"] == 3600000

    def test_auth_self_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "self_id", {"jid": "123@s.whatsapp.net", "e164": "+123", "name": "User"}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get("/api/auth/self", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["jid"] == "123@s.whatsapp.net"

    def test_auth_exists_bridge_error(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_error("auth_exists", BridgeError("err"))
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get("/api/auth/exists", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 500


class TestWebhookEndpoints:
    def test_list_webhooks(self):
        tenant = _make_tenant()
        tenant.webhook_urls = ["http://example.com/hook"]
        app = _make_app(tenant)
        with TestClient(app) as client:
            resp = client.get("/api/webhooks", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["urls"] == ["http://example.com/hook"]

    def test_add_webhook_success(self):
        tenant = _make_tenant()
        app = _make_app(tenant)
        with (
            patch(
                "src.api.routes.tenant_manager.add_webhook", new_callable=AsyncMock
            ) as mock_add,
            TestClient(app) as client,
        ):
            resp = client.post(
                "/api/webhooks",
                json={"url": "https://example.com/hook"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "added"

    def test_add_webhook_ssrf_rejected(self):
        tenant = _make_tenant()
        app = _make_app(tenant)
        with TestClient(app) as client:
            resp = client.post(
                "/api/webhooks",
                json={"url": "http://localhost/hook"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 400

    def test_add_webhook_invalid_scheme(self):
        tenant = _make_tenant()
        app = _make_app(tenant)
        with TestClient(app) as client:
            resp = client.post(
                "/api/webhooks",
                json={"url": "ftp://example.com/hook"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 400

    def test_remove_webhook_success(self):
        tenant = _make_tenant()
        app = _make_app(tenant)
        with (
            patch(
                "src.api.routes.tenant_manager.remove_webhook",
                new_callable=AsyncMock,
                return_value=True,
            ),
            TestClient(app) as client,
        ):
            resp = client.delete(
                "/api/webhooks?url=https://example.com/hook",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "removed"

    def test_remove_webhook_not_found(self):
        tenant = _make_tenant()
        app = _make_app(tenant)
        with (
            patch(
                "src.api.routes.tenant_manager.remove_webhook",
                new_callable=AsyncMock,
                return_value=False,
            ),
            TestClient(app) as client,
        ):
            resp = client.delete(
                "/api/webhooks?url=https://example.com/hook",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 404


class TestGroupEndpoints:
    def test_create_group_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_create",
            {
                "status": "created",
                "group_jid": "g@g",
                "subject": "Test",
                "participants": ["a@s.whatsapp.net"],
            },
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/group/create",
                json={"subject": "Test", "participants": ["a@s.whatsapp.net"]},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["group_jid"] == "g@g"

    def test_create_group_bridge_error(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_error("group_create", BridgeError("failed"))
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/group/create",
                json={"subject": "T", "participants": ["a"]},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 500

    def test_update_group_subject_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_update_subject",
            {"status": "updated", "group_jid": "g@g", "subject": "New"},
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                f"/api/group/updateSubject?group_jid=g@g&subject=New",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_update_group_description_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_update_description", {"status": "updated", "group_jid": "g@g"}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                f"/api/group/updateDescription?group_jid=g@g&description=Desc",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_update_group_picture_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_update_picture", {"status": "updated", "group_jid": "g@g"}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                f"/api/group/updatePicture?group_jid=g@g&image_url=https://example.com/img.png",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_update_group_picture_ssrf_rejected(self):
        tenant = _make_tenant()
        app = _make_app(tenant)
        with TestClient(app) as client:
            resp = client.post(
                f"/api/group/updatePicture?group_jid=g@g&image_url=http://127.0.0.1/img.png",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 400
        assert "SSRF" in resp.json()["detail"]

    def test_find_group_infos_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_get_info", {"group_jid": "g@g", "name": "Group", "size": 5}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get(
                f"/api/group/findGroupInfos?group_jid=g@g",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["group_jid"] == "g@g"

    def test_fetch_all_groups_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_get_all", {"groups": [{"jid": "g1@g", "name": "G1", "size": 3}]}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get(
                "/api/group/fetchAllGroups", headers={"X-API-Key": MOCK_API_KEY}
            )
        assert resp.status_code == 200
        assert len(resp.json()["groups"]) == 1

    def test_fetch_all_groups_with_participants(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_get_all",
            {
                "groups": [
                    {
                        "jid": "g1@g",
                        "name": "G1",
                        "size": 2,
                        "participants": [{"jid": "a@s.w", "admin": "admin"}],
                    }
                ]
            },
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get(
                "/api/group/fetchAllGroups?get_participants=true",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["groups"][0]["participants"][0]["jid"] == "a@s.w"

    def test_get_group_participants_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_get_participants",
            {"participants": [{"jid": "a@s.w", "admin": "admin"}]},
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get(
                f"/api/group/participants?group_jid=g@g",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["group_jid"] == "g@g"

    def test_get_invite_code_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("group_get_invite_code", {"invite_code": "ABC123"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get(
                f"/api/group/inviteCode?group_jid=g@g",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["invite_code"] == "ABC123"

    def test_revoke_invite_code_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("group_revoke_invite", {"new_invite_code": "XYZ789"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                f"/api/group/revokeInviteCode?group_jid=g@g",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["new_invite_code"] == "XYZ789"

    def test_accept_invite_code_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_accept_invite", {"status": "accepted", "group_jid": "g@g"}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get(
                f"/api/group/acceptInviteCode?invite_code=ABC",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_get_invite_info_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_get_invite_info", {"group_jid": "g@g", "name": "Group"}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get(
                f"/api/group/inviteInfo?invite_code=ABC",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_update_group_participant_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_update_participant", {"results": [{"status": "ok", "jid": "a@s.w"}]}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/group/updateParticipant",
                json={
                    "group_jid": "g@g",
                    "action": "promote",
                    "participants": ["a@s.w"],
                },
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["action"] == "promote"

    def test_update_group_setting_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_update_setting",
            {"status": "updated", "group_jid": "g@g", "setting": "announcement"},
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/group/updateSetting",
                json={"group_jid": "g@g", "action": "announcement"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_toggle_ephemeral_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "group_toggle_ephemeral", {"status": "updated", "group_jid": "g@g"}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/group/toggleEphemeral",
                json={"group_jid": "g@g", "expiration": 86400},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["expiration"] == 86400

    def test_leave_group_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("group_leave", {"status": "left", "group_jid": "g@g"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.delete(
                f"/api/group/leaveGroup?group_jid=g@g",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200


class TestAdvancedMessaging:
    def test_send_location_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("send_location", {"message_id": "loc1", "to": "123@s.w"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/message/sendLocation",
                json={"number": "123@s.w", "latitude": 40.7, "longitude": -74.0},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_send_location_with_name_and_address(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("send_location", {"message_id": "loc1", "to": "123@s.w"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/message/sendLocation",
                json={
                    "number": "123@s.w",
                    "latitude": 40.7,
                    "longitude": -74.0,
                    "name": "Office",
                    "address": "123 St",
                },
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_send_contact_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("send_contact", {"message_id": "c1", "to": "123@s.w"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/message/sendContact",
                json={
                    "number": "123@s.w",
                    "contacts": [{"name": "Alice", "phone": "+1555"}],
                },
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_send_sticker_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("send_sticker", {"message_id": "s1", "to": "123@s.w"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/sticker",
                json={"number": "123@s.w", "sticker": "base64data"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_send_sticker_with_gif(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("send_sticker", {"message_id": "s1", "to": "123@s.w"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/sticker",
                json={"number": "123@s.w", "sticker": "data", "gif_playback": True},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_send_buttons_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("send_buttons", {"message_id": "b1", "to": "123@s.w"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            payload = {
                "number": "123@s.w",
                "title": "Choose",
                "description": "Pick one",
                "buttons": [{"type": "reply", "display_text": "A", "id": "a"}],
            }
            resp = client.post(
                "/api/buttons", json=payload, headers={"X-API-Key": MOCK_API_KEY}
            )
        assert resp.status_code == 200

    def test_send_list_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("send_list", {"message_id": "l1", "to": "123@s.w"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            payload = {
                "number": "123@s.w",
                "title": "Menu",
                "description": "Select",
                "button_text": "View",
                "sections": [
                    {"title": "S1", "rows": [{"title": "R1", "row_id": "r1"}]}
                ],
            }
            resp = client.post(
                "/api/list", json=payload, headers={"X-API-Key": MOCK_API_KEY}
            )
        assert resp.status_code == 200

    def test_send_status_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "send_status",
            {"message_id": "st1", "to": "broadcast", "recipient_count": 5},
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/status",
                json={"type": "text", "content": "Hello", "all_contacts": True},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_send_status_with_jid_list(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "send_status",
            {"message_id": "st1", "to": "broadcast", "recipient_count": 2},
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/status",
                json={
                    "type": "text",
                    "content": "Hi",
                    "status_jid_list": ["a@s.w", "b@s.w"],
                },
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200


class TestChatOperations:
    def test_archive_chat_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "archive_chat", {"status": "archived", "chat_jid": "c@g", "archived": True}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/chat/archiveChat",
                json={"chat_jid": "c@g", "archive": True},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_block_user_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("block_user", {"status": "blocked", "jid": "123@s.w"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/chat/updateBlockStatus",
                json={"jid": "123@s.w", "block": True},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_edit_message_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("edit_message", {"message_id": "m1", "to": "123@s.w"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/chat/updateMessage",
                json={"to": "123@s.w", "message_id": "m1", "text": "edited"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_whatsapp_numbers_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "check_whatsapp", {"results": [{"number": "123", "exists": True}]}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/chat/whatsappNumbers",
                json={"numbers": ["+1234567890"]},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert len(resp.json()["results"]) == 1

    def test_mark_read_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("mark_read", {"status": "read", "chat_jid": "c@g"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/chat/markRead",
                json={"chat_jid": "c@g", "message_ids": ["m1", "m2"]},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200


class TestProfileOperations:
    def test_update_profile_name_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("update_profile_name", {"status": "updated"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/chat/updateProfileName",
                json={"name": "NewName"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_update_profile_status_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("update_profile_status", {"status": "updated"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/chat/updateProfileStatus",
                json={"status": "Hey there!"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_update_profile_picture_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("update_profile_picture", {"status": "updated"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/chat/updateProfilePicture",
                json={"image_url": "https://example.com/pic.jpg"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_update_profile_picture_ssrf_rejected(self):
        tenant = _make_tenant()
        app = _make_app(tenant)
        with TestClient(app) as client:
            resp = client.post(
                "/api/chat/updateProfilePicture",
                json={"image_url": "http://169.254.169.254/pic.jpg"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 400
        assert "SSRF" in resp.json()["detail"]

    def test_remove_profile_picture_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("remove_profile_picture", {"status": "removed"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.delete(
                "/api/chat/removeProfilePicture", headers={"X-API-Key": MOCK_API_KEY}
            )
        assert resp.status_code == 200

    def test_fetch_profile_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("get_profile", {"jid": "123@s.w", "exists": True})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/chat/fetchProfile?jid=123@s.w",
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["exists"] is True

    def test_fetch_profile_picture_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "get_profile_picture",
            {"jid": "123@s.w", "url": "https://example.com/pic.jpg"},
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/chat/fetchProfilePicture",
                json={"jid": "123@s.w"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["url"] == "https://example.com/pic.jpg"

    def test_fetch_profile_picture_unsafe_url_nullified(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "get_profile_picture",
            {"jid": "123@s.w", "url": "http://169.254.169.254/pic.jpg"},
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/chat/fetchProfilePicture",
                json={"jid": "123@s.w"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["url"] is None


class TestMessageManagement:
    def test_delete_message_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "delete_message",
            {"status": "deleted", "chat_jid": "c@g", "message_id": "m1"},
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.request(
                "DELETE",
                "/api/message/delete",
                json={"chat_jid": "c@g", "message_id": "m1"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_delete_message_bridge_error(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_error("delete_message", BridgeError("not found"))
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.request(
                "DELETE",
                "/api/message/delete",
                json={"chat_jid": "c@g", "message_id": "m1"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 500


class TestContacts:
    def test_get_contacts_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "get_contacts",
            {
                "contacts": [
                    {
                        "jid": "a@s.w",
                        "name": "Alice",
                        "phone": "+123",
                        "is_group": False,
                    }
                ]
            },
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get("/api/contacts", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert len(resp.json()["contacts"]) == 1

    def test_get_contacts_empty(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("get_contacts", {"contacts": []})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get("/api/contacts", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["contacts"] == []


class TestHistorySync:
    def test_sync_history_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("fetch_chat_history", {"chats": [], "total_messages": 0})
        tenant.message_store = None
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post("/api/sync-history", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["status"] == "synced"

    def test_sync_history_bridge_error(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_error("fetch_chat_history", BridgeError("sync failed"))
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post("/api/sync-history", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 500


class TestPrivacyAndSettings:
    def test_get_privacy_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "fetch_privacy_settings",
            {
                "readreceipts": "all",
                "profile": "all",
                "status": "all",
                "online": "all",
                "last": "all",
                "groupadd": "all",
            },
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get("/api/privacy", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["readreceipts"] == "all"

    def test_update_privacy_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result("update_privacy_settings", {"status": "updated"})
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/privacy",
                json={"readreceipts": "none"},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200

    def test_get_settings_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "get_settings",
            {"reject_call": True, "msg_call": "Busy", "always_online": False},
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.get("/api/settings", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 200
        assert resp.json()["reject_call"] is True

    def test_update_settings_success(self):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_result(
            "update_settings", {"reject_call": False, "always_online": True}
        )
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            resp = client.post(
                "/api/settings",
                json={"reject_call": False},
                headers={"X-API-Key": MOCK_API_KEY},
            )
        assert resp.status_code == 200


class TestAdminEndpoints:
    def test_create_tenant_success(self):
        app = _make_app(admin_key=MOCK_ADMIN_KEY)
        mock_tenant = MagicMock(spec=Tenant)
        mock_tenant.name = "NewTenant"
        mock_tenant.created_at = datetime.now(timezone.utc)
        with (
            patch(
                "src.api.routes.tenant_manager.create_tenant",
                new_callable=AsyncMock,
                return_value=(mock_tenant, "new-api-key"),
            ),
            TestClient(app) as client,
        ):
            resp = client.post(
                "/admin/v1/tenants?name=NewTenant",
                headers={"X-API-Key": MOCK_ADMIN_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["api_key"] == "new-api-key"

    def test_list_tenants_success(self):
        app = _make_app(admin_key=MOCK_ADMIN_KEY)
        mock_t = MagicMock(spec=Tenant)
        mock_t.name = "T1"
        mock_t.created_at = datetime.now(timezone.utc)
        mock_t.webhook_urls = []
        with (
            patch("src.api.routes.tenant_manager.list_tenants", return_value=[mock_t]),
            TestClient(app) as client,
        ):
            resp = client.get(
                "/admin/v1/tenants", headers={"X-API-Key": MOCK_ADMIN_KEY}
            )
        assert resp.status_code == 200
        assert len(resp.json()["tenants"]) == 1

    def test_delete_tenant_success(self):
        app = _make_app(admin_key=MOCK_ADMIN_KEY)
        with (
            patch(
                "src.api.routes.tenant_manager.delete_tenant",
                new_callable=AsyncMock,
                return_value=True,
            ),
            TestClient(app) as client,
        ):
            resp = client.delete(
                "/admin/v1/tenants?api_key=some-key",
                headers={"X-API-Key": MOCK_ADMIN_KEY},
            )
        assert resp.status_code == 200
        assert resp.json()["status"] == "deleted"

    def test_delete_tenant_not_found(self):
        app = _make_app(admin_key=MOCK_ADMIN_KEY)
        with (
            patch(
                "src.api.routes.tenant_manager.delete_tenant",
                new_callable=AsyncMock,
                return_value=False,
            ),
            TestClient(app) as client,
        ):
            resp = client.delete(
                "/admin/v1/tenants?api_key=missing",
                headers={"X-API-Key": MOCK_ADMIN_KEY},
            )
        assert resp.status_code == 404

    def test_get_blocked_ips(self):
        app = _make_app(admin_key=MOCK_ADMIN_KEY)
        with (
            patch(
                "src.api.routes.rate_limiter.get_blocked_ips",
                return_value=[{"ip": "1.2.3.4", "remaining_seconds": 300}],
            ),
            TestClient(app) as client,
        ):
            resp = client.get(
                "/admin/v1/rate-limit/blocked", headers={"X-API-Key": MOCK_ADMIN_KEY}
            )
        assert resp.status_code == 200
        assert len(resp.json()["blocked_ips"]) == 1

    def test_block_ip_success(self):
        app = _make_app(admin_key=MOCK_ADMIN_KEY)
        with (
            patch("src.api.routes.rate_limiter.block_ip") as mock_block,
            TestClient(app) as client,
        ):
            resp = client.post(
                "/admin/v1/rate-limit/block?ip=1.2.3.4",
                headers={"X-API-Key": MOCK_ADMIN_KEY},
            )
        assert resp.status_code == 200
        mock_block.assert_called_once_with("1.2.3.4", reason="admin")

    def test_unblock_ip_success(self):
        app = _make_app(admin_key=MOCK_ADMIN_KEY)
        with (
            patch("src.api.routes.rate_limiter.unblock_ip", return_value=True),
            TestClient(app) as client,
        ):
            resp = client.delete(
                "/admin/v1/rate-limit/block?ip=1.2.3.4",
                headers={"X-API-Key": MOCK_ADMIN_KEY},
            )
        assert resp.status_code == 200

    def test_unblock_ip_not_found(self):
        app = _make_app(admin_key=MOCK_ADMIN_KEY)
        with (
            patch("src.api.routes.rate_limiter.unblock_ip", return_value=False),
            TestClient(app) as client,
        ):
            resp = client.delete(
                "/admin/v1/rate-limit/block?ip=1.2.3.4",
                headers={"X-API-Key": MOCK_ADMIN_KEY},
            )
        assert resp.status_code == 404

    def test_rate_limit_stats(self):
        app = _make_app(admin_key=MOCK_ADMIN_KEY)
        with (
            patch(
                "src.api.routes.rate_limiter.get_stats",
                return_value={
                    "unique_ips_minute": 5,
                    "unique_ips_hour": 10,
                    "blocked_ips_count": 0,
                },
            ),
            TestClient(app) as client,
        ):
            resp = client.get(
                "/admin/v1/rate-limit/stats", headers={"X-API-Key": MOCK_ADMIN_KEY}
            )
        assert resp.status_code == 200

    def test_rate_limit_stats_for_ip(self):
        app = _make_app(admin_key=MOCK_ADMIN_KEY)
        with (
            patch(
                "src.api.routes.rate_limiter.get_stats",
                return_value={
                    "ip": "1.2.3.4",
                    "requests_last_minute": 3,
                    "blocked": False,
                },
            ),
            TestClient(app) as client,
        ):
            resp = client.get(
                "/admin/v1/rate-limit/stats?ip=1.2.3.4",
                headers={"X-API-Key": MOCK_ADMIN_KEY},
            )
        assert resp.status_code == 200

    def test_get_failed_auth_attempts(self):
        app = _make_app(admin_key=MOCK_ADMIN_KEY)
        with (
            patch(
                "src.api.routes.rate_limiter.get_failed_auth_attempts",
                return_value={"ips_with_failures": {}, "max_attempts": 5},
            ),
            TestClient(app) as client,
        ):
            resp = client.get(
                "/admin/v1/rate-limit/failed-auth",
                headers={"X-API-Key": MOCK_ADMIN_KEY},
            )
        assert resp.status_code == 200

    def test_clear_failed_auth_attempts(self):
        app = _make_app(admin_key=MOCK_ADMIN_KEY)
        with (
            patch("src.api.routes.rate_limiter.clear_failed_auth") as mock_clear,
            TestClient(app) as client,
        ):
            resp = client.delete(
                "/admin/v1/rate-limit/failed-auth?ip=1.2.3.4",
                headers={"X-API-Key": MOCK_ADMIN_KEY},
            )
        assert resp.status_code == 200
        mock_clear.assert_called_once_with("1.2.3.4")

    def test_admin_no_auth_401(self):
        app = FastAPI()
        app.include_router(admin_router)
        with TestClient(app) as client:
            resp = client.get("/admin/v1/tenants")
        assert resp.status_code == 401

    def test_admin_invalid_auth_401(self):
        app = FastAPI()
        app.include_router(admin_router)
        with (
            patch("src.api.auth.settings") as mock_settings,
            patch("src.api.auth.rate_limiter") as mock_rl,
            TestClient(app) as client,
        ):
            mock_settings.admin_api_key = "real-admin-key"
            mock_rl.is_blocked.return_value = False
            mock_rl.record_failed_auth.return_value = (1, False)
            resp = client.get("/admin/v1/tenants", headers={"X-API-Key": "wrong-key"})
        assert resp.status_code == 401

    def test_admin_no_admin_key_configured_503(self):
        app = FastAPI()
        app.include_router(admin_router)
        with (
            patch("src.api.auth.settings") as mock_settings,
            patch("src.api.auth.rate_limiter") as mock_rl,
            TestClient(app) as client,
        ):
            mock_settings.admin_api_key = ""
            mock_rl.is_blocked.return_value = False
            resp = client.get("/admin/v1/tenants", headers={"X-API-Key": "some-key"})
        assert resp.status_code == 503


class TestAuthFailureOnAllEndpoints:
    def test_any_endpoint_returns_401_without_auth(self):
        app = FastAPI()
        app.include_router(router)
        with TestClient(app) as client:
            resp = client.get("/api/status")
        assert resp.status_code == 401

    def test_any_endpoint_returns_401_with_invalid_key(self):
        app = FastAPI()
        app.include_router(router)
        with (
            patch("src.api.auth.settings") as mock_settings,
            patch("src.api.auth.rate_limiter") as mock_rl,
            patch("src.api.auth.tenant_manager") as mock_tm,
            TestClient(app) as client,
        ):
            mock_settings.trusted_proxies = []
            mock_rl.is_blocked.return_value = False
            mock_rl.record_failed_auth.return_value = (1, False)
            mock_tm.get_tenant_by_key.return_value = None
            resp = client.get("/api/status", headers={"X-API-Key": "bad-key"})
        assert resp.status_code == 401


class TestBridgeErrorOnAllEndpointGroups:
    @pytest.mark.parametrize(
        "method,path,body,bridge_method",
        [
            ("POST", "/api/login", None, "login"),
            (
                "POST",
                "/api/react",
                {"chat": "g@g", "message_id": "m1", "emoji": "x"},
                "send_reaction",
            ),
            (
                "POST",
                "/api/poll",
                {"to": "g@g", "name": "P", "values": ["A"]},
                "send_poll",
            ),
            ("POST", "/api/typing?to=123", None, "send_typing"),
            ("GET", "/api/auth/exists", None, "auth_exists"),
            ("GET", "/api/auth/age", None, "auth_age"),
            ("GET", "/api/auth/self", None, "self_id"),
            ("GET", "/api/contacts", None, "get_contacts"),
        ],
    )
    def test_endpoint_returns_500_on_bridge_error(
        self, method, path, body, bridge_method
    ):
        tenant = _make_tenant()
        bridge = _mock_bridge()
        bridge.set_error(bridge_method, BridgeError("bridge down"))
        app = _make_app(tenant)
        with _patch_get_bridge(bridge), TestClient(app) as client:
            if body is not None:
                resp = client.request(
                    method, path, json=body, headers={"X-API-Key": MOCK_API_KEY}
                )
            else:
                resp = client.request(method, path, headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 500


class TestInputValidation:
    def test_send_message_missing_to_field(self):
        app = FastAPI()
        app.include_router(router)
        tenant = _make_tenant()
        app.dependency_overrides[get_tenant] = lambda: tenant
        with TestClient(app) as client:
            resp = client.post(
                "/api/send", json={"text": "hi"}, headers={"X-API-Key": MOCK_API_KEY}
            )
        assert resp.status_code == 422

    def test_typing_missing_to_param(self):
        app = FastAPI()
        app.include_router(router)
        tenant = _make_tenant()
        app.dependency_overrides[get_tenant] = lambda: tenant
        with TestClient(app) as client:
            resp = client.post("/api/typing", headers={"X-API-Key": MOCK_API_KEY})
        assert resp.status_code == 422

    def test_group_update_subject_missing_params(self):
        app = FastAPI()
        app.include_router(router)
        tenant = _make_tenant()
        app.dependency_overrides[get_tenant] = lambda: tenant
        with TestClient(app) as client:
            resp = client.post(
                "/api/group/updateSubject", headers={"X-API-Key": MOCK_API_KEY}
            )
        assert resp.status_code == 422

    def test_send_reaction_missing_fields(self):
        app = FastAPI()
        app.include_router(router)
        tenant = _make_tenant()
        app.dependency_overrides[get_tenant] = lambda: tenant
        with TestClient(app) as client:
            resp = client.post(
                "/api/react", json={"chat": "g@g"}, headers={"X-API-Key": MOCK_API_KEY}
            )
        assert resp.status_code == 422
