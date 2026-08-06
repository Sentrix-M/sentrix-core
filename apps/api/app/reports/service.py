"""Report Service — orchestrates incident report generation and export.

:class:`ReportService` is the application-layer seam for the Phase 13
reporting feature. It ties together the Tool Engine (via
:class:`~app.tools.executor.ToolExecutor`), the RAG knowledge layer (via an
optional :class:`~app.rag.service.RagService`), the :class:`ReportEngine`, and
the formatters.

The service returns formatted output (strings/bytes) rather than writing
files, so the caller (API or frontend) decides whether to stream or persist
the result. An optional ``output_path`` is supported for future CLI usage.

When an optional :class:`~app.memory.service.MemoryService` is provided
(Phase 15B), every generated report is persisted to long-term memory and the
user's preferred report format is honoured automatically (best-effort). When
omitted, the service behaves exactly as before (backward compatible).
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.providers.base import BaseProvider
from app.rag.service import RagService
from app.reports.engine import ReportEngine
from app.reports.formatters import format_report
from app.reports.models import (
    IncidentReport,
    ReportFormat,
)
from app.tools.base import ToolResult
from app.tools.executor import ToolExecutor

if TYPE_CHECKING:
    from app.memory.service import MemoryService

#: Default tool execution timeout used when collecting tool results.
DEFAULT_TOOL_TIMEOUT = 30.0

#: Location of the report engine's ``__init__`` marker (future CLI default).
_GENERATED_BY = "Sentrix Incident Report Generator"


class ReportService:
    """Collect investigation data, build a report, and export it.

    :param executor: The :class:`ToolExecutor` used to run the supporting
        tools (nmap, virustotal, shodan, wazuh).
    :param engine: Optional :class:`ReportEngine`. Defaults to one built from
        the provided ``provider``.
    :param provider: Optional :class:`BaseProvider` for the executive summary.
        Ignored when ``engine`` is provided explicitly.
    :param rag_service: Optional :class:`RagService` for knowledge context.
    :param memory_service: Optional :class:`MemoryService` used to persist
        generated reports and read the user's report-format preference. When
        omitted (default), no persistence occurs (backward compatible).
    """

    def __init__(
        self,
        *,
        executor: ToolExecutor,
        engine: ReportEngine | None = None,
        provider: BaseProvider | None = None,
        rag_service: RagService | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self._executor = executor
        self._engine = engine or ReportEngine(provider=provider)
        self._rag_service = rag_service
        self._memory_service = memory_service

    @property
    def executor(self) -> ToolExecutor:
        """The wrapped tool executor."""
        return self._executor

    @property
    def engine(self) -> ReportEngine:
        """The wrapped report engine."""
        return self._engine

    @property
    def rag_service(self) -> RagService | None:
        """The optional RAG service."""
        return self._rag_service

    @property
    def memory_service(self) -> MemoryService | None:
        """The optional memory service ("None" when not wired)."""
        return self._memory_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def collect_results(
        self,
        *,
        tool_inputs: list[tuple[str, dict[str, Any]]],
        user_permissions: set[str] | None = None,
        timeout: float | None = None,
    ) -> list[ToolResult]:
        """Run a list of tools and return their results.

        :param tool_inputs: List of ``(tool_name, input_dict)`` pairs.
        :param user_permissions: Optional permission set passed to the executor.
        :param timeout: Per-tool execution timeout.
        :returns: The list of :class:`ToolResult` (some may be failures).
        """
        results: list[ToolResult] = []
        for tool_name, input_data in tool_inputs:
            result = await self._executor.execute(
                tool_name=tool_name,
                input_data=input_data,
                user_permissions=user_permissions,
                timeout=timeout,
            )
            results.append(result)
        return results

    async def generate(
        self,
        *,
        incident_title: str,
        tool_inputs: list[tuple[str, dict[str, Any]]] | None = None,
        tool_results: list[ToolResult] | None = None,
        user_permissions: set[str] | None = None,
        rag_query: str | None = None,
        analyst_notes: list[str] | None = None,
        recommendations: list[str] | None = None,
        timeout: float | None = None,
    ) -> IncidentReport:
        """Collect tool results, enrich with RAG, and build an :class:`IncidentReport`.

        When ``tool_results`` is provided, those pre-collected results are used
        directly (e.g. results already gathered by the Planner/Workflow) and no
        additional tools are executed. Otherwise ``tool_inputs`` are executed
        through the tool executor.

        :param incident_title: Short incident title.
        :param tool_inputs: List of ``(tool_name, input_dict)`` pairs to run.
            Ignored when ``tool_results`` is provided.
        :param tool_results: Optional pre-collected :class:`ToolResult` list.
            When provided, no tools are executed and these results are used.
        :param user_permissions: Optional permission set for tool execution.
        :param rag_query: Optional RAG query. When omitted, the engine builds
            one automatically from the tool evidence.
        :param analyst_notes: Optional analyst observations.
        :param recommendations: Optional remediation recommendations.
        :param timeout: Per-tool execution timeout.
        :returns: A populated :class:`IncidentReport`.
        """
        if tool_results is not None:
            results = tool_results
        else:
            results = await self.collect_results(
                tool_inputs=tool_inputs or [],
                user_permissions=user_permissions,
                timeout=timeout,
            )

        rag_context = None
        if self._rag_service is not None:
            query = rag_query or incident_title
            try:
                rag_context = await self._rag_service.search(query, top_k=5)
            except Exception:  # noqa: BLE001 - RAG is best-effort
                rag_context = None

        report = self._engine.generate(
            incident_title=incident_title,
            tool_results=results,
            rag_context=rag_context,
            query=rag_query,
            analyst_notes=analyst_notes,
            recommendations=recommendations,
        )

        self._record_report(report)

        return report

    def resolve_report_format(
        self,
        *,
        user_id: str,
        default: ReportFormat = ReportFormat.MARKDOWN,
    ) -> ReportFormat:
        """Resolve the preferred report format for a user (Phase 15B).

        Consults the memory-backed ``report_format`` preference when a memory
        service is wired; otherwise returns ``default``. Invalid stored
        values fall back to ``default``.
        """
        if self._memory_service is None:
            return default
        try:
            preferred = self._memory_service.get_report_format_preference(
                user_id=user_id,
                default=default.value,
            )
            return ReportFormat(preferred)
        except (Exception, ValueError):  # noqa: BLE001 - preference is best-effort
            return default

    def export(
        self,
        report: IncidentReport,
        fmt: ReportFormat,
        *,
        output_path: str | None = None,
    ) -> str | bytes:
        """Format a report and optionally persist it.

        :param report: The report to format.
        :param fmt: Desired :class:`ReportFormat`.
        :param output_path: Optional file path. When provided, the formatted
            output is written to disk and the path is returned.
        :returns: The Markdown/JSON string, PDF bytes, or the output path when
            ``output_path`` is provided.
        """
        formatted = format_report(report, fmt)
        if output_path is not None:
            path = Path(output_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            data = formatted.encode("utf-8") if isinstance(formatted, str) else formatted
            path.write_bytes(data)
            return str(path)
        return formatted

    def export_all(
        self,
        report: IncidentReport,
        *,
        output_dir: str,
    ) -> dict[str, str]:
        """Export a report in all supported formats to ``output_dir``.

        :param report: The report to export.
        :param output_dir: Directory to write the files into.
        :returns: Map of format name → written file path.
        """
        directory = Path(output_dir)
        directory.mkdir(parents=True, exist_ok=True)
        base = _safe_filename(report.incident_title)
        paths: dict[str, str] = {}
        for fmt, ext in (
            (ReportFormat.MARKDOWN, "md"),
            (ReportFormat.JSON, "json"),
            (ReportFormat.PDF, "pdf"),
        ):
            output_path = directory / f"{base}.{ext}"
            result = self.export(report, fmt, output_path=str(output_path))
            paths[fmt.value] = str(result)
        return paths

    # ------------------------------------------------------------------
    # Memory integration (Phase 15B)
    # ------------------------------------------------------------------

    def _record_report(self, report: IncidentReport) -> None:
        """Persist a generated report to memory (best-effort)."""
        if self._memory_service is None:
            return
        with suppress(Exception):
            self._memory_service.record_report(
                title=report.incident_title,
                report_format=report.report_format.value,
                severity=report.severity.value,
                summary=report.executive_summary,
                payload=report.to_dict(),
            )


def _safe_filename(title: str) -> str:
    """Convert an incident title into a filesystem-safe filename."""
    cleaned = "".join(
        c if c.isalnum() or c in " _-" else "_" for c in title
    ).strip().replace(" ", "_")
    return cleaned or "incident_report"


__all__ = ["ReportService", "_safe_filename"]
