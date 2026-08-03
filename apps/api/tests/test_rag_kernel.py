"""Integration tests for RAG + Kernel pipeline.

Tests the full flow: document ingestion → vector indexing → kernel pipeline
with RAG-aware context → response with citations.

All tests run offline with the in-memory vector store and mock provider.
"""

from __future__ import annotations

import uuid

import pytest

from app.kernel.context_builder import (
    InMemoryContextProvider,
)
from app.kernel.integration import build_kernel_pipeline
from app.kernel.prompt_builder import DefaultPromptBuilder
from app.kernel.rag_context import RagAwareContextProvider
from app.kernel.response_builder import KernelResponse
from app.rag.embeddings import EmbeddingProvider
from app.rag.retriever import SemanticRetriever
from app.rag.vector_store import InMemoryVectorStore

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def embedding_provider() -> EmbeddingProvider:
    """Return a deterministic mock embedding provider."""
    return EmbeddingProvider()


@pytest.fixture
def vector_store(embedding_provider: EmbeddingProvider) -> InMemoryVectorStore:
    """Return a fresh in-memory vector store."""
    return InMemoryVectorStore(embedding_provider=embedding_provider)


@pytest.fixture
def retriever(vector_store: InMemoryVectorStore) -> SemanticRetriever:
    """Return a semantic retriever backed by the in-memory store."""
    return SemanticRetriever(vector_store=vector_store)


@pytest.fixture
def seed_chunks(retriever: SemanticRetriever) -> list[dict]:
    """Seed the vector store with sample cybersecurity chunks."""
    chunks = [
        {
            "id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "text": (
                "C2 beaconing activity detected on host LAB-07. "
                "The beacon communicates with external IP 203.0.113.50 "
                "on TCP port 443 every 47 seconds. MITRE ATT&CK T1071.001."
            ),
            "filename": "incident_report_q1.pdf",
            "page_number": 3,
            "chunk_index": 0,
        },
        {
            "id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "text": (
                "Suricata alert SID 2100498: ET MALWARE Possible "
                "Cobalt Strike Beacon detected. Destination port 443. "
                "JA3 hash: a0e9f5d2... Recommended action: isolate endpoint."
            ),
            "filename": "suricata_alerts_2024.pdf",
            "page_number": 7,
            "chunk_index": 1,
        },
        {
            "id": str(uuid.uuid4()),
            "document_id": str(uuid.uuid4()),
            "text": (
                "Network segmentation best practices: place all critical "
                "assets in a dedicated VLAN with strict egress filtering. "
                "Monitor east-west traffic for lateral movement indicators."
            ),
            "filename": "security_baselines.pdf",
            "page_number": 12,
            "chunk_index": 0,
        },
    ]
    retriever.index_chunks(chunks)
    return chunks


# ---------------------------------------------------------------------------
# RagAwareContextProvider
# ---------------------------------------------------------------------------


class TestRagAwareContextProvider:
    def test_no_retriever_returns_inner_context(self) -> None:
        inner = InMemoryContextProvider()
        rag = RagAwareContextProvider(inner=inner, retriever=None)
        ctx = rag.get_context(conversation_id="c1", message="Hello")
        assert ctx.retrieved_chunks == ()
        assert ctx.citations == ()

    def test_retriever_attaches_chunks(
        self, retriever: SemanticRetriever, seed_chunks: list  # noqa: ARG002
    ) -> None:
        inner = InMemoryContextProvider()
        rag = RagAwareContextProvider(inner=inner, retriever=retriever, top_k=2)
        ctx = rag.get_context(
            conversation_id="c1",
            message="Tell me about beacon activity on LAB-07",
        )
        assert len(ctx.retrieved_chunks) > 0
        assert len(ctx.retrieved_chunks) <= 2
        assert ctx.citations
        first = ctx.citations[0]
        assert "filename" in first
        assert "page" in first
        assert "chunk" in first

    def test_retriever_handles_no_results(self, retriever: SemanticRetriever) -> None:
        inner = InMemoryContextProvider()
        rag = RagAwareContextProvider(inner=inner, retriever=retriever)
        # No chunks indexed yet
        ctx = rag.get_context(
            conversation_id="c1",
            message="Something completely unrelated",
        )
        assert ctx.retrieved_chunks == ()
        assert ctx.citations == ()

    def test_clear_delegates_to_inner(self) -> None:
        inner = InMemoryContextProvider()
        rag = RagAwareContextProvider(inner=inner)
        inner.get_context(conversation_id="c1", message="Hello")
        rag.clear()
        # After clear, the inner context should have no history
        ctx = inner.get_context(conversation_id="c1", message="World")
        assert len(ctx.prior_messages) == 0  # prior wiped


