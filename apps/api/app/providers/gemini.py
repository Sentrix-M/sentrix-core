"""Google Gemini provider for the Sentrix AI Provider Layer.

``GeminiProvider`` implements :class:`~app.providers.base.BaseProvider` using
the official ``google-genai`` SDK. It reads its configuration (API key, model,
provider name) from the application :class:`~app.config.settings.Settings`
object, so credentials never appear in code.

The provider normalizes Gemini responses into the Sentrix
:class:`~app.kernel.response_builder.ProviderOutput` contract — the same
contract used by the offline :class:`~app.providers.mock.MockProvider` — so
the kernel, conversation API, and streaming contracts are unaffected.

Failure handling
----------------
If the API key is missing, empty, or rejected by the SDK, the provider
surfaces a typed :class:`GeminiError`. The factory catches this and falls
back to the deterministic :class:`MockProvider`, which keeps the platform
fully functional without credentials.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.kernel.prompt_builder import Prompt
from app.kernel.response_builder import ProviderOutput
from app.providers.base import BaseProvider, ProviderHealth

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from google.genai import Client


class GeminiError(Exception):
    """Raised when the Gemini configuration or API call is invalid."""


class GeminiNotConfiguredError(GeminiError):
    """Raised when no usable ``GEMINI_API_KEY`` is configured."""


def _extract_text_from_response(response: object) -> str:
    """Best-effort extraction of plain text from a Gemini response.

    The SDK exposes a convenience ``text`` property on
    ``GenerateContentResponse``; we also fall back to scanning candidate
    ``parts`` so the adapter keeps working across minor SDK revisions.
    """
    # 1. Preferred: the SDK's convenience property.
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text

    # 2. Fallback: scan response.parts[*].text.
    parts = getattr(response, "parts", None)
    if parts is not None:
        chunks: list[str] = []
        for part in parts:
            part_text = getattr(part, "text", None)
            if isinstance(part_text, str):
                chunks.append(part_text)
        if chunks:
            return "".join(chunks)

    return ""


def _build_content_parts(prompt: Prompt) -> list[dict[str, str]]:
    """Convert a :class:`Prompt` into Gemini ``contents`` parts.

    The pipeline's ``Prompt`` already holds ``system``, ``messages``, and
    ``instruction``; we flatten the user/history turns into the natural
    chat-style ordering Gemini expects.
    """
    parts: list[dict[str, str]] = []
    if prompt.system:
        parts.append({"role": "system", "text": prompt.system})
    for message in prompt.messages:
        parts.append({"role": message.role, "text": message.content})
    if prompt.instruction:
        parts.append({"role": "user", "text": f"Instruction: {prompt.instruction}"})
    return parts


class GeminiProvider(BaseProvider):  # type: ignore[misc]
    """Google Gemini provider adapter.

    :param api_key: Google API key for Gemini. Defaults to the value from
        :class:`Settings.gemini_api_key`.
    :param model: Gemini model name. Defaults to
        :attr:`Settings.gemini_model`.
    :param client_factory: Optional callable returning a configured
        ``google.genai.Client``. Provided for tests; when omitted, the SDK's
        :func:`Client` is constructed with ``api_key``.
    """

    name = "gemini"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str | None = None,
        client_factory=None,
    ) -> None:
        from app.config.settings import get_settings

        cfg = get_settings()
        self.api_key = api_key if api_key is not None else cfg.gemini_api_key
        self.model = model or cfg.gemini_model
        self._client = None
        self._client_factory = client_factory
        if not self.api_key.strip():
            raise GeminiNotConfiguredError(
                "GEMINI_API_KEY is not set. Falling back to the mock provider."
            )

    # -- internal plumbing -------------------------------------------------

    @property
    def client(self) -> Client:
        """Lazily construct and cache the Google Gen AI client."""
        if self._client is None:
            from google.genai import Client

            if self._client_factory is not None:
                self._client = self._client_factory()
            else:
                self._client = Client(api_key=self.api_key)
        return self._client

    # -- BaseProvider contract --------------------------------------------

    def generate(self, prompt: Prompt) -> ProviderOutput:
        """Generate a completion for ``prompt`` via the Gemini API."""
        parts = _build_content_parts(prompt)
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=parts,
            )
        except GeminiNotConfiguredError:
            raise
        except Exception as exc:  # noqa: BLE001 - normalize SDK/network errors
            logger.exception("Gemini generate_content failed.")
            raise GeminiError(f"Gemini generation failed: {exc}") from exc

        text = _extract_text_from_response(response)
        if not text.strip():
            raise GeminiError("Gemini returned an empty response.")

        return ProviderOutput(
            text=text,
            model=self.model,
            metadata={
                "provider": "gemini",
                "model": self.model,
                "mode": "cloud",
            },
        )

    def stream(self, prompt: Prompt) -> list[str]:
        """Return the response as a list of word-level chunks.

        Cumulates the streamed chunks, normalizes whitespace, and splits into
        words so the SSE layer (``streaming/manager.py``) can replay them
        token by token — no streaming contract changes required.
        """
        parts = _build_content_parts(prompt)
        try:
            stream = self.client.models.generate_content_stream(
                model=self.model,
                contents=parts,
            )
        except Exception as exc:  # noqa: BLE001 - normalize SDK/network errors
            logger.exception("Gemini generate_content_stream failed.")
            raise GeminiError(f"Gemini streaming failed: {exc}") from exc

        chunks: list[str] = []
        for item in stream:
            fragment = _extract_text_from_response(item)
            if fragment:
                chunks.append(fragment)
        text = " ".join("".join(chunks).split())
        if not text:
            raise GeminiError("Gemini stream returned no content.")
        return text.split(" ")

    def health(self) -> ProviderHealth:
        """Report availability without expensive model calls.

        The health check verifies the configuration (API key present) and
        that the SDK client can be constructed; a real network round-trip is
        avoided so health probes stay fast and are safe to call on a schedule.
        """
        if not self.api_key.strip():
            return ProviderHealth(
                ok=False,
                message="GEMINI_API_KEY is not configured.",
            )
        try:
            # Touch the client property; construction can raise if the key is
            # empty or malformed.
            _ = self.client
        except Exception as exc:  # noqa: BLE001
            return ProviderHealth(ok=False, message=f"Gemini client error: {exc}")
        return ProviderHealth(
            ok=True,
            message=f"Gemini provider is configured (model={self.model}).",
        )


__all__ = ["GeminiError", "GeminiNotConfiguredError", "GeminiProvider"]

