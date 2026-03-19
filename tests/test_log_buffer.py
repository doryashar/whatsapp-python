import pytest
import asyncio
import logging
import time
from unittest.mock import AsyncMock, MagicMock, patch

from src.admin.log_buffer import (
    LogEntry,
    LogBuffer,
    LogBufferHandler,
    queue_broadcast,
    shutdown_broadcast,
    _ws_broadcast_queue,
)


@pytest.fixture
def fresh_buffer(request):
    size = getattr(request, "param", 100)
    return LogBuffer(max_size=size)


def _make_entry(**overrides):
    defaults = {
        "id": 0,
        "timestamp": "2026-01-01T00:00:00+00:00",
        "type": "log",
        "level": "INFO",
        "source": "test.logger",
        "message": "test message",
        "tenant": "",
        "details": {},
    }
    defaults.update(overrides)
    return LogEntry(**defaults)


# ─── TestLogEntry ───


class TestLogEntry:
    def test_to_dict_all_fields(self):
        e = LogEntry(
            id=1,
            timestamp="2026-01-01T00:00:00Z",
            type="log",
            level="INFO",
            source="whatsapp.admin",
            message="hello world",
            tenant="MyTenant",
            details={"event_type": "connected"},
        )
        d = e.to_dict()
        assert d["id"] == 1
        assert d["timestamp"] == "2026-01-01T00:00:00Z"
        assert d["type"] == "log"
        assert d["level"] == "INFO"
        assert d["source"] == "whatsapp.admin"
        assert d["message"] == "hello world"
        assert d["tenant"] == "MyTenant"
        assert d["details"] == {"event_type": "connected"}

    def test_defaults(self):
        e = LogEntry(id=0, timestamp="", type="", level="", source="", message="")
        assert e.tenant == ""
        assert e.details == {}

    def test_with_unicode_and_emoji(self):
        e = LogEntry(
            id=1,
            timestamp="",
            type="",
            level="",
            source="",
            message="Hello 🌍 世界 <>&\"'",
        )
        d = e.to_dict()
        assert "🌍" in d["message"]
        assert "世界" in d["message"]

    def test_with_empty_fields(self):
        e = LogEntry(id=0, timestamp="", type="", level="", source="", message="")
        d = e.to_dict()
        assert d["message"] == ""

    def test_with_newlines(self):
        e = LogEntry(
            id=1,
            timestamp="",
            type="",
            level="",
            source="",
            message="line1\nline2\nline3",
        )
        d = e.to_dict()
        assert "\n" in d["message"]


# ─── TestLogBufferInit ───


class TestLogBufferInit:
    def test_default_max_size(self):
        buf = LogBuffer()
        assert buf.max_size == 2000

    @pytest.mark.parametrize("size", [5, 10, 50, 2000])
    def test_custom_max_size(self, size):
        buf = LogBuffer(max_size=size)
        assert buf.max_size == size

    @pytest.mark.asyncio
    async def test_max_size_one(self):
        buf = LogBuffer(max_size=1)
        buf.add_sync(_make_entry(id=0, message="first"))
        buf.add_sync(_make_entry(id=0, message="second"))
        entries, total = await buf.list(limit=10)
        assert total == 1
        assert entries[0]["message"] == "second"

    @pytest.mark.asyncio
    async def test_max_size_zero_discards_all(self):
        buf = LogBuffer(max_size=0)
        buf.add_sync(_make_entry(message="gone"))
        entries, total = await buf.list()
        assert total == 0


# ─── TestLogBufferAdd ───


