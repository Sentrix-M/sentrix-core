"""Incident Report Generator tool for the Sentrix Tool Engine.

:class:`ReportGeneratorTool` implements the existing
:class:`~app.tools.base.BaseTool` interface. When invoked, it collects
investigation context from the configured supporting tools (via the Tool
Engine), builds an :class:`~app.reports.models.IncidentReport` through the
:class:`~app.reports.engine.ReportEngine`, and returns the formatted report
(Markdown, JSON, or PDF) as the tool output.

The tool is intentionally thin — it delegates all collection/formatting to the
:class:`~app.reports.service.ReportService` so the reporting logic stays in
one place and remains testable in isolation.
"""

from __future__ import annotations

from typing import Any, ClassVar

from app.reports.models import IncidentReport, ReportFormat
from app.reports.service import ReportService
from app.tools.base import (
    ToolHealth,
    ToolPermission,
    ToolResult,
)

#: Default incident title used when the caller does not provide one.
DEFAULT_TITLE = "Security Incident"

#: Default list of supporting tools to run when collecting investigation data.
DEFAULT_TOOL_INPUTS: list[tuple[str, dict[str, Any]]] = [
    ("virustotal", {"query": "44d88612fea8a8f36de82e1278abb02f"}),
]


class ReportGeneratorTool:
    """Generate an incident report from collected investigation data.

    :param service: The :class:`ReportService` used to collect tool results,
        build the report, and export it.
    :param format_name: Default export format (``markdown``, ``json``, or
        ``pdf``). Defaults to ``markdown``.
    """

    name = "report_generator"
    description = (
        "Collect investigation context from security tools and generate a "
        "structured incident report (Markdown, JSON, or PDF)."
    )
    version = "0.1.0"
    permissions: ClassVar[set[ToolPermission]] = {
        ToolPermission(resource="reports", action="generate"),
    }

    def __init__(
        self,
        *,
        service: ReportService,
        format_name: str = "markdown",
    ) -> None:
        self._service = service
        self._format_name = format_name

    # ------------------------------------------------------------------
    # BaseTool contract
    # ------------------------------------------------------------------

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema describing the accepted report options."""
        return {
            "type": "object",
            "properties": {
                "incident_title": {
                    "type": "string",
                    "description": "Short title for the incident.",
                },
                "tool_inputs": {
                    "type": "array",
                    "description": (
                        "Optional list of [tool_name, input_dict] pairs to run. "
                        "Defaults to a small set of supporting tools."
                    ),
                },
                "format": {
                    "type": "string",
                    "enum": ["markdown", "json", "pdf"],
                    "description": "Report export format.",
                },
                "rag_query": {
                    "type": "string",
                    "description": "Optional RAG search query.",
                },
            },
            "required": [],
        }

    @property
    def output_schema(self) -> dict[str, Any]:
        """JSON Schema describing the structured report output."""
        return {
            "type": "object",
            "properties": {
                "format": {"type": "string"},
                "report_id": {"type": "string"},
                "incident_title": {"type": "string"},
                "severity": {"type": "string"},
                "content": {"type": "string"},
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Generate an incident report and return the formatted output.

        :param incident_title: Short incident title (optional).
        :param tool_inputs: Optional list of ``[tool_name, input_dict]`` pairs.
        :param format: Report format (``markdown``/``json``/``pdf``).
        :param rag_query: Optional RAG search query.
        """
        title = (kwargs.get("incident_title") or "").strip() or DEFAULT_TITLE
        fmt = self._resolve_format(kwargs.get("format"))
        tool_inputs = self._resolve_tool_inputs(kwargs.get("tool_inputs"))
        rag_query = kwargs.get("rag_query")

        try:
            report: IncidentReport = await self._service.generate(
                incident_title=title,
                tool_inputs=tool_inputs,
                rag_query=rag_query,
            )
        except Exception as exc:  # noqa: BLE001 - surface as structured failure
            return ToolResult.fail(
                self.name,
                f"Failed to generate incident report: {exc}",
            )

        content = self._service.export(report, fmt)
        if isinstance(content, bytes):
            content_text = f"<{len(content)} bytes of {fmt.value} data>"
        else:
            content_text = content

        return ToolResult.ok(
            self.name,
            {
                "format": fmt.value,
                "report_id": report.report_id,
                "incident_title": report.incident_title,
                "severity": report.severity.value,
                "content": content_text,
                "report": report.to_dict(),
            },
        )

    async def health(self) -> ToolHealth:
        """Report whether the report generator is ready.

        The tool is always ready when its :class:`ReportService` is usable.
        """
        return ToolHealth(
            ok=True,
            message="Report generator is available.",
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _resolve_format(self, value: Any) -> ReportFormat:
        """Resolve a format string/object to a :class:`ReportFormat`."""
        if isinstance(value, ReportFormat):
            return value
        if isinstance(value, str):
            for fmt in ReportFormat:
                if fmt.value == value.lower():
                    return fmt
        return ReportFormat(self._format_name)

    def _resolve_tool_inputs(
        self, value: Any
    ) -> list[tuple[str, dict[str, Any]]]:
        """Resolve the tool inputs, falling back to the defaults."""
        if value is None:
            return DEFAULT_TOOL_INPUTS
        if not isinstance(value, list):
            return DEFAULT_TOOL_INPUTS
        inputs: list[tuple[str, dict[str, Any]]] = []
        for item in value:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            name, data = item
            if isinstance(name, str) and isinstance(data, dict):
                inputs.append((name, data))
        return inputs or DEFAULT_TOOL_INPUTS


__all__ = ["DEFAULT_TOOL_INPUTS", "ReportGeneratorTool"]
