"""Security primitives: password hashing and JWT encoding/decoding.

Passwords are hashed with Argon2id via ``pwdlib``. JWTs are signed with
``PyJWT`` using the configured algorithm (HS256 by default).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Literal

import jwt
from pwdlib import PasswordHash

from app.config.settings import Settings

# Token types — used to constrain the ``typ`` claim so an access token can
# never be used as a refresh token and vice versa.
TokenType = Literal["access", "refresh"]

password_hash = PasswordHash.recommended()


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using Argon2id."""
    return password_hash.hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain-text password against its Argon2id hash."""
    return password_hash.verify(plain_password, hashed_password)


def _base_claims(
    *,
    subject: str,
    org_id: str,
    role: str,
    permissions: list[str],
    token_type: TokenType,
    settings: Settings,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build the shared claim set for access and refresh tokens.

    Both token kinds carry audience/issuer/type constraints, and refresh
    tokens additionally require a ``jti`` for rotation/replay detection.
    """
    issued_at = now or datetime.now(timezone.utc)
    lifetime = (
        timedelta(minutes=settings.access_token_expire_minutes)
        if token_type == "access"
        else timedelta(days=settings.refresh_token_expire_days)
    )
    return {
        "sub": subject,
        "org_id": org_id,
        "role": role,
        "permissions": permissions,
        "typ": token_type,
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
        "iat": issued_at,
        "exp": issued_at + lifetime,
    }


def create_access_token(
    *,
    subject: str,
    org_id: str,
    role: str,
    permissions: list[str],
    settings: Settings,
    jti: str | None = None,
) -> str:
    """Create a short-lived JWT access token."""
    claims = _base_claims(
        subject=subject,
        org_id=org_id,
        role=role,
        permissions=permissions,
        token_type="access",
        settings=settings,
    )
    if jti:
        claims["jti"] = jti
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_refresh_token(
    *,
    subject: str,
    org_id: str,
    role: str,
    permissions: list[str],
    jti: str,
    settings: Settings,
) -> str:
    """Create a long-lived, single-use JWT refresh token with a JTI."""
    claims = _base_claims(
        subject=subject,
        org_id=org_id,
        role=role,
        permissions=permissions,
        token_type="refresh",
        settings=settings,
    )
    claims["jti"] = jti
    return jwt.encode(claims, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str, settings: Settings) -> dict[str, Any]:
    """Decode and validate a JWT (signature, expiry, audience, issuer).

    Raises ``jwt.PyJWTError`` on any validation failure; callers map this to
    the appropriate domain exception.
    """
    return jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
        audience=settings.jwt_audience,
        issuer=settings.jwt_issuer,
        options={"require": ["sub", "exp", "iat"]},
    )