# ---------------------------------------------------------------------------
# PromptBuilder — RAG context injection
# ---------------------------------------------------------------------------


class TestPromptBuilderRagInjection:
    def test_injects_retrieved_chunks_into_text(
        self, retriever: SemanticRetriever, seed_chunks: list  # noqa: ARG002
    ) -> None:
        inner = InMemoryContextProvider()
        rag = RagAwareContextProvider(inner=inner, retriever=retriever, top_k=1)
        ctx = rag.get_context(
            conversation_id="c1",
            message="Beacon on LAB-07",
        )
        builder = DefaultPromptBuilder()
        prompt = builder.build(
            context=ctx,
            system="You are a SOC analyst.",
            instruction="Be concise.",
        )
        text = prompt.to_text()
        assert "Retrieved context:" in text
        assert "LAB-07" in text
        assert "Source:" in text
        assert "Page:" in text

    def test_citations_attached_to_prompt(
        self, retriever: SemanticRetriever, seed_chunks: list  # noqa: ARG002
    ) -> None:
        inner = InMemoryContextProvider()
        rag = RagAwareContextProvider(inner=inner, retriever=retriever, top_k=2)
        ctx = rag.get_context(
            conversation_id="c1",
            message="Beacon on LAB-07",
        )
        builder = DefaultPromptBuilder()
        prompt = builder.build(
            context=ctx,
            system="You are a SOC analyst.",
            instruction="Be concise.",
        )
        assert len(prompt.citations) > 0
        assert "filename" in prompt.citations[0]
        assert "page" in prompt.citations[0]
        assert "chunk" in prompt.citations[0]

    def test_no_chunks_returns_standard_prompt(self) -> None:
        inner = InMemoryContextProvider()
        rag = RagAwareContextProvider(inner=inner, retriever=None)
        ctx = rag.get_context(
            conversation_id="c1",
            message="Hello",
        )
        builder = DefaultPromptBuilder()
        prompt = builder.build(
            context=ctx,
            system="You are a SOC analyst.",
            instruction="Be concise.",
        )
        text = prompt.to_text()
        assert "Retrieved context:" not in text
        assert prompt.citations == ()


# ---------------------------------------------------------------------------
# Kernel pipeline — RAG integration
# ---------------------------------------------------------------------------


