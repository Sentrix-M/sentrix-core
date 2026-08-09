"""PostgreSQL connection helper for the persistent authentication layer.

This module provides a thin, dependency-light wrapper around ``psycopg``
(psycopg3) async connections for the Phase 17 persistent authentication
repositories. It intentionally does **not** introduce an ORM or a migration
framework: tables are created idempotently with ``CREATE TABLE IF NOT EXISTS``
so the application can bootstrap against a fresh Neon PostgreSQL database
without running a separate migration step.

Design notes
------------
- A single :class:`AsyncConnectionPool` is created once (typically during the
  FastAPI lifespan) and shared by the user and refresh-token repositories.
  If ``psycopg_pool`` is unavailable, the pool falls back to a simple lazy
  connection factory so the feature still works with ``psycopg[binary]``
  alone.
- The schema matches the existing, persistence-agnostic Pydantic entities in
  :mod:`app.models` (``User`` and ``RefreshToken``) so no model changes are
  required.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import psycopg  # type: ignore[import-not-found]

logger = logging.getLogger(__name__)

#: DDL executed once at startup to ensure the ``users`` table exists.
USERS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS auth_users (
    id            TEXT PRIMARY KEY,
    email         TEXT NOT NULL UNIQUE,
    full_name     TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role          TEXT NOT NULL,
    org_id        TEXT NOT NULL,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    mfa_enabled   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL,
    updated_at    TIMESTAMPTZ NOT NULL
)
"""

#: DDL executed once at startup to ensure the ``refresh_tokens`` table exists.
REFRESH_TOKENS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS auth_refresh_tokens (
    jti        TEXT PRIMARY KEY,
    user_id    TEXT NOT NULL,
    org_id     TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    state      TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL
)
"""

#: Index to speed up family revocation (revoke by user+org).
REFRESH_TOKENS_FAMILY_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS idx_auth_refresh_tokens_family
    ON auth_refresh_tokens (user_id, org_id)
"""


class PostgresConfigurationError(Exception):
    """Raised when PostgreSQL is selected but not correctly configured."""


class AsyncConnectionPool:
    """A small async PostgreSQL connection container.

    :param dsn: The ``psycopg`` async connection string (Neon compatible).
    :param min_size: Minimum pooled connections (only used if ``psycopg_pool``
        is available).
    :param max_size: Maximum pooled connections (only used if ``psycopg_pool``
        is available).
    """

    def __init__(
        self,
        dsn: str,
        *,
        min_size: int = 1,
        max_size: int = 5,
    ) -> None:
        self._dsn = dsn
        self._min_size = min_size
        self._max_size = max_size
        self._pool: Any = None

    async def open(self) -> None:
        """Open the underlying connection pool (idempotent)."""
        if self._pool is not None:
            return
        try:
            from psycopg_pool import AsyncConnectionPool  # type: ignore[import-not-found]

            self._pool = AsyncConnectionPool(
                self._dsn,
                min_size=self._min_size,
                max_size=self._max_size,
                open=False,
            )
            await self._pool.open(wait=False)
        except ImportError:
            # ``psycopg_pool`` is optional. Fall back to a lazy, per-operation
            # connection so the feature works with ``psycopg[binary]`` alone.
            logger.info("psycopg_pool not installed; using per-operation connections.")
            self._pool = None

    async def close(self) -> None:
        """Close the underlying pool (idempotent)."""
        if self._pool is None:
            return
        try:
            await self._pool.close()
        finally:
            self._pool = None

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[Any]:
        """Yield a usable async connection (pooled or fresh)."""
        if self._pool is not None:
            async with self._pool.connection() as conn:
                yield conn
            return

        # Fallback: open a dedicated connection per operation.
        async with await psycopg.AsyncConnection.connect(self._dsn) as conn:
            yield conn

    async def initialize(self) -> None:
        """Ensure required tables exist (runs idempotent DDL)."""
        async with self.connection() as conn, conn.cursor() as cur:
            await cur.execute(USERS_TABLE_DDL)
            await cur.execute(REFRESH_TOKENS_TABLE_DDL)
            await cur.execute(REFRESH_TOKENS_FAMILY_INDEX_DDL)
        logger.info("PostgreSQL auth schema is initialized.")


def build_connection_pool(dsn: str) -> AsyncConnectionPool:
    """Build an :class:`AsyncConnectionPool` from a DSN."""
    if not dsn or not dsn.strip():
        raise PostgresConfigurationError(
            "DATABASE_URL is required when AUTH_BACKEND=postgres."
        )
    return AsyncConnectionPool(dsn.strip())


__all__ = [
    "AsyncConnectionPool",
    "PostgresConfigurationError",
    "build_connection_pool",
]
