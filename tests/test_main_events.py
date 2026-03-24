import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock
from pathlib import Path

from src.tenant import Tenant
from src.store.messages import MessageStore, StoredMessage


def make_tenant(**overrides):
    defaults = {
        "api_key_hash": "abc123hash456",
        "name": "Test Tenant",
        "connection_state": "disconnected",
        "has_auth": True,
        "creds_json": {"some": "data"},
        "webhook_urls": [],
        "chatwoot_config": None,
        "self_jid": "123@s.whatsapp.net",
        "self_phone": "+1234567890",
        "self_name": "Test",
    }
    defaults.update(overrides)
    return Tenant(**defaults)


class MockWebSocket:
    def __init__(self):
        self.sent_messages = []
        self.accepted = False
        self.closed = False

    async def accept(self):
        self.accepted = True

    async def send_text(self, message):
        self.sent_messages.append(message)

    async def close(self, code=1000, reason=None):
        self.closed = True


@pytest.fixture
def tenant():
    return make_tenant()


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.fixture
def mock_admin_ws():
    return AsyncMock()


@pytest.fixture
def app_state(tenant, mock_db, mock_admin_ws, monkeypatch):
    monkeypatch.setattr("src.main.tenant_manager._db", mock_db)
    monkeypatch.setattr("src.main.admin_ws_manager", mock_admin_ws)
    monkeypatch.setattr("src.main.tenant_manager._tenants", {"abc123hash456": tenant})
    monkeypatch.setattr("src.main.tenant_manager._event_handler", MagicMock())
    monkeypatch.setattr("src.main.log_buffer_inst", MagicMock())
    monkeypatch.setattr("src.main.queue_broadcast", MagicMock())
    yield tenant, mock_db, mock_admin_ws


