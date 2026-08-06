"""Sentrix Intelligent Workflow Planner.

Phase 14 introduces a deterministic orchestration layer that maps a user
message to an ordered set of security tools, executes them through the
existing Tool Engine, aggregates the results, and optionally assembles an
:class:`~app.reports.models.IncidentReport` when the workflow warrants one.

The planner is intentionally additive: it reuses the existing
:class:`~app.tools.executor.ToolExecutor`, :class:`~app.mitre.mapper.MitreMapper`,
:class:`~app.rag.service.RagService`, and :class:`~app.reports.service.ReportService`
without changing any of their contracts. The kernel's single-tool
:class:`~app.kernel.tool_integration.ToolCoordinator` path remains unchanged.
"""

from app.planner.engine import PlannerEngine, detect_workflow
from app.planner.models import (
    PlannedStep,
    WorkflowPlan,
    WorkflowResult,
)
from app.planner.orchestrator import WorkflowOrchestrator
from app.planner.router import IntentRouter

__all__ = [
    "IntentRouter",
    "PlannedStep",
    "PlannerEngine",
    "WorkflowOrchestrator",
    "WorkflowPlan",
    "WorkflowResult",
    "detect_workflow",
]
