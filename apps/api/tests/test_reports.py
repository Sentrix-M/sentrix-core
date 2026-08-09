"""Unit tests for the Phase 13 Incident Report Generator.

Covers the report data models, the :class:`ReportEngine` (tools → MITRE →
RAG → provider summary → severity), the :class:`ReportService` (collect →
build → export), and the Markdown/JSON/PDF formatters. The suite is fully
offline: the engine uses no provider (or the deterministic
:class:`MockProvider`), and the service uses a ToolExecutor with lightweight
fake tools — no real network or external tool calls are ever made.
"""

from __future__ import annotations

import asyncio
import json
import tempfile
from pathlib import Path
from typing import Any

from app.main import app  # noqa: F401 - must import first to break import cycles
from app.providers.mock import MockProvider
from app.rag.schemas import SearchResultItem
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
from app.reports.service import ReportService, _safe_filename
from app.tools.base import ToolResult
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _tool_result(
    tool: str,
    output: dict[str, Any],
    *,
    success: bool = True,
) -> ToolResult:
    """Build a ToolResult for a given tool name and output dict."""
    if success:
        return ToolResult.ok(tool, output)
    return ToolResult.fail(tool, "tool failed")


def _nmap_result() -> ToolResult:
    """A successful Nmap scan result."""
    return _tool_result(
        "nmap",
        {
            "target": "10.0.0.5",
            "execution_time": 12,
            "hosts": [
                {
                    "ip": "10.0.0.5",
                    "hostname": "db.internal",
                    "open_ports": [
                        {"port": 22, "protocol": "tcp", "service": "ssh"},
                        {"port": 3306, "protocol": "tcp", "service": "mysql"},
                    ],
                }
            ],
        },
    )


def _virustotal_result() -> ToolResult:
    """A successful VirusTotal lookup flagged as malicious."""
    return _tool_result(
        "virustotal",
        {
            "query": "44d88612fea8a8f36de82e1278abb02f",
            "indicator_type": "hash",
            "malicious": 12,
            "suspicious": 1,
            "harmless": 0,
            "permalink": "https://www.virustotal.com/gui/hash/_",
        },
    )


def _shodan_result() -> ToolResult:
    """A successful Shodan host-intelligence result."""
    return _tool_result(
        "shodan",
        {
            "query": "203.0.113.7",
            "ip": "203.0.113.7",
            "organization": "Acme Corp",
            "asn": "AS64496",
            "country": "US",
            "ports": [80, 443],
            "services": [{"port": 443, "product": "nginx", "transport": "tcp"}],
            "vulnerabilities": ["CVE-2021-44228"],
            "risk_score": "high",
        },
    )


def _wazuh_result() -> ToolResult:
    """A successful Wazuh security-alert result."""
    return _tool_result(
        "wazuh",
        {
            "operation": "alert",
            "severity": 14,
            "agent": {"name": "web-01", "id": "001"},
            "rule": {
                "rule_id": "1002",
                "description": "Suspicious outbound connection",
                "groups": ["malware"],
                "mitre": ["T1071.001"],
            },
            "timestamp": "2025-01-01T00:00:00Z",
            "recommendations": ["Isolate the endpoint."],
        },
    )


def _sample_report() -> IncidentReport:
    """Build a fully populated IncidentReport for formatter tests."""
    return IncidentReport(
        incident_title="Ransomware on web-01",
        severity=Severity.CRITICAL,
        executive_summary="A ransomware incident was confirmed on web-01.",
        timeline=[
            TimelineEvent(timestamp="2025-01-01T00:00:00Z", description="Alert raised.")
        ],
        affected_assets=[
            AffectedAsset(asset_type="endpoint", value="web-01", detail="001")
        ],
        iocs=[IndicatorOfCompromise(indicator_type="hash", value="abc123")],
        mitre_mapping={
            "techniques": [
                {
                    "technique_id": "T1486",
                    "name": "Data Encrypted for Impact",
                    "tactic": "Impact",
                }
            ]
        },
        nmap_findings=[{"target": "10.0.0.5"}],
        virustotal_findings=[{"query": "abc123", "malicious": 12}],
        shodan_findings=[{"query": "203.0.113.7"}],
        wazuh_alerts=[{"operation": "alert", "severity": 14}],
        risk_assessment=RiskAssessment(likelihood="High", impact="High", score=0.9),
        recommendations=["Isolate the endpoint."],
        analyst_notes=["Confirmed by SOC."],
        rag_context=[{"chunk_id": "c1", "text": "known-ransomware behavior"}],
    )


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestModels:
    def test_incident_report_defaults(self) -> None:
        report = IncidentReport(incident_title="Test Incident")
        assert report.report_id
        assert report.report_version == REPORT_VERSION
        assert report.severity == Severity.MEDIUM
        assert report.timeline == []
        assert report.affected_assets == []
        assert report.iocs == []
        assert report.recommendations == []
        assert report.analyst_notes == []
        assert report.rag_context == []

    def test_severity_enum_values(self) -> None:
        assert [s.value for s in Severity] == ["Low", "Medium", "High", "Critical"]

    def test_report_format_enum_values(self) -> None:
        assert [f.value for f in ReportFormat] == ["markdown", "pdf", "json"]

    def test_to_dict_is_json_safe(self) -> None:
        report = _sample_report()
        data = report.to_dict()
        assert isinstance(data, dict)
        assert data["incident_title"] == "Ransomware on web-01"
        assert data["severity"] == "Critical"
        assert data["report_version"] == REPORT_VERSION
        # Round-trips through JSON without error.
        json.dumps(data)