class TestLogBufferAdd:
    @pytest.mark.asyncio
    async def test_add_single_entry_gets_id(self, fresh_buffer):
        e = _make_entry()
        await fresh_buffer.add(e)
        assert e.id == 1

    @pytest.mark.asyncio
    async def test_add_multiple_sequential_ids(self, fresh_buffer):
        for i in range(10):
            await fresh_buffer.add(_make_entry(message=f"msg-{i}"))
        entries, total = await fresh_buffer.list(limit=20)
        assert total == 10
        assert entries[0]["id"] == 1
        assert entries[-1]["id"] == 10

    @pytest.mark.asyncio
    async def test_add_beyond_max_size_evicts_oldest(self):
        buf = LogBuffer(max_size=5)
        for i in range(10):
            await buf.add(_make_entry(message=f"msg-{i}"))
        entries, total = await buf.list(limit=20)
        assert total == 5
        assert entries[0]["id"] == 6
        assert entries[-1]["id"] == 10

    @pytest.mark.asyncio
    async def test_add_sync(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(message="sync-msg"))
        entries, total = await fresh_buffer.list()
        assert total == 1
        assert entries[0]["message"] == "sync-msg"

    @pytest.mark.asyncio
    async def test_add_sync_with_empty_message(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(message=""))
        entries, total = await fresh_buffer.list()
        assert total == 1
        assert entries[0]["message"] == ""

    @pytest.mark.asyncio
    async def test_add_sync_with_long_message(self, fresh_buffer):
        long_msg = "A" * 10000
        fresh_buffer.add_sync(_make_entry(message=long_msg))
        entries, total = await fresh_buffer.list()
        assert total == 1
        assert len(entries[0]["message"]) == 10000

    @pytest.mark.asyncio
    async def test_add_sync_with_unicode(self, fresh_buffer):
        fresh_buffer.add_sync(
            _make_entry(message="Hello 🌍 世界 <script>alert(1)</script>")
        )
        entries, total = await fresh_buffer.list()
        assert total == 1
        assert "<script>" in entries[0]["message"]

    @pytest.mark.asyncio
    async def test_add_sync_with_newlines(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(message="line1\nline2"))
        entries, total = await fresh_buffer.list()
        assert total == 1
        assert "\n" in entries[0]["message"]


# ─── TestLogBufferList ───


