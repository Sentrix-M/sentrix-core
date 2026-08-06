"""Conversation service — coordinates AI conversation turns.

Currently returns a deterministic mock reply. The interface is designed so a
real model provider (LLM router, RAG, tool execution) can be swapped in later
without changing the routers or schemas: the metadata block is the contract
for reasoning/evidence/sources/tools output.

The service is intentionally stateless — conversations are identified by a
client-generated ``conversation_id`` and no persistence is used yet.

When an optional :class:`~app.memory.service.MemoryService` is provided
(Phase 15B), every turn is recorded to long-term memory and recent context
can be retrieved for a conversation. When omitted, the service behaves
exactly as before (backward compatible).
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.schemas.conversation import (
    ConversationMessageRequest,
    ConversationMessageResponse,
    ConversationMetadata,
)

if TYPE_CHECKING:
    from app.memory.service import MemoryService


class ConversationService:
    """Implements the conversation use cases (mock AI for now)."""

    #: Placeholder model identifier until the AI router is implemented.
    MOCK_MODEL = "sentrix-mock-0.1"

    def __init__(
        self,
        memory_service: MemoryService | None = None,
    ) -> None:
        """Build the service.

        :param memory_service: Optional :class:`MemoryService` used to record
            each turn and retrieve recent conversation context. When omitted
            (default), no persistence occurs (backward compatible).
        """
        self._memory_service = memory_service

    @property
    def memory_service(self) -> MemoryService | None:
        """The optional memory service ("None" when not wired)."""
        return self._memory_service

    def reply(
        self, request: ConversationMessageRequest
    ) -> ConversationMessageResponse:
        """Return a mock assistant reply for a user message.

        The reply is deterministic per message content so the endpoint is
        testable while remaining clearly synthetic.

        When a memory service is wired, the user turn and the assistant turn
        are recorded to long-term memory (best-effort).
        """
        message = request.message.strip()
        response = self._build_mock_response(message)

        self._record_turn(request.conversation_id, message, response)

        return ConversationMessageResponse(
            conversation_id=request.conversation_id,
            response=response,
            timestamp=datetime.now(timezone.utc),
            metadata=ConversationMetadata(
                model=self.MOCK_MODEL,
                execution_time_ms=12,  # simulated latency for the mock engine
            ),
        )

    def get_recent_context(
        self,
        conversation_id: str,
        *,
        limit: int = 20,
    ) -> list[tuple[str, str]]:
        """Return recent ``(role, content)`` pairs for a conversation.

        Additive Phase 15B helper. When no memory service is wired, an empty
        list is returned.
        """
        if self._memory_service is None:
            return []
        records = self._memory_service.get_conversation_messages(
            conversation_id=conversation_id,
            limit=limit,
        )
        # Records are newest-first; expose oldest-first for context.
        return [
            (record.role, record.content)
            for record in reversed(records)
        ]

    def _record_turn(
        self,
        conversation_id: str,
        user_message: str,
        assistant_response: str,
    ) -> None:
        """Persist the user + assistant turns to memory (best-effort)."""
        if self._memory_service is None:
            return
        try:
            self._memory_service.record_conversation_message(
                conversation_id=conversation_id,
                content=user_message,
                role="user",
            )
            self._memory_service.record_conversation_message(
                conversation_id=conversation_id,
                content=assistant_response,
                role="assistant",
            )
        except Exception:  # noqa: BLE001 - memory must never break the turn
            pass

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
