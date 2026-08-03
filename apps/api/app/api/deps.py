"""Dependency-injection container and FastAPI security dependencies.

Repositories are created at application startup and shared through
``request.app.state`` so tests can override them with clean doubles.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config.settings import Settings, get_settings
from app.core.exceptions import (
    SentrixError,
)
from app.models.user import User
from app.rag.service import RagService
from app.repositories.refresh_token_repository import (
    RefreshTokenRepository,
)
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.conversation_service import ConversationService
from app.services.token_service import TokenService
from app.tools.executor import ToolExecutor

SettingsDep = Annotated[Settings, Depends(get_settings)]


# ---------------------------------------------------------------------------
# Repositories / services (shared application state)
# ---------------------------------------------------------------------------


def get_user_repository(request: Request) -> UserRepository:
    """Return the user repository stored on application state."""
    repo = getattr(request.app.state, "user_repository", None)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="User repository is not initialized.",
        )
    return repo


def get_refresh_token_repository(request: Request) -> RefreshTokenRepository:
    """Return the refresh-token repository stored on application state."""
    repo = getattr(request.app.state, "refresh_token_repository", None)
    if repo is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Refresh-token repository is not initialized.",
        )
    return repo


def get_conversation_service(request: Request) -> ConversationService:
    """Return the shared conversation service stored on application state."""
    service = getattr(request.app.state, "conversation_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Conversation service is not initialized.",
        )
    return service


def get_rag_service(request: Request) -> RagService:
    """Return the shared RAG service stored on application state."""
    service = getattr(request.app.state, "rag_service", None)
    if service is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="RAG service is not initialized.",
        )
    return service


def get_auth_service(
    user_repository: Annotated[UserRepository, Depends(get_user_repository)],
    refresh_token_repository: Annotated[
        RefreshTokenRepository, Depends(get_refresh_token_repository)
    ],
) -> AuthService:
    """Construct the shared auth service from app state repositories."""
    settings = get_settings()
    token_service = TokenService(
        refresh_token_repository=refresh_token_repository,
        user_repository=user_repository,
        settings=settings,
    )
    return AuthService(
        user_repository=user_repository,
        refresh_token_repository=refresh_token_repository,
        token_service=token_service,
        settings=settings,
    )


# ---------------------------------------------------------------------------
# Security dependency (HTTP Bearer)
# ---------------------------------------------------------------------------

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer_scheme)
    ],
    request: Request,
) -> User:
    """Resolve the authenticated :class:`User` from the bearer access token."""
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid authorization header.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    settings = get_settings()
    token_service = TokenService(
        refresh_token_repository=get_refresh_token_repository(request),
        user_repository=get_user_repository(request),
        settings=settings,
    )
    try:
        data = token_service.decode(credentials.credentials)
        token_service.require_token_type(data, "access")
        user = await get_user_repository(request).get_by_id(data.sub)
    except SentrixError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from None

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account is inactive or no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


def require_permission(permission: str):
    """Return a dependency that enforces a permission on the current user."""

    def dependency(
        user: Annotated[User, Depends(get_current_user)],
    ) -> User:
        if permission not in user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions for this operation.",
            )
        return user

    return dependency


def get_tool_executor(request: Request) -> ToolExecutor:
    """Return the tool executor stored on application state."""
    executor = getattr(request.app.state, "tool_executor", None)
    if executor is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tool executor is not initialized.",
        )
    return executor


CurrentUser = Annotated[User, Depends(get_current_user)]

