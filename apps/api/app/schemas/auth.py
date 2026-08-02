"""Pydantic schemas for the authentication module.

Request/response models are deliberately decoupled from the domain entities so
the API contract can evolve independently of the persistence model.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ---------------------------------------------------------------------------
# User-facing schemas
# ---------------------------------------------------------------------------


class UserPublic(BaseModel):
    """Public user representation returned by the API."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    email: EmailStr
    full_name: str
    role: str
    org_id: str
    is_active: bool
    mfa_enabled: bool
    created_at: datetime


class TokenPair(BaseModel):
    """Access + refresh token pair returned on login/refresh."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(
        description="Access-token lifetime in seconds.",
    )


class RegisterRequest(BaseModel):
    """Payload for creating a new user account."""

    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    full_name: str = Field(min_length=1, max_length=120)


class LoginRequest(BaseModel):
    """Payload for authenticating an existing user."""

    email: EmailStr
    password: str = Field(min_length=1)


class RefreshRequest(BaseModel):
    """Payload for rotating a refresh token."""

    refresh_token: str = Field(min_length=1)


class LogoutRequest(BaseModel):
    """Payload for revoking a refresh token on logout."""

    refresh_token: str = Field(min_length=1)


class UserListResponse(BaseModel):
    """List of users returned to admin/authorized callers."""

    users: list[UserPublic]
    total: int


# ---------------------------------------------------------------------------
# Token/error internal helpers
# ---------------------------------------------------------------------------


class TokenData(BaseModel):
    """Decoded claims extracted from a validated JWT."""

    sub: str
    org_id: str
    role: str
    permissions: list[str]
    token_type: str
    jti: str | None = None
    iat: int | None = None
    exp: int | None = None


class ErrorResponse(BaseModel):
    """Standard error shape used across the API."""

    error: dict[str, Any] = Field(
        default_factory=lambda: {"code": "internal_error", "message": "Unknown error"}
    )

