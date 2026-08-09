"""Refresh token entity and its lifecycle state.

Refresh tokens are single-use by design. Every issued refresh token carries a
unique ``jti`` (JWT ID). Rotation on every refresh enables replay detection:
if a used/rotated token is presented again, the entire token family is
revoked.
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class RefreshTokenState(str, enum.Enum):
    """Lifecycle state of a refresh token."""

    ACTIVE = "active"
    USED = "used"
    REVOKED = "revoked"
    EXPIRED = "expired"

    def __str__(self) -> str:
        return self.value


class RefreshToken(BaseModel):
    """A single-use JWT refresh token record."""

    model_config = ConfigDict(frozen=True)

    jti: str = Field(description="JWT ID — unique per token.")
    user_id: str = Field(description="Owner of the refresh token.")
    org_id: str = Field(description="Tenant scope.")
    expires_at: datetime = Field(description="Absolute expiration.")
    state: RefreshTokenState = RefreshTokenState.ACTIVE
    created_at: datetime
    updated_at: datetime

    @property
    def is_active(self) -> bool:
        return self.state == RefreshTokenState.ACTIVE

    def rotated_copy(self, *, now: datetime) -> RefreshToken:
        """Return a copy of this token with state set to ``USED``."""
        return self.model_copy(
            update={"state": RefreshTokenState.USED, "updated_at": now}
        )

