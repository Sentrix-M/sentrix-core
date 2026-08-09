"""Application settings loaded from environment variables via Pydantic.

Values can be overridden by a local `.env` file or by process environment
variables. See `.env.example` for the supported keys.

Security-sensitive values (``jwt_secret_key``, seed admin credentials) must be
provided through a secure secret manager in production deployments.
"""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application configuration."""

    model_config = SettingsConfigDict(
        # Resolve `.env` relative to the API package root (`apps/api/.env`)
        # so the file is found regardless of the process working directory.
        env_file=str(Path(__file__).resolve().parents[2] / ".env"),
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
    gemini_model: str = "gemini-3.5-flash"

    # VirusTotal threat intelligence
    # `VIRUSTOTAL_API_KEY` authenticates the VirusTotalTool. When it is
    # missing or empty, the tool reports an unhealthy state and returns a
    # clear structured error on execute.
    virustotal_api_key: str = Field(default="", repr=False)
    # Base URL for the VirusTotal REST API v3.
    virustotal_base_url: str = "https://www.virustotal.com/api/v3"

    # Shodan threat intelligence
    # `SHODAN_API_KEY` authenticates the ShodanTool. When it is missing or
    # empty, the tool reports an unhealthy state and returns a clear
    # structured error on execute.
    shodan_api_key: str = Field(default="", repr=False)
    # Base URL for the Shodan REST API.
    shodan_base_url: str = "https://api.shodan.io"

    # Wazuh security-alert integration
    # `WAZUH_URL` is the full API base URL (e.g. https://wazuh-manager:55000).
    # `WAZUH_USERNAME` / `WAZUH_PASSWORD` authenticate against the Wazuh REST
    # API; the tool exchanges them for a JWT token via the official
    # `/security/user/authenticate` endpoint and refreshes it when expired.
    wazuh_url: str = Field(default="", repr=False)
    wazuh_username: str = Field(default="", repr=False)
    wazuh_password: str = Field(default="", repr=False)

    # Seed admin — used only by the in-memory repository for local development.
    admin_email: str = "admin@sentrix.io"
    admin_password: str = "ChangeMe_123!"
    admin_full_name: str = "Sentrix Admin"
    admin_org_id: str = "00000000-0000-0000-0000-000000000000"

    # Authentication backend (Phase 17 — persistent authentication)
    # `AUTH_BACKEND` selects the storage backend for users and refresh tokens.
    # Supported values:
    #   - "memory" (default) — in-memory repositories (offline-safe, no disk).
    #   - "postgres" — persistent PostgreSQL repositories (built for Neon).
    # The default remains "memory" so existing development and the test suite
    # are unchanged; switch to "postgres" to enable persistence across restarts.
    auth_backend: Literal["memory", "postgres"] = "memory"

    # `DATABASE_URL` is the PostgreSQL connection string used when
    # `AUTH_BACKEND="postgres"`. It must be a valid `psycopg` async DSN
    # (e.g. a Neon PostgreSQL connection string). When empty while postgres
    # is selected, the repositories fail fast with a clear configuration error.
    database_url: str = Field(default="", repr=False)

    # Long-Term Memory backend
    # `MEMORY_BACKEND` selects the storage backend for the Long-Term Memory
    # layer. Supported values:
    #   - "memory" (default) — in-memory repository (offline-safe, no disk).
    #   - "sqlite" — persists to a local SQLite file (stdlib sqlite3 only).
    # A future "postgres" value can be added without changing public APIs.
    memory_backend: Literal["memory", "sqlite"] = "memory"

    # `MEMORY_DB_PATH` is the SQLite file used when `memory_backend="sqlite"`.
    # Relative paths resolve from the API package root (`apps/api`).
    memory_db_path: str = "data/sentrix_memory.db"

    # Speech-to-Text (Phase 16A)
    # `STT_PROVIDER` selects the speech-to-text backend for the voice
    # assistant. Supported values:
    #   - "mock" (default) — deterministic offline STT, no heavy model.
    #   - "faster_whisper" — local Faster-Whisper model (optional, enabled
    #     only via this setting; never forced on developer machines).
    # A future "openai_realtime" value can be added without changing APIs.
    stt_provider: str = "mock"

    # Faster-Whisper configuration. Only used when `STT_PROVIDER="faster_whisper"`.
    # `WHISPER_MODEL` names the model (e.g. "base", "small", "medium").
    # `WHISPER_DEVICE` selects the compute device ("cpu" default, or "cuda").
    # `WHISPER_COMPUTE_TYPE` controls precision ("int8" default).
    whisper_model: str = "base"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    # Text-to-Speech (Phase 16C — config added now for forward compatibility).
    # `TTS_PROVIDER` selects the TTS backend. Supported values:
    #   - "mock" (default) — deterministic offline TTS, no heavy model.
    #   - "kokoro" — local Kokoro TTS (added in Phase 16C).
    tts_provider: str = "mock"


@lru_cache
def get_settings() -> Settings:
    """Return a cached settings instance."""
    return Settings()
