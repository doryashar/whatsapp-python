import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch
from pydantic import ValidationError
from tests.conftest import ADMIN_PASSWORD


def _make_mock_bridge(result=None, error=None):
    bridge = AsyncMock()
    if error:
        bridge.send_message = AsyncMock(side_effect=error)
    else:
        bridge.send_message = AsyncMock(
            return_value=result or {"message_id": "m1", "to": "jid"}
        )
    return bridge


class TestAdminSendMessageModel:
    def test_requires_to_and_text(self):
        from src.admin.routes import AdminSendMessage

        with pytest.raises(ValidationError):
            AdminSendMessage()

    def test_accepts_quoted_fields(self):
        from src.admin.routes import AdminSendMessage

        msg = AdminSendMessage(
            to="jid",
            text="hello",
            quoted_message_id="q1",
            quoted_text="original msg",
            quoted_chat="chat_jid",
        )
        assert msg.quoted_message_id == "q1"
        assert msg.quoted_text == "original msg"
        assert msg.quoted_chat == "chat_jid"

    def test_quoted_fields_default_none(self):
        from src.admin.routes import AdminSendMessage

        msg = AdminSendMessage(to="jid", text="hi")
        assert msg.quoted_message_id is None
        assert msg.quoted_text is None
        assert msg.quoted_chat is None


class TestAdminSendMessageEndpoint:
    @pytest.mark.asyncio
    async def test_send_message_success(self, setup_tenant_manager):
        from src.main import app
        from src.tenant import tenant_manager

        tenant, api_key = await tenant_manager.create_tenant("Send Test")
        tenant.has_auth = True
        mock_bridge = _make_mock_bridge({"message_id": "new_msg", "to": "jid"})
        setup_tenant_manager.get_or_create_bridge = AsyncMock(return_value=mock_bridge)

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
                response = await client.post(
                    f"/admin/api/tenants/{tenant.api_key_hash}/send",
                    json={"to": "jid", "text": "hello"},
                )
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "sent"
                assert data["message_id"] == "new_msg"
        finally:
            await tenant_manager.delete_tenant(api_key)

    @pytest.mark.asyncio
    async def test_send_message_with_quoted_reply(self, setup_tenant_manager):
        from src.main import app
        from src.tenant import tenant_manager

        tenant, api_key = await tenant_manager.create_tenant("Quote Test")
        tenant.has_auth = True
        mock_bridge = _make_mock_bridge()
        setup_tenant_manager.get_or_create_bridge = AsyncMock(return_value=mock_bridge)

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
                response = await client.post(
                    f"/admin/api/tenants/{tenant.api_key_hash}/send",
                    json={
                        "to": "jid",
                        "text": "reply text",
                        "quoted_message_id": "orig_msg_id",
                        "quoted_text": "original message",
                        "quoted_chat": "chat_jid@g.us",
                    },
                )
                assert response.status_code == 200
                mock_bridge.send_message.assert_called_once()
                call_kwargs = mock_bridge.send_message.call_args
                assert call_kwargs.kwargs["quoted_message_id"] == "orig_msg_id"
                assert call_kwargs.kwargs["quoted_text"] == "original message"
                assert call_kwargs.kwargs["quoted_chat"] == "chat_jid@g.us"
        finally:
            await tenant_manager.delete_tenant(api_key)

    @pytest.mark.asyncio
    async def test_send_message_without_quoted_fields(self, setup_tenant_manager):
        from src.main import app
        from src.tenant import tenant_manager

        tenant, api_key = await tenant_manager.create_tenant("No Quote Test")
        tenant.has_auth = True
        mock_bridge = _make_mock_bridge()
        setup_tenant_manager.get_or_create_bridge = AsyncMock(return_value=mock_bridge)

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
                response = await client.post(
                    f"/admin/api/tenants/{tenant.api_key_hash}/send",
                    json={"to": "jid", "text": "hello"},
                )
                assert response.status_code == 200
                call_kwargs = mock_bridge.send_message.call_args.kwargs
                assert call_kwargs["quoted_message_id"] is None
        finally:
            await tenant_manager.delete_tenant(api_key)

    @pytest.mark.asyncio
    async def test_send_message_tenant_not_found(self, setup_tenant_manager):
        from src.main import app

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
            response = await client.post(
                "/admin/api/tenants/nonexistent_hash/send",
                json={"to": "jid", "text": "hello"},
            )
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_send_message_tenant_not_connected(self, setup_tenant_manager):
        from src.main import app
        from src.tenant import tenant_manager

        tenant, api_key = await tenant_manager.create_tenant("Not Connected")
        tenant.has_auth = False

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
                response = await client.post(
                    f"/admin/api/tenants/{tenant.api_key_hash}/send",
                    json={"to": "jid", "text": "hello"},
                )
                assert response.status_code == 400
                assert "not connected" in response.json()["detail"].lower()
        finally:
            await tenant_manager.delete_tenant(api_key)

    @pytest.mark.asyncio
    async def test_send_message_missing_to(self, setup_tenant_manager):
        from src.main import app
        from src.tenant import tenant_manager

        tenant, api_key = await tenant_manager.create_tenant("Missing To")
        tenant.has_auth = True

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
                response = await client.post(
                    f"/admin/api/tenants/{tenant.api_key_hash}/send",
                    json={"text": "hello"},
                )
                assert response.status_code == 422
        finally:
            await tenant_manager.delete_tenant(api_key)

    @pytest.mark.asyncio
    async def test_send_message_missing_text(self, setup_tenant_manager):
        from src.main import app
        from src.tenant import tenant_manager

        tenant, api_key = await tenant_manager.create_tenant("Missing Text")
        tenant.has_auth = True

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
                response = await client.post(
                    f"/admin/api/tenants/{tenant.api_key_hash}/send",
                    json={"to": "jid"},
                )
                assert response.status_code == 422
        finally:
            await tenant_manager.delete_tenant(api_key)

    @pytest.mark.asyncio
    async def test_send_message_bridge_exception(self, setup_tenant_manager):
        from src.main import app
        from src.tenant import tenant_manager

        tenant, api_key = await tenant_manager.create_tenant("Bridge Error")
        tenant.has_auth = True
        mock_bridge = _make_mock_bridge(error=Exception("connection timeout"))
        setup_tenant_manager.get_or_create_bridge = AsyncMock(return_value=mock_bridge)

        try:
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                await client.post("/admin/login", data={"password": ADMIN_PASSWORD})
                response = await client.post(
                    f"/admin/api/tenants/{tenant.api_key_hash}/send",
                    json={"to": "jid", "text": "hello"},
                )
                assert response.status_code == 500
                assert "connection timeout" in response.json()["detail"]
        finally:
            await tenant_manager.delete_tenant(api_key)


