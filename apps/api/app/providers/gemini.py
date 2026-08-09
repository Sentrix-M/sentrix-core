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


def _build_content_parts(prompt: Prompt) -> list[dict[str, object]]:
    """Convert a :class:`Prompt` into Gemini ``contents`` entries.

    The google-genai SDK (v2.x) expects ``contents`` to be a list of
    ``Content`` dicts shaped ``{"role": "user"|"model", "parts": [{"text": ...}]}``.
    The pipeline's ``Prompt`` already holds ``system``, ``messages``, and
    ``instruction``:

    - ``prompt.system`` is delivered via ``config.system_instruction`` (the
      Gemini API does not accept a ``system`` role inside ``contents``).
    - ``prompt.messages`` (the current user turn plus any prior turns) are
      flattened into chat-style ``Content`` entries. Any assistant/model
      history is mapped to the ``"model"`` role.
    - ``prompt.instruction`` is appended to the final user message so the
      per-turn instruction is preserved in the request.
    """
    entries: list[dict[str, object]] = []
    last_user_index = -1
    for message in prompt.messages:
        raw_role = (message.role or "").lower()
        role = "model" if raw_role in ("model", "assistant") else "user"
        entries.append({"role": role, "parts": [{"text": message.content}]})
        if role == "user":
            last_user_index = len(entries) - 1

    if prompt.instruction:
        text = f"Instruction: {prompt.instruction}"
        if last_user_index >= 0:
            parts = entries[last_user_index]["parts"]
            assert isinstance(parts, list) and parts
            first = parts[0]
            assert isinstance(first, dict)
            first["text"] = f"{first['text']}\n{text}"
        else:
            entries.append({"role": "user", "parts": [{"text": text}]})

    # Inject live tool results (e.g. VirusTotal/Shodan findings) into the
    # final user message so the provider can base its answer on the actual
    # tool output rather than generic knowledge. Mirrors Prompt.to_text().
    if prompt.tool_results:
        tool_lines = ["Tool results:"]
        for i, result in enumerate(prompt.tool_results, 1):
            tool_name = result.get("tool", "unknown")
            success = bool(result.get("success", False))
            status = "succeeded" if success else "failed"
            tool_lines.append(f"[{i}] {tool_name} {status}")
            if success:
                output = result.get("output")
                if output is not None:
                    tool_lines.append(f"Output: {output}")
            error = result.get("error")
            if error:
                tool_lines.append(f"Error: {error}")
        tool_lines.append(
            "Use the tool results above to answer the user's request naturally "
            "and accurately. When a tool failed, explain what happened and "
            "suggest a next step."
        )
        tool_text = "\n".join(tool_lines)
        if last_user_index >= 0:
            parts = entries[last_user_index]["parts"]
            assert isinstance(parts, list) and parts
            first = parts[0]
            assert isinstance(first, dict)
            first["text"] = f"{first['text']}\n\n{tool_text}"
        else:
            entries.append({"role": "user", "parts": [{"text": tool_text}]})

    return entries


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
        contents = _build_content_parts(prompt)
        config = {"system_instruction": prompt.system} if prompt.system else None
        logger.info(
            "GeminiProvider.generate — model=%s  contents=%d  system_instruction=%s",
            self.model,
            len(contents),
            "present" if prompt.system else "absent",
        )
        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=contents,
                config=config,
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
        contents = _build_content_parts(prompt)
        config = {"system_instruction": prompt.system} if prompt.system else None
        logger.info(
            "GeminiProvider.stream — model=%s  contents=%d  system_instruction=%s",
            self.model,
            len(contents),
            "present" if prompt.system else "absent",
        )
        try:
            stream = self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config,
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