class TestLogBufferList:
    @pytest.mark.asyncio
    async def test_list_empty(self, fresh_buffer):
        entries, total = await fresh_buffer.list()
        assert entries == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_default_params(self, fresh_buffer):
        for i in range(5):
            fresh_buffer.add_sync(_make_entry(message=f"m{i}"))
        entries, total = await fresh_buffer.list()
        assert total == 5
        assert len(entries) == 5

    @pytest.mark.asyncio
    async def test_list_with_limit(self, fresh_buffer):
        for i in range(50):
            fresh_buffer.add_sync(_make_entry(message=f"m{i}"))
        entries, total = await fresh_buffer.list(limit=5)
        assert total == 50
        assert len(entries) == 5

    @pytest.mark.asyncio
    async def test_list_with_offset(self, fresh_buffer):
        for i in range(10):
            fresh_buffer.add_sync(_make_entry(message=f"m{i}"))
        entries, total = await fresh_buffer.list(offset=5, limit=10)
        assert total == 10
        assert len(entries) == 5
        assert entries[0]["message"] == "m5"

    @pytest.mark.asyncio
    async def test_list_offset_beyond_size(self, fresh_buffer):
        for i in range(5):
            fresh_buffer.add_sync(_make_entry(message=f"m{i}"))
        entries, total = await fresh_buffer.list(offset=100)
        assert entries == []
        assert total == 5

    @pytest.mark.asyncio
    async def test_list_offset_plus_limit_exceeds(self, fresh_buffer):
        for i in range(5):
            fresh_buffer.add_sync(_make_entry(message=f"m{i}"))
        entries, total = await fresh_buffer.list(offset=3, limit=10)
        assert len(entries) == 2

    @pytest.mark.asyncio
    async def test_list_type_filter_log(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(type="log", message="log entry"))
        fresh_buffer.add_sync(_make_entry(type="event", message="event entry"))
        fresh_buffer.add_sync(_make_entry(type="log", message="another log"))
        entries, total = await fresh_buffer.list(type_filter="log")
        assert total == 2
        assert all(e["type"] == "log" for e in entries)

    @pytest.mark.asyncio
    async def test_list_type_filter_event(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(type="log"))
        fresh_buffer.add_sync(_make_entry(type="event"))
        entries, total = await fresh_buffer.list(type_filter="event")
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_type_filter_nonexistent(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(type="log"))
        entries, total = await fresh_buffer.list(type_filter="nonexistent")
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_level_filter(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(level="INFO"))
        fresh_buffer.add_sync(_make_entry(level="ERROR"))
        fresh_buffer.add_sync(_make_entry(level="DEBUG"))
        entries, total = await fresh_buffer.list(level_filter="ERROR")
        assert total == 1
        assert entries[0]["level"] == "ERROR"

    @pytest.mark.asyncio
    async def test_list_level_filter_event(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(level="INFO"))
        fresh_buffer.add_sync(_make_entry(level="EVENT"))
        entries, total = await fresh_buffer.list(level_filter="EVENT")
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_source_filter_case_insensitive(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(source="whatsapp.bridge"))
        fresh_buffer.add_sync(_make_entry(source="whatsapp.admin"))
        entries, total = await fresh_buffer.list(source_filter="BRIDGE")
        assert total == 1
        assert entries[0]["source"] == "whatsapp.bridge"

    @pytest.mark.asyncio
    async def test_list_source_filter_substring(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(source="whatsapp.bridge.core"))
        fresh_buffer.add_sync(_make_entry(source="bridge"))
        entries, total = await fresh_buffer.list(source_filter="bridge")
        assert total == 2

    @pytest.mark.asyncio
    async def test_list_search_message(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(message="tenant connected successfully"))
        fresh_buffer.add_sync(_make_entry(message="bridge crashed"))
        entries, total = await fresh_buffer.list(search="connected")
        assert total == 1
        assert "connected" in entries[0]["message"]

    @pytest.mark.asyncio
    async def test_list_search_source(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(source="whatsapp.bridge", message="event"))
        fresh_buffer.add_sync(_make_entry(source="whatsapp.admin", message="event"))
        entries, total = await fresh_buffer.list(search="admin")
        assert total == 1
        assert entries[0]["source"] == "whatsapp.admin"

    @pytest.mark.asyncio
    async def test_list_search_case_insensitive(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry(message="Tenant CONNECTED"))
        entries, total = await fresh_buffer.list(search="connected")
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_combined_filters(self, fresh_buffer):
        fresh_buffer.add_sync(
            _make_entry(
                type="log", level="INFO", source="whatsapp.admin", message="admin info"
            )
        )
        fresh_buffer.add_sync(
            _make_entry(
                type="log",
                level="ERROR",
                source="whatsapp.admin",
                message="admin error",
            )
        )
        fresh_buffer.add_sync(
            _make_entry(
                type="event", level="EVENT", source="bridge", message="connected"
            )
        )
        entries, total = await fresh_buffer.list(
            type_filter="log", level_filter="INFO", source_filter="admin"
        )
        assert total == 1
        assert entries[0]["message"] == "admin info"

    @pytest.mark.asyncio
    async def test_list_all_filters_on_empty(self, fresh_buffer):
        entries, total = await fresh_buffer.list(
            type_filter="log", level_filter="ERROR", search="test"
        )
        assert entries == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_list_entries_have_details(self, fresh_buffer):
        fresh_buffer.add_sync(
            _make_entry(details={"event_type": "message", "tenant_hash": "abc"})
        )
        entries, total = await fresh_buffer.list()
        assert total == 1
        assert "details" in entries[0]
        assert entries[0]["details"]["event_type"] == "message"

    @pytest.mark.asyncio
    async def test_list_search_matches_both_message_and_source(self, fresh_buffer):
        fresh_buffer.add_sync(
            _make_entry(message="not a match", source="whatsapp.bridge")
        )
        fresh_buffer.add_sync(
            _make_entry(message="match here", source="whatsapp.admin")
        )
        fresh_buffer.add_sync(
            _make_entry(message="admin action", source="whatsapp.tenant")
        )
        entries, total = await fresh_buffer.list(search="admin")
        assert total == 2

    @pytest.mark.asyncio
    async def test_list_empty_search_returns_all(self, fresh_buffer):
        for i in range(5):
            fresh_buffer.add_sync(_make_entry(message=f"m{i}"))
        entries, total = await fresh_buffer.list(search="")
        assert total == 5


