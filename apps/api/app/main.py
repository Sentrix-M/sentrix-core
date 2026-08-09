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
from app.db.db import MemoryDatabase
from app.db.postgres import build_connection_pool
from app.kernel.integration import build_kernel_pipeline
from app.memory.repository import SQLiteMemoryRepository
from app.memory.service import MemoryService
from app.providers.factory import ProviderFactory
from app.rag.repository import InMemoryDocumentRepository
from app.rag.service import RagService
from app.reports.service import ReportService
from app.repositories.refresh_token_repository import (
    InMemoryRefreshTokenRepository,
    PostgreSQLRefreshTokenRepository,
)
from app.repositories.user_repository import (
    InMemoryUserRepository,
    PostgreSQLUserRepository,
)
from app.services.conversation_service import ConversationService
from app.tools.executor import ToolExecutor
from app.tools.mock_tools import (
    MockFilesystemTool,
    MockPythonTool,
    MockTerminalTool,
)
from app.tools.nmap_tool import NmapTool
from app.tools.registry import ToolRegistry
from app.tools.report_generator_tool import ReportGeneratorTool
from app.tools.shodan_tool import ShodanTool
from app.tools.virustotal_tool import VirusTotalTool
from app.tools.wazuh_tool import WazuhTool
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

    # Authentication persistence — selectable backend.
    #   AUTH_BACKEND=memory   (default) uses the in-memory repositories.
    #   AUTH_BACKEND=postgres uses the persistent PostgreSQL repositories
    #   backed by a connection pool (tables are created idempotently).
    # The chosen repositories are stored on app.state and consumed by the
    # dependency-injection layer, so the service layer is unaware of the swap.
    auth_pool = None
    if settings.auth_backend == "postgres":
        auth_pool = build_connection_pool(settings.database_url)
        await auth_pool.open()
        await auth_pool.initialize()
        user_repository = PostgreSQLUserRepository(pool=auth_pool)
        refresh_token_repository = PostgreSQLRefreshTokenRepository(pool=auth_pool)
        logger.info("AUTH_BACKEND=postgres — using persistent repositories.")
    else:
        user_repository = InMemoryUserRepository()
        refresh_token_repository = InMemoryRefreshTokenRepository()

    app.state.user_repository = user_repository
    app.state.refresh_token_repository = refresh_token_repository

    # Long-Term Memory — SQLite when configured, otherwise in-memory.
    if settings.memory_backend == "sqlite":
        memory_db = MemoryDatabase(path=settings.memory_db_path)
    else:
        memory_db = MemoryDatabase(path=":memory:")
    memory_repository = SQLiteMemoryRepository(db=memory_db)
    app.state.memory_service = MemoryService(repository=memory_repository)

    # RAG document ingestion engine — in-memory for development.
    document_repository = InMemoryDocumentRepository()
    app.state.rag_service = RagService(repository=document_repository)

    # Tool Engine — standalone foundation (already wired into the Kernel for
    # the conversation pipeline below).
    tool_registry = ToolRegistry()
    tool_registry.register(MockFilesystemTool())
    tool_registry.register(MockTerminalTool())
    tool_registry.register(MockPythonTool())
    tool_registry.register(NmapTool())
    tool_registry.register(VirusTotalTool())
    tool_registry.register(ShodanTool())
    tool_registry.register(WazuhTool())
    tool_executor = ToolExecutor(registry=tool_registry)
    app.state.tool_executor = tool_executor

    # Incident Report Generator — combines tool results, MITRE, RAG, and the
    # AI provider into a downloadable report (markdown/json/pdf). Long-term
    # memory records every report and honours the user's format preference.
    # Built before the kernel pipeline so report_service can be wired into
    # the conversation engine for chat-driven report generation.
    report_service = ReportService(
        executor=tool_executor,
        provider=factory.create(),
        rag_service=app.state.rag_service,
        memory_service=app.state.memory_service,
    )
    app.state.report_service = report_service
    tool_registry.register(
        ReportGeneratorTool(service=report_service, format_name="markdown")
    )

    # Conversation engine — kernel-backed so tool results and provider output
    # reach the client. When the pipeline is unavailable, the service falls
    # back to a deterministic mock reply (backward compatible).
    app.state.conversation_service = ConversationService(
        memory_service=app.state.memory_service,
        pipeline=build_kernel_pipeline(
            tool_executor=tool_executor,
            memory_service=app.state.memory_service,
            report_service=report_service,
        ),
    )

# Seed the default admin account for local development.
    await seed_admin_user(user_repository, settings)

    try:
        yield
    finally:
        # Close the PostgreSQL connection pool when it was opened.
        if auth_pool is not None:
            await auth_pool.close()


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