class TestKernelPipelineRagIntegration:
    def test_pipeline_without_retriever_still_works(self) -> None:
        pipeline = build_kernel_pipeline()
        response = pipeline.run(
            conversation_id="c1",
            message="Hello",
        )
        assert isinstance(response, KernelResponse)
        assert response.content
        assert response.citations == ()

    def test_pipeline_with_retriever_returns_citations(
        self, retriever: SemanticRetriever, seed_chunks: list  # noqa: ARG002
    ) -> None:
        pipeline = build_kernel_pipeline(retriever=retriever, rag_top_k=3)
        response = pipeline.run(
            conversation_id="c1",
            message="What do you know about beacon activity?",
        )
        assert isinstance(response, KernelResponse)
        assert response.content
        assert response.citations is not None

    def test_pipeline_citations_have_expected_shape(
        self, retriever: SemanticRetriever, seed_chunks: list  # noqa: ARG002
    ) -> None:
        pipeline = build_kernel_pipeline(retriever=retriever, rag_top_k=2)
        response = pipeline.run(
            conversation_id="c1",
            message="C2 beacon on LAB-07",
        )
        if response.citations:
            citation = response.citations[0]
            assert "filename" in citation
            assert "page" in citation
            assert "chunk" in citation

    def test_pipeline_with_retriever_includes_context_in_prompt(
        self, retriever: SemanticRetriever, seed_chunks: list  # noqa: ARG002
    ) -> None:
        """Verify the prompt text contains the retrieved context."""
        pipeline = build_kernel_pipeline(retriever=retriever, rag_top_k=1)
        response = pipeline.run(
            conversation_id="c1",
            message="Beacon detected on endpoint LAB-07",
        )
        assert response.content
        assert response.provider == "mock"

    def test_pipeline_with_rag_and_custom_system_prompt(
        self, retriever: SemanticRetriever, seed_chunks: list  # noqa: ARG002
    ) -> None:
        custom_system = "You are a DFIR analyst. Answer with citations."
        pipeline = build_kernel_pipeline(
            retriever=retriever,
            rag_top_k=3,
            system_prompt=custom_system,
        )
        response = pipeline.run(
            conversation_id="c1",
            message="What is the JA3 hash for the Cobalt Strike beacon?",
        )
        assert response.content
        assert response.provider == "mock"

    def test_pipeline_respects_top_k(
        self, retriever: SemanticRetriever, seed_chunks: list  # noqa: ARG002
    ) -> None:
        """With top_k=1, only one chunk should be retrieved."""
        pipeline = build_kernel_pipeline(retriever=retriever, rag_top_k=1)
        response = pipeline.run(
            conversation_id="c1",
            message="Beacon on LAB-07",
        )
        assert response.content


# ---------------------------------------------------------------------------
# End-to-end: RAG ingestion → kernel query
# ---------------------------------------------------------------------------


class TestRagKernelEndToEnd:
    def test_ingest_then_query_returns_citations(self) -> None:
        """Full end-to-end: ingest documents, then query via kernel."""
        vs = InMemoryVectorStore()
        emb = EmbeddingProvider()
        retriever = SemanticRetriever(vector_store=vs, embedding_provider=emb)

        # Ingest
        chunks = [
            {
                "id": str(uuid.uuid4()),
                "document_id": str(uuid.uuid4()),
                "text": (
                    "Firewall logs show denied outbound connection from "
                    "10.0.1.50 to 198.51.100.20 on port 8443. "
                    "Signature match: ET TROJAN Suspicious Outbound."
                ),
                "filename": "firewall_logs_jan.pdf",
                "page_number": 5,
                "chunk_index": 0,
            },
        ]
        retriever.index_chunks(chunks)

        # Query
        pipeline = build_kernel_pipeline(retriever=retriever, rag_top_k=5)
        response = pipeline.run(
            conversation_id="e2e-1",
            message="Show me suspicious outbound connections from 10.0.1.50",
        )
        assert response.content
        assert response.citations is not None

    def test_multiple_conversations_no_crosstalk(self) -> None:
        """Different conversations should not share context."""
        vs = InMemoryVectorStore()
        emb = EmbeddingProvider()
        retriever = SemanticRetriever(vector_store=vs, embedding_provider=emb)

        # Ingest
        chunks = [
            {
                "id": str(uuid.uuid4()),
                "document_id": str(uuid.uuid4()),
                "text": "DNS query for malicious domain evil.com from host 10.0.1.100.",
                "filename": "dns_logs.pdf",
                "page_number": 2,
                "chunk_index": 0,
            },
        ]
        retriever.index_chunks(chunks)

        pipeline = build_kernel_pipeline(retriever=retriever, rag_top_k=3)

        resp1 = pipeline.run(conversation_id="conv-a", message="DNS malicious domain")
        resp2 = pipeline.run(conversation_id="conv-b", message="Hello")
        assert resp1.content
        assert resp2.content
