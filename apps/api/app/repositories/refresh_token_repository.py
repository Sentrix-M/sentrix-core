"""Refresh-token repository — interface + implementations.

Refresh tokens are single-use; the repository records their lifecycle
(``active`` → ``used``/``revoked``/``expired``) so rotation and replay
detection can be enforced by the service layer.

Two implementations are provided:

- ``InMemoryRefreshTokenRepository`` — thread-safe in-memory store.
- ``PostgreSQLRefreshTokenRepository`` — scaffold mirroring the interface.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Protocol

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


class PostgreSQLRefreshTokenRepository:
    """Scaffold for the PostgreSQL implementation.

    NOT IMPLEMENTED yet — mirrors the interface so production wiring can swap
    implementations without touching the service layer.
    """

    def __init__(self) -> None:
        raise NotImplementedError(
            "PostgreSQLRefreshTokenRepository is a scaffold; wire your async "
            "session and model before enabling this implementation."
        )