# ─── TestLogBufferClear ───


class TestLogBufferClear:
    @pytest.mark.asyncio
    async def test_clear_empty(self, fresh_buffer):
        count = await fresh_buffer.clear()
        assert count == 0

    @pytest.mark.asyncio
    async def test_clear_with_entries(self, fresh_buffer):
        for i in range(10):
            fresh_buffer.add_sync(_make_entry(message=f"m{i}"))
        count = await fresh_buffer.clear()
        assert count == 10

    @pytest.mark.asyncio
    async def test_list_after_clear(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry())
        await fresh_buffer.clear()
        entries, total = await fresh_buffer.list()
        assert entries == []
        assert total == 0

    @pytest.mark.asyncio
    async def test_add_after_clear_ids_monotonic(self, fresh_buffer):
        for i in range(5):
            fresh_buffer.add_sync(_make_entry(message=f"m{i}"))
        await fresh_buffer.clear()
        fresh_buffer.add_sync(_make_entry(message="after-clear"))
        entries, total = await fresh_buffer.list()
        assert total == 1
        assert entries[0]["id"] == 6

    @pytest.mark.asyncio
    async def test_clear_twice(self, fresh_buffer):
        fresh_buffer.add_sync(_make_entry())
        count1 = await fresh_buffer.clear()
        count2 = await fresh_buffer.clear()
        assert count1 == 1
        assert count2 == 0


# ─── TestLogBufferSize ───


class TestLogBufferSize:
    @pytest.mark.asyncio
    async def test_size_empty(self, fresh_buffer):
        assert await fresh_buffer.size() == 0

    @pytest.mark.asyncio
    async def test_size_after_adds(self, fresh_buffer):
        for i in range(15):
            fresh_buffer.add_sync(_make_entry(message=f"m{i}"))
        assert await fresh_buffer.size() == 15

    @pytest.mark.asyncio
    async def test_size_capped_at_max(self):
        buf = LogBuffer(max_size=5)
        for i in range(20):
            buf.add_sync(_make_entry(message=f"m{i}"))
        assert await buf.size() == 5


# ─── TestBroadcastQueue ───


class TestBroadcastQueue:
    @pytest.mark.asyncio
    async def test_queue_broadcast_with_space(self):
        _ws_broadcast_queue._queue.clear()
        queue_broadcast("test_event", {"message": "hello"})
        assert not _ws_broadcast_queue.empty()

    @pytest.mark.asyncio
    async def test_queue_broadcast_full_silently_drops(self):
        _ws_broadcast_queue._queue.clear()
        for _ in range(501):
            queue_broadcast("test", {"i": 1})
        assert _ws_broadcast_queue.full()
        items_before = _ws_broadcast_queue.qsize()
        queue_broadcast("overflow", {"i": 1})
        assert _ws_broadcast_queue.qsize() == items_before

    @pytest.mark.asyncio
    async def test_queue_broadcast_before_set_manager_no_crash(self):
        _ws_broadcast_queue._queue.clear()
        queue_broadcast("test", {"data": 1})

    @pytest.mark.asyncio
    async def test_shutdown_broadcast(self):
        import src.admin.log_buffer as lb_mod

        lb_mod._ws_manager = MagicMock()
        lb_mod._ws_manager.broadcast = AsyncMock(side_effect=RuntimeError("test error"))
        lb_mod._broadcast_task = asyncio.get_running_loop().create_task(
            _ws_broadcast_queue.get()
        )
        await lb_mod.shutdown_broadcast()
        lb_mod._broadcast_task = None


