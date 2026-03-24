import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from src.bridge.client import BaileysBridge, BridgeError


@pytest.fixture
def mock_process():
    process = AsyncMock()
    process.pid = 12345
    process.returncode = None
    process.stdin = AsyncMock()
    process.stdout = AsyncMock()
    process.stderr = AsyncMock()
    process.terminate = MagicMock()
    process.kill = MagicMock()
    process.wait = AsyncMock()
    return process


@pytest.fixture
def bridge(mock_process):
    with patch("asyncio.create_subprocess_exec", return_value=mock_process):
        b = BaileysBridge(auth_dir="/tmp/test-auth", tenant_id="test-tenant")
        b._process = mock_process
        b._running = True
        yield b


class TestBaileysBridgeInit:
    def test_default_values(self):
        b = BaileysBridge()
        assert b.auto_login is False
        assert b.tenant_id is None
        assert b.auto_mark_read is True
        assert b._process is None
        assert b._reader_task is None
        assert b._request_id == 0
        assert b._pending == {}
        assert b._event_handlers == []
        assert b._running is False

    def test_custom_values(self):
        b = BaileysBridge(
            auth_dir="/tmp/test",
            tenant_id="t1",
            auto_login=True,
            auto_mark_read=False,
        )
        assert b.auth_dir == "/tmp/test"
        assert b.tenant_id == "t1"
        assert b.auto_login is True
        assert b.auto_mark_read is False

    def test_path_defaults_from_settings(self):
        from src.config import settings

        b = BaileysBridge()
        assert b.bridge_path == settings.bridge_path
        assert b.auth_dir == settings.auth_dir


class TestOnEvent:
    def test_registers_handler(self, bridge):
        handler = MagicMock()
        bridge.on_event(handler)
        assert len(bridge._event_handlers) == 1
        assert bridge._event_handlers[0] is handler

    def test_registers_multiple_handlers(self, bridge):
        h1 = MagicMock()
        h2 = MagicMock()
        bridge.on_event(h1)
        bridge.on_event(h2)
        assert len(bridge._event_handlers) == 2


def _make_finishing_process():
    process = AsyncMock()
    process.pid = 12345
    process.returncode = None
    process.stdin = AsyncMock()
    process.stdout = AsyncMock()
    process.stderr = AsyncMock()
    process.terminate = MagicMock()
    process.kill = MagicMock()
    process.wait = AsyncMock()
    process.stdout.readline = AsyncMock(return_value=b"")
    process.stderr.readline = AsyncMock(return_value=b"")
    return process


class TestStart:
    async def test_start_calls_create_subprocess(self):
        mock_process = _make_finishing_process()
        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            b = BaileysBridge(auth_dir="/tmp/test-auth")
            await b.start()
            mock_exec.assert_called_once()
            args = mock_exec.call_args
            assert args[0][0] == "node"
            assert "env" in args[1]

    async def test_start_sets_running_true(self):
        mock_process = _make_finishing_process()
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            b = BaileysBridge(auth_dir="/tmp/test-auth")
            assert b._running is False
            await b.start()
            assert b._running is True

    async def test_start_creates_reader_task(self):
        mock_process = _make_finishing_process()
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            b = BaileysBridge(auth_dir="/tmp/test-auth")
            await b.start()
            assert b._reader_task is not None

    async def test_start_when_already_running(self):
        mock_process = _make_finishing_process()
        with patch("asyncio.create_subprocess_exec", return_value=mock_process):
            b = BaileysBridge(auth_dir="/tmp/test-auth")
            await b.start()
            await b.start()
            assert mock_process.pid == 12345

    async def test_start_sets_env_vars(self):
        mock_process = _make_finishing_process()
        with patch(
            "asyncio.create_subprocess_exec", return_value=mock_process
        ) as mock_exec:
            b = BaileysBridge(
                auth_dir="/tmp/test-auth", auto_login=True, auto_mark_read=False
            )
            await b.start()
            env = mock_exec.call_args[1]["env"]
            assert env["WHATSAPP_AUTH_DIR"] == "/tmp/test-auth"
            assert env["AUTO_LOGIN"] == "true"
            assert env["AUTO_MARK_READ"] == "false"


