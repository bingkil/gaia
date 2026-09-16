"""SQLite access.

One connection guarded by a lock. At this event volume (tens per minute at
most) that is simpler and more predictable than a pool, and it removes the
coordination that Redis provided in the cloud design.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import threading
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_PATH = Path(__file__).parent / "schema.sql"


def utcnow() -> datetime:
    return datetime.now(UTC)


def to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def from_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode = WAL")
        self._conn.execute("PRAGMA synchronous = NORMAL")
        self._conn.execute("PRAGMA foreign_keys = ON")

    def migrate(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
            # CREATE TABLE IF NOT EXISTS above does not add columns to a table that
            # already exists from before this column was introduced.
            try:
                self._conn.execute("ALTER TABLE notification ADD COLUMN archived_at TEXT")
            except sqlite3.OperationalError:
                pass
            self._conn.commit()

    @contextmanager
    def tx(self) -> Iterator[sqlite3.Connection]:
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def execute(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Cursor:
        with self.tx() as conn:
            return conn.execute(sql, tuple(params))

    def query(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def query_one(self, sql: str, params: Iterable[Any] = ()) -> sqlite3.Row | None:
        rows = self.query(sql, params)
        return rows[0] if rows else None

    async def aquery(self, sql: str, params: Iterable[Any] = ()) -> list[sqlite3.Row]:
        return await asyncio.to_thread(self.query, sql, tuple(params))

    async def aexecute(self, sql: str, params: Iterable[Any] = ()) -> None:
        await asyncio.to_thread(self.execute, sql, tuple(params))

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


def dumps(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), default=str)


_db: Database | None = None


def get_db() -> Database:
    if _db is None:
        raise RuntimeError("database not initialised; call init_db() first")
    return _db


def init_db(path: Path) -> Database:
    global _db
    if _db is not None:
        _db.close()
    _db = Database(path)
    _db.migrate()
    return _db
