"""Response building for the Sentrix Kernel.

``ResponseBuilder`` converts raw provider output into the canonical Sentrix
response format. The kernel intentionally has no vendor SDKs, so provider
adapters are expected to return a normalized :class:`ProviderOutput` — this
module is responsible only for shaping that output into the public contract
(:class:`KernelResponse`).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol


class ResponseBuildError(Exception):
    """Raised when provider output cannot be shaped into a response."""


@dataclass(frozen=True)
class ProviderOutput:
    """Normalized output from a provider adapter."""

    text: str
    reasoning: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    tools_used: tuple[str, ...] = ()
    model: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class KernelResponse:
    """The canonical Sentrix response returned by the kernel."""

    provider: str
    content: str
    reasoning: tuple[str, ...] = ()
    evidence: tuple[str, ...] = ()
    sources: tuple[str, ...] = ()
    tools_used: tuple[str, ...] = ()
    model: str | None = None
    metadata: dict[str, object] = field(default_factory=dict)


class ResponseBuilder(Protocol):
    """Interface for components that shape provider output."""

    def build(self, *, provider: str, output: ProviderOutput) -> KernelResponse:
        """Convert provider output into a :class:`KernelResponse`."""
        ...


class DefaultResponseBuilder:
    """Maps normalized provider output to the Sentrix response contract.

    The transformation is pure and defensive: missing fields become empty
    tuples and no assumption is made about vendor-specific payloads.
    """

    def build(self, *, provider: str, output: ProviderOutput) -> KernelResponse:
        """Shape ``output`` into a :class:`KernelResponse`."""
        text = output.text.strip()
        if not text:
            raise ResponseBuildError("Provider returned an empty response.")

        return KernelResponse(
            provider=provider,
            content=text,
            reasoning=tuple(output.reasoning),
            evidence=tuple(output.evidence),
            sources=tuple(output.sources),
            tools_used=tuple(output.tools_used),
            model=output.model,
            metadata=dict(output.metadata),
        )


__all__ = [
    "DefaultResponseBuilder",
    "KernelResponse",
    "ProviderOutput",
    "ResponseBuildError",
    "ResponseBuilder",
]