class TestStop:
    async def test_stop_clears_pending(self, bridge):
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        bridge._pending[1] = future
        await bridge.stop()
        assert bridge._running is False
        assert len(bridge._pending) == 0

    async def test_stop_cancels_reader_task(self, bridge):
        bridge._reader_task = asyncio.create_task(asyncio.sleep(10))
        await bridge.stop()
        assert bridge._reader_task.done()

    async def test_stop_closes_stdin(self, bridge):
        await bridge.stop()
        bridge._process.stdin.close.assert_called_once()

    async def test_stop_terminates_process(self, bridge):
        bridge._process.returncode = None
        await bridge.stop()
        bridge._process.terminate.assert_called_once()

    async def test_stop_when_not_running(self, bridge):
        bridge._running = False
        await bridge.stop()
        bridge._process.terminate.assert_not_called()

    async def test_stop_kills_process_after_timeout(self, bridge):
        bridge._process.returncode = None
        bridge._process.wait.side_effect = asyncio.TimeoutError()
        await bridge.stop()
        bridge._process.kill.assert_called_once()

    async def test_stop_handles_process_lookup_error(self, bridge):
        bridge._process.returncode = None
        bridge._process.terminate.side_effect = ProcessLookupError()
        await bridge.stop()

    async def test_stop_already_terminated_process(self, bridge):
        bridge._process.returncode = 0
        await bridge.stop()
        bridge._process.terminate.assert_not_called()


class TestCall:
    async def test_call_writes_json_to_stdin(self, bridge, monkeypatch):
        monkeypatch.setattr("src.bridge.client.settings.bridge_timeout_seconds", 5)

        loop = asyncio.get_running_loop()
        pre_resolved = loop.create_future()
        pre_resolved.set_result({"status": "ok"})

        with patch.object(loop, "create_future", return_value=pre_resolved):
            bridge._process.stdin.write = MagicMock()
            bridge._process.stdin.drain = AsyncMock()
            result = await bridge.call("get_status")

        assert result == {"status": "ok"}
        bridge._process.stdin.write.assert_called_once()
        written = bridge._process.stdin.write.call_args[0][0]
        data = json.loads(written)
        assert data["method"] == "get_status"
        assert data["jsonrpc"] == "2.0"
        assert "id" in data

    async def test_call_when_not_started_raises(self):
        b = BaileysBridge()
        with pytest.raises(BridgeError, match="not started"):
            await b.call("test")

    async def test_call_timeout_raises_bridge_error(self, bridge, monkeypatch):
        monkeypatch.setattr("src.bridge.client.settings.bridge_timeout_seconds", 0.001)
        with pytest.raises(BridgeError, match="timed out"):
            await bridge.call("slow_method")


class TestIsAlive:
    def test_alive_when_running_and_no_returncode(self, bridge):
        bridge._running = True
        bridge._process.returncode = None
        assert bridge.is_alive() is True

    def test_not_alive_when_not_running(self, bridge):
        bridge._running = False
        assert bridge.is_alive() is False

    def test_not_alive_when_process_has_returncode(self, bridge):
        bridge._running = True
        bridge._process.returncode = 1
        assert bridge.is_alive() is False

    def test_not_alive_when_no_process(self, bridge):
        bridge._running = True
        bridge._process = None
        assert bridge.is_alive() is False


class TestReadLoop:
    async def test_read_loop_processes_json_response(self, bridge):
        from src.bridge.protocol import JsonRpcResponse

        loop = asyncio.get_running_loop()
        future = loop.create_future()
        bridge._pending[1] = future

        response_data = json.dumps({"jsonrpc": "2.0", "result": {"ok": True}, "id": 1})
        bridge._process.stdout = AsyncMock()
        bridge._process.stdout.readline = AsyncMock(
            side_effect=[response_data.encode(), b""]
        )

        await bridge._read_loop()
        await asyncio.sleep(0.01)
        assert future.done()
        assert future.result() == {"ok": True}

    async def test_read_loop_processes_event(self, bridge):
        handler = MagicMock()
        bridge.on_event(handler)

        event_data = json.dumps(
            {"jsonrpc": "2.0", "method": "qr", "params": {"qr": "abc"}}
        )
        bridge._process.stdout.readline = AsyncMock(
            side_effect=[event_data.encode(), b""]
        )

        await bridge._read_loop()
        handler.assert_called_once_with("qr", {"qr": "abc"}, "test-tenant")

    async def test_read_loop_skips_non_json_rpc(self, bridge):
        non_json = b"some debug output\n"
        bridge._process.stdout.readline = AsyncMock(side_effect=[non_json, b""])
        await bridge._read_loop()

    async def test_read_loop_skips_empty_lines(self, bridge):
        bridge._process.stdout.readline = AsyncMock(side_effect=[b"\n", b"\n", b""])
        await bridge._read_loop()

    async def test_read_loop_handles_cancelled(self, bridge):
        bridge._process.stdout.readline = AsyncMock(
            side_effect=asyncio.CancelledError()
        )
        await bridge._read_loop()

    async def test_read_loop_handles_decode_error(self, bridge):
        bridge._process.stdout.readline = AsyncMock(
            side_effect=[b"not valid json\n", b""]
        )
        await bridge._read_loop()


