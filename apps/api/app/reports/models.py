"""Data models for the Sentrix Incident Report Generator.

These models are deliberately framework-light Pydantic models so they can be
serialized/deserialized anywhere in the application (kernel, HTTP, streaming,
exporters) without coupling to a specific report framework.

The :class:`IncidentReport` aggregates investigation context from the Tool
Engine (Nmap, VirusTotal, Shodan, Wazuh), the MITRE mapper, and the RAG
knowledge layer into one structured, versioned report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

#: Current report schema version. Bump when the report shape changes.
REPORT_VERSION = "1.0"


class Severity(str, Enum):
    """Overall incident severity derived from multiple evidence sources."""

    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class ReportFormat(str, Enum):
    """Supported report export formats."""

    MARKDOWN = "markdown"
    PDF = "pdf"
    JSON = "json"


class AffectedAsset(BaseModel):
    """A single affected asset (host, IP, hostname, or endpoint)."""

    asset_type: str = Field(description="e.g. 'ip', 'hostname', 'host', 'endpoint'.")
    value: str = Field(description="The asset identifier.")
    detail: str = ""


class IndicatorOfCompromise(BaseModel):
    """A single indicator of compromise (IOC)."""

    indicator_type: str = Field(description="e.g. 'ip', 'domain', 'hash', 'url'.")
    value: str = Field(description="The IOC value.")


class TimelineEvent(BaseModel):
    """A single timeline entry for the incident."""

    timestamp: str = Field(description="ISO-8601 timestamp or relative time label.")
    description: str = Field(description="What happened at this point.")


class RiskAssessment(BaseModel):
    """Qualitative risk assessment for the incident."""

    likelihood: str = Field(default="Medium", description="e.g. Low/Medium/High.")
    impact: str = Field(default="Medium", description="e.g. Low/Medium/High.")
    score: float = Field(default=0.0, ge=0.0, le=1.0, description="Normalized 0-1 score.")


class IncidentReport(BaseModel):
    """The canonical Sentrix incident report.

    Combines the outputs of the security tooling, MITRE ATT&CK mapping,
    RAG context, and the AI provider summary into a single structured report.
    """

    model_config = ConfigDict(frozen=True)

    # --- Metadata -----------------------------------------------------
    report_id: str = Field(
        default_factory=lambda: str(uuid4()),
        description="Unique report identifier.",
    )
    report_version: str = Field(
        default=REPORT_VERSION,
        description="Report schema version.",
    )
    generated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="When the report was generated (UTC).",
    )
    generated_by: str = Field(
        default="Sentrix Incident Report Generator",
        description="Tool/provider that produced the report.",
    )
    report_format: ReportFormat = Field(
        default=ReportFormat.MARKDOWN,
        description="Default export format.",
    )

    # --- Summary ------------------------------------------------------
    incident_title: str = Field(description="Short incident title.")
    severity: Severity = Field(default=Severity.MEDIUM, description="Overall severity.")
    executive_summary: str = Field(
        default="",
        description="Executive summary produced by the AI provider.",
    )

    # --- Investigation data -------------------------------------------
    timeline: list[TimelineEvent] = Field(default_factory=list)
    affected_assets: list[AffectedAsset] = Field(default_factory=list)
    iocs: list[IndicatorOfCompromise] = Field(default_factory=list)

    # --- Tool findings ------------------------------------------------
    mitre_mapping: dict[str, Any] = Field(
        default_factory=dict,
        description="MITRE ATT&CK mapping (from MitreMapper.to_dict()).",
    )
    nmap_findings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Nmap scan findings.",
    )
    virustotal_findings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="VirusTotal indicator findings.",
    )
    shodan_findings: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Shodan internet-exposure findings.",
    )
    wazuh_alerts: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Wazuh security-alert findings.",
    )

    # --- Analysis -----------------------------------------------------
    risk_assessment: RiskAssessment = Field(
        default_factory=RiskAssessment,
        description="Qualitative risk assessment.",
    )
    recommendations: list[str] = Field(default_factory=list)
    analyst_notes: list[str] = Field(default_factory=list)

    # --- RAG context --------------------------------------------------
    rag_context: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Retrieved knowledge-base context used to enrich the report.",
    )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the report to a plain JSON-safe dict."""
        return self.model_dump(mode="json")


__all__ = [
    "REPORT_VERSION",
    "AffectedAsset",
    "IncidentReport",
    "IndicatorOfCompromise",
    "ReportFormat",
    "RiskAssessment",
    "Severity",
    "TimelineEvent",
]