# ---------------------------------------------------------------------------
# ReportEngine
# ---------------------------------------------------------------------------


class TestReportEngine:
    def test_engine_builds_report_without_provider(self) -> None:
        engine = ReportEngine()
        report = engine.generate(
            incident_title="Phishing campaign",
            tool_results=[_nmap_result(), _virustotal_result()],
        )
        assert report.incident_title == "Phishing campaign"
        assert report.executive_summary  # fallback summary used
        assert "indicator(s)" in report.executive_summary
        assert report.severity == Severity.CRITICAL
        assert report.nmap_findings
        assert report.virustotal_findings
        assert report.affected_assets
        assert report.iocs
        assert report.mitre_mapping

    def test_engine_uses_provider_summary(self) -> None:
        engine = ReportEngine(provider=MockProvider())
        assert engine.provider is not None
        report = engine.generate(
            incident_title="Critical beacon detected",
            tool_results=[_wazuh_result()],
        )
        assert report.executive_summary
        # MockProvider returns a C2-beacon triage line for critical input.
        assert "C2 beacon" in report.executive_summary

    def test_engine_extracts_timeline_assets_iocs(self) -> None:
        engine = ReportEngine()
        report = engine.generate(
            incident_title="Multi-tool investigation",
            tool_results=[
                _nmap_result(),
                _virustotal_result(),
                _shodan_result(),
                _wazuh_result(),
            ],
        )
        assert any(a.value == "10.0.0.5" for a in report.affected_assets)
        assert any(a.value == "web-01" for a in report.affected_assets)
        assert any(i.value == "44d88612fea8a8f36de82e1278abb02f" for i in report.iocs)
        assert any(i.value == "CVE-2021-44228" for i in report.iocs)
        assert any(
            t.description == "Wazuh security alert detected." for t in report.timeline
        )

    def test_engine_merges_recommendations(self) -> None:
        engine = ReportEngine()
        report = engine.generate(
            incident_title="Wazuh alert",
            tool_results=[_wazuh_result()],
            recommendations=["Update firewall rules."],
        )
        assert "Isolate the endpoint." in report.recommendations
        assert "Update firewall rules." in report.recommendations

    def test_engine_carries_analyst_notes(self) -> None:
        engine = ReportEngine()
        report = engine.generate(
            incident_title="Notes check",
            tool_results=[],
            analyst_notes=["Reviewed manually."],
        )
        assert report.analyst_notes == ["Reviewed manually."]

    def test_engine_includes_rag_context(self) -> None:
        engine = ReportEngine()
        rag = [
            SearchResultItem(
                chunk_id="c1",
                document_id="d1",
                text="known ransomware behavior",
                filename="kb.md",
                page_number=1,
                chunk_index=0,
                score=0.9,
            )
        ]
        report = engine.generate(
            incident_title="RAG enhanced",
            tool_results=[_virustotal_result()],
            rag_context=rag,
        )
        assert report.rag_context
        assert report.rag_context[0]["text"] == "known ransomware behavior"

    def test_engine_ignores_failed_results(self) -> None:
        engine = ReportEngine()
        report = engine.generate(
            incident_title="Failure tolerant",
            tool_results=[_tool_result("nmap", {}, success=False)],
        )
        assert report.nmap_findings == []
        assert report.affected_assets == []
        assert report.iocs == []

    def test_engine_deduplicates_assets(self) -> None:
        engine = ReportEngine()
        report = engine.generate(
            incident_title="Dedupe",
            tool_results=[_nmap_result(), _nmap_result(), _nmap_result()],
        )
        assert len(report.affected_assets) == 2  # ip + hostname, not 6

    def test_engine_risk_assessment_matches_severity(self) -> None:
        engine = ReportEngine()
        low = engine.generate(incident_title="Low", tool_results=[]).severity
        assert low == Severity.LOW


# ---------------------------------------------------------------------------
# ReportService
# ---------------------------------------------------------------------------