class TestBridgeClientSendMessage:
    @pytest.mark.asyncio
    async def test_send_message_with_quoted(self):
        from src.bridge.client import BaileysBridge

        bridge = BaileysBridge(auth_dir="/tmp/test", auto_login=False)
        bridge.call = AsyncMock(return_value={"message_id": "m1"})

        await bridge.send_message(
            to="jid",
            text="reply",
            quoted_message_id="q1",
            quoted_text="original text",
            quoted_chat="chat_jid",
        )

        bridge.call.assert_called_once()
        payload = bridge.call.call_args[0][1]
        assert payload["to"] == "jid"
        assert payload["text"] == "reply"
        assert "quoted" in payload
        assert payload["quoted"]["message_id"] == "q1"
        assert payload["quoted"]["text"] == "original text"
        assert payload["quoted"]["chat"] == "chat_jid"

    @pytest.mark.asyncio
    async def test_send_message_without_quoted(self):
        from src.bridge.client import BaileysBridge

        bridge = BaileysBridge(auth_dir="/tmp/test", auto_login=False)
        bridge.call = AsyncMock(return_value={"message_id": "m1"})

        await bridge.send_message(to="jid", text="hello")

        bridge.call.assert_called_once()
        payload = bridge.call.call_args[0][1]
        assert "quoted" not in payload

    @pytest.mark.asyncio
    async def test_quoted_text_defaults_empty_string(self):
        from src.bridge.client import BaileysBridge

        bridge = BaileysBridge(auth_dir="/tmp/test", auto_login=False)
        bridge.call = AsyncMock(return_value={"message_id": "m1"})

        await bridge.send_message(
            to="jid",
            text="reply",
            quoted_message_id="q1",
        )

        payload = bridge.call.call_args[0][1]
        assert payload["quoted"]["text"] == ""
        assert payload["quoted"]["chat"] == ""

    @pytest.mark.asyncio
    async def test_send_message_with_media_url_and_quoted(self):
        from src.bridge.client import BaileysBridge

        bridge = BaileysBridge(auth_dir="/tmp/test", auto_login=False)
        bridge.call = AsyncMock(return_value={"message_id": "m1"})

        await bridge.send_message(
            to="jid",
            text="caption",
            media_url="/path/to/image.jpg",
            quoted_message_id="q1",
            quoted_text="orig",
            quoted_chat="chat",
        )

        payload = bridge.call.call_args[0][1]
        assert payload["media_url"] == "/path/to/image.jpg"
        assert payload["quoted"]["message_id"] == "q1"


class TestWebSocketBroadcastOnSend:
    @pytest.mark.asyncio
    async def test_sent_event_broadcasts_new_message(self):
        from unittest.mock import patch, MagicMock
        from src.admin.websocket import admin_ws_manager

        mock_tenant = MagicMock()
        mock_tenant.name = "Test Tenant"

        mock_create_task = MagicMock()
        captured_tasks = []

        def fake_create_task(coro, name=""):
            captured_tasks.append(coro)

        with patch("src.main.create_task_with_logging", side_effect=fake_create_task):
            admin_ws_manager.broadcast = AsyncMock()

            event_params = {
                "message_id": "sent_msg_1",
                "from": "123@s.whatsapp.net",
                "to": "456@s.whatsapp.net",
                "text": "Hello!",
                "type": "text",
                "timestamp": 1234567890,
                "direction": "outbound",
            }

            from src.main import _broadcast_to_websockets

            _broadcast_to_websockets("sent", mock_tenant, "test_hash", event_params)

            assert len(captured_tasks) >= 2
            for task in captured_tasks:
                await task
                break

        admin_ws_manager.broadcast.assert_called()
        calls = [c for c in admin_ws_manager.broadcast.call_args_list]
        new_msg_calls = [c for c in calls if c[0][0] == "new_message"]
        assert len(new_msg_calls) > 0