class TestHandleEvent:
    async def test_calls_sync_handler(self, bridge):
        handler = MagicMock()
        bridge.on_event(handler)
        await bridge._handle_event("message", {"text": "hi"})
        handler.assert_called_once_with("message", {"text": "hi"}, "test-tenant")

    async def test_calls_async_handler(self, bridge):
        async_handler = AsyncMock()
        bridge.on_event(async_handler)
        await bridge._handle_event("message", {"text": "hi"})
        async_handler.assert_called_once_with("message", {"text": "hi"}, "test-tenant")

    async def test_handler_error_does_not_stop_others(self, bridge):
        handler1 = MagicMock(side_effect=ValueError("err"))
        handler2 = MagicMock()
        bridge.on_event(handler1)
        bridge.on_event(handler2)
        await bridge._handle_event("message", {})
        handler2.assert_called_once()

    async def test_no_handlers_no_error(self, bridge):
        await bridge._handle_event("message", {"text": "hi"})


class TestStderrLoop:
    async def test_stderr_reads_lines(self, bridge, caplog):
        bridge._process.stderr.readline = AsyncMock(
            side_effect=[b"stderr line 1\n", b"stderr line 2\n", b""]
        )
        await bridge._stderr_loop()

    async def test_stderr_handles_cancelled(self, bridge):
        bridge._process.stderr.readline = AsyncMock(
            side_effect=asyncio.CancelledError()
        )
        await bridge._stderr_loop()

    async def test_stderr_handles_generic_error(self, bridge, caplog):
        bridge._process.stderr.readline = AsyncMock(
            side_effect=RuntimeError("stderr error")
        )
        await bridge._stderr_loop()


