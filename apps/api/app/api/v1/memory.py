"""Memory API — expose the Long-Term Memory foundation over HTTP.

Endpoints (all under ``/api/v1/memory``):

- ``GET  /reports`` — list report history
- ``GET  /preferences`` — list user preferences
- ``GET  /findings`` — list security-findings history
- ``GET  /investigations`` — list investigations
- ``GET  /recall`` — recall memory by temporal / entity / keyword query

This is the read/query surface for the Memory Foundation (Phase 15A). The
write/record calls are exercised by the service layer and will be wired into
the Planner, Reports, and Conversation seams in Phase 15B.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_memory_service
from app.memory.retriever import MemoryRetriever, RecallResponse
from app.memory.schemas import (
    FindingRecord,
    InvestigationRecord,
    MemoryListResponse,
    PreferenceRecord,
    ReportRecord,
)
from app.memory.service import MemoryService

router = APIRouter(prefix="/memory", tags=["memory"])

MemoryServiceDep = Annotated[MemoryService, Depends(get_memory_service)]


@router.get("/reports", response_model=MemoryListResponse, summary="List report history")
async def list_reports(
    memory: MemoryServiceDep,
    org_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> MemoryListResponse:
    """Return generated reports, newest first."""
    items: list[ReportRecord] = memory.get_reports(
        org_id=org_id,
        user_id=user_id,
        limit=limit,
    )
    return MemoryListResponse(items=items, total=len(items))


@router.get(
    "/preferences",
    response_model=MemoryListResponse,
    summary="List user preferences",
)
async def list_preferences(
    memory: MemoryServiceDep,
    user_id: str | None = Query(default=None),
    org_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> MemoryListResponse:
    """Return stored user preferences."""
    items: list[PreferenceRecord] = memory.get_preferences(
        user_id=user_id,
        org_id=org_id,
        limit=limit,
    )
    return MemoryListResponse(items=items, total=len(items))


@router.get(
    "/findings",
    response_model=MemoryListResponse,
    summary="List security-findings history",
)
async def list_findings(
    memory: MemoryServiceDep,
    finding_type: str | None = Query(default=None),
    target: str | None = Query(default=None),
    org_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> MemoryListResponse:
    """Return recorded security findings, newest first."""
    items: list[FindingRecord] = memory.get_findings(
        finding_type=finding_type,
        target=target,
        org_id=org_id,
        user_id=user_id,
        limit=limit,
    )
    return MemoryListResponse(items=items, total=len(items))


@router.get(
    "/investigations",
    response_model=MemoryListResponse,
    summary="List investigations",
)
async def list_investigations(
    memory: MemoryServiceDep,
    org_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> MemoryListResponse:
    """Return recorded investigations, newest first."""
    items: list[InvestigationRecord] = memory.get_investigations(
        org_id=org_id,
        user_id=user_id,
        limit=limit,
    )
    return MemoryListResponse(items=items, total=len(items))


@router.get(
    "/recall",
    response_model=RecallResponse,
    summary="Recall memory by query",
)
async def recall(
    memory: MemoryServiceDep,
    q: str = Query(..., min_length=1, description="Temporal / entity / keyword query"),
    org_id: str | None = Query(default=None),
    user_id: str | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
) -> RecallResponse:
    """Recall memory matching the query (temporal, entity, or keyword)."""
    retriever = MemoryRetriever(memory)
    return retriever.recall(
        query=q,
        limit=limit,
        org_id=org_id,
        user_id=user_id,
    )


__all__ = ["router"]
