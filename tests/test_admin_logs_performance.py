import pytest
import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock

from src.admin.log_buffer import (
    LogEntry,
    LogBuffer,
    LogBufferHandler,
    queue_broadcast,
    _ws_broadcast_queue,
)
import src.admin.log_buffer as lb_mod


# ─── TestLogBufferPerformance ───


class TestLogBufferPerformance:
    @pytest.mark.asyncio
    async def test_rapid_add_10000_entries(self):
        buf = LogBuffer(max_size=2000)
        start = time.monotonic()
        for i in range(10000):
            buf.add_sync(
                LogEntry(
                    id=0,
                    timestamp="",
                    type="log",
                    level="INFO",
                    source="perf.test",
                    message=f"perf-msg-{i}",
                )
            )
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"Adding 10000 entries took {elapsed:.2f}s"

        size = await buf.size()
        assert size <= 2000

        entries, total = await buf.list(limit=10000)
        assert len(entries) <= 2000
        assert entries[-1]["message"] == "perf-msg-9999"

    @pytest.mark.asyncio
    async def test_concurrent_list_calls(self):
        buf = LogBuffer(max_size=1000)
        for i in range(500):
            buf.add_sync(
                LogEntry(
                    id=0,
                    timestamp="",
                    type="log",
                    level="INFO",
                    source="concurrent",
                    message=f"msg-{i}",
                )
            )

        async def do_list():
            return await buf.list(limit=100)

        start = time.monotonic()
        results = await asyncio.gather(*[do_list() for _ in range(100)])
        elapsed = time.monotonic() - start
        assert elapsed < 2.0, f"100 concurrent list() calls took {elapsed:.2f}s"

        for entries, total in results:
            assert total == 500
            assert len(entries) == 100

    @pytest.mark.asyncio
    async def test_list_with_search_on_full_buffer(self):
        buf = LogBuffer(max_size=2000)
        for i in range(2000):
            buf.add_sync(
                LogEntry(
                    id=0,
                    timestamp="",
                    type="log" if i % 2 == 0 else "event",
                    level="INFO" if i % 3 == 0 else "ERROR",
                    source=f"whatsapp.module{i % 10}",
                    message=f"searchable message number {i} with some keywords",
                )
            )

        start = time.monotonic()
        entries, total = await buf.list(search="keywords")
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"Search on 2000 entries took {elapsed:.2f}s"
        assert total > 0

    @pytest.mark.asyncio
    async def test_alternating_clear_and_add(self):
        buf = LogBuffer(max_size=100)
        for i in range(100):
            buf.add_sync(
                LogEntry(
                    id=0,
                    timestamp="",
                    type="log",
                    level="INFO",
                    source="t",
                    message=f"m{i}",
                )
            )
            await buf.clear()

        entries, total = await buf.list()
        assert total == 0

    @pytest.mark.asyncio
    async def test_very_large_message(self):
        buf = LogBuffer(max_size=100)
        large_msg = "X" * (1024 * 1024)
        buf.add_sync(
            LogEntry(
                id=0,
                timestamp="",
                type="log",
                level="INFO",
                source="large",
                message=large_msg,
            )
        )

        entries, total = await buf.list()
        assert total == 1
        assert len(entries[0]["message"]) == 1024 * 1024


# ─── TestBroadcastQueuePerformance ───


class TestBroadcastQueuePerformance:
    def test_queue_at_capacity_no_crash(self):
        _ws_broadcast_queue._queue.clear()
        for i in range(600):
            queue_broadcast("test", {"i": i})
        assert _ws_broadcast_queue.full()
        queue_broadcast("overflow", {"i": 999})
        assert _ws_broadcast_queue.full()
        _ws_broadcast_queue._queue.clear()

    @pytest.mark.asyncio
    async def test_broadcast_throughput_throttle(self):
        buf = LogBuffer(max_size=2000)
        handler = LogBufferHandler(buf)
        handler.setLevel(logging.DEBUG)

        mgr = MagicMock()
        mgr.broadcast = AsyncMock()

        old_manager = lb_mod._ws_manager
        old_task = lb_mod._broadcast_task

        _ws_broadcast_queue._queue.clear()
        lb_mod._ws_manager = mgr
        lb_mod._broadcast_task = None

        lb_mod.set_ws_manager(mgr)

        for i in range(1000):
            record = logging.LogRecord(
                name="perf",
                level=logging.INFO,
                pathname="t.py",
                lineno=1,
                msg=f"msg-{i}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
        await asyncio.sleep(0.3)

        broadcast_count = mgr.broadcast.call_count
        assert broadcast_count < 100, (
            f"Expected < 100 broadcasts, got {broadcast_count}"
        )

        size = await buf.size()
        assert size == 1000

        await lb_mod.shutdown_broadcast()
        lb_mod._ws_manager = old_manager
        lb_mod._broadcast_task = old_task

    @pytest.mark.asyncio
    async def test_handler_emit_at_1000_per_sec(self):
        buf = LogBuffer(max_size=2000)
        handler = LogBufferHandler(buf)

        start = time.monotonic()
        for i in range(1000):
            record = logging.LogRecord(
                name="perf",
                level=logging.INFO,
                pathname="t.py",
                lineno=1,
                msg=f"high-freq-{i}",
                args=(),
                exc_info=None,
            )
            handler.emit(record)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"1000 emits took {elapsed:.2f}s"

        entries, total = await buf.list(limit=1000)
        assert total == 1000
        assert entries[-1]["message"] == "high-freq-999"
