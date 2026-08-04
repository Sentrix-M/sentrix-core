"""Sentrix API — application entry point.

Wires together configuration, repositories, seed data, exception handlers,
CORS, and the versioned v1 router.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.v1 import api_router
from app.config.settings import get_settings
from app.providers.factory import ProviderFactory
from app.rag.repository import InMemoryDocumentRepository
from app.rag.service import RagService
from app.repositories.refresh_token_repository import InMemoryRefreshTokenRepository
from app.repositories.user_repository import InMemoryUserRepository
from app.services.conversation_service import ConversationService
from app.tools.executor import ToolExecutor
from app.tools.mock_tools import (
    MockFilesystemTool,
    MockPythonTool,
    MockTerminalTool,
)
from app.tools.nmap_tool import NmapTool
from app.tools.registry import ToolRegistry
from app.tools.virustotal_tool import VirusTotalTool
from app.utils.seed import seed_admin_user

logger = logging.getLogger(__name__)

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifecycle: initialize repositories and seed data."""

    # ------------------------------------------------------------------
    # Provider diagnostics — log every startup so the operator can see
    # which AI provider is actually selected and why.
    # ------------------------------------------------------------------
    has_key = bool(settings.gemini_api_key.strip())
    logger.info(
        "AI_PROVIDER=%s  GEMINI_MODEL=%s  GEMINI_API_KEY=%s",
        settings.ai_provider,
        settings.gemini_model,
        "present" if has_key else "MISSING — will fall back to MockProvider",
    )

    factory = ProviderFactory()
    try:
        provider = factory.create()
        logger.info(
            "ProviderFactory resolved provider: name=%s  type=%s",
            provider.name,
            type(provider).__name__,
        )
    except Exception as exc:
        logger.warning("ProviderFactory failed to create provider: %s", exc)
    # ------------------------------------------------------------------

    # Development store. Swap for PostgreSQLUserRepository when the DB layer
    # is implemented.
    user_repository = InMemoryUserRepository()
    refresh_token_repository = InMemoryRefreshTokenRepository()

    app.state.user_repository = user_repository
    app.state.refresh_token_repository = refresh_token_repository

    # Conversation engine — stateless and mock-backed for now.
    app.state.conversation_service = ConversationService()

    # RAG document ingestion engine — in-memory for development.
    document_repository = InMemoryDocumentRepository()
    app.state.rag_service = RagService(repository=document_repository)

    # Tool Engine — standalone foundation (not yet connected to the Kernel).
    tool_registry = ToolRegistry()
    tool_registry.register(MockFilesystemTool())
    tool_registry.register(MockTerminalTool())
    tool_registry.register(MockPythonTool())
    tool_registry.register(NmapTool())
    tool_registry.register(VirusTotalTool())
    app.state.tool_executor = ToolExecutor(registry=tool_registry)

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
