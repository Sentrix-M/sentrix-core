"""Refresh-token repository — interface + implementations.

Refresh tokens are single-use; the repository records their lifecycle
(``active`` → ``used``/``revoked``/``expired``) so rotation and replay
detection can be enforced by the service layer.

Two implementations are provided:

- ``InMemoryRefreshTokenRepository`` — thread-safe in-memory store.
- ``PostgreSQLRefreshTokenRepository`` — persistent PostgreSQL store used
  when ``AUTH_BACKEND=postgres`` (table ``auth_refresh_tokens``).
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Protocol

from app.db.postgres import AsyncConnectionPool
from app.models.refresh_token import RefreshToken, RefreshTokenState


class RefreshTokenRepository(Protocol):
    """Contract for persisting and retrieving :class:`RefreshToken` records."""

    async def create(self, token: RefreshToken) -> RefreshToken: ...
    async def get_by_jti(self, jti: str) -> RefreshToken | None: ...
    async def save(self, token: RefreshToken) -> RefreshToken: ...
    async def revoke_family(self, *, user_id: str, org_id: str) -> int: ...


class InMemoryRefreshTokenRepository:
    """Thread-safe in-memory refresh-token store (development/testing)."""

    def __init__(self) -> None:
        self._tokens: dict[str, RefreshToken] = {}
        self._lock = threading.RLock()

    async def create(self, token: RefreshToken) -> RefreshToken:
        with self._lock:
            stored = token.model_copy(deep=True)
            self._tokens[stored.jti] = stored
            return stored.model_copy(deep=True)

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        with self._lock:
            token = self._tokens.get(jti)
            return token.model_copy(deep=True) if token else None

    async def save(self, token: RefreshToken) -> RefreshToken:
        with self._lock:
            existing = self._tokens.get(token.jti)
            if existing is None:
                raise KeyError(f"Refresh token {token.jti!r} does not exist.")
            stored = token.model_copy(
                deep=True, update={"updated_at": datetime.now(timezone.utc)}
            )
            self._tokens[stored.jti] = stored
            return stored.model_copy(deep=True)

    async def revoke_family(self, *, user_id: str, org_id: str) -> int:
        """Revoke every token belonging to a user family.

        Replay detection rotates the family: when a used token is replayed,
        all tokens for the user are revoked to invalidate the attacker's
        stolen access.
        """
        now = datetime.now(timezone.utc)
        revoked = 0
        with self._lock:
            for jti, token in list(self._tokens.items()):
                if (
                    token.user_id == user_id
                    and token.org_id == org_id
                    and token.state != RefreshTokenState.REVOKED
                ):
                    self._tokens[jti] = token.model_copy(
                        update={
                            "state": RefreshTokenState.REVOKED,
                            "updated_at": now,
                        }
                    )
                    revoked += 1
        return revoked


#: Columns used when fetching a refresh-token row (must match the DDL).
_TOKEN_COLUMNS = (
    "jti",
    "user_id",
    "org_id",
    "expires_at",
    "state",
    "created_at",
    "updated_at",
)


def _token_from_row(row: dict[str, Any]) -> RefreshToken:
    """Build a :class:`RefreshToken` from a database row dict."""
    return RefreshToken(
        jti=row["jti"],
        user_id=row["user_id"],
        org_id=row["org_id"],
        expires_at=row["expires_at"],
        state=RefreshTokenState(row["state"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgreSQLRefreshTokenRepository:
    """Persistent :class:`RefreshTokenRepository` backed by PostgreSQL (Neon).

    :param pool: An :class:`AsyncConnectionPool` used for all operations.
        The pool must already be initialized (tables created) by the caller.
    """

    def __init__(self, pool: AsyncConnectionPool) -> None:
        if pool is None:
            raise ValueError(
                "PostgreSQLRefreshTokenRepository requires a connection pool."
            )
        self._pool = pool

    async def create(self, token: RefreshToken) -> RefreshToken:
        query = (
            "INSERT INTO auth_refresh_tokens ("
            "jti, user_id, org_id, expires_at, state, created_at, updated_at"
            ") VALUES (%s, %s, %s, %s, %s, %s, %s)"
        )
        values = (
            token.jti,
            token.user_id,
            token.org_id,
            token.expires_at,
            token.state.value,
            token.created_at,
            token.updated_at,
        )
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(query, values)
        return token.model_copy(deep=True)

    async def get_by_jti(self, jti: str) -> RefreshToken | None:
        query = (
            f"SELECT {', '.join(_TOKEN_COLUMNS)} FROM auth_refresh_tokens "
            "WHERE jti = %s"
        )
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(query, (jti,))
            row = await cur.fetchone()
        if row is None:
            return None
        return _token_from_row(dict(zip(_TOKEN_COLUMNS, row, strict=False)))

    async def save(self, token: RefreshToken) -> RefreshToken:
        query = (
            "UPDATE auth_refresh_tokens SET "
            "user_id = %s, org_id = %s, expires_at = %s, state = %s, "
            "created_at = %s, updated_at = %s "
            "WHERE jti = %s"
        )
        values = (
            token.user_id,
            token.org_id,
            token.expires_at,
            token.state.value,
            token.created_at,
            token.updated_at,
            token.jti,
        )
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(query, values)
            if cur.rowcount == 0:
                raise KeyError(f"Refresh token {token.jti!r} does not exist.")
        return token.model_copy(deep=True)

    async def revoke_family(self, *, user_id: str, org_id: str) -> int:
        """Revoke every active/expired token belonging to a user family.

        Replay detection rotates the family: when a used token is replayed,
        all tokens for the user are revoked to invalidate the attacker's
        stolen access. Already-revoked tokens are left untouched.
        """
        query = (
            "UPDATE auth_refresh_tokens SET state = %s, updated_at = %s "
            "WHERE user_id = %s AND org_id = %s AND state != %s"
        )
        now = datetime.now(timezone.utc)
        values = (
            RefreshTokenState.REVOKED.value,
            now,
            user_id,
            org_id,
            RefreshTokenState.REVOKED.value,
        )
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(query, values)
            rowcount = cur.rowcount
        return rowcount

