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
            reasoning=(
                "Synthesized the response from the mock provider prompt context.",
            ),
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

    @staticmethod
    def _surface_tool_results(prompt: Prompt) -> str | None:
        """Return a prose reply reflecting ``prompt.tool_results``, if any.

        Surfaces each successful tool's output (and reasons for failures) so
        real VirusTotal/Shodan/Wazuh/Nmap findings reach the final response.
        Returns ``None`` when no tool results are present so the legacy
        keyword-aware branches still apply.
        """
        results = prompt.tool_results
        if not results:
            return None

        lines: list[str] = [
            "I ran the requested security checks and here are the live tool findings."
        ]
        succeeded = 0
        for i, result in enumerate(results, 1):
            tool = result.get("tool", "unknown")
            success = bool(result.get("success", False))
            output = result.get("output")
            error = result.get("error")
            if success:
                succeeded += 1
                lines.append(f"[{i}] {tool}: {output}")
            else:
                lines.append(f"[{i}] {tool} failed: {error or 'unknown error'}")

        if succeeded:
            lines.append(
                "These results are from the live tool integration. Use them to "
                "inform your containment and remediation decisions."
            )
        else:
            lines.append(
                "None of the tool checks completed successfully. I recommend "
                "reviewing the errors above and retrying."
            )
        return "\n".join(lines)

    def _build_response(self, prompt: Prompt) -> str:
        """Build a keyword-aware mock reply from the current user message.

        When the prompt carries tool results (from the kernel pipeline), those
        findings are surfaced first so the response reflects real tool output.
        Otherwise it falls back to the deterministic keyword-aware branches.
        """
        surfaced = self._surface_tool_results(prompt)
        if surfaced is not None:
            return surfaced

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