class TestHandleQrEvent:
    def test_qr_broadcasts_to_admin(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        from src.main import _handle_qr_event

        _handle_qr_event(
            "qr", tenant, "abc123hash456", {"qr": "qr_data", "qr_data_url": "url"}
        )
        mock_admin_ws.broadcast.assert_called_once()

    def test_qr_triggers_chatwoot_when_enabled(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.chatwoot_config = {"enabled": True, "url": "http://cw.test"}
        mock_create_task = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_create_task)
        from src.main import _handle_qr_event

        _handle_qr_event("qr", tenant, "abc123hash456", {"qr": "data"})
        assert mock_create_task.call_count >= 2

    def test_qr_no_chatwoot_when_disabled(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.chatwoot_config = None
        mock_create_task = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_create_task)
        from src.main import _handle_qr_event

        _handle_qr_event("qr", tenant, "abc123hash456", {"qr": "data"})
        assert mock_create_task.call_count == 1


class TestHandleConnectedEvent:
    def test_updates_session_state(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        monkeypatch.setattr("src.main.tenant_manager.update_session_state", AsyncMock())
        from src.main import _handle_connected_event

        _handle_connected_event(
            "connected",
            tenant,
            "abc123hash456",
            {"jid": "123@s.whatsapp.net", "phone": "+123", "name": "Test"},
        )
        from src.main import tenant_manager

        tenant_manager.update_session_state.assert_called_once()


class TestHandleDisconnectedEvent:
    def test_logged_out_clears_creds(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        monkeypatch.setattr("src.main.tenant_manager.update_session_state", AsyncMock())
        monkeypatch.setattr("src.main.tenant_manager.clear_creds", AsyncMock())
        from src.main import _handle_disconnected_event

        _handle_disconnected_event(
            "disconnected",
            tenant,
            "abc123hash456",
            {"reason": "logout", "reason_name": "loggedOut"},
        )
        from src.main import tenant_manager

        tenant_manager.clear_creds.assert_called_once_with(tenant)

    def test_banned_does_not_clear_creds(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        monkeypatch.setattr("src.main.tenant_manager.update_session_state", AsyncMock())
        monkeypatch.setattr("src.main.tenant_manager.clear_creds", AsyncMock())
        from src.main import _handle_disconnected_event

        _handle_disconnected_event(
            "disconnected",
            tenant,
            "abc123hash456",
            {"reason": "banned", "reason_name": "banned"},
        )
        from src.main import tenant_manager

        tenant_manager.clear_creds.assert_not_called()

    def test_normal_disconnect_triggers_reconnect(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        monkeypatch.setattr("src.main.trigger_bridge_reconnect", AsyncMock())
        from src.main import _handle_disconnected_event

        _handle_disconnected_event(
            "disconnected",
            tenant,
            "abc123hash456",
            {
                "reason": "connection_lost",
                "reason_name": "connection_lost",
                "should_reconnect": True,
            },
        )
        from src.main import trigger_bridge_reconnect

        assert trigger_bridge_reconnect.called

    def test_no_reconnect_when_should_reconnect_false(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        monkeypatch.setattr("src.main.trigger_bridge_reconnect", AsyncMock())
        from src.main import _handle_disconnected_event

        _handle_disconnected_event(
            "disconnected",
            tenant,
            "abc123hash456",
            {
                "reason": "user",
                "reason_name": "user_request",
                "should_reconnect": False,
            },
        )
        from src.main import trigger_bridge_reconnect

        trigger_bridge_reconnect.assert_not_called()


class TestHandleStateEvent:
    def test_reconnecting_updates_state(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        monkeypatch.setattr("src.main.tenant_manager.update_session_state", AsyncMock())
        from src.main import _handle_state_event

        _handle_state_event(
            "reconnecting", tenant, "abc123hash456", {"reason": "timeout"}
        )
        from src.main import tenant_manager

        tenant_manager.update_session_state.assert_called_once()

    def test_reconnect_failed_returns_early_without_update(
        self, app_state, monkeypatch
    ):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        monkeypatch.setattr("src.main.tenant_manager.update_session_state", AsyncMock())
        from src.main import _handle_state_event

        _handle_state_event(
            "reconnect_failed", tenant, "abc123hash456", {"error": "fail"}
        )
        from src.main import tenant_manager

        tenant_manager.update_session_state.assert_not_called()

    def test_connecting_updates_state(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        monkeypatch.setattr("src.main.tenant_manager.update_session_state", AsyncMock())
        from src.main import _handle_state_event

        _handle_state_event("connecting", tenant, "abc123hash456", {})
        from src.main import tenant_manager

        tenant_manager.update_session_state.assert_called_once()


class TestHandleAuthUpdateEvent:
    def test_saves_auth_state_when_params(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        monkeypatch.setattr("src.main.tenant_manager.save_auth_state", AsyncMock())
        from src.main import _handle_auth_update_event

        _handle_auth_update_event(
            "auth.update", tenant, "abc123hash456", {"creds": "data"}
        )
        from src.main import tenant_manager

        tenant_manager.save_auth_state.assert_called_once()

    def test_skips_when_no_params(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        from src.main import _handle_auth_update_event

        _handle_auth_update_event("auth.update", tenant, "abc123hash456", None)
        mock_ctwl.assert_not_called()

    def test_skips_when_empty_params(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        from src.main import _handle_auth_update_event

        _handle_auth_update_event("auth.update", tenant, "abc123hash456", {})
        mock_ctwl.assert_not_called()


class TestHandleSyncEvent:
    def test_contacts_sync_creates_task(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        from src.main import _handle_sync_event

        _handle_sync_event(
            "contacts", tenant, "abc123hash456", {"contacts": [{"jid": "a@b.c"}]}
        )
        from src.main import create_task_with_logging

        create_task_with_logging.assert_called_once()

    def test_chats_history_sync_creates_task(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        from src.main import _handle_sync_event

        _handle_sync_event(
            "chats_history", tenant, "abc123hash456", {"chats": [], "total_messages": 0}
        )
        from src.main import create_task_with_logging

        create_task_with_logging.assert_called_once()


class TestHandleMessageLogEvent:
    def test_message_event_does_not_raise(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        from src.main import _handle_message_log_event

        _handle_message_log_event(
            "message", tenant, "abc123hash456", {"from": "123", "text": "hi"}
        )

    def test_sent_event_does_not_raise(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        from src.main import _handle_message_log_event

        _handle_message_log_event(
            "sent", tenant, "abc123hash456", {"to": "456", "text": "hi"}
        )


class TestHandleChatwootMessageEvent:
    def test_skips_when_chatwoot_disabled(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.chatwoot_config = None
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        from src.main import _handle_chatwoot_message_event

        _handle_chatwoot_message_event(
            "message_deleted", tenant, "abc123hash456", {"message_id": "id"}
        )
        mock_ctwl.assert_not_called()

    def test_triggers_chatwoot_when_enabled(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.chatwoot_config = {"enabled": True}
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        from src.main import _handle_chatwoot_message_event

        _handle_chatwoot_message_event(
            "message_deleted", tenant, "abc123hash456", {"message_id": "id"}
        )
        from src.main import create_task_with_logging

        create_task_with_logging.assert_called_once()

    def test_message_read_triggers_chatwoot(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.chatwoot_config = {"enabled": True}
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        from src.main import _handle_chatwoot_message_event

        _handle_chatwoot_message_event(
            "message_read", tenant, "abc123hash456", {"chat_jid": "grp@g.us"}
        )
        from src.main import create_task_with_logging

        create_task_with_logging.assert_called_once()


class TestStoreMessage:
    def test_stores_inbound_message(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_store = MagicMock()
        mock_store.max_messages = 100
        mock_store._messages = []
        tenant.message_store = mock_store
        del mock_store.add_with_persist
        from src.main import _store_message

        _store_message(
            "message",
            tenant,
            {
                "id": "msg1",
                "from": "123@s.whatsapp.net",
                "text": "hi",
                "type": "text",
                "timestamp": 1000,
            },
        )
        mock_store.add.assert_called_once()

    def test_stores_outbound_sent_message(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_store = MagicMock()
        mock_store.max_messages = 100
        mock_store._messages = []
        tenant.message_store = mock_store
        del mock_store.add_with_persist
        from src.main import _store_message

        _store_message(
            "sent",
            tenant,
            {
                "id": "msg2",
                "to": "456@s.whatsapp.net",
                "text": "hello",
                "type": "text",
                "timestamp": 1000,
            },
        )
        mock_store.add.assert_called_once()
        msg = mock_store.add.call_args[0][0]
        assert msg.direction == "outbound"

    def test_skips_when_no_message_store(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.message_store = None
        from src.main import _store_message

        _store_message("message", tenant, {"id": "msg1", "from": "123"})
        pass

    def test_stores_message_with_add_with_persist(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_store = MagicMock()
        mock_store.add_with_persist = AsyncMock()
        tenant.message_store = mock_store
        monkeypatch.setattr("src.main.create_task_with_logging", MagicMock())
        from src.main import _store_message

        _store_message(
            "message",
            tenant,
            {"id": "msg1", "from": "123", "type": "text", "timestamp": 1000},
        )
        from src.main import create_task_with_logging

        create_task_with_logging.assert_called()

    def test_triggers_media_download_for_image(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.message_store = MessageStore(max_messages=100)
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        from src.main import _store_message

        _store_message(
            "message",
            tenant,
            {
                "id": "msg1",
                "from": "123",
                "type": "image",
                "media_url": "http://img.url",
                "mimetype": "image/jpeg",
                "timestamp": 1000,
            },
        )
        calls = mock_ctwl.call_args_list
        media_call = [c for c in calls if "cache_media" in str(c)]
        assert len(media_call) == 1

    def test_no_media_download_for_text(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.message_store = MessageStore(max_messages=100)
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        from src.main import _store_message

        _store_message(
            "message",
            tenant,
            {"id": "msg1", "from": "123", "type": "text", "timestamp": 1000},
        )
        calls = mock_ctwl.call_args_list
        media_call = [c for c in calls if "cache_media" in str(c)]
        assert len(media_call) == 0


class TestBroadcastToWebsockets:
    def test_broadcasts_to_manager(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        monkeypatch.setattr("src.main.manager.broadcast", AsyncMock())
        from src.main import _broadcast_to_websockets

        _broadcast_to_websockets("message", tenant, "abc123hash456", {"from": "123"})
        from src.main import create_task_with_logging, manager

        calls = [str(c) for c in mock_ctwl.call_args_list]
        assert any("broadcast_event" in c for c in calls)

    def test_state_change_broadcasts_to_admin(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        monkeypatch.setattr("src.main.manager.broadcast", AsyncMock())
        from src.main import _broadcast_to_websockets

        _broadcast_to_websockets("connected", tenant, "abc123hash456", {"jid": "123"})
        from src.main import admin_ws_manager

        admin_ws_manager.broadcast.assert_called()

    def test_message_broadcasts_to_admin(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        monkeypatch.setattr("src.main.manager.broadcast", AsyncMock())
        from src.main import _broadcast_to_websockets

        _broadcast_to_websockets(
            "message", tenant, "abc123hash456", {"from": "123", "push_name": "Alice"}
        )
        from src.main import admin_ws_manager

        admin_ws_manager.broadcast.assert_called()

    def test_sent_broadcasts_to_admin(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        monkeypatch.setattr("src.main.manager.broadcast", AsyncMock())
        from src.main import _broadcast_to_websockets

        _broadcast_to_websockets("sent", tenant, "abc123hash456", {"to": "456"})
        from src.main import admin_ws_manager

        admin_ws_manager.broadcast.assert_called()

    def test_admin_broadcast_uses_jid_for_sender_name(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        monkeypatch.setattr("src.main.manager.broadcast", AsyncMock())
        from src.main import _broadcast_to_websockets

        _broadcast_to_websockets(
            "message", tenant, "abc123hash456", {"from": "1234567890@s.whatsapp.net"}
        )
        call_args = mock_admin_ws.broadcast.call_args
        assert call_args[0][0] == "new_message"
        assert call_args[0][1]["sender_name"] == "1234567890"


class TestSendWebhook:
    def test_no_webhook_urls_skips(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.webhook_urls = []
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        from src.main import _send_webhook

        _send_webhook("message", tenant, {"from": "123"})
        mock_ctwl.assert_not_called()

    def test_with_webhook_urls_sends(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.webhook_urls = ["http://hook.test"]
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        monkeypatch.setattr("src.main.WebhookSender", MagicMock())
        from src.main import _send_webhook

        _send_webhook("message", tenant, {"from": "123"})
        mock_ctwl.assert_called_once()


class TestHandleChatwootIntegration:
    def test_skips_when_disabled(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.chatwoot_config = None
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        from src.main import _handle_chatwoot_integration

        _handle_chatwoot_integration("message", tenant, {"from": "123"})
        mock_ctwl.assert_not_called()

    def test_triggers_for_message(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.chatwoot_config = {"enabled": True}
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        from src.main import _handle_chatwoot_integration

        _handle_chatwoot_integration("message", tenant, {"from": "123"})
        mock_ctwl.assert_called_once()

    def test_triggers_for_connected(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.chatwoot_config = {"enabled": True}
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        from src.main import _handle_chatwoot_integration

        _handle_chatwoot_integration("connected", tenant, {})
        mock_ctwl.assert_called_once()

    def test_skips_for_unknown_event(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.chatwoot_config = {"enabled": True}
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        from src.main import _handle_chatwoot_integration

        _handle_chatwoot_integration("unknown_event", tenant, {})
        mock_ctwl.assert_not_called()


class TestHandleBridgeEvent:
    def test_no_tenant_id_ignores(self, monkeypatch):
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        from src.main import handle_bridge_event

        handle_bridge_event("message", {"from": "123"}, None)
        mock_ctwl.assert_not_called()

    def test_unknown_tenant_ignores(self, monkeypatch):
        monkeypatch.setattr("src.main.tenant_manager._tenants", {})
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        from src.main import handle_bridge_event

        handle_bridge_event("message", {"from": "123"}, "nonexistent")
        mock_ctwl.assert_not_called()

    def test_dispatches_to_known_handler(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        monkeypatch.setattr("src.main.manager.broadcast", AsyncMock())
        monkeypatch.setattr("src.main.queue_broadcast", MagicMock())
        monkeypatch.setattr("src.main.log_buffer_inst.add_sync", MagicMock())
        from src.main import handle_bridge_event

        handle_bridge_event("qr", {"qr": "data"}, "abc123hash456")

    def test_unknown_event_type_still_broadcasts(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        monkeypatch.setattr("src.main.manager.broadcast", AsyncMock())
        monkeypatch.setattr("src.main.queue_broadcast", MagicMock())
        monkeypatch.setattr("src.main.log_buffer_inst.add_sync", MagicMock())
        from src.main import handle_bridge_event

        handle_bridge_event("custom_event", {"data": "val"}, "abc123hash456")
        calls = [str(c) for c in mock_ctwl.call_args_list]
        assert any("broadcast_event" in c for c in calls)

    def test_message_event_stores_and_broadcasts(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_store = MagicMock()
        tenant.message_store = mock_store
        del mock_store.add_with_persist
        mock_ctwl = MagicMock()
        monkeypatch.setattr("src.main.create_task_with_logging", mock_ctwl)
        monkeypatch.setattr("src.main.manager.broadcast", AsyncMock())
        monkeypatch.setattr("src.main.queue_broadcast", MagicMock())
        monkeypatch.setattr("src.main.log_buffer_inst.add_sync", MagicMock())
        from src.main import handle_bridge_event

        handle_bridge_event(
            "message",
            {
                "id": "m1",
                "from": "123@s.whatsapp.net",
                "type": "text",
                "timestamp": 1000,
            },
            "abc123hash456",
        )
        mock_store.add.assert_called_once()


class TestHandleBridgeCrash:
    async def test_crash_triggers_restart(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant._restarting = False
        monkeypatch.setattr(
            "src.main.tenant_manager.can_restart", MagicMock(return_value=True)
        )
        monkeypatch.setattr("src.main.tenant_manager.record_restart", MagicMock())
        monkeypatch.setattr(
            "src.main.tenant_manager.reset_health_failures", MagicMock()
        )
        monkeypatch.setattr("src.main.settings.restart_cooldown_seconds", 0)

        mock_bridge = AsyncMock()
        mock_bridge.stop = AsyncMock()
        mock_bridge.start = AsyncMock()
        mock_bridge._process = AsyncMock()
        mock_bridge._process.pid = 99
        mock_bridge._event_handlers = []
        tenant.bridge = mock_bridge

        with patch("src.main.BaileysBridge", return_value=mock_bridge):
            from src.main import handle_bridge_crash

            await handle_bridge_crash(tenant)

    async def test_crash_updates_state_on_failure(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant._restarting = True
        monkeypatch.setattr("src.main.tenant_manager.update_session_state", AsyncMock())
        from src.main import handle_bridge_crash

        await handle_bridge_crash(tenant)
        from src.main import tenant_manager

        tenant_manager.update_session_state.assert_called_once()


class TestTriggerBridgeReconnect:
    async def test_calls_restart_bridge(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant._restarting = True
        monkeypatch.setattr("src.main._restart_bridge", AsyncMock(return_value=False))
        from src.main import trigger_bridge_reconnect

        await trigger_bridge_reconnect(tenant)
        from src.main import _restart_bridge

        _restart_bridge.assert_called_once_with(tenant, "disconnect_reconnect")


class TestRestartBridge:
    async def test_restart_skips_when_already_restarting(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant._restarting = True
        from src.main import _restart_bridge

        result = await _restart_bridge(tenant, "test")
        assert result is False

    async def test_restart_skips_when_no_auth(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant._restarting = False
        tenant.has_auth = False
        tenant.creds_json = None
        from src.main import _restart_bridge

        result = await _restart_bridge(tenant, "test")
        assert result is False

    async def test_restart_skips_when_rate_limited(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant._restarting = False
        monkeypatch.setattr(
            "src.main.tenant_manager.can_restart", MagicMock(return_value=False)
        )
        from src.main import _restart_bridge

        result = await _restart_bridge(tenant, "test")
        assert result is False

    async def test_restart_success(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant._restarting = False
        monkeypatch.setattr(
            "src.main.tenant_manager.can_restart", MagicMock(return_value=True)
        )
        monkeypatch.setattr("src.main.tenant_manager.record_restart", MagicMock())
        monkeypatch.setattr(
            "src.main.tenant_manager.reset_health_failures", MagicMock()
        )
        monkeypatch.setattr("src.main.tenant_manager._event_handler", None)
        monkeypatch.setattr("src.main.settings.restart_cooldown_seconds", 0)

        mock_bridge = AsyncMock()
        mock_bridge.stop = AsyncMock()
        mock_bridge.start = AsyncMock()
        mock_bridge._process = AsyncMock()
        mock_bridge._process.pid = 99
        mock_bridge._event_handlers = []
        tenant.bridge = mock_bridge

        with patch("src.main.BaileysBridge", return_value=mock_bridge):
            from src.main import _restart_bridge

            result = await _restart_bridge(tenant, "test")
            assert result is True
            assert tenant.bridge is mock_bridge

    async def test_restart_resets_restarting_flag(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant._restarting = False
        monkeypatch.setattr(
            "src.main.tenant_manager.can_restart", MagicMock(return_value=False)
        )
        from src.main import _restart_bridge

        await _restart_bridge(tenant, "test")
        assert tenant._restarting is False


class TestConnectionManager:
    def test_connect_adds_websocket(self):
        from src.main import ConnectionManager

        mgr = ConnectionManager()
        ws = MockWebSocket()
        asyncio.run(mgr.connect("hash1", ws))
        assert ws.accepted is True
        assert "hash1" in mgr._connections
        assert len(mgr._connections["hash1"]) == 1

    def test_disconnect_removes_websocket(self):
        from src.main import ConnectionManager

        mgr = ConnectionManager()
        ws = MockWebSocket()
        asyncio.run(mgr.connect("hash1", ws))
        mgr.disconnect("hash1", ws)
        assert len(mgr._connections["hash1"]) == 0

    def test_disconnect_nonexistent_websocket_no_error(self):
        from src.main import ConnectionManager

        mgr = ConnectionManager()
        ws = MockWebSocket()
        mgr.disconnect("hash1", ws)

    async def test_broadcast_sends_to_all_connections(self):
        from src.main import ConnectionManager

        mgr = ConnectionManager()
        ws1 = MockWebSocket()
        ws2 = MockWebSocket()
        await mgr.connect("hash1", ws1)
        await mgr.connect("hash1", ws2)
        await mgr.broadcast("hash1", "message", {"text": "hi"})
        assert len(ws1.sent_messages) == 1
        assert len(ws2.sent_messages) == 1
        data = json.loads(ws1.sent_messages[0])
        assert data["type"] == "message"
        assert data["data"]["text"] == "hi"

    async def test_broadcast_nonexistent_key_no_error(self):
        from src.main import ConnectionManager

        mgr = ConnectionManager()
        await mgr.broadcast("nonexistent", "event", {})

    async def test_broadcast_handles_send_error(self):
        from src.main import ConnectionManager

        mgr = ConnectionManager()
        ws = MagicMock()
        ws.send_text = AsyncMock(side_effect=RuntimeError("send error"))
        mgr._connections["hash1"] = [ws]
        await mgr.broadcast("hash1", "event", {})
        assert ws.send_text.called


class TestDownloadAndCacheMedia:
    async def test_skip_when_no_media_url(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        from src.main import _download_and_cache_media

        await _download_and_cache_media(
            tenant, "msg1", "", "image", "image/jpeg", "f.jpg"
        )

    async def test_skip_when_no_message_id(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        from src.main import _download_and_cache_media

        await _download_and_cache_media(
            tenant, "", "http://url", "image", "image/jpeg", "f.jpg"
        )

    async def test_downloads_and_caches(self, app_state, monkeypatch, tmp_path):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.settings.data_dir", tmp_path)

        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_response.headers = {"content-length": "10"}
        mock_response.aiter_bytes = MagicMock(
            return_value=AsyncIteratorBytes([b"hello12345"])
        )

        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client_cm)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)
        mock_client_cm.stream = MagicMock(return_value=mock_response)

        mock_response_cm = AsyncMock()
        mock_response_cm.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client_cm.stream = MagicMock(return_value=mock_response_cm)

        import httpx as httpx_mod

        monkeypatch.setattr(
            httpx_mod, "AsyncClient", MagicMock(return_value=mock_client_cm)
        )
        mock_update = AsyncMock()
        monkeypatch.setattr("src.main._update_media_url_in_db", mock_update)

        from src.main import _download_and_cache_media

        await _download_and_cache_media(
            tenant, "msg1", "http://img.url/img.jpg", "image", "image/jpeg", "img.jpg"
        )
        media_dir = tmp_path / "media" / tenant.api_key_hash
        assert media_dir.exists()
        files = list(media_dir.iterdir())
        assert len(files) == 1

    async def test_skips_already_cached_file(self, app_state, monkeypatch, tmp_path):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.settings.data_dir", tmp_path)

        media_dir = tmp_path / "media" / tenant.api_key_hash
        media_dir.mkdir(parents=True)
        (media_dir / "msg1.jpg").write_bytes(b"cached")

        mock_update = AsyncMock()
        monkeypatch.setattr("src.main._update_media_url_in_db", mock_update)

        from src.main import _download_and_cache_media

        await _download_and_cache_media(
            tenant, "msg1", "http://img.url", "image", "image/jpeg", "f.jpg"
        )
        mock_update.assert_called_once()

    async def test_skips_on_http_error(self, app_state, monkeypatch, tmp_path):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.settings.data_dir", tmp_path)

        mock_resp = AsyncMock(status_code=404)
        mock_response_cm = AsyncMock()
        mock_response_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_response_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client_cm)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)
        mock_client_cm.stream = MagicMock(return_value=mock_response_cm)

        import httpx as httpx_mod

        monkeypatch.setattr(
            httpx_mod, "AsyncClient", MagicMock(return_value=mock_client_cm)
        )

        from src.main import _download_and_cache_media

        await _download_and_cache_media(
            tenant, "msg1", "http://img.url", "image", "image/jpeg", "f.jpg"
        )
        media_dir = tmp_path / "media" / tenant.api_key_hash
        files = list(media_dir.iterdir()) if media_dir.exists() else []
        assert len(files) == 0

    async def test_skips_on_content_length_too_large(
        self, app_state, monkeypatch, tmp_path
    ):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.settings.data_dir", tmp_path)

        mock_resp = AsyncMock(status_code=200)
        mock_resp.headers = {"content-length": str(30 * 1024 * 1024)}
        mock_response_cm = AsyncMock()
        mock_response_cm.__aenter__ = AsyncMock(return_value=mock_resp)
        mock_response_cm.__aexit__ = AsyncMock(return_value=False)

        mock_client_cm = AsyncMock()
        mock_client_cm.__aenter__ = AsyncMock(return_value=mock_client_cm)
        mock_client_cm.__aexit__ = AsyncMock(return_value=False)
        mock_client_cm.stream = MagicMock(return_value=mock_response_cm)

        import httpx as httpx_mod

        monkeypatch.setattr(
            httpx_mod, "AsyncClient", MagicMock(return_value=mock_client_cm)
        )

        from src.main import _download_and_cache_media

        await _download_and_cache_media(
            tenant, "msg1", "http://img.url", "image", "image/jpeg", "f.jpg"
        )


class TestUpdateMediaUrlInDb:
    async def test_updates_when_db_exists(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        from src.main import _update_media_url_in_db

        await _update_media_url_in_db(tenant, "msg1", "/path/to/file.jpg")
        mock_db.update_message_media_url.assert_called_once()

    async def test_no_error_when_no_db(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.tenant_manager._db", None)
        from src.main import _update_media_url_in_db

        await _update_media_url_in_db(tenant, "msg1", "/path")

    async def test_handles_db_error(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_db.update_message_media_url = AsyncMock(side_effect=RuntimeError("db err"))
        from src.main import _update_media_url_in_db

        await _update_media_url_in_db(tenant, "msg1", "/path")


class TestHandleContactsSync:
    async def test_skips_when_no_db(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.tenant_manager._db", None)
        from src.main import handle_contacts_sync

        await handle_contacts_sync(tenant, [{"jid": "a@b.c", "phone": "123"}])

    async def test_syncs_contacts(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_db.upsert_contact = AsyncMock()
        from src.main import handle_contacts_sync

        await handle_contacts_sync(
            tenant, [{"jid": "123@s.whatsapp.net", "phone": "123", "name": "Test"}]
        )
        mock_db.upsert_contact.assert_called_once()

    async def test_skips_contact_without_jid(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_db.upsert_contact = AsyncMock()
        from src.main import handle_contacts_sync

        await handle_contacts_sync(tenant, [{"phone": "123", "name": "Test"}])
        mock_db.upsert_contact.assert_not_called()

    async def test_group_contact_uses_jid_as_phone(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_db.upsert_contact = AsyncMock()
        from src.main import handle_contacts_sync

        await handle_contacts_sync(tenant, [{"jid": "grp@g.us", "is_group": True}])
        mock_db.upsert_contact.assert_called_once()
        call_args = mock_db.upsert_contact.call_args
        assert call_args[1]["phone"] == "grp"
        assert call_args[1]["is_group"] is True

    async def test_handles_contact_sync_error(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_db.upsert_contact = AsyncMock(side_effect=RuntimeError("err"))
        from src.main import handle_contacts_sync

        await handle_contacts_sync(
            tenant, [{"jid": "123@s.whatsapp.net", "phone": "123"}]
        )
        assert mock_db.upsert_contact.called


class TestHandleHistorySync:
    async def test_skips_when_no_db(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        monkeypatch.setattr("src.main.tenant_manager._db", None)
        from src.main import handle_history_sync

        await handle_history_sync(tenant, {"chats": [], "total_messages": 0})

    async def test_skips_when_no_message_store(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.message_store = None
        from src.main import handle_history_sync

        await handle_history_sync(tenant, {"chats": [], "total_messages": 0})

    async def test_syncs_history(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_store_chat = AsyncMock(
            return_value={"stored": 5, "duplicates": 0, "errors": 0}
        )
        import src.utils.history as hist_mod

        monkeypatch.setattr(hist_mod, "store_chat_messages", mock_store_chat)
        from src.main import handle_history_sync

        await handle_history_sync(
            tenant, {"chats": [{"jid": "123@s.whatsapp.net"}], "total_messages": 5}
        )
        mock_store_chat.assert_called_once()


class TestHandleChatwootEvent:
    async def test_skips_when_not_enabled(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.chatwoot_config = None
        from src.main import handle_chatwoot_event

        await handle_chatwoot_event(tenant, "message", {"from": "123"})

    async def test_skips_when_enabled_false(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.chatwoot_config = {"enabled": False}
        from src.main import handle_chatwoot_event

        await handle_chatwoot_event(tenant, "message", {"from": "123"})

    async def test_handles_integration_error(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        tenant.chatwoot_config = {
            "enabled": True,
            "url": "http://cw",
            "api_token": "t",
            "account_id": 1,
            "inbox_id": 1,
        }
        mock_db.get_global_config = AsyncMock(side_effect=RuntimeError("db err"))
        from src.main import handle_chatwoot_event

        await handle_chatwoot_event(tenant, "message", {"from": "123"})


class TestCaptureEventToLogBuffer:
    def test_captures_message_event(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_buffer = MagicMock()
        monkeypatch.setattr("src.main.log_buffer_inst", mock_buffer)
        monkeypatch.setattr("src.main.queue_broadcast", MagicMock())
        from src.main import _capture_event_to_log_buffer

        _capture_event_to_log_buffer(
            "message", tenant, {"from": "123@s.whatsapp.net", "text": "hello"}
        )
        mock_buffer.add_sync.assert_called_once()

    def test_captures_connected_event(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_buffer = MagicMock()
        monkeypatch.setattr("src.main.log_buffer_inst", mock_buffer)
        monkeypatch.setattr("src.main.queue_broadcast", MagicMock())
        from src.main import _capture_event_to_log_buffer

        _capture_event_to_log_buffer(
            "connected", tenant, {"jid": "123", "phone": "+123"}
        )
        mock_buffer.add_sync.assert_called_once()

    def test_captures_disconnected_event(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_buffer = MagicMock()
        monkeypatch.setattr("src.main.log_buffer_inst", mock_buffer)
        monkeypatch.setattr("src.main.queue_broadcast", MagicMock())
        from src.main import _capture_event_to_log_buffer

        _capture_event_to_log_buffer(
            "disconnected", tenant, {"reason": "loggedOut", "reason_name": "loggedOut"}
        )
        mock_buffer.add_sync.assert_called_once()

    def test_captures_qr_event(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_buffer = MagicMock()
        monkeypatch.setattr("src.main.log_buffer_inst", mock_buffer)
        monkeypatch.setattr("src.main.queue_broadcast", MagicMock())
        from src.main import _capture_event_to_log_buffer

        _capture_event_to_log_buffer("qr", tenant, {"qr": "data"})
        mock_buffer.add_sync.assert_called_once()

    def test_captures_sent_event(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_buffer = MagicMock()
        monkeypatch.setattr("src.main.log_buffer_inst", mock_buffer)
        monkeypatch.setattr("src.main.queue_broadcast", MagicMock())
        from src.main import _capture_event_to_log_buffer

        _capture_event_to_log_buffer("sent", tenant, {"to": "456", "text": "hello"})
        mock_buffer.add_sync.assert_called_once()

    def test_captures_contacts_sync_event(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_buffer = MagicMock()
        monkeypatch.setattr("src.main.log_buffer_inst", mock_buffer)
        monkeypatch.setattr("src.main.queue_broadcast", MagicMock())
        from src.main import _capture_event_to_log_buffer

        _capture_event_to_log_buffer(
            "contacts", tenant, {"contacts": [{"jid": "a@b.c"}]}
        )
        mock_buffer.add_sync.assert_called_once()

    def test_entry_has_event_level(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_buffer = MagicMock()
        monkeypatch.setattr("src.main.log_buffer_inst", mock_buffer)
        monkeypatch.setattr("src.main.queue_broadcast", MagicMock())
        from src.main import _capture_event_to_log_buffer

        _capture_event_to_log_buffer("message", tenant, {"from": "123"})
        entry = mock_buffer.add_sync.call_args[0][0]
        assert entry.level == "EVENT"

    def test_entry_has_bridge_source(self, app_state, monkeypatch):
        tenant, mock_db, mock_admin_ws = app_state
        mock_buffer = MagicMock()
        monkeypatch.setattr("src.main.log_buffer_inst", mock_buffer)
        monkeypatch.setattr("src.main.queue_broadcast", MagicMock())
        from src.main import _capture_event_to_log_buffer

        _capture_event_to_log_buffer("message", tenant, {"from": "123"})
        entry = mock_buffer.add_sync.call_args[0][0]
        assert entry.source == "bridge"


class AsyncIteratorBytes:
    def __init__(self, chunks):
        self._chunks = chunks
        self._idx = 0

    def __aiter__(self):
        return self

    async def __anext__(self):
        if self._idx >= len(self._chunks):
            raise StopAsyncIteration
        chunk = self._chunks[self._idx]
        self._idx += 1
        return chunk
