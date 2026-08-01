"""Provider abstraction for the Sentrix AI Provider Layer.

Every provider (mock today, OpenAI/Gemini/Claude/Ollama tomorrow) implements
:class:`BaseProvider`. The interface is deliberately small — ``generate``,
``stream`` and ``health`` — and purely synchronous, deterministic, and
dependency-free so providers stay trivially testable without network access.
"""

from __future__ import annotations

from typing import Protocol

from app.kernel.prompt_builder import Prompt
from app.kernel.response_builder import ProviderOutput


class ProviderHealth:
    """Health status for a provider."""

    def __init__(self, *, ok: bool, message: str = "") -> None:
        self.ok = ok
        self.message = message

    def __repr__(self) -> str:  # pragma: no cover - debug helper
        return f"<ProviderHealth ok={self.ok} message={self.message!r}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProviderHealth):
            return NotImplemented
        return self.ok == other.ok and self.message == other.message


class BaseProvider(Protocol):
    """Contract implemented by all Sentrix AI providers.

    Conforms to the kernel's ``ProviderClient`` protocol for ``name`` and
    ``generate``, so providers can be registered directly with a kernel
    ``ProviderRegistry``.
    """

    name: str

    def generate(self, prompt: Prompt) -> ProviderOutput:
        """Return a complete, normalized provider response."""
        ...

    def stream(self, prompt: Prompt) -> list[str]:
        """Yield the response incrementally as a list of text chunks.

        Providers that support true token streaming can expose an async
        generator; the synchronous form keeps this interface uniform and
        testable across all providers.
        """
        ...

    def health(self) -> ProviderHealth:
        """Report provider availability."""
        ...


def check_health(provider: BaseProvider) -> ProviderHealth:
    """Call ``provider.health()`` with graceful error handling."""
    try:
        return provider.health()
    except Exception as exc:  # noqa: BLE001 - health checks must not raise
        return ProviderHealth(ok=False, message=f"Health check failed: {exc}")


__all__ = ["BaseProvider", "ProviderHealth", "check_health"]