class _FakeTool:
    """A lightweight fake tool that returns a canned output."""

    name = "fake"
    description = "fake"
    version = "0.1.0"
    permissions: set = set()

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    @property
    def output_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> ToolResult:  # noqa: ARG002
        return _nmap_result()

    async def health(self) -> Any:
        from app.tools.base import ToolHealth

        return ToolHealth(ok=True, message="ok")


class _FakeRagService:
    """A fake RAG service returning a single canned result."""

    async def search(
        self,
        query: str,  # noqa: ARG002
        *,
        top_k: int = 5,  # noqa: ARG002
    ) -> list[SearchResultItem]:
        return [
            SearchResultItem(
                chunk_id="c1",
                document_id="d1",
                text="canned rag result",
                filename="kb.md",
                page_number=1,
                chunk_index=0,
                score=0.8,
            )
        ]


def _build_service(*, with_rag: bool = False) -> ReportService:
    """Build a ReportService wired to a registry with a fake tool."""
    registry = ToolRegistry()
    registry.register(_FakeTool())
    executor = ToolExecutor(registry)
    rag_service = _FakeRagService() if with_rag else None
    return ReportService(executor=executor, rag_service=rag_service)


class TestReportService:
    def test_collect_results(self) -> None:
        service = _build_service()
        results = asyncio.run(service.collect_results(tool_inputs=[("fake", {})]))
        assert len(results) == 1
        assert results[0].success is True
        assert results[0].tool == "nmap"

    def test_generate(self) -> None:
        service = _build_service()
        report = asyncio.run(
            service.generate(
                incident_title="Service test",
                tool_inputs=[("fake", {})],
            )
        )
        assert report.incident_title == "Service test"
        assert report.nmap_findings

    def test_generate_with_rag(self) -> None:
        service = _build_service(with_rag=True)
        report = asyncio.run(
            service.generate(
                incident_title="RAG service",
                tool_inputs=[("fake", {})],
                rag_query="ransomware",
            )
        )
        assert report.rag_context
        assert report.rag_context[0]["text"] == "canned rag result"

    def test_export_markdown(self) -> None:
        service = _build_service()
        out = service.export(_sample_report(), ReportFormat.MARKDOWN)
        assert isinstance(out, str)
        assert "# Ransomware on web-01" in out
        assert "## Executive Summary" in out
        assert "## Affected Assets" in out
        assert "## Indicators of Compromise" in out

    def test_export_json(self) -> None:
        service = _build_service()
        out = service.export(_sample_report(), ReportFormat.JSON)
        assert isinstance(out, str)
        data = json.loads(out)
        assert data["incident_title"] == "Ransomware on web-01"

    def test_export_pdf(self) -> None:
        service = _build_service()
        out = service.export(_sample_report(), ReportFormat.PDF)
        assert isinstance(out, bytes)
        assert out.startswith(b"%PDF")

    def test_export_to_output_path(self) -> None:
        service = _build_service()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "report.md"
            result = service.export(
                _sample_report(),
                ReportFormat.MARKDOWN,
                output_path=str(path),
            )
            assert result == str(path)
            assert path.exists()
            assert path.read_text().startswith("#")

    def test_export_all(self) -> None:
        service = _build_service()
        with tempfile.TemporaryDirectory() as tmp:
            paths = service.export_all(_sample_report(), output_dir=tmp)
            assert set(paths) == {"markdown", "json", "pdf"}
            assert Path(paths["markdown"]).exists()
            assert Path(paths["json"]).exists()
            assert Path(paths["pdf"]).exists()


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------


class TestFormatters:
    def test_to_markdown_sections(self) -> None:
        md = to_markdown(_sample_report())
        for section in (
            "## Executive Summary",
            "## Timeline",
            "## Affected Assets",
            "## Indicators of Compromise",
            "## MITRE ATT&CK Mapping",
            "## Nmap Findings",
            "## VirusTotal Findings",
            "## Shodan Findings",
            "## Wazuh Alerts",
            "## Risk Assessment",
            "## Recommendations",
            "## Analyst Notes",
            "## RAG Context",
        ):
            assert section in md

    def test_to_json_roundtrip(self) -> None:
        data = json.loads(to_json(_sample_report()))
        assert data["severity"] == "Critical"
        assert data["risk_assessment"]["score"] == 0.9

    def test_to_pdf_returns_pdf_bytes(self) -> None:
        pdf = to_pdf(_sample_report())
        assert isinstance(pdf, bytes)
        assert pdf.startswith(b"%PDF")

    def test_format_report_unknown(self) -> None:
        try:
            format_report(_sample_report(), "bogus")  # type: ignore[arg-type]
        except ValueError:
            pass
        else:
            raise AssertionError("Expected ValueError for unknown format")


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


class TestSafeFilename:
    def test_sanitizes_title(self) -> None:
        assert _safe_filename("Ransomware / web-01") == "Ransomware___web-01"
        assert _safe_filename("") == "incident_report"
