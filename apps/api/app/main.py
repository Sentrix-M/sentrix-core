"""Sentrix API — application entry point.

Wires together configuration, repositories, seed data, exception handlers,
CORS, and the versioned v1 router.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.v1 import api_router
from app.config.settings import get_settings
from app.repositories.refresh_token_repository import InMemoryRefreshTokenRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.conversation_service import ConversationService
from app.utils.seed import seed_admin_user

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle: initialize repositories and seed data."""
    # Development store. Swap for PostgreSQLUserRepository when the DB layer
    # is implemented.
    user_repository = InMemoryUserRepository()
    refresh_token_repository = InMemoryRefreshTokenRepository()

    app.state.user_repository = user_repository
    app.state.refresh_token_repository = refresh_token_repository

    # Conversation engine — stateless and mock-backed for now. The real AI
    # router/RAG/tool layers can be injected here without touching the routers.
    app.state.conversation_service = ConversationService()

    # Seed the default admin account for local development.
    await seed_admin_user(user_repository, settings)

    try:
        yield
    finally:
        # Future: close DB connections here.
        pass


app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
    description=(
        "Sentrix — enterprise AI-powered cybersecurity platform. "
        "This API exposes the v1 gateway under /api/v1."
    ),
    lifespan=lifespan,
)

# CORS — restrict to configured origins.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Domain-exception → JSON error envelope.
register_exception_handlers(app)

# Versioned API routes.
app.include_router(api_router, prefix=settings.api_v1_prefix)


@app.get("/health", tags=["health"], summary="Liveness probe")
async def health() -> dict[str, str]:
    """Return service health status for orchestration and monitoring."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
    }

