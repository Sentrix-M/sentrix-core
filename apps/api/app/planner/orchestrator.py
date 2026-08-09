"""Workflow orchestrator — execute a plan through the Tool Engine.

:class:`WorkflowOrchestrator` runs a :class:`~app.planner.models.WorkflowPlan`
using the existing :class:`~app.tools.executor.ToolExecutor`. It:

1. Executes each :class:`~app.planner.models.PlannedStep` in order.
2. MITRE-enriches each successful result (reusing
   :func:`~app.mitre.integration.enrich_tool_result`).
3. Invokes an optional ``on_progress`` callback after every step so the
   streaming layer can emit live ``status`` events.
4. When the plan requests a report, feeds the collected results into the
   :class:`~app.reports.service.ReportService` (which reuses the
   :class:`~app.reports.engine.ReportEngine` for MITRE + RAG + provider
   summary) and stores the serialized report.

No new execution primitive is introduced — this is a thin orchestration
loop over the existing stack.

When an optional :class:`~app.memory.service.MemoryService` is provided
(Phase 15B), each tool execution and each completed investigation is recorded
to long-term memory (best-effort). When omitted, the orchestrator behaves
exactly as before (backward compatible).
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import suppress
from typing import TYPE_CHECKING, Any

from app.mitre.integration import enrich_tool_result
from app.mitre.mapper import MitreMapper
from app.planner.models import PlannedStep, WorkflowPlan, WorkflowResult
from app.reports.models import IncidentReport
from app.tools.base import ToolResult
from app.tools.executor import ToolExecutor

if TYPE_CHECKING:
    from app.memory.service import MemoryService
    from app.reports.service import ReportService

logger = logging.getLogger(__name__)

#: Signature of the optional progress callback.
ProgressCallback = Callable[[PlannedStep, bool], None]


class WorkflowOrchestrator:
    """Execute a :class:`WorkflowPlan` and aggregate the results.

    :param executor: The :class:`ToolExecutor` used to run each step.
    :param report_service: Optional :class:`ReportService`. When provided and
        the plan requests a report, the collected tool results are passed to
        it for report generation. When omitted, report generation is skipped
        even if ``generate_report`` is set.
    :param mitre_mapper: Optional :class:`MitreMapper`. Defaults to a fresh
        instance so MITRE enrichment is self-contained.
    :param memory_service: Optional :class:`MemoryService` used to record tool
        executions and investigations. When omitted (default), no persistence
        occurs (backward compatible).
    """

    def __init__(
        self,
        *,
        executor: ToolExecutor,
        report_service: ReportService | None = None,
        mitre_mapper: MitreMapper | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        self._executor = executor
        self._report_service = report_service
        self._mitre_mapper = mitre_mapper
        self._memory_service = memory_service

    @property
    def executor(self) -> ToolExecutor:
        """The wrapped tool executor."""
        return self._executor

    @property
    def report_service(self) -> ReportService | None:
        """The optional report service."""
        return self._report_service

    @property
    def memory_service(self) -> MemoryService | None:
        """The optional memory service ("None" when not wired)."""
        return self._memory_service

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def run(
        self,
        plan: WorkflowPlan,
        *,
        user_permissions: set[str] | None = None,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> WorkflowResult:
        """Execute ``plan`` and aggregate the results.

        :param plan: The plan to execute.
        :param user_permissions: Optional permission set for tool execution.
        :param timeout: Per-step execution timeout.
        :param on_progress: Optional callback invoked after each step with
            ``(PlannedStep, success)``.
        :returns: A :class:`WorkflowResult` with one :class:`ToolResult` per
            planned step (same order) and an optional serialized report.
        """
        results: list[ToolResult] = []
        for step in plan.steps:
            result = await self._executor.execute(
                tool_name=step.tool_name,
                input_data=step.input_data,
                user_permissions=user_permissions,
                timeout=timeout,
            )
            if result.success:
                result.metadata["mitre"] = enrich_tool_result(
                    result, mapper=self._mitre_mapper
                )
            results.append(result)
            self._record_tool_execution(step, result)
            if on_progress is not None:
                on_progress(step, result.success)

        report: dict[str, Any] | None = None
        if plan.generate_report and self._report_service is not None:
            report = await self._generate_report(plan, results)

        self._record_investigation(plan, results, report)

        return WorkflowResult(plan=plan, results=results, report=report)

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    async def _generate_report(
        self,
        plan: WorkflowPlan,
        results: list[ToolResult],
    ) -> dict[str, Any]:
        """Assemble an incident report from the collected results.

        The collected results are passed to the public
        :meth:`~app.reports.service.ReportService.generate` API, which reuses
        :class:`~app.reports.engine.ReportEngine` for MITRE + RAG + provider
        summary and records the generated report to long-term memory when a
        :class:`~app.memory.service.MemoryService` is wired. Passing
        ``tool_results`` avoids re-running any tools.
        """
        assert self._report_service is not None  # guard for mypy/logic
        incident_title = plan.incident_title or "Security Incident"

        try:
            report: IncidentReport = await self._report_service.generate(
                incident_title=incident_title,
                tool_results=results,
            )
        except Exception as exc:  # noqa: BLE001 - surface as structured failure
            logger.warning("Workflow report generation failed: %s", exc)
            return {
                "error": str(exc),
                "incident_title": incident_title,
            }
        return report.to_dict()

    # ------------------------------------------------------------------
    # Memory integration (Phase 15B)
    # ------------------------------------------------------------------

    def _record_tool_execution(
        self,
        step: PlannedStep,
        result: ToolResult,
    ) -> None:
        """Record a single tool execution to memory (best-effort)."""
        if self._memory_service is None:
            return
        with suppress(Exception):
            self._memory_service.record_tool_execution(
                tool_name=step.tool_name,
                success=result.success,
                input=step.input_data,
                output=result.output if isinstance(result.output, dict) else None,
                error=result.error or "",
            )

    def _record_investigation(
        self,
        plan: WorkflowPlan,
        results: list[ToolResult],
        report: dict[str, Any] | None,
    ) -> None:
        """Record a completed investigation to memory (best-effort)."""
        if self._memory_service is None:
            return
        title = plan.incident_title or "Security Investigation"
        summary = report.get("executive_summary", "") if isinstance(report, dict) else ""
        findings = [
            {
                "tool": result.tool,
                "success": result.success,
                "output": result.output,
                "error": result.error,
            }
            for result in results
        ]
        with suppress(Exception):
            self._memory_service.record_investigation(
                title=title,
                target=",".join(
                    str(step.input_data.get("host", ""))
                    for step in plan.steps
                    if step.input_data.get("host")
                ),
                summary=summary,
                findings=findings,
            )

    def run_sync(
        self,
        plan: WorkflowPlan,
        *,
        user_permissions: set[str] | None = None,
        timeout: float | None = None,
        on_progress: ProgressCallback | None = None,
    ) -> WorkflowResult:
        """Run the workflow synchronously (kernel-friendly bridge).

        The kernel pipeline is synchronous; this helper runs the async
        orchestrator to completion in a loop-safe way.
        """
        import asyncio  # noqa: PLC0415

        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                self.run(
                    plan,
                    user_permissions=user_permissions,
                    timeout=timeout,
                    on_progress=on_progress,
                )
            )

        # Running inside an event loop: execute in a dedicated worker thread.
        import threading  # noqa: PLC0415

        result_box: dict[str, Any] = {}
        error_box: dict[str, Any] = {}

        def _worker() -> None:
            try:
                result_box["value"] = asyncio.run(
                    self.run(
                        plan,
                        user_permissions=user_permissions,
                        timeout=timeout,
                        on_progress=on_progress,
                    )
                )
            except BaseException as exc:  # noqa: BLE001 - re-raised
                error_box["error"] = exc

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        thread.join()
        if "error" in error_box:
            raise error_box["error"]
        return result_box["value"]


__all__ = ["WorkflowOrchestrator"]
