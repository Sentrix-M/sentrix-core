"""RAG ingestion routes under ``/api/v1/rag``.

Provides endpoints for uploading PDF documents, listing ingested documents,
retrieving chunk details, and semantic search. All endpoints require
authentication.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import CurrentUser, get_rag_service
from app.rag.schemas import (
    ChunkListResponse,
    DocumentListResponse,
    DocumentUploadResponse,
    SearchQuery,
    SearchResponse,
)
from app.rag.service import RagService

router = APIRouter(prefix="/rag", tags=["rag"])


@router.post(
    "/upload",
    response_model=DocumentUploadResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload and ingest a PDF document",
)
async def upload_document(
    current_user: CurrentUser,  # noqa: ARG001 - auth guard
    rag_service: Annotated[RagService, Depends(get_rag_service)],
    file: UploadFile = File(description="PDF file to upload"),  # noqa: B008
) -> DocumentUploadResponse:
    """Upload a PDF file, extract text, chunk it, and store in memory.

    The file must be a valid PDF. Accepted content types:
    ``application/pdf``.
    """
    if file.content_type and file.content_type != "application/pdf":
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"Unsupported content type '{file.content_type}'. Only PDF files are accepted.",
        )

    content = await file.read()
    if not content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )

    try:
        result = await rag_service.ingest_pdf(
            content,
            filename=file.filename or f"document_{uuid.uuid4().hex[:8]}.pdf",
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to ingest PDF: {exc}",
        ) from exc

    return result


@router.get(
    "/documents",
    response_model=DocumentListResponse,
    summary="List all ingested documents",
)
async def list_documents(
    current_user: CurrentUser,  # noqa: ARG001 - auth guard
    rag_service: Annotated[RagService, Depends(get_rag_service)],
) -> DocumentListResponse:
    """Return a list of all documents that have been ingested."""
    return await rag_service.list_documents()


@router.get(
    "/documents/{document_id}/chunks",
    response_model=ChunkListResponse,
    summary="Get chunks for a document",
)
async def get_document_chunks(
    document_id: uuid.UUID,
    current_user: CurrentUser,  # noqa: ARG001 - auth guard
    rag_service: Annotated[RagService, Depends(get_rag_service)],
) -> ChunkListResponse:
    """Return all chunks for a specific document."""
    from app.rag.repository import InMemoryDocumentRepository

    # Get the document to retrieve filename.
    repo = rag_service._repository  # noqa: SLF001
    if isinstance(repo, InMemoryDocumentRepository):
        doc = await repo.get_document(document_id)
        if doc is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Document {document_id} not found.",
            )
        chunks = await repo.get_chunks(document_id)
        return ChunkListResponse(
            document_id=document_id,
            filename=doc.filename,
            chunks=chunks,
            total=len(chunks),
        )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Repository type not supported for chunk retrieval.",
    )


@router.post(
    "/search",
    response_model=SearchResponse,
    summary="Semantic search over ingested document chunks",
)
async def search_chunks(
    query: SearchQuery,
    current_user: CurrentUser,  # noqa: ARG001 - auth guard
    rag_service: Annotated[RagService, Depends(get_rag_service)],
) -> SearchResponse:
    """Search for semantically relevant chunks using vector embeddings.

    Returns the top-k matching chunks with metadata (filename, page number,
    chunk index, similarity score).  The search uses the configured embedding
    provider and vector store — no Gemini integration is performed at this
    stage.
    """
    try:
        results = await rag_service.search(query.query, top_k=query.top_k)
        return SearchResponse(
            query=query.query,
            results=results,
            total=len(results),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Semantic search failed: {exc}",
        ) from exc
