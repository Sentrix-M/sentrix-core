"""User-management routes under ``/api/v1/users``.

This module demonstrates RBAC enforcement in the dependency layer: only
callers holding ``users:read`` (e.g. the seeded admin) may list users.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, status

from app.api.deps import get_auth_service, require_permission
from app.models.user import User
from app.schemas.auth import UserListResponse, UserPublic
from app.services.auth_service import AuthService

router = APIRouter(prefix="/users", tags=["users"])


@router.get(
    "",
    response_model=UserListResponse,
    status_code=status.HTTP_200_OK,
    summary="List users (admin only)",
)
async def list_users(
    current_user: Annotated[User, Depends(require_permission("users:read"))],
    auth_service: Annotated[AuthService, Depends(get_auth_service)],
) -> UserListResponse:
    """Return the full user list to callers with ``users:read``.

    ``require_permission`` both authenticates the caller and enforces the
    ``users:read`` permission. The service layer re-checks the permission to
    preserve the authorization invariant independently of the HTTP layer.
    """
    users = await auth_service.list_users(current_user)
    return UserListResponse(
        users=[UserPublic.model_validate(u) for u in users],
        total=len(users),
    )

