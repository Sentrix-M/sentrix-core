"""Application settings loaded from environment variables via Pydantic.

Values can be overridden by a local `.env` file or by process environment
variables. See `.env.example` for the supported keys.

Security-sensitive values (``jwt_secret_key``, seed admin credentials) must be
provided through a secure secret manager in production deployments.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "Sentrix API"
    app_version: str = "0.1.0"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"
    environment: Literal["development", "staging", "production"] = "development"

    # CORS — comma-separated list of allowed origins.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # JWT configuration
    # NOTE: the dev default is insecure by design; production must set a
    # strong secret via `JWT_SECRET_KEY` (or a secret manager).
    jwt_secret_key: str = Field(
        default="dev-only-change-me-please-use-a-strong-secret-in-prod",
        repr=False,
        min_length=32,
    )
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "sentrix-api"
    jwt_audience: str = "sentrix-web"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    @field_validator("jwt_secret_key")
    @classmethod
    def _validate_secret_strength(cls, value: str, info) -> str:
        """Refuse weak secrets outside development.

        A short HMAC secret is the classic way JWT implementations get
        compromised. Development defaults are tolerated; staging/production
        must provide a cryptographically strong key (>= 32 bytes).
        """
        environment = info.data.get("environment", "development")
        if environment != "development" and len(value) < 32:
            raise ValueError(
                "JWT_SECRET_KEY must be at least 32 characters in non-development "
                f"environments (got {len(value)})."
            )
        return value

    # AI provider selection
    # `AI_PROVIDER` controls which provider the factory resolves by default.
    # Supported values: "mock" (default), "gemini".
    ai_provider: str = "mock"

    # Google Gemini
    # `GEMINI_API_KEY` authenticates the GeminiProvider. When it is missing,
    # empty, or the SDK raises an auth error, the factory falls back to the
    # offline MockProvider so the pipeline never fails at composition time.
    gemini_api_key: str = Field(default="", repr=False)
    gemini_model: str = "gemini-2.0-flash"

    # Seed admin — used only by the in-memory repository for local development.
    admin_email: str = "admin@sentrix.io"
    admin_password: str = "ChangeMe_123!"
    admin_full_name: str = "Sentrix Admin"
    admin_org_id: str = "00000000-0000-0000-0000-000000000000"


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()

