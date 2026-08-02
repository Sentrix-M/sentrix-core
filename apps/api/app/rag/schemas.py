"""Pydantic schemas for the RAG (Retrieval-Augmented Generation) layer.

Defines the data contracts for document ingestion, chunk storage, and
API responses — no embeddings, no vector stores, just the foundation.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Domain entities
# ---------------------------------------------------------------------------


class Document(BaseModel):
    """A single uploaded document with its metadata."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4, description="Unique document identifier.")
    filename: str = Field(description="Original uploaded filename.")
    content_type: str = Field(default="application/pdf", description="MIME type.")
    page_count: int = Field(ge=0, description="Number of pages extracted.")
    total_chunks: int = Field(ge=0, default=0, description="Number of chunks produced.")
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Chunk(BaseModel):
    """A single text chunk extracted from a document page."""

    model_config = ConfigDict(frozen=True)

    id: UUID = Field(default_factory=uuid4, description="Unique chunk identifier.")
    document_id: UUID = Field(description="Parent document ID.")
    text: str = Field(description="Chunk text content.")
    page_number: int = Field(ge=1, description="Source page number (1-indexed).")
    chunk_index: int = Field(ge=0, description="Chunk ordinal within the page.")
    filename: str = Field(description="Original source filename.")
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# API request / response schemas
# ---------------------------------------------------------------------------


class DocumentUploadResponse(BaseModel):
    """Response returned after a successful document upload."""

    document_id: UUID
    filename: str
    page_count: int
    total_chunks: int
    message: str = "Document ingested successfully."


class DocumentSummary(BaseModel):
    """Lightweight document summary for list endpoints."""

    id: UUID
    filename: str
    page_count: int
    total_chunks: int
    uploaded_at: datetime


class DocumentListResponse(BaseModel):
    """Response wrapping a list of ingested documents."""

    documents: list[DocumentSummary]
    total: int


class ChunkListResponse(BaseModel):
    """Response wrapping a list of chunks for a document."""

    document_id: UUID
    filename: str
    chunks: list[Chunk]
    total: int


class SearchQuery(BaseModel):
    """Payload for semantic search over ingested chunks."""

    query: str = Field(description="Natural-language search query.", min_length=1)
    top_k: int = Field(default=5, ge=1, le=100, description="Number of results to return.")


class SearchResultItem(BaseModel):
    """A single search result with chunk metadata."""

    chunk_id: str
    document_id: str
    text: str
    filename: str
    page_number: int
    chunk_index: int
    score: float


class SearchResponse(BaseModel):
    """Response wrapping semantic search results."""

    query: str
    results: list[SearchResultItem]
    total: int


__all__ = [
    "Chunk",
    "ChunkListResponse",
    "Document",
    "DocumentListResponse",
    "DocumentSummary",
    "DocumentUploadResponse",
    "SearchQuery",
    "SearchResultItem",
    "SearchResponse",
]
