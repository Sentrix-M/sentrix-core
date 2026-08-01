"""Token service: issue, decode, rotate, and revoke JWTs.

Implements the refresh-token rotation and replay-detection strategy:

- Access tokens are short-lived (default 15 minutes) and stateless.
- Refresh tokens are single-use: each refresh marks the presented token as
  ``USED`` and issues a new token with a fresh ``jti``.
- If a ``USED`` refresh token is ever presented again, the whole token family
  for that user (same ``org_id``) is revoked. This bounds the blast radius of
  stolen refresh tokens.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import jwt

from app.config.settings import Settings
from app.core.exceptions import (
    InvalidTokenError,
    RefreshTokenExpiredError,
    RefreshTokenRevokedError,
)
from app.core.security import create_access_token, create_refresh_token, decode_token
from app.models.refresh_token import RefreshToken, RefreshTokenState
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import TokenData


class TokenService:
    """Issues and validates JWTs for a tenant-scoped user."""

    def __init__(
        self,
        refresh_token_repository: RefreshTokenRepository,
        user_repository: UserRepository,
        settings: Settings,
    ) -> None:
        self._repo = refresh_token_repository
        self._users = user_repository
        self._settings = settings

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def _expiry(self, *, now: datetime) -> datetime:
        return now + timedelta(days=self._settings.refresh_token_expire_days)

    def _new_jti(self) -> str:
        return str(uuid.uuid4())

    # ------------------------------------------------------------------
    # Issuance
    # ------------------------------------------------------------------

    async def issue_access_token(self, user: User) -> str:
        """Issue a short-lived access token for a user."""
        return create_access_token(
            subject=user.id,
            org_id=user.org_id,
            role=user.role,
            permissions=user.permissions,
            settings=self._settings,
            jti=self._new_jti(),
        )

    async def issue_refresh_token(self, user: User) -> str:
        """Persist and return a new single-use refresh token for a user."""
        now = self._now()
        jti = self._new_jti()
        record = RefreshToken(
            jti=jti,
            user_id=user.id,
            org_id=user.org_id,
            expires_at=self._expiry(now=now),
            state=RefreshTokenState.ACTIVE,
            created_at=now,
            updated_at=now,
        )
        await self._repo.create(record)
        return create_refresh_token(
            subject=user.id,
            org_id=user.org_id,
            role=user.role,
            permissions=user.permissions,
            jti=jti,
            settings=self._settings,
        )

    # ------------------------------------------------------------------
    # Validation / decoding
    # ------------------------------------------------------------------

    def decode(self, token: str) -> TokenData:
        """Decode a JWT, normalizing validation failures to domain errors."""
        try:
            payload = decode_token(token, self._settings)
        except jwt.PyJWTError as exc:
            raise InvalidTokenError(str(exc)) from exc

        return TokenData(
            sub=payload["sub"],
            org_id=payload["org_id"],
            role=payload["role"],
            permissions=payload.get("permissions") or [],
            token_type=payload.get("typ", ""),
            jti=payload.get("jti"),
            iat=payload.get("iat"),
            exp=payload.get("exp"),
        )

    def require_token_type(self, data: TokenData, expected: str) -> TokenData:
        """Enforce that a decoded token has the expected ``typ`` claim."""
        if data.token_type != expected:
            raise InvalidTokenError(f"Expected {expected!r} token.")
        return data

    # ------------------------------------------------------------------
    # Rotation / revocation
    # ------------------------------------------------------------------

    async def rotate_refresh_token(self, refresh_token: str) -> tuple[str, str]:
        """Rotate a refresh token and return a new ``(access, refresh)`` pair.

        Rejects expired and revoked tokens, marks presented tokens as used,
        and triggers family revocation on replay.
        """
        now = self._now()

        # Decode after enforcing the refresh-token type.
        data = self.decode(refresh_token)
        self.require_token_type(data, "refresh")

        if data.jti is None:
            raise InvalidTokenError("Refresh token missing jti.")

        record = await self._repo.get_by_jti(data.jti)
        if record is None:
            # Unknown token — treat as potential replay of a purged family.
            raise RefreshTokenRevokedError()

        if record.expires_at < now:
            await self._repo.save(
                record.model_copy(
                    update={"state": RefreshTokenState.EXPIRED, "updated_at": now}
                )
            )
            raise RefreshTokenExpiredError()

        if record.state == RefreshTokenState.REVOKED:
            raise RefreshTokenRevokedError()

        if record.state == RefreshTokenState.USED:
            # Replay detected — revoke the entire family for this user+org.
            await self._repo.revoke_family(
                user_id=record.user_id, org_id=record.org_id
            )
            raise RefreshTokenRevokedError()

        # Load the owner to confirm the user is still active.
        user = await self._users.get_by_id(record.user_id)
        if user is None or not user.is_active:
            await self._repo.revoke_family(
                user_id=record.user_id, org_id=record.org_id
            )
            raise InvalidTokenError("User account is not active.")

        # Mark the presented token as used (rotation).
        await self._repo.save(record.rotated_copy(now=now))

        # Issue fresh tokens bound to the same user/tenant.
        access = await self.issue_access_token(user)
        new_refresh = await self.issue_refresh_token(user)
        return access, new_refresh

    async def revoke_refresh_token(self, refresh_token: str) -> None:
        """Revoke a refresh token on explicit logout."""
        data = self.decode(refresh_token)
        self.require_token_type(data, "refresh")
        if data.jti is None:
            raise InvalidTokenError("Refresh token missing jti.")

        record = await self._repo.get_by_jti(data.jti)
        if record is None:
            # Nothing to revoke; idempotent logout.
            return
        now = self._now()
        if record.state != RefreshTokenState.REVOKED:
            await self._repo.save(
                record.model_copy(
                    update={"state": RefreshTokenState.REVOKED, "updated_at": now}
                )
            )