@pytest.mark.parametrize(
    "method_name,args,expected_method,expected_params",
    [
        ("login", (), "login", None),
        ("logout", (), "logout", None),
        ("get_status", (), "get_status", None),
        (
            "send_message",
            ("123", "hello"),
            "send_message",
            {"to": "123", "text": "hello", "media_url": None},
        ),
        ("auth_exists", (), "auth_exists", None),
        ("auth_age", (), "auth_age", None),
        ("self_id", (), "self_id", None),
        ("get_contacts", (), "get_contacts", None),
        (
            "get_profile_picture",
            ("jid@test",),
            "get_profile_picture",
            {"jid": "jid@test"},
        ),
        (
            "delete_message",
            ("chat", "msg_id"),
            "delete_message",
            {"to": "chat", "message_id": "msg_id", "from_me": False},
        ),
        (
            "mark_read",
            ("chat", ["id1", "id2"]),
            "mark_read",
            {"to": "chat", "message_ids": ["id1", "id2"]},
        ),
        ("send_typing", ("123",), "send_typing", {"to": "123"}),
        (
            "send_reaction",
            ("chat", "msg_id", "\U0001f44d"),
            "send_reaction",
            {
                "chat": "chat",
                "message_id": "msg_id",
                "emoji": "\U0001f44d",
                "from_me": False,
            },
        ),
        (
            "send_poll",
            ("to", "poll", ["a", "b"]),
            "send_poll",
            {
                "to": "to",
                "poll": {"name": "poll", "values": ["a", "b"], "selectableCount": 1},
            },
        ),
        (
            "group_create",
            ("subject", ["p1", "p2"]),
            "group_create",
            {"subject": "subject", "participants": ["p1", "p2"], "description": None},
        ),
        ("group_get_info", ("grp@g.us",), "group_get_info", {"group_jid": "grp@g.us"}),
        ("group_leave", ("grp@g.us",), "group_leave", {"group_jid": "grp@g.us"}),
        (
            "group_update_subject",
            ("grp@g.us", "new"),
            "group_update_subject",
            {"group_jid": "grp@g.us", "subject": "new"},
        ),
        (
            "send_location",
            ("to", 1.0, 2.0),
            "send_location",
            {
                "to": "to",
                "latitude": 1.0,
                "longitude": 2.0,
                "name": None,
                "address": None,
            },
        ),
        (
            "send_contact",
            ("to", [{"name": "A"}]),
            "send_contact",
            {"to": "to", "contacts": [{"name": "A"}]},
        ),
        (
            "archive_chat",
            ("chat", True),
            "archive_chat",
            {"chat_jid": "chat", "archive": True},
        ),
        ("block_user", ("jid", True), "block_user", {"jid": "jid", "block": True}),
        (
            "edit_message",
            ("to", "id", "new text"),
            "edit_message",
            {"to": "to", "message_id": "id", "text": "new text", "from_me": True},
        ),
        ("check_whatsapp", (["123"],), "check_whatsapp", {"numbers": ["123"]}),
        (
            "update_profile_name",
            ("New Name",),
            "update_profile_name",
            {"name": "New Name"},
        ),
        (
            "update_profile_status",
            ("status text",),
            "update_profile_status",
            {"status": "status text"},
        ),
        ("remove_profile_picture", (), "remove_profile_picture", None),
        ("get_profile", ("jid@test",), "get_profile", {"jid": "jid@test"}),
        ("get_chats_with_messages", (25,), "get_chats_with_messages", {"limit": 25}),
        (
            "fetch_chat_history",
            (10, 5),
            "fetch_chat_history",
            {"limit_per_chat": 10, "max_chats": 5},
        ),
        ("fetch_privacy_settings", (), "fetch_privacy_settings", None),
        ("get_settings", (), "get_settings", None),
        (
            "send_sticker",
            ("to", "sticker_url", False),
            "send_sticker",
            {"to": "to", "sticker": "sticker_url", "gif_playback": False},
        ),
        (
            "send_buttons",
            ("to", "t", "d", [{"id": "1"}]),
            "send_buttons",
            {
                "to": "to",
                "title": "t",
                "description": "d",
                "footer": None,
                "buttons": [{"id": "1"}],
                "thumbnail_url": None,
            },
        ),
        ("group_get_all", (True,), "group_get_all", {"get_participants": True}),
        (
            "group_accept_invite",
            ("code123",),
            "group_accept_invite",
            {"invite_code": "code123"},
        ),
        (
            "group_revoke_invite",
            ("grp@g.us",),
            "group_revoke_invite",
            {"group_jid": "grp@g.us"},
        ),
        (
            "update_settings",
            (True, "msg"),
            "update_settings",
            {
                "reject_call": True,
                "msg_call": "msg",
                "groups_ignore": None,
                "always_online": None,
                "read_messages": None,
                "read_status": None,
                "sync_full_history": None,
            },
        ),
    ],
)
async def test_bridge_method_delegates_to_call(
    bridge, method_name, args, expected_method, expected_params
):
    bridge.call = AsyncMock(return_value={"status": "ok"})
    method = getattr(bridge, method_name)
    result = await method(*args)
    assert bridge.call.called
    call_args = bridge.call.call_args
    assert call_args[0][0] == expected_method
    if expected_params is not None:
        assert call_args[0][1] == expected_params
    else:
        assert len(call_args[0]) == 1
    assert result == {"status": "ok"}


@pytest.mark.parametrize(
    "method_name,args",
    [
        ("send_message", ("123", "hi", "url", "qid", "qtxt", "qchat")),
        ("send_poll", ("to", "name", ["a", "b"], 2)),
        ("send_location", ("to", 1.0, 2.0, "loc", "addr")),
        ("delete_message", ("to", "id", True)),
        ("send_reaction", ("chat", "id", "\U0001f44d", True)),
        ("send_sticker", ("to", "url", True)),
        ("send_list", ("to", "t", "d", "btn", [{"title": "s1"}], "footer")),
        ("send_status", ("image", "url", "cap", "#fff", 1, ["jid"], True)),
        ("update_privacy_settings", ("all", "all", "all", "all", "all", "all")),
        ("group_create", ("subj", ["p1"], "desc")),
        ("group_update_description", ("grp", "desc")),
        ("group_update_picture", ("grp", "url")),
        ("group_get_participants", ("grp@g.us",)),
        ("group_get_invite_code", ("grp@g.us",)),
        ("group_get_invite_info", ("code",)),
        ("group_update_participant", ("grp", "add", ["p1"])),
        ("group_update_setting", ("grp", "unlock")),
        ("group_toggle_ephemeral", ("grp", 86400)),
        ("update_profile_picture", ("url",)),
        ("get_profile", (None,)),
        ("archive_chat", ("chat", False)),
        ("block_user", ("jid", False)),
        ("edit_message", ("to", "id", "txt", False)),
    ],
)
async def test_bridge_method_optional_args(bridge, method_name, args):
    bridge.call = AsyncMock(return_value={"status": "ok"})
    method = getattr(bridge, method_name)
    result = await method(*args)
    assert result == {"status": "ok"}
    assert bridge.call.called
