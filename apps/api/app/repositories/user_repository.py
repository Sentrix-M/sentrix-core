"""User repository — interface + implementations.

Two implementations are provided:

- ``InMemoryUserRepository`` — a thread-safe in-memory store used in
  development and tests (no persistence, as required by the current stage).
- ``PostgreSQLUserRepository`` — a persistent PostgreSQL implementation used
  when ``AUTH_BACKEND=postgres``. It mirrors the same interface and stores
  users in the ``auth_users`` table (created idempotently at startup).

The service layer depends only on ``UserRepository`` protocol.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any, Protocol

from app.db.postgres import AsyncConnectionPool
from app.models.user import User


class UserRepository(Protocol):
    """Contract for persisting and retrieving :class:`User` entities."""

    async def get_by_email(self, email: str) -> User | None: ...
    async def get_by_id(self, user_id: str) -> User | None: ...
    async def create(self, user: User) -> User: ...
    async def list_all(self) -> list[User]: ...
    async def update(self, user: User) -> User: ...
    async def delete(self, user_id: str) -> None: ...


class InMemoryUserRepository:
    """Thread-safe in-memory user store (development/testing)."""

    def __init__(self) -> None:
        self._users: dict[str, User] = {}
        self._lock = threading.RLock()

    async def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        with self._lock:
            for user in self._users.values():
                if user.email == normalized:
                    # Return a copy to keep external mutation isolated.
                    return user.model_copy(deep=True)
        return None

    async def get_by_id(self, user_id: str) -> User | None:
        with self._lock:
            user = self._users.get(user_id)
            return user.model_copy(deep=True) if user else None

    async def create(self, user: User) -> User:
        with self._lock:
            if user.id in self._users:
                raise ValueError(f"User with id {user.id!r} already exists.")
            stored = user.model_copy(deep=True)
            self._users[stored.id] = stored
            return stored.model_copy(deep=True)

    async def list_all(self) -> list[User]:
        with self._lock:
            return [u.model_copy(deep=True) for u in self._users.values()]

    async def update(self, user: User) -> User:
        with self._lock:
            existing = self._users.get(user.id)
            if existing is None:
                raise KeyError(f"User with id {user.id!r} does not exist.")
            updated = user.model_copy(
                deep=True, update={"updated_at": datetime.now(timezone.utc)}
            )
            self._users[updated.id] = updated
            return updated.model_copy(deep=True)

    async def delete(self, user_id: str) -> None:
        with self._lock:
            self._users.pop(user_id, None)


#: Column set used when fetching a user row (must match the DDL).
_USER_COLUMNS = (
    "id",
    "email",
    "full_name",
    "password_hash",
    "role",
    "org_id",
    "is_active",
    "mfa_enabled",
    "created_at",
    "updated_at",
)


def _user_from_row(row: dict[str, Any]) -> User:
    """Build a :class:`User` from a database row dict."""
    return User(
        id=row["id"],
        email=row["email"],
        full_name=row["full_name"],
        password_hash=row["password_hash"],
        role=row["role"],
        org_id=row["org_id"],
        is_active=bool(row["is_active"]),
        mfa_enabled=bool(row["mfa_enabled"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class PostgreSQLUserRepository:
    """Persistent :class:`UserRepository` backed by PostgreSQL (Neon).

    :param pool: An :class:`AsyncConnectionPool` used for all operations.
        The pool must already be initialized (tables created) by the caller.
    """

    def __init__(self, pool: AsyncConnectionPool) -> None:
        if pool is None:
            raise ValueError("PostgreSQLUserRepository requires a connection pool.")
        self._pool = pool

    async def get_by_email(self, email: str) -> User | None:
        normalized = email.strip().lower()
        query = (
            f"SELECT {', '.join(_USER_COLUMNS)} FROM auth_users "
            "WHERE email = %s"
        )
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(query, (normalized,))
            row = await cur.fetchone()
        if row is None:
            return None
        return _user_from_row(dict(zip(_USER_COLUMNS, row, strict=False)))

    async def get_by_id(self, user_id: str) -> User | None:
        query = (
            f"SELECT {', '.join(_USER_COLUMNS)} FROM auth_users "
            "WHERE id = %s"
        )
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(query, (user_id,))
            row = await cur.fetchone()
        if row is None:
            return None
        return _user_from_row(dict(zip(_USER_COLUMNS, row, strict=False)))

    async def create(self, user: User) -> User:
        query = (
            "INSERT INTO auth_users ("
            "id, email, full_name, password_hash, role, org_id, is_active, "
            "mfa_enabled, created_at, updated_at"
            ") VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)"
        )
        values = (
            user.id,
            str(user.email),
            user.full_name,
            user.password_hash,
            user.role,
            user.org_id,
            user.is_active,
            user.mfa_enabled,
            user.created_at,
            user.updated_at,
        )
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(query, values)
        return user.model_copy(deep=True)

    async def list_all(self) -> list[User]:
        query = f"SELECT {', '.join(_USER_COLUMNS)} FROM auth_users ORDER BY created_at"
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(query)
            rows = await cur.fetchall()
        return [_user_from_row(dict(zip(_USER_COLUMNS, row, strict=False))) for row in rows]

    async def update(self, user: User) -> User:
        query = (
            "UPDATE auth_users SET "
            "email = %s, full_name = %s, password_hash = %s, role = %s, "
            "org_id = %s, is_active = %s, mfa_enabled = %s, "
            "created_at = %s, updated_at = %s "
            "WHERE id = %s"
        )
        values = (
            str(user.email),
            user.full_name,
            user.password_hash,
            user.role,
            user.org_id,
            user.is_active,
            user.mfa_enabled,
            user.created_at,
            user.updated_at,
            user.id,
        )
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(query, values)
            if cur.rowcount == 0:
                raise KeyError(f"User with id {user.id!r} does not exist.")
        return user.model_copy(deep=True)

    async def delete(self, user_id: str) -> None:
        query = "DELETE FROM auth_users WHERE id = %s"
        async with self._pool.connection() as conn, conn.cursor() as cur:
            await cur.execute(query, (user_id,))

