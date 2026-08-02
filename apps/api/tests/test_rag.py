"""Unit tests for the RAG document ingestion layer.

Tests cover the loader, parser, chunker, repository, service, and the
HTTP endpoints. No network access is used.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.rag.chunker import ChunkingConfig, TextChunker
from app.rag.loader import PdfLoader, PdfLoadError
from app.rag.parser import TextParser
from app.rag.repository import InMemoryDocumentRepository
from app.rag.schemas import Chunk, Document, DocumentUploadResponse
from app.rag.service import RagService

ADMIN_EMAIL = "admin@sentrix.io"
ADMIN_PASSWORD = "ChangeMe_123!"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a TestClient with the lifespan executed."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def admin_token(client: TestClient) -> str:
    """Log in as the seeded admin."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


def _auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Minimal valid PDF (a single blank page)
# ---------------------------------------------------------------------------

# This is a minimal valid PDF that PyMuPDF can open. It contains one blank
# page with the text "Hello World".
MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n"
    b"0 4\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"trailer<</Size 4/Root 1 0 R>>\n"
    b"startxref\n"
    b"190\n"
    b"%%EOF"
)

MULTI_PAGE_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R 4 0 R]/Count 2>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"4 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\n"
    b"xref\n"
    b"0 5\n"
    b"0000000000 65535 f \n"
    b"0000000009 00000 n \n"
    b"0000000058 00000 n \n"
    b"0000000115 00000 n \n"
    b"0000000172 00000 n \n"
    b"trailer<</Size 5/Root 1 0 R>>\n"
    b"startxref\n"
    b"229\n"
    b"%%EOF"
)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------


class TestPdfLoader:
    def test_loads_minimal_pdf(self) -> None:
        loader = PdfLoader()
        doc = loader.load(MINIMAL_PDF, filename="test.pdf")
        assert doc.filename == "test.pdf"
        assert doc.page_count == 1
        assert len(doc.pages) == 1

    def test_loads_multi_page_pdf(self) -> None:
        loader = PdfLoader()
        doc = loader.load(MULTI_PAGE_PDF, filename="multi.pdf")
        assert doc.page_count == 2
        assert len(doc.pages) == 2
        assert doc.pages[0].page_number == 1
        assert doc.pages[1].page_number == 2

    def test_raises_on_invalid_content(self) -> None:
        loader = PdfLoader()
        with pytest.raises(PdfLoadError):
            loader.load(b"not a pdf", filename="bad.pdf")

    def test_raises_on_empty_content(self) -> None:
        loader = PdfLoader()
        with pytest.raises(PdfLoadError):
            loader.load(b"", filename="empty.pdf")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


class TestTextParser:
    def test_parser_preserves_text(self) -> None:
        from app.rag.loader import PdfPage

        parser = TextParser()
        raw_pages = (PdfPage(text="Hello world", page_number=1),)
        parsed = parser.parse(raw_pages, filename="test.pdf")
        assert parsed.page_count == 1
        assert parsed.pages[0].text == "Hello world"
        assert parsed.pages[0].page_number == 1

    def test_parser_normalises_whitespace(self) -> None:
        from app.rag.loader import PdfPage

        parser = TextParser()
        raw_pages = (
            PdfPage(text="  Line1\n\n\n\nLine2  ", page_number=1),
        )
        parsed = parser.parse(raw_pages, filename="test.pdf")
        # Excessive blank lines should be collapsed.
        assert "\n\n\n" not in parsed.pages[0].text


# ---------------------------------------------------------------------------
# Chunker
# ---------------------------------------------------------------------------


