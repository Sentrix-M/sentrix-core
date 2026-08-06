"""Retriever — recall long-term memory by temporal, entity, or keyword.

:class:`MemoryRetriever` provides lightweight heuristic recall over the
:class:`~app.memory.service.MemoryService`:

- **Temporal recall** — "what happened yesterday / last week"
- **Entity recall** — "what do we know about <indicator/IP/domain>"
- **Keyword recall** — fuzzy/substring match over recorded text fields

This is a deterministic, offline-safe foundation. It does **not** use a
vector store or embeddings; a semantic retrieval layer can be layered on
top later without changing this API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.memory.service import MemoryService

#: Regexes used for entity extraction from free-text queries.
_IP_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_DOMAIN_RE = re.compile(r"\b(?:[a-zA-Z0-9-]+\.)+[a-zA-Z]{2,}\b")
_HASH_RE = re.compile(r"\b[0-9a-f]{32,64}\b", re.IGNORECASE)


@dataclass(frozen=True)
class RecallResult:
    """A single recalled memory item."""

    kind: str
    record: Any
    score: float = field(default=1.0)

    @property
    def id(self) -> str:  # noqa: A003 - attribute name mirrors record.id
        """The underlying record ID."""
        return str(getattr(self.record, "id", ""))


@dataclass(frozen=True)
class RecallResponse:
    """Aggregated recall result."""

    results: list[RecallResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        """Number of recalled items."""
        return len(self.results)


class MemoryRetriever:
    """Heuristic recall over the memory service.

    :param service: The :class:`MemoryService` to query.
    """

    def __init__(self, service: MemoryService) -> None:
        self._service = service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def recall(
        self,
        query: str,
        *,
        limit: int = 20,
        org_id: str | None = None,
        user_id: str | None = None,
    ) -> RecallResponse:
        """Recall memory matching *query*.

        Combines temporal, entity, and keyword strategies and returns
        results ordered by relevance score.
        """
        results: list[RecallResult] = []

        # Temporal recall for relative time phrases.
        window = self._parse_time_window(query)
        if window is not None:
            results.extend(
                self._recall_temporal(
                    since=window,
                    org_id=org_id,
                    user_id=user_id,
                    limit=limit,
                )
            )

        # Entity recall for indicators/IPs/domains/hashes.
        entities = self._extract_entities(query)
        for _entity_type, value in entities:
            results.extend(
                self._recall_entity(
                    value=value,
                    org_id=org_id,
                    user_id=user_id,
                    limit=limit,
                )
            )

        # Keyword recall for remaining textual matches.
        if not entities and window is None:
            results.extend(
                self._recall_keyword(
                    query,
                    org_id=org_id,
                    user_id=user_id,
                    limit=limit,
                )
            )

        # Deduplicate by record ID, then sort by score descending.
        seen: set[str] = set()
        unique: list[RecallResult] = []
        for result in results:
            if result.id in seen:
                continue
            seen.add(result.id)
            unique.append(result)
        unique.sort(key=lambda r: r.score, reverse=True)
        return RecallResponse(results=unique[:limit])

    # ------------------------------------------------------------------
    # Temporal recall
    # ------------------------------------------------------------------

    def _parse_time_window(self, query: str) -> datetime | None:
        """Parse a relative time phrase into a UTC datetime cutoff."""
        lowered = query.lower()
        now = datetime.now(timezone.utc)
        if "yesterday" in lowered:
            return now - timedelta(days=1)
        if "last week" in lowered or "past week" in lowered:
            return now - timedelta(weeks=1)
        if "last month" in lowered or "past month" in lowered:
            return now - timedelta(days=30)
        if "last 24 hours" in lowered or "past 24 hours" in lowered:
            return now - timedelta(hours=24)
        if "last hour" in lowered or "past hour" in lowered:
            return now - timedelta(hours=1)
        return None

    def _recall_temporal(
        self,
        *,
        since: datetime,
        org_id: str | None,
        user_id: str | None,
        limit: int,
    ) -> list[RecallResult]:
        """Return records created since *since*."""
        results: list[RecallResult] = []

        for record in self._service.get_reports(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            if record.created_at >= since:
                results.append(RecallResult(kind="report", record=record))

        for record in self._service.get_investigations(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            if record.created_at >= since:
                results.append(RecallResult(kind="investigation", record=record))

        for record in self._service.get_findings(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            if record.created_at >= since:
                results.append(RecallResult(kind="finding", record=record))

        for record in self._service.get_tool_executions(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            if record.created_at >= since:
                results.append(RecallResult(kind="tool_execution", record=record))

        for record in self._service.get_conversation_messages(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            if record.created_at >= since:
                results.append(RecallResult(kind="conversation", record=record))

        return results

    # ------------------------------------------------------------------
    # Entity recall
    # ------------------------------------------------------------------

    def _extract_entities(self, query: str) -> list[tuple[str, str]]:
        """Extract (type, value) entity pairs from *query*."""
        entities: list[tuple[str, str]] = []
        for match in _IP_RE.findall(query):
            entities.append(("ip", match))
        for match in _HASH_RE.findall(query):
            entities.append(("hash", match))
        for match in _DOMAIN_RE.findall(query):
            entities.append(("domain", match))
        return entities

    def _recall_entity(
        self,
        *,
        value: str,
        org_id: str | None,
        user_id: str | None,
        limit: int,
    ) -> list[RecallResult]:
        """Return records related to a specific entity value."""
        results: list[RecallResult] = []

        # Findings targeting this entity.
        for record in self._service.get_findings(
            target=value, org_id=org_id, user_id=user_id, limit=limit
        ):
            results.append(RecallResult(kind="finding", record=record, score=1.0))

        # Investigations targeting this entity.
        for record in self._service.get_investigations(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            if value in record.target or value in record.title:
                results.append(
                    RecallResult(kind="investigation", record=record, score=0.9)
                )

        # Tool executions whose output references the entity.
        for record in self._service.get_tool_executions(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            blob = _flatten(record.output) + " " + record.error
            if value in blob:
                results.append(
                    RecallResult(kind="tool_execution", record=record, score=0.8)
                )

        # Conversation messages referencing the entity.
        for record in self._service.get_conversation_messages(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            if value in record.content:
                results.append(
                    RecallResult(kind="conversation", record=record, score=0.7)
                )

        # Reports referencing the entity.
        for record in self._service.get_reports(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            blob = _flatten(record.payload) + " " + record.summary + " " + record.title
            if value in blob:
                results.append(RecallResult(kind="report", record=record, score=0.6))

        return results

    # ------------------------------------------------------------------
    # Keyword recall
    # ------------------------------------------------------------------

    def _recall_keyword(
        self,
        query: str,
        *,
        org_id: str | None,
        user_id: str | None,
        limit: int,
    ) -> list[RecallResult]:
        """Return records whose text contains *query* (case-insensitive)."""
        needle = query.strip().lower()
        results: list[RecallResult] = []

        _record: Any

        for _record in self._service.get_findings(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            if needle in _record.description.lower() or needle in (
                _record.finding_type + " " + _record.target
            ).lower():
                results.append(RecallResult(kind="finding", record=_record))

        for _record in self._service.get_investigations(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            blob = f"{_record.title} {_record.summary} {_record.target}".lower()
            if needle in blob:
                results.append(RecallResult(kind="investigation", record=_record))

        for _record in self._service.get_reports(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            blob = f"{_record.title} {_record.summary}".lower()
            if needle in blob:
                results.append(RecallResult(kind="report", record=_record))

        for _record in self._service.get_conversation_messages(
            org_id=org_id, user_id=user_id, limit=limit
        ):
            if needle in _record.content.lower():
                results.append(RecallResult(kind="conversation", record=_record))

        return results


def _flatten(value: Any) -> str:
    """Serialize an arbitrary value into a lowercase searchable string."""
    try:
        import json

        return json.dumps(value, default=str).lower()
    except (TypeError, ValueError):
        return str(value).lower()


__all__ = ["MemoryRetriever", "RecallResponse", "RecallResult"]
