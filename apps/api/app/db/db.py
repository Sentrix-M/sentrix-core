"""Lightweight SQLite storage foundation for the Sentrix Memory Layer.

This module wraps the Python standard-library ``sqlite3`` driver and manages
the schema for the memory tables. It intentionally does **not** introduce an
ORM, a migration framework, or a connection pool — the storage is kept simple
and is hidden behind the :class:`~app.memory.repository.MemoryRepository`
interface so a future PostgreSQL/SQLModel backend can replace it without
changing any public API.

Schema creation is idempotent (``CREATE TABLE IF NOT EXISTS``) so the
database is initialised automatically on first use.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Any

#: Sentinel used to represent an in-memory (temporary) database.
_MEMORY_DB = ":memory:"

#: All six memory tables are created idempotently on first use.
_SCHEMA_STATEMENTS = (
    """
    CREATE TABLE IF NOT EXISTS conversations (
        id              TEXT PRIMARY KEY,
        org_id          TEXT NOT NULL DEFAULT '',
        user_id         TEXT NOT NULL DEFAULT '',
        conversation_id TEXT NOT NULL,
        role            TEXT NOT NULL,
        content         TEXT NOT NULL,
        metadata        TEXT NOT NULL DEFAULT '{}',
        created_at      TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS investigations (
        id              TEXT PRIMARY KEY,
        org_id          TEXT NOT NULL DEFAULT '',
        user_id         TEXT NOT NULL DEFAULT '',
        title           TEXT NOT NULL,
        target          TEXT NOT NULL DEFAULT '',
        summary         TEXT NOT NULL DEFAULT '',
        findings        TEXT NOT NULL DEFAULT '[]',
        created_at      TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS reports (
        id              TEXT PRIMARY KEY,
        org_id          TEXT NOT NULL DEFAULT '',
        user_id         TEXT NOT NULL DEFAULT '',
        title           TEXT NOT NULL,
        report_format   TEXT NOT NULL DEFAULT 'markdown',
        severity        TEXT NOT NULL DEFAULT 'Medium',
        summary         TEXT NOT NULL DEFAULT '',
        payload         TEXT NOT NULL DEFAULT '{}',
        created_at      TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS preferences (
        id         TEXT PRIMARY KEY,
        org_id     TEXT NOT NULL DEFAULT '',
        user_id    TEXT NOT NULL,
        user_key   TEXT NOT NULL,
        value      TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (org_id, user_id, user_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS tool_executions (
        id          TEXT PRIMARY KEY,
        org_id      TEXT NOT NULL DEFAULT '',
        user_id     TEXT NOT NULL DEFAULT '',
        tool_name   TEXT NOT NULL,
        success     INTEGER NOT NULL,
        input       TEXT NOT NULL DEFAULT '{}',
        output      TEXT NOT NULL DEFAULT '{}',
        error       TEXT NOT NULL DEFAULT '',
        created_at  TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS findings (
        id             TEXT PRIMARY KEY,
        org_id         TEXT NOT NULL DEFAULT '',
        user_id        TEXT NOT NULL DEFAULT '',
        finding_type   TEXT NOT NULL,
        target         TEXT NOT NULL DEFAULT '',
        severity       TEXT NOT NULL DEFAULT 'Medium',
        description    TEXT NOT NULL DEFAULT '',
        detail         TEXT NOT NULL DEFAULT '{}',
        created_at     TEXT NOT NULL
    )
    """,
)


def _now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def dumps(value: Any) -> str:
    """Serialize *value* to a JSON string for storage."""
    return json.dumps(value, default=str)


def loads(value: str | None, default: Any) -> Any:
    """Deserialize *value* from a JSON string, falling back to *default*."""
    if not value:
        return default
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


class MemoryDatabase:
    """Thread-safe wrapper around a SQLite connection.

    :param path: Filesystem path to the database file, or ``":memory:"`` for
        a transient in-memory database (used by tests and the default dev
        flow). When ``None`` a transient in-memory database is used.
    """

    def __init__(self, path: str | None = None) -> None:
        self._path = path or _MEMORY_DB
        self._lock = threading.RLock()

        parent = Path(self._path).parent if self._path != _MEMORY_DB else None
        if parent is not None:
            parent.mkdir(parents=True, exist_ok=True)

        self._conn = sqlite3.connect(self._path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.execute("PRAGMA foreign_keys=ON;")
        self._init_schema()

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def _init_schema(self) -> None:
        """Create all memory tables if they do not already exist."""
        with self._lock:
            cur = self._conn.cursor()
            for statement in _SCHEMA_STATEMENTS:
                cur.execute(statement)
            self._conn.commit()

    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            self._conn.close()

    # ------------------------------------------------------------------
    # DDL helpers
    # ------------------------------------------------------------------

    @property
    def path(self) -> str:
        """The database path (``:memory:`` for a transient store)."""
        return self._path

    def execute(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> sqlite3.Cursor:
        """Execute a statement under the connection lock."""
        with self._lock:
            cur = self._conn.execute(sql, params)
            self._conn.commit()
            return cur

    def query(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> list[sqlite3.Row]:
        """Execute a SELECT and return all rows."""
        with self._lock:
            return list(self._conn.execute(sql, params))

    def query_one(
        self,
        sql: str,
        params: tuple[Any, ...] = (),
    ) -> sqlite3.Row | None:
        """Execute a SELECT and return the first row, if any."""
        with self._lock:
            cur = self._conn.execute(sql, params)
            return cur.fetchone()

    def insert(self, table: str, values: dict[str, Any]) -> None:
        """Insert a row into *table* from a column→value mapping."""
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        sql = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
        self.execute(sql, tuple(values.values()))

    def upsert(self, table: str, values: dict[str, Any]) -> None:
        """Insert a row, replacing any row with the same primary key."""
        columns = ", ".join(values)
        placeholders = ", ".join("?" for _ in values)
        sql = (
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT(id) DO UPDATE SET "
            + ", ".join(f"{c} = excluded.{c}" for c in values if c != "id")
        )
        self.execute(sql, tuple(values.values()))


__all__ = ["MemoryDatabase", "loads", "dumps"]
