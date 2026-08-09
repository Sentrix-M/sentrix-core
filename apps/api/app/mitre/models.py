"""Data models for the Sentrix MITRE ATT&CK mapping engine.

These models are deliberately plain and dependency-free so they can be
serialized/deserialized anywhere in the application (kernel, prompt builder,
streaming, HTTP) without coupling to a specific framework.

The outward contract matches the Phase 11 requirements:

    {
        "techniques": [],
        "tactics": [],
        "mitigations": [],
        "detections": [],
        "confidence": ...,
    }
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class MitreTechnique:
    """A single MITRE ATT&CK technique identified by the mapper.

    :param technique_id: ATT&CK technique ID (e.g. ``T1071.001``).
    :param name: Human-readable technique name.
    :param tactic: Parent tactic (e.g. ``Command & Control``).
    :param mitigation: Recommended mitigation guidance.
    :param detection: Detection guidance for the technique.
    :param evidence: Human-readable evidence string explaining why the
        technique was mapped (which service/CVE/behavior triggered it).
    :param confidence: Per-technique confidence in ``[0.0, 1.0]``.
    """

    technique_id: str
    name: str
    tactic: str
    mitigation: str = ""
    detection: str = ""
    evidence: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        """Serialize the technique to a plain dict."""
        return {
            "technique_id": self.technique_id,
            "name": self.name,
            "tactic": self.tactic,
            "mitigation": self.mitigation,
            "detection": self.detection,
            "evidence": self.evidence,
            "confidence": self.confidence,
        }


def _dedupe(techniques: list[MitreTechnique]) -> list[MitreTechnique]:
    """Return techniques with duplicate IDs removed (first occurrence wins)."""
    seen: set[str] = set()
    unique: list[MitreTechnique] = []
    for technique in techniques:
        if technique.technique_id in seen:
            continue
        seen.add(technique.technique_id)
        unique.append(technique)
    return unique


@dataclass
class MitreMapping:
    """The complete ATT&CK mapping for a single tool result.

    :param techniques: Ordered list of matched techniques.
    :param confidence: Overall confidence of the mapping in ``[0.0, 1.0]``.
    :param source: Name of the tool that produced the mapped result.
    """

    techniques: list[MitreTechnique] = field(default_factory=list)
    confidence: float = 0.0
    source: str = ""

    @property
    def techniques_deduped(self) -> list[MitreTechnique]:
        """Techniques with duplicate IDs removed, preserving order."""
        return _dedupe(self.techniques)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the mapping to the required contract shape.

        The returned dict mirrors the Phase 11 requirement:

        - ``techniques`` — list of ``{technique_id, name, tactic, ...}``
        - ``tactics`` — unique parent tactic names
        - ``mitigations`` — unique mitigation strings
        - ``detections`` — unique detection strings
        - ``confidence`` — overall confidence
        """
        techniques = self.techniques_deduped
        return {
            "techniques": [t.to_dict() for t in techniques],
            "tactics": sorted({t.tactic for t in techniques if t.tactic}),
            "mitigations": sorted(
                {t.mitigation for t in techniques if t.mitigation}
            ),
            "detections": sorted(
                {t.detection for t in techniques if t.detection}
            ),
            "confidence": self.confidence,
        }


__all__ = ["MitreMapping", "MitreTechnique"]