# ─── TestLogBufferHandler ───


class TestLogBufferHandler:
    def _make_record(
        self, level=logging.INFO, name="test.logger", msg="hello", tenant=None
    ):
        record = logging.LogRecord(
            name=name,
            level=level,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        if tenant:
            record.tenant = tenant
        return record

    @pytest.mark.asyncio
    async def test_emit_debug_record(self, fresh_buffer):
        handler = LogBufferHandler(fresh_buffer)
        record = self._make_record(level=logging.DEBUG)
        handler.emit(record)
        entries, total = await fresh_buffer.list()
        assert total == 1
        assert entries[0]["type"] == "log"
        assert entries[0]["level"] == "DEBUG"

    @pytest.mark.asyncio
    async def test_emit_error_record(self, fresh_buffer):
        handler = LogBufferHandler(fresh_buffer)
        record = self._make_record(level=logging.ERROR)
        handler.emit(record)
        entries, total = await fresh_buffer.list()
        assert total == 1
        assert entries[0]["level"] == "ERROR"

    @pytest.mark.asyncio
    async def test_emit_with_tenant_attribute(self, fresh_buffer):
        handler = LogBufferHandler(fresh_buffer)
        record = self._make_record(tenant="MyTenant")
        handler.emit(record)
        entries, total = await fresh_buffer.list()
        assert entries[0]["tenant"] == "MyTenant"

    @pytest.mark.asyncio
    async def test_emit_without_tenant_attribute(self, fresh_buffer):
        handler = LogBufferHandler(fresh_buffer)
        record = self._make_record()
        handler.emit(record)
        entries, total = await fresh_buffer.list()
        assert entries[0]["tenant"] == ""

    @pytest.mark.asyncio
    async def test_emit_uses_custom_formatter(self, fresh_buffer):
        handler = LogBufferHandler(fresh_buffer)
        handler.setFormatter(logging.Formatter("[CUSTOM] %(message)s"))
        record = self._make_record(msg="test msg")
        handler.emit(record)
        entries, total = await fresh_buffer.list()
        assert entries[0]["message"] == "test msg"

    def test_emit_throttle_rapid(self):
        buf = LogBuffer(max_size=1000)
        handler = LogBufferHandler(buf)
        with patch("src.admin.log_buffer.queue_broadcast") as mock_broadcast:
            for i in range(20):
                handler.emit(self._make_record(msg=f"msg-{i}"))
            assert mock_broadcast.call_count < 20

    def test_emit_after_throttle_gap(self):
        buf = LogBuffer(max_size=1000)
        handler = LogBufferHandler(buf)
        handler._throttle_last = 0.0
        with patch("src.admin.log_buffer.queue_broadcast") as mock_broadcast:
            handler.emit(self._make_record(msg="first"))
            count1 = mock_broadcast.call_count
            time.sleep(0.15)
            handler.emit(self._make_record(msg="second"))
            count2 = mock_broadcast.call_count
            assert count2 > count1

    @pytest.mark.asyncio
    async def test_emit_queue_full_still_adds_to_buffer(self, fresh_buffer):
        import src.admin.log_buffer as lb_mod

        handler = LogBufferHandler(fresh_buffer)
        original_queue = lb_mod._ws_broadcast_queue
        zero_queue = asyncio.Queue(maxsize=0)
        lb_mod._ws_broadcast_queue = zero_queue
        try:
            for i in range(5):
                handler.emit(self._make_record(msg=f"msg-{i}"))
            entries, total = await fresh_buffer.list()
            assert total == 5
        finally:
            lb_mod._ws_broadcast_queue = original_queue

    @pytest.mark.asyncio
    async def test_emit_format_exception_no_crash(self, fresh_buffer):
        handler = LogBufferHandler(fresh_buffer)
        handler.setFormatter(logging.Formatter("%(message)s"))
        record = self._make_record(msg="normal")
        handler.emit(record)
        entries, total = await fresh_buffer.list()
        assert total == 1
