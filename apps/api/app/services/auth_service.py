"""Authentication service — the application's auth use cases.

Responsibilities:

- Register new users (role-gated to a default role; role assignment from an
  admin flow is out of scope for the initial module).
- Authenticate users by email/password and return a token pair.
- Rotate refresh tokens and revoke them on logout.
- Resolve the authenticated user from an access token.

The service depends only on repository interfaces, the token service, and the
security primitives — never on HTTP/FastAPI concerns.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from app.config.settings import Settings
from app.core.exceptions import (
    InsufficientPermissionsError,
    InvalidCredentialsError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from app.core.security import hash_password, verify_password
from app.models.role import RoleName
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserPublic,
)
from app.services.token_service import TokenService


class AuthService:
    """Implements authentication and user-management use cases."""

    #: Role assigned to newly self-registered users.
    DEFAULT_REGISTER_ROLE = RoleName.SOC_ANALYST.value

    def __init__(
        self,
        user_repository: UserRepository,
        refresh_token_repository: RefreshTokenRepository,
        token_service: TokenService,
        settings: Settings,
    ) -> None:
        self._users = user_repository
        self._refresh_tokens = refresh_token_repository
        self._tokens = token_service
        self._settings = settings

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    async def register(self, request: RegisterRequest) -> TokenPair:
        """Register a new user and return an authenticated token pair.

        New users are assigned the default SOC analyst role; org assignment
        will follow tenant provisioning.
        """
        email = str(request.email).strip().lower()
        existing = await self._users.get_by_email(email)
        if existing is not None:
            raise UserAlreadyExistsError()

        now = datetime.now(timezone.utc)
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            full_name=request.full_name.strip(),
            password_hash=hash_password(request.password),
            role=self.DEFAULT_REGISTER_ROLE,
            org_id=self._settings.admin_org_id,
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        await self._users.create(user)

        access = await self._tokens.issue_access_token(user)
        refresh = await self._tokens.issue_refresh_token(user)
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._settings.access_token_expire_minutes * 60,
        )

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    async def login(self, request: LoginRequest) -> TokenPair:
        """Authenticate a user and return a fresh token pair."""
        email = str(request.email).strip().lower()
        user = await self._users.get_by_email(email)
        if user is None or not user.is_active:
            raise InvalidCredentialsError()
        if not verify_password(request.password, user.password_hash):
            raise InvalidCredentialsError()

        access = await self._tokens.issue_access_token(user)
        refresh = await self._tokens.issue_refresh_token(user)
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._settings.access_token_expire_minutes * 60,
        )

    async def refresh(self, request: RefreshRequest) -> TokenPair:
        """Rotate the presented refresh token and return a new token pair."""
        access, refresh = await self._tokens.rotate_refresh_token(request.refresh_token)
        return TokenPair(
            access_token=access,
            refresh_token=refresh,
            expires_in=self._settings.access_token_expire_minutes * 60,
        )

    async def logout(self, request: LogoutRequest) -> None:
        """Revoke the presented refresh token."""
        await self._tokens.revoke_refresh_token(request.refresh_token)

    # ------------------------------------------------------------------
    # Current user
    # ------------------------------------------------------------------

    async def get_user_by_id(self, user_id: str) -> User:
        """Return the user corresponding to an authenticated subject."""
        user = await self._users.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError()
        if not user.is_active:
            raise InvalidCredentialsError()
        return user

    async def get_current_user_from_token(self, token_payload_sub: str) -> User:
        """Resolve the current user from the access-token ``sub`` claim."""
        return await self.get_user_by_id(token_payload_sub)

    # ------------------------------------------------------------------
    # Admin / RBAC demo
    # ------------------------------------------------------------------

    async def list_users(self, requesting_user: User) -> list[User]:
        """Return all users to a caller with ``users:read`` permission."""
        if "users:read" not in requesting_user.permissions:
            raise InsufficientPermissionsError()
        return await self._users.list_all()

    def public_user(self, user: User) -> UserPublic:
        """Convert a domain user into the public API representation."""
        return UserPublic(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
            role=user.role,
            org_id=user.org_id,
            is_active=user.is_active,
            mfa_enabled=user.mfa_enabled,
            created_at=user.created_at,
        )

