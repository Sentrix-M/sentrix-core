"""Incident Report Generator.

Phase 13 reporting engine. The :class:`~app.reports.engine.ReportEngine`
combines Tool Engine results (Nmap, VirusTotal, Shodan, Wazuh), MITRE ATT&CK
mapping, RAG context, and an AI provider summary into a structured
:class:`~app.reports.models.IncidentReport`. The formatters export it to
Markdown, JSON, and PDF, and :class:`~app.reports.service.ReportService`
orchestrates the full collection → build → export flow.
"""

from app.reports.engine import ReportEngine
from app.reports.formatters import format_report, to_json, to_markdown, to_pdf
from app.reports.models import (
    REPORT_VERSION,
    AffectedAsset,
    IncidentReport,
    IndicatorOfCompromise,
    ReportFormat,
    RiskAssessment,
    Severity,
    TimelineEvent,
)
from app.reports.service import ReportService

__all__ = [
    "REPORT_VERSION",
    "AffectedAsset",
    "IncidentReport",
    "IndicatorOfCompromise",
    "ReportEngine",
    "ReportFormat",
    "ReportService",
    "RiskAssessment",
    "Severity",
    "TimelineEvent",
    "format_report",
    "to_json",
    "to_markdown",
    "to_pdf",
]
