"""Authentication routes under ``/api/v1/auth``.

Exposes the auth use cases implemented by :class:`AuthService`.
Tokens are always returned explicitly in the JSON body; no cookie handling is
used so the API is framework-agnostic for any frontend.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_auth_service, get_current_user
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserPublic,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post(
    "/register",
    response_model=TokenPair,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(
    payload: RegisterRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenPair:
    """Create a user account and return an authenticated token pair."""
    return await auth_service.register(payload)


@router.post(
    "/login",
    response_model=TokenPair,
    status_code=status.HTTP_200_OK,
    summary="Authenticate a user",
)
async def login(
    payload: LoginRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenPair:
    """Authenticate with email/password and receive a token pair."""
    return await auth_service.login(payload)


@router.post(
    "/refresh",
    response_model=TokenPair,
    status_code=status.HTTP_200_OK,
    summary="Rotate a refresh token",
)
async def refresh(
    payload: RefreshRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> TokenPair:
    """Exchange a single-use refresh token for a new token pair."""
    return await auth_service.refresh(payload)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Revoke the presented refresh token",
)
async def logout(
    payload: LogoutRequest,
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> None:
    """Revoke a refresh token, terminating the session."""
    await auth_service.logout(payload)


# ---------------------------------------------------------------------------
# Authenticated endpoints
# ---------------------------------------------------------------------------


@router.get(
    "/me",
    response_model=UserPublic,
    status_code=status.HTTP_200_OK,
    summary="Return the current authenticated user",
)
async def me(
    current_user: Annotated[User, Depends(get_current_user)],
) -> UserPublic:
    """Return the profile of the authenticated user."""
    return UserPublic(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        org_id=current_user.org_id,
        is_active=current_user.is_active,
        mfa_enabled=current_user.mfa_enabled,
        created_at=current_user.created_at,
    )

