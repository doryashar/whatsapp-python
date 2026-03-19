import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional


@dataclass
class LogEntry:
    id: int
    timestamp: str
    type: str
    level: str
    source: str
    message: str
    tenant: str = ""
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class LogBuffer:
    def __init__(self, max_size: int = 2000):
        self._buffer: deque[LogEntry] = deque(maxlen=max_size)
        self._max_size = max_size
        self._counter = 0
        self._lock = asyncio.Lock()
        self._sync_lock = threading.Lock()

    @property
    def max_size(self) -> int:
        return self._max_size

    async def add(self, entry: LogEntry) -> None:
        async with self._lock:
            self._counter += 1
            entry.id = self._counter
            self._buffer.append(entry)

    def add_sync(self, entry: LogEntry) -> None:
        with self._sync_lock:
            self._counter += 1
            entry.id = self._counter
            self._buffer.append(entry)

    async def list(
        self,
        limit: int = 100,
        offset: int = 0,
        type_filter: Optional[str] = None,
        level_filter: Optional[str] = None,
        source_filter: Optional[str] = None,
        search: Optional[str] = None,
    ) -> tuple[list[dict], int]:
        async with self._lock:
            entries = list(self._buffer)

        filtered = entries
        if type_filter:
            filtered = [e for e in filtered if e.type == type_filter]
        if level_filter:
            filtered = [e for e in filtered if e.level == level_filter]
        if source_filter:
            s = source_filter.lower()
            filtered = [e for e in filtered if s in e.source.lower()]
        if search:
            q = search.lower()
            filtered = [
                e for e in filtered if q in e.message.lower() or q in e.source.lower()
            ]

        total = len(filtered)
        result = filtered[offset : offset + limit]
        return [e.to_dict() for e in result], total

    async def clear(self) -> int:
        async with self._lock:
            count = len(self._buffer)
            self._buffer.clear()
            return count

    async def size(self) -> int:
        async with self._lock:
            return len(self._buffer)


_ws_manager = None
_ws_broadcast_queue: asyncio.Queue = asyncio.Queue(maxsize=500)
_broadcast_task: Optional[asyncio.Task] = None


def set_ws_manager(manager) -> None:
    global _ws_manager, _broadcast_task
    _ws_manager = manager
    if _broadcast_task is None or _broadcast_task.done():
        _broadcast_task = asyncio.get_running_loop().create_task(_broadcast_loop())


async def shutdown_broadcast() -> None:
    global _broadcast_task
    if _broadcast_task and not _broadcast_task.done():
        _broadcast_task.cancel()
        try:
            await _broadcast_task
        except asyncio.CancelledError:
            pass
        _broadcast_task = None


async def _broadcast_loop() -> None:
    while True:
        try:
            event_type, data = await _ws_broadcast_queue.get()
            if _ws_manager:
                await _ws_manager.broadcast(event_type, data)
        except asyncio.CancelledError:
            break
        except Exception:
            await asyncio.sleep(0.1)


def queue_broadcast(event_type: str, data: dict) -> None:
    try:
        _ws_broadcast_queue.put_nowait((event_type, data))
    except asyncio.QueueFull:
        logging.getLogger("whatsapp.admin").warning(
            f"Broadcast queue full, dropped {event_type} event"
        )


class LogBufferHandler(logging.Handler):
    def __init__(self, buffer: LogBuffer, level=logging.DEBUG):
        super().__init__(level)
        self._buffer = buffer
        self._throttle_count = 0
        self._throttle_last = 0.0

    def emit(self, record: logging.LogRecord) -> None:
        try:
            entry = LogEntry(
                id=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                type="log",
                level=record.levelname,
                source=record.name,
                message=record.getMessage(),
                tenant=getattr(record, "tenant", ""),
                details={},
            )
            self._buffer.add_sync(entry)

            now = time.monotonic()
            if now - self._throttle_last < 0.1:
                self._throttle_count += 1
                return
            self._throttle_last = now
            self._throttle_count = 0

            queue_broadcast(
                "log_entry",
                {
                    "id": entry.id,
                    "timestamp": entry.timestamp,
                    "type": entry.type,
                    "level": entry.level,
                    "source": entry.source,
                    "message": entry.message,
                    "tenant": entry.tenant,
                    "details": entry.details,
                },
            )
        except Exception:
            self.handleError(record)


log_buffer: Optional[LogBuffer] = None
