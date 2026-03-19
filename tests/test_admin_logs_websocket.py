import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
import logging

from src.admin.log_buffer import (
    LogBuffer,
    LogBufferHandler,
    set_ws_manager,
    shutdown_broadcast,
    queue_broadcast,
    _ws_broadcast_queue,
)
from src.admin.websocket import AdminConnectionManager
import src.admin.log_buffer as lb_mod


@pytest.fixture
def fresh_buffer():
    return LogBuffer(max_size=100)


# ─── TestLogBroadcastViaWebSocket ───


class TestLogBroadcastViaWebSocket:
    @pytest.mark.asyncio
    async def test_log_entry_broadcast_to_manager(self, fresh_buffer):
        mgr = MagicMock()
        mgr.broadcast = AsyncMock()

        old_manager = lb_mod._ws_manager
        old_task = lb_mod._broadcast_task

        _ws_broadcast_queue._queue.clear()
        lb_mod._ws_manager = mgr
        lb_mod._broadcast_task = None

        set_ws_manager(mgr)

        handler = LogBufferHandler(fresh_buffer)
        handler._throttle_last = 0.0
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="t.py",
            lineno=1,
            msg="broadcast test",
            args=(),
            exc_info=None,
        )
        handler.emit(record)
        await asyncio.sleep(0.15)

        assert mgr.broadcast.called
        call_args = mgr.broadcast.call_args
        assert call_args[0][0] == "log_entry"
        assert call_args[0][1]["message"] == "broadcast test"

        await lb_mod.shutdown_broadcast()
        lb_mod._ws_manager = old_manager
        lb_mod._broadcast_task = old_task

    @pytest.mark.asyncio
    async def test_app_event_broadcast_to_manager(self):
        mgr = MagicMock()
        mgr.broadcast = AsyncMock()

        old_manager = lb_mod._ws_manager
        old_task = lb_mod._broadcast_task

        _ws_broadcast_queue._queue.clear()
        lb_mod._ws_manager = mgr
        lb_mod._broadcast_task = None

        set_ws_manager(mgr)

        queue_broadcast("app_event", {"message": "test event"})
        await asyncio.sleep(0.15)

        mgr.broadcast.assert_awaited_once_with("app_event", {"message": "test event"})

        await lb_mod.shutdown_broadcast()
        lb_mod._ws_manager = old_manager
        lb_mod._broadcast_task = old_task

    @pytest.mark.asyncio
    async def test_broadcast_without_manager_no_crash(self):
        old_manager = lb_mod._ws_manager
        old_task = lb_mod._broadcast_task

        lb_mod._ws_manager = None
        _ws_broadcast_queue._queue.clear()
        lb_mod._broadcast_task = asyncio.get_running_loop().create_task(
            _ws_broadcast_queue.get()
        )
        queue_broadcast("test", {"data": 1})
        await asyncio.sleep(0.1)

        lb_mod._ws_manager = old_manager
        lb_mod._broadcast_task = old_task

    @pytest.mark.asyncio
    async def test_broadcast_manager_exception_continues(self):
        mgr = MagicMock()
        mgr.broadcast = AsyncMock(side_effect=RuntimeError("test error"))

        old_manager = lb_mod._ws_manager
        old_task = lb_mod._broadcast_task

        _ws_broadcast_queue._queue.clear()
        lb_mod._ws_manager = mgr
        lb_mod._broadcast_task = None

        set_ws_manager(mgr)

        queue_broadcast("test", {"data": 1})
        await asyncio.sleep(0.2)

        await lb_mod.shutdown_broadcast()
        lb_mod._ws_manager = old_manager
        lb_mod._broadcast_task = old_task

    @pytest.mark.asyncio
    async def test_broadcast_throttle(self):
        buf = LogBuffer(max_size=100)
        handler = LogBufferHandler(buf)
        handler.setLevel(logging.DEBUG)

        mgr = MagicMock()
        mgr.broadcast = AsyncMock()

        old_manager = lb_mod._ws_manager
        old_task = lb_mod._broadcast_task

        _ws_broadcast_queue._queue.clear()
        lb_mod._ws_manager = mgr
        lb_mod._broadcast_task = None

        set_ws_manager(mgr)

        for i in range(50):
            record = logging.LogRecord(
                name="test",
                level=logging.INFO,
                pathname="t.py",
                lineno=1,
                msg=f"msg-{i}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
        await asyncio.sleep(0.2)

        assert mgr.broadcast.call_count < 50

        await lb_mod.shutdown_broadcast()
        lb_mod._ws_manager = old_manager
        lb_mod._broadcast_task = old_task


# ─── TestMultipleClientsBroadcast ───


class TestMultipleClientsBroadcast:
    @pytest.mark.asyncio
    async def test_all_ws_clients_receive_log(self):
        manager = AdminConnectionManager()

        mock_ws1 = AsyncMock()
        mock_ws2 = AsyncMock()

        await manager.connect(mock_ws1, "session1")
        await manager.connect(mock_ws2, "session2")

        await manager.broadcast(
            "log_entry", {"message": "test broadcast", "level": "INFO"}
        )

        assert mock_ws1.send_text.called
        assert mock_ws2.send_text.called

        msg1 = mock_ws1.send_text.call_args[0][0]
        msg2 = mock_ws2.send_text.call_args[0][0]

        import json

        data1 = json.loads(msg1)
        data2 = json.loads(msg2)
        assert data1["type"] == "log_entry"
        assert data2["type"] == "log_entry"

    @pytest.mark.asyncio
    async def test_ws_disconnect_during_broadcast(self):
        manager = AdminConnectionManager()

        mock_ws_ok = AsyncMock()

        mock_ws_fail = AsyncMock()
        mock_ws_fail.send_text = AsyncMock(side_effect=Exception("Connection lost"))

        await manager.connect(mock_ws_ok, "session-ok")
        await manager.connect(mock_ws_fail, "session-fail")

        await manager.broadcast("log_entry", {"message": "test"})

        assert manager.get_connection_count() == 1
        mock_ws_ok.send_text.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_broadcast_to_empty_manager(self):
        manager = AdminConnectionManager()

        await manager.broadcast("log_entry", {"message": "test"})
        assert manager.get_connection_count() == 0
