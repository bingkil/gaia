"""In-memory tail of recent log records, so the running process can be
inspected from the UI regardless of how it was launched (dev script, `uv run`,
or the packaged executable, none of which guarantee a place to `tail -f`).
"""

from __future__ import annotations

import logging
import threading
from collections import deque
from datetime import UTC, datetime
from typing import Any

_MAX_MESSAGE_LENGTH = 2000


class RingBufferHandler(logging.Handler):
    """A bounded, thread-safe tail of formatted log records.

    Older records are dropped once the buffer is full rather than raising or
    blocking, so a noisy provider cannot turn this into a memory leak or slow
    down request handling.
    """

    def __init__(self, capacity: int = 500) -> None:
        super().__init__()
        self._records: deque[dict[str, Any]] = deque(maxlen=capacity)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            message = self.format(record)
        except Exception:  # noqa: BLE001 - formatting must never crash logging
            message = record.getMessage()
        if len(message) > _MAX_MESSAGE_LENGTH:
            message = message[:_MAX_MESSAGE_LENGTH] + "…"

        entry = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "levelno": record.levelno,
            "logger": record.name,
            "message": message,
        }
        with self._lock:
            self._records.append(entry)

    def tail(self, limit: int = 500, min_level: int = logging.NOTSET) -> list[dict[str, Any]]:
        with self._lock:
            records = list(self._records)
        if min_level:
            records = [r for r in records if r["levelno"] >= min_level]
        return [{k: v for k, v in r.items() if k != "levelno"} for r in records[-limit:]]


# One process-wide buffer, attached to the root logger by `cli._configure_logging`
# and read by the `/v1/logs` endpoint.
BUFFER = RingBufferHandler()
