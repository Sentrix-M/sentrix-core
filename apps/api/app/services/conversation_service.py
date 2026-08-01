"""Conversation service — coordinates AI conversation turns.

Currently returns a deterministic mock reply. The interface is designed so a
real model provider (LLM router, RAG, tool execution) can be swapped in later
without changing the routers or schemas: the metadata block is the contract
for reasoning/evidence/sources/tools output.

The service is intentionally stateless — conversations are identified by a
client-generated ``conversation_id`` and no persistence is used yet.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.schemas.conversation import (
    ConversationMessageRequest,
    ConversationMessageResponse,
    ConversationMetadata,
)


class ConversationService:
    """Implements the conversation use cases (mock AI for now)."""

    #: Placeholder model identifier until the AI router is implemented.
    MOCK_MODEL = "sentrix-mock-0.1"

    def reply(
        self, request: ConversationMessageRequest
    ) -> ConversationMessageResponse:
        """Return a mock assistant reply for a user message.

        The reply is deterministic per message content so the endpoint is
        testable while remaining clearly synthetic.
        """
        message = request.message.strip()
        response = self._build_mock_response(message)

        return ConversationMessageResponse(
            conversation_id=request.conversation_id,
            response=response,
            timestamp=datetime.now(timezone.utc),
            metadata=ConversationMetadata(
                model=self.MOCK_MODEL,
                execution_time_ms=12,  # simulated latency for the mock engine
            ),
        )

    @staticmethod
    def _build_mock_response(message: str) -> str:
        """Generate a plausible, keyword-aware mock cybersecurity reply."""
        lower = message.lower()
        if any(keyword in lower for keyword in ("alert", "critical", "beacon", "c2")):
            return (
                "I've triaged the telemetry referenced in your request. The pattern is "
                "consistent with a periodic C2 beacon (MITRE ATT&CK T1071.001) with a "
                "~47s interval. Recommended next step: isolate the endpoint and "
                "preserve a memory snapshot for DFIR. "
                "(Mock response — an AI model is not attached yet.)"
            )
        if any(
            keyword in lower
            for keyword in ("log", "suricata", "zeek", "wireshark", "pcap")
        ):
            return (
                "I've correlated the relevant log sources and found a small set of "
                "suspicious flows. I recommend pivoting on the destination ASN and "
                "checking for matching YARA rules before blocking. "
                "(Mock response — an AI model is not attached yet.)"
            )
        return (
            "Acknowledged — your message has been logged for the selected agent. "
            "The conversation engine prepared context and is ready for the next turn. "
            "(Mock response — an AI model is not attached yet.)"
        )

