"""Retrieval-Augmented Generation (RAG) knowledge layer.

Phase 1 — Document Ingestion
=============================
- Load PDFs with PyMuPDF (fitz).
- Parse and normalise text.
- Split into configurable chunks with overlap.
- Store in memory (no vector database yet).

Phase 2 — Embeddings + Vector Store
====================================
- Generate embeddings via Google's text-embedding model (mock fallback).
- Store in ChromaDB (or in-memory fallback for testing).
- Semantic retrieval via cosine similarity.

Modules
-------
- ``loader.py`` — PDF loading and raw text extraction.
- ``parser.py`` — Text normalisation and cleaning.
- ``chunker.py`` — Configurable chunk splitting.
- ``schemas.py`` — Pydantic models for documents, chunks, and API responses.
- ``repository.py`` — In-memory document/chunk storage.
- ``service.py`` — Orchestration pipeline (load -> parse -> chunk -> store -> index).
- ``embeddings.py`` — Embedding provider (Google GenAI or mock).
- ``vector_store.py`` — ChromaDB-backed vector store (in-memory fallback).
- ``retriever.py`` — Semantic retriever for similarity search.
"""

from app.rag.chunker import ChunkingConfig, TextChunker
from app.rag.embeddings import DEFAULT_EMBEDDING_MODEL, EMBEDDING_DIMENSIONS, EmbeddingProvider
from app.rag.loader import PdfDocument, PdfLoader, PdfLoadError, PdfPage
from app.rag.parser import ParsedDocument, ParsedPage, TextParser
from app.rag.repository import InMemoryDocumentRepository
from app.rag.retriever import SemanticRetriever
from app.rag.schemas import (
    Chunk,
    ChunkListResponse,
    Citation,
    Document,
    DocumentListResponse,
    DocumentSummary,
    DocumentUploadResponse,
    SearchQuery,
    SearchResponse,
    SearchResultItem,
)
from app.rag.service import RagService
from app.rag.vector_store import (
    DEFAULT_COLLECTION,
    ChromaVectorStore,
    InMemoryVectorStore,
    SearchResult,
    VectorStoreError,
)

__all__ = [
    "ChromaVectorStore",
    "Chunk",
    "ChunkingConfig",
    "ChunkListResponse",
    "Citation",
    "DEFAULT_COLLECTION",
    "DEFAULT_EMBEDDING_MODEL",
    "Document",
    "DocumentListResponse",
    "DocumentSummary",
    "DocumentUploadResponse",
    "EMBEDDING_DIMENSIONS",
    "EmbeddingProvider",
    "InMemoryDocumentRepository",
    "InMemoryVectorStore",
    "ParsedDocument",
    "ParsedPage",
    "PdfDocument",
    "PdfLoadError",
    "PdfLoader",
    "PdfPage",
    "RagService",
    "SearchQuery",
    "SearchResponse",
    "SearchResult",
    "SearchResultItem",
    "SemanticRetriever",
    "TextChunker",
    "TextParser",
    "VectorStoreError",
]
