"""Data models for the Sentrix Intelligent Workflow Planner.

These dataclasses describe a *planned* multi-tool workflow segment and the
results produced once it has been orchestrated. They are deliberately
transport-neutral (no references to the HTTP layer) so the planner stays a
pure, testable domain concern.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.tools.base import ToolResult


@dataclass(frozen=True)
class PlannedStep:
    """A single tool invocation within a planned workflow.

    :param tool_name: Name of the tool to run (e.g. ``shodan``, ``nmap``).
    :param input_data: The input dict passed to the tool's ``execute``.
    :param reason: Human-readable reason this step is included.
    """

    tool_name: str
    input_data: dict[str, Any]
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialize the step for logging/streaming payloads."""
        return {
            "tool": self.tool_name,
            "input": self.input_data,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class WorkflowPlan:
    """An ordered set of tool steps to execute for a user message.

    :param message: The original user message that produced this plan.
    :param steps: Ordered list of :class:`PlannedStep`.
    :param intent: A short label describing the detected intent.
    :param generate_report: Whether to auto-generate an incident report after
        the tool results are collected.
    :param incident_title: Optional incident title used when a report is
        generated.
    """

    message: str
    steps: list[PlannedStep] = field(default_factory=list)
    intent: str = ""
    generate_report: bool = False
    incident_title: str = ""

    @property
    def tool_names(self) -> tuple[str, ...]:
        """Names of the tools in this plan, in execution order."""
        return tuple(step.tool_name for step in self.steps)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the plan for logging/streaming payloads."""
        return {
            "intent": self.intent,
            "steps": [step.to_dict() for step in self.steps],
            "generate_report": self.generate_report,
            "incident_title": self.incident_title,
        }


@dataclass
class WorkflowResult:
    """The aggregated output of orchestrating a :class:`WorkflowPlan`.

    :param plan: The plan that was executed.
    :param results: One :class:`ToolResult` per planned step (same order).
    :param report: Optional serialized :class:`IncidentReport.to_dict` output
        when the workflow generated a report.
    """

    plan: WorkflowPlan
    results: list[ToolResult] = field(default_factory=list)
    report: dict[str, Any] | None = None

    @property
    def tools_used(self) -> tuple[str, ...]:
        """Names of the tools that executed successfully."""
        return tuple(
            r.tool for r in self.results if r.success
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize the result for logging/streaming payloads."""
        return {
            "plan": self.plan.to_dict(),
            "results": [
                {
                    "tool": r.tool,
                    "success": r.success,
                    "error": r.error,
                }
                for r in self.results
            ],
            "report": self.report,
        }


__all__ = [
    "PlannedStep",
    "WorkflowPlan",
    "WorkflowResult",
]
