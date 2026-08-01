"""Deterministic mock provider for the Sentrix AI Provider Layer.

``MockProvider`` implements :class:`BaseProvider` (and therefore the kernel's
``ProviderClient`` protocol) without any network access. It produces stable,
keyword-aware cybersecurity responses so the full pipeline — from router to
prompt to response — can be exercised offline and in tests.
"""

from __future__ import annotations

from app.kernel.prompt_builder import Prompt
from app.kernel.response_builder import ProviderOutput
from app.providers.base import BaseProvider, ProviderHealth


class MockProvider(BaseProvider):  # type: ignore[misc]
    """Synchronous, offline, deterministic mock provider."""

    name = "mock"

    def __init__(self, *, model: str = "sentrix-mock-0.1") -> None:
        """Create the provider with a configurable model identifier."""
        self.model = model

    def generate(self, prompt: Prompt) -> ProviderOutput:
        """Return a deterministic mock response for ``prompt``."""
        text = self._build_response(prompt)
        return ProviderOutput(
            text=text,
            model=self.model,
            reasoning=("Matched the user message against the mock cybersecurity keyword rules.",),
            metadata={"provider": "mock", "mode": "offline"},
        )

    def stream(self, prompt: Prompt) -> list[str]:
        """Return the response split into word-level chunks.

        Kept synchronous for uniformity; a real provider can expose an async
        generator and satisfy the same protocol at the call site.
        """
        return self.generate(prompt).text.split(" ")

    def health(self) -> ProviderHealth:
        """Mock providers are always healthy (they need no network)."""
        return ProviderHealth(ok=True, message="Mock provider is available.")

    def _build_response(self, prompt: Prompt) -> str:
        """Build a keyword-aware mock reply from the current user message."""
        text = prompt.to_text()
        lower = text.lower()
        if any(word in lower for word in ("beacon", "c2", "alert", "critical")):
            return (
                "I've triaged the telemetry referenced in your request. The pattern is "
                "consistent with a periodic C2 beacon (MITRE ATT&CK T1071.001) with a "
                "~47s interval. Recommended next step: isolate the endpoint and "
                "preserve a memory snapshot for DFIR."
            )
        if any(word in lower for word in ("log", "suricata", "zeek", "wireshark", "pcap")):
            return (
                "I've correlated the relevant log sources and found a small set of "
                "suspicious flows. I recommend pivoting on the destination ASN and "
                "checking for matching YARA rules before blocking."
            )
        return (
            "Acknowledged — your message has been logged for the selected agent. "
            "The conversation engine prepared context and is ready for the next turn."
        )


__all__ = ["MockProvider"]
