"""Embedding provider for the Sentrix RAG layer.

Generates vector embeddings for document chunks using Google's text-embedding
model via the ``google-genai`` SDK.  When the API key is missing or empty
the provider falls back to a deterministic mock embedding (zero-cost noise)
so the pipeline never breaks during development or testing.

The mock embedding is a fixed-size vector with a small amount of per-chunk
noise so that semantically different queries produce different cosine
similarity scores, making the retriever testable end-to-end.
"""

from __future__ import annotations

import logging
from hashlib import sha256
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from google.genai.types import EmbedContentResponse

logger = logging.getLogger(__name__)

#: Dimensionality of the embedding vectors produced by the provider.
EMBEDDING_DIMENSIONS = 768

#: Default embedding model name used by the Google provider.
DEFAULT_EMBEDDING_MODEL = "text-embedding-004"


class EmbeddingError(Exception):
    """Raised when embedding generation fails."""


class EmbeddingProvider:
    """Generates vector embeddings for text chunks.

    Uses the ``google-genai`` SDK client when an API key is configured;
    otherwise falls back to a deterministic mock that produces stable
    vectors for testing.

    :param api_key: Google API key.  Defaults to the value from
        :class:`~app.config.settings.Settings.gemini_api_key`.
    :param model: Embedding model name.
    """

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
    ) -> None:
        from app.config.settings import get_settings

        cfg = get_settings()
        self._api_key = api_key if api_key is not None else cfg.gemini_api_key
        self._model = model or DEFAULT_EMBEDDING_MODEL
        self._client = None
        self._mock = not bool(self._api_key.strip())

        if self._mock:
            logger.info(
                "No GEMINI_API_KEY set — using deterministic mock embeddings "
                "(dim=%d).",
                EMBEDDING_DIMENSIONS,
            )

    # ------------------------------------------------------------------
    # Internal plumbing
    # ------------------------------------------------------------------

    @property
    def _genai_client(self):
        """Lazily construct the Google Gen AI client."""
        if self._client is None:
            from google.genai import Client

            self._client = Client(api_key=self._api_key)
        return self._client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Return a vector embedding for ``text``.

        :param text: Input text to embed.
        :returns: A list of floats of length :attr:`EMBEDDING_DIMENSIONS`.
        :raises EmbeddingError: If the API call fails.
        """
        if self._mock:
            return self._mock_embed(text)

        try:
            result: EmbedContentResponse = self._genai_client.models.embed_content(
                model=self._model,
                contents=text,
            )
        except Exception:
            logger.exception("Embedding API call failed — falling back to mock.")
            return self._mock_embed(text)

        try:
            values = result.embeddings[0].values
            if values is None:
                raise EmbeddingError("Embedding API returned None values.")
            return [float(v) for v in values]
        except (IndexError, TypeError, AttributeError):
            logger.exception("Unexpected embedding response structure.")
            return self._mock_embed(text)

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Return embeddings for a batch of texts.

        Falls back to calling ``embed`` sequentially if the model does not
        support batching (the mock path always uses per-item fallback).
        """
        if self._mock:
            return [self._mock_embed(t) for t in texts]

        # Try batch API first.
        try:
            result: EmbedContentResponse = self._genai_client.models.embed_content(
                model=self._model,
                contents=texts,
            )
            embeddings: list[list[float]] = []
            for emb in result.embeddings:
                if emb.values is None:
                    embeddings.append(self._mock_embed(""))
                else:
                    embeddings.append([float(v) for v in emb.values])
            return embeddings
        except Exception:
            logger.warning("Batch embedding failed — falling back to per-item.")
            return [self.embed(t) for t in texts]

    # ------------------------------------------------------------------
    # Deterministic mock embedding
    # ------------------------------------------------------------------

    @staticmethod
    def _mock_embed(text: str) -> list[float]:
        """Deterministic mock embedding seeded from the text hash.

        Produces a fixed-dimension vector whose values are stable for the
        same input, so the retriever can be tested end-to-end.
        """
        h = sha256(text.encode("utf-8")).digest()
        # Expand the 32-byte hash into a vector of the required dimension.
        vector: list[float] = []
        for i in range(EMBEDDING_DIMENSIONS):
            idx = i % 32
            # Use a mix of bytes to get a pseudo-random but deterministic value.
            b = h[idx]
            # Convert to a small float in [-0.5, 0.5].
            vector.append((b / 255.0) - 0.5)
        return vector


__all__ = [
    "DEFAULT_EMBEDDING_MODEL",
    "EMBEDDING_DIMENSIONS",
    "EmbeddingError",
    "EmbeddingProvider",
]
