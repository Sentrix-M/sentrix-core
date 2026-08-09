"""WebSocket authentication for the Sentrix Voice Assistant.

The voice WebSocket endpoint authenticates the client with the same JWT used
by the REST API. The access token is decoded and validated exactly like
:func:`~app.api.deps.get_current_user`, but for a WebSocket we read the token
from either the ``Authorization`` header or a ``token`` query parameter
(browsers cannot set headers on ``WebSocket`` connections, so the query
parameter is the practical path for the frontend).
"""

from __future__ import annotations

from fastapi import WebSocket, WebSocketException, status

from app.config.settings import Settings, get_settings
from app.core.exceptions import SentrixError
from app.models.user import User
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.user_repository import UserRepository
from app.services.token_service import TokenService


def _extract_token(websocket: WebSocket) -> str | None:
    """Read the access token from the Authorization header or query params."""
    # 1. Authorization: Bearer <token> header.
    auth_header = websocket.headers.get("authorization", "")
    if auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()

    # 2. `?token=<token>` query parameter (browser-friendly).
    token = websocket.query_params.get("token")
    if token:
        return token.strip()

    return None


def _user_repository(websocket: WebSocket) -> UserRepository:
    """Return the user repository from app state (raises if uninitialised)."""
    repo = getattr(websocket.app.state, "user_repository", None)
    if repo is None:
        raise WebSocketException(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="User repository is not initialized.",
        )
    return repo


def _refresh_token_repository(websocket: WebSocket) -> RefreshTokenRepository:
    """Return the refresh-token repository from app state."""
    repo = getattr(websocket.app.state, "refresh_token_repository", None)
    if repo is None:
        raise WebSocketException(
            code=status.WS_1011_INTERNAL_ERROR,
            reason="Refresh-token repository is not initialized.",
        )
    return repo


async def authenticate_websocket(websocket: WebSocket) -> User:
    """Validate the WebSocket client's JWT and return the authenticated user.

    :param websocket: The active WebSocket connection.
    :returns: The authenticated :class:`User`.
    :raises WebSocketException: When the token is missing, invalid, or the
        user account is inactive.
    """
    token = _extract_token(websocket)
    if not token:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Missing access token. Provide it via ?token= or Authorization header.",
        )

    settings: Settings = get_settings()
    token_service = TokenService(
        refresh_token_repository=_refresh_token_repository(websocket),
        user_repository=_user_repository(websocket),
        settings=settings,
    )

    try:
        data = token_service.decode(token)
        token_service.require_token_type(data, "access")
        user = await _user_repository(websocket).get_by_id(data.sub)
    except SentrixError:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="Invalid or expired access token.",
        ) from None

    if user is None or not user.is_active:
        raise WebSocketException(
            code=status.WS_1008_POLICY_VIOLATION,
            reason="User account is inactive or no longer exists.",
        )
    return user


async def get_current_user_ws(websocket: WebSocket) -> User:
    """Dependency-style helper returning the authenticated user for a socket."""
    return await authenticate_websocket(websocket)


# Re-exported for convenience / type clarity.
__all__ = ["authenticate_websocket", "get_current_user_ws"]
