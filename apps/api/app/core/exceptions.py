"""Domain exceptions for the Sentrix API.

These exceptions are raised by the service layer and translated into HTTP
responses by the global exception handlers registered in ``app.main``.
Keeping them in the domain layer preserves clean-architecture boundaries:
repositories/services never depend on FastAPI/HTTP concerns.
"""


class SentrixError(Exception):
    """Base exception for all Sentrix domain errors."""

    status_code = 500
    error_code = "internal_error"
    message = "An unexpected error occurred."

    def __init__(self, message: str | None = None) -> None:
        super().__init__(message or self.message)
        self.message = message or self.message


class InvalidCredentialsError(SentrixError):
    """Raised when login credentials are incorrect."""

    status_code = 401
    error_code = "invalid_credentials"
    message = "Invalid email or password."


class UserAlreadyExistsError(SentrixError):
    """Raised when a user tries to register with an existing email."""

    status_code = 409
    error_code = "user_already_exists"
    message = "A user with this email already exists."


class UserNotFoundError(SentrixError):
    """Raised when a user cannot be found."""

    status_code = 404
    error_code = "user_not_found"
    message = "User not found."


class InvalidTokenError(SentrixError):
    """Raised when a JWT token is malformed, expired, or has a bad signature."""

    status_code = 401
    error_code = "invalid_token"
    message = "The provided token is invalid or expired."


class RefreshTokenRevokedError(SentrixError):
    """Raised when a refresh token has been revoked or replayed."""

    status_code = 401
    error_code = "refresh_token_revoked"
    message = "The refresh token has been revoked or already used."


class RefreshTokenExpiredError(SentrixError):
    """Raised when a refresh token has expired."""

    status_code = 401
    error_code = "refresh_token_expired"
    message = "The refresh token has expired."


class InsufficientPermissionsError(SentrixError):
    """Raised when a user lacks the required permission for an action."""

    status_code = 403
    error_code = "insufficient_permissions"
    message = "You do not have permission to perform this action."


class ContextMissingError(SentrixError):
    """Raised when a required dependency/context is unavailable."""

    status_code = 500
    error_code = "context_missing"
    message = "A required execution context is missing."


class TokenAlreadyRevokedError(SentrixError):
    """Raised on logout when the token was already revoked."""

    status_code = 400
    error_code = "token_already_revoked"
    message = "The token has already been revoked."

