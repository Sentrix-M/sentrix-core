"""User repository — interface + implementations.

Two implementations are provided:

- ``InMemoryUserRepository`` — a thread-safe in-memory store used in
  development and tests (no persistence, as required by the current stage).
- ``PostgreSQLUserRepository`` — a scaffold that mirrors the interface for a
  future PostgreSQL ``users`` table. It intentionally raises
  ``NotImplementedError`` so the contract is explicit and compile-time safe.

The service layer depends only on ``UserRepository`` protocol.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Protocol

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


class PostgreSQLUserRepository:
    """Scaffold for the PostgreSQL implementation of ``UserRepository``.

    NOT IMPLEMENTED yet — the interface is mirrored here so production wiring
    can swap the in-memory store without changes to the service layer.
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "PostgreSQLUserRepository is a scaffold; wire your async session "
            "and SQLAlchemy models before enabling this implementation."
        )