class TestTextChunker:
    def test_chunks_single_page(self) -> None:
        from app.rag.loader import PdfPage
        from app.rag.parser import TextParser

        parser = TextParser()
        raw = (PdfPage(text="A " * 2000, page_number=1),)
        parsed = parser.parse(raw, filename="test.pdf")
        chunker = TextChunker()
        config = ChunkingConfig(chunk_size=500, chunk_overlap=50, min_chunk_length=20)
        chunks = chunker.chunk(parsed, config=config)
        assert len(chunks) >= 1
        for c in chunks:
            assert c.page_number == 1
            assert c.filename == "test.pdf"

    def test_chunks_preserve_metadata(self) -> None:
        from app.rag.loader import PdfPage
        from app.rag.parser import TextParser

        parser = TextParser()
        raw = (PdfPage(text="Hello world", page_number=1),)
        parsed = parser.parse(raw, filename="report.pdf")
        chunker = TextChunker()
        doc_id = uuid.uuid4()
        chunks = chunker.chunk(parsed, document_id=doc_id)
        assert len(chunks) == 1
        assert chunks[0].document_id == doc_id
        assert chunks[0].filename == "report.pdf"
        assert chunks[0].page_number == 1
        assert chunks[0].chunk_index == 0

    def test_chunks_respect_page_boundaries(self) -> None:
        from app.rag.loader import PdfPage
        from app.rag.parser import TextParser

        parser = TextParser()
        raw = (
            PdfPage(text="Page 1 text " * 500, page_number=1),
            PdfPage(text="Page 2 text " * 500, page_number=2),
        )
        parsed = parser.parse(raw, filename="multi.pdf")
        chunker = TextChunker()
        config = ChunkingConfig(chunk_size=200, chunk_overlap=20, min_chunk_length=10)
        chunks = chunker.chunk(parsed, config=config)
        # All chunks from page 1 should come before page 2 chunks.
        page_numbers = [c.page_number for c in chunks]
        transitions = sum(
            1 for i in range(1, len(page_numbers)) if page_numbers[i] != page_numbers[i - 1]
        )
        # There should be at most one transition (page 1 -> page 2).
        assert transitions <= 1


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class TestInMemoryDocumentRepository:
    async def test_create_and_retrieve_document(self) -> None:
        repo = InMemoryDocumentRepository()
        doc = Document(
            id=uuid.uuid4(),
            filename="test.pdf",
            page_count=1,
        )
        stored = await repo.create_document(doc)
        assert stored.id == doc.id
        assert stored.filename == "test.pdf"

        retrieved = await repo.get_document(doc.id)
        assert retrieved is not None
        assert retrieved.filename == "test.pdf"

    async def test_save_and_retrieve_chunks(self) -> None:
        repo = InMemoryDocumentRepository()
        doc_id = uuid.uuid4()
        doc = Document(id=doc_id, filename="test.pdf", page_count=1)
        await repo.create_document(doc)

        chunks = [
            Chunk(
                id=uuid.uuid4(),
                document_id=doc_id,
                text="Chunk 1",
                page_number=1,
                chunk_index=0,
                filename="test.pdf",
            ),
            Chunk(
                id=uuid.uuid4(),
                document_id=doc_id,
                text="Chunk 2",
                page_number=1,
                chunk_index=1,
                filename="test.pdf",
            ),
        ]
        count = await repo.save_chunks(doc_id, chunks)
        assert count == 2

        retrieved = await repo.get_chunks(doc_id)
        assert len(retrieved) == 2
        assert retrieved[0].text == "Chunk 1"
        assert retrieved[1].text == "Chunk 2"

    async def test_list_documents(self) -> None:
        repo = InMemoryDocumentRepository()
        doc1 = Document(id=uuid.uuid4(), filename="a.pdf", page_count=1)
        doc2 = Document(id=uuid.uuid4(), filename="b.pdf", page_count=2)
        await repo.create_document(doc1)
        await repo.create_document(doc2)

        docs = await repo.list_documents()
        assert len(docs) == 2

    async def test_delete_document(self) -> None:
        repo = InMemoryDocumentRepository()
        doc_id = uuid.uuid4()
        doc = Document(id=doc_id, filename="test.pdf", page_count=1)
        await repo.create_document(doc)

        deleted = await repo.delete_document(doc_id)
        assert deleted is True

        retrieved = await repo.get_document(doc_id)
        assert retrieved is None


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class TestRagService:
    async def test_ingest_pdf(self) -> None:
        repo = InMemoryDocumentRepository()
        svc = RagService(repository=repo)
        result = await svc.ingest_pdf(MINIMAL_PDF, filename="test.pdf")
        assert isinstance(result, DocumentUploadResponse)
        assert result.filename == "test.pdf"
        assert result.page_count == 1
        assert result.total_chunks >= 1

    async def test_list_documents(self) -> None:
        repo = InMemoryDocumentRepository()
        svc = RagService(repository=repo)
        await svc.ingest_pdf(MINIMAL_PDF, filename="a.pdf")
        await svc.ingest_pdf(MULTI_PAGE_PDF, filename="b.pdf")

        result = await svc.list_documents()
        assert result.total == 2
        assert len(result.documents) == 2

    async def test_ingest_pdf_updates_chunk_count(self) -> None:
        repo = InMemoryDocumentRepository()
        svc = RagService(repository=repo)
        result = await svc.ingest_pdf(MINIMAL_PDF, filename="test.pdf")
        doc = await repo.get_document(result.document_id)
        assert doc is not None
        assert doc.total_chunks == result.total_chunks


# ---------------------------------------------------------------------------
# HTTP endpoint
# ---------------------------------------------------------------------------


class TestRagEndpoints:
    def test_upload_rejects_non_pdf(self, client: TestClient, admin_token: str) -> None:
        headers = _auth_headers(admin_token)
        response = client.post(
            "/api/v1/rag/upload",
            files={"file": ("test.txt", b"hello world", "text/plain")},
            headers=headers,
        )
        assert response.status_code == 415

    def test_upload_requires_auth(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/rag/upload",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
        )
        assert response.status_code == 401

    def test_list_documents_requires_auth(self, client: TestClient) -> None:
        response = client.get("/api/v1/rag/documents")
        assert response.status_code == 401

    def test_upload_and_list_documents(
        self, client: TestClient, admin_token: str
    ) -> None:
        headers = _auth_headers(admin_token)
        upload = client.post(
            "/api/v1/rag/upload",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
            headers=headers,
        )
        assert upload.status_code == 201
        body = upload.json()
        assert body["filename"] == "test.pdf"
        assert body["page_count"] == 1
        assert body["total_chunks"] >= 1

        # List documents.
        listing = client.get(
            "/api/v1/rag/documents",
            headers=headers,
        )
        assert listing.status_code == 200
        list_body = listing.json()
        assert list_body["total"] >= 1
        filenames = [d["filename"] for d in list_body["documents"]]
        assert "test.pdf" in filenames

    def test_search_requires_auth(self, client: TestClient) -> None:
        response = client.post(
            "/api/v1/rag/search",
            json={"query": "test query", "top_k": 5},
        )
        assert response.status_code == 401

    def test_search_returns_results(
        self, client: TestClient, admin_token: str
    ) -> None:
        headers = _auth_headers(admin_token)
        # Upload a document first so there's something to search.
        upload = client.post(
            "/api/v1/rag/upload",
            files={"file": ("test.pdf", MINIMAL_PDF, "application/pdf")},
            headers=headers,
        )
        assert upload.status_code == 201

        # Perform search.
        response = client.post(
            "/api/v1/rag/search",
            json={"query": "test", "top_k": 5},
            headers=headers,
        )
        assert response.status_code == 200
        body = response.json()
        assert body["query"] == "test"
        assert isinstance(body["results"], list)
        assert isinstance(body["total"], int)
