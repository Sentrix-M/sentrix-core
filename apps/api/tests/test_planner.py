"""Tests for the Intelligent SOC Workflow Planner (Phase 14).

Covers the planner engine (intent → tool selection), the workflow
orchestrator (multi-tool execution + MITRE enrichment + report generation),
and the backward-compatible ``plan_and_execute`` bridge in
:class:`~app.kernel.tool_integration.ToolCoordinator`.

All tools are offline fakes so the tests never touch the network or require
API keys.
"""

from __future__ import annotations

import asyncio
from typing import Any, ClassVar

from app.kernel.integration import build_kernel_pipeline
from app.kernel.response_builder import KernelResponse
from app.kernel.tool_integration import ToolCoordinator
from app.planner.engine import PlannerEngine, detect_workflow
from app.planner.models import PlannedStep, WorkflowPlan, WorkflowResult
from app.planner.orchestrator import WorkflowOrchestrator
from app.reports.service import ReportService
from app.tools.base import (
    ToolHealth,
    ToolPermission,
    ToolResult,
)
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry

# Permissions granted to the seeded admin role (all tools).
ADMIN_TOOL_PERMISSIONS = {
    "threatintel:read",
    "nmap:scan",
    "wazuh:read",
}


# ---------------------------------------------------------------------------
# Offline fake tools
# ---------------------------------------------------------------------------


class _FakeShodanTool:
    """Offline stand-in for the Shodan tool."""

    name = "shodan"
    description = "Fake Shodan for planner tests."
    version = "0.0.0"
    permissions: ClassVar[set[ToolPermission]] = {
        ToolPermission(resource="threatintel", action="read"),
    }

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    @property
    def output_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    async def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        return ToolResult.ok(
            self.name,
            {
                "query": query,
                "ip": "8.8.8.8",
                "organization": "Google LLC",
                "ports": [53, 443],
                "services": [{"port": 443, "product": "nginx"}],
                "vulnerabilities": [],
                "risk_score": "medium",
            },
        )

    async def health(self) -> ToolHealth:
        return ToolHealth(ok=True)


class _FakeVirusTotalTool:
    """Offline stand-in for the VirusTotal tool."""

    name = "virustotal"
    description = "Fake VirusTotal for planner tests."
    version = "0.0.0"
    permissions: ClassVar[set[ToolPermission]] = {
        ToolPermission(resource="threatintel", action="read"),
    }

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        }

    @property
    def output_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult.ok(
            self.name,
            {
                "query": kwargs.get("query", ""),
                "indicator_type": "ip",
                "malicious": 3,
                "suspicious": 1,
                "harmless": 60,
                "tags": ["botnet", "malicious"],
            },
        )

    async def health(self) -> ToolHealth:
        return ToolHealth(ok=True)


class _FakeNmapTool:
    """Offline stand-in for the Nmap tool."""

    name = "nmap"
    description = "Fake Nmap for planner tests."
    version = "0.0.0"
    permissions: ClassVar[set[ToolPermission]] = {
        ToolPermission(resource="tools", action="execute"),
    }

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"host": {"type": "string"}},
            "required": ["host"],
        }

    @property
    def output_schema(self) -> dict[str, Any]:
        return {"type": "object"}

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult.ok(
            self.name,
            {
                "target": kwargs.get("host", ""),
                "hosts": [
                    {
                        "ip": kwargs.get("host", ""),
                        "open_ports": [
                            {"port": 22, "service": "ssh", "protocol": "tcp"},
                            {"port": 80, "service": "http", "protocol": "tcp"},
                        ],
                    }
                ],
            },
        )

    async def health(self) -> ToolHealth:
        return ToolHealth(ok=True)


def _build_executor() -> ToolExecutor:
    """Build a ToolExecutor with the offline fake tools registered."""
    registry = ToolRegistry()
    registry.register(_FakeShodanTool())
    registry.register(_FakeVirusTotalTool())
    registry.register(_FakeNmapTool())
    return ToolExecutor(registry)


# ---------------------------------------------------------------------------
# Planner engine
# ---------------------------------------------------------------------------


class TestPlannerEngine:
    def test_scan_intent_selects_nmap(self) -> None:
        plan = PlannerEngine().plan("Scan host 192.168.1.15")
        assert plan.intent == "network_scan"
        assert plan.tool_names == ("nmap",)
        assert plan.steps[0].input_data["host"] == "192.168.1.15"
        assert plan.generate_report is False

    def test_threat_intel_chains_shodan_then_virustotal(self) -> None:
        plan = PlannerEngine().plan("Analyze 8.8.8.8")
        assert plan.tool_names == ("shodan", "virustotal")
        assert plan.generate_report is True

    def test_threat_intel_hash_skips_shodan(self) -> None:
        plan = PlannerEngine().plan(
            "Analyze 44d88612fea8a8f36de82e1278abb02f"
        )
        assert plan.tool_names == ("virustotal",)

    def test_alert_intent_selects_wazuh_and_generates_report(self) -> None:
        plan = PlannerEngine().plan("Show recent security alerts")
        assert plan.tool_names == ("wazuh",)
        assert plan.generate_report is True

    def test_report_intent_no_steps(self) -> None:
        plan = PlannerEngine().plan("Generate an incident report")
        assert plan.intent == "report"
        assert plan.tool_names == () or plan.steps == []
        assert plan.generate_report is True

    def test_unknown_intent_empty_plan(self) -> None:
        plan = PlannerEngine().plan("What is the weather?")
        assert plan.intent == "unknown"
        assert plan.steps == []
        assert plan.generate_report is False

    def test_detect_workflow_helper(self) -> None:
        plan = detect_workflow("Analyze 8.8.8.8")
        assert isinstance(plan, WorkflowPlan)
        assert plan.tool_names == ("shodan", "virustotal")


# ---------------------------------------------------------------------------
# Workflow orchestrator
# ---------------------------------------------------------------------------


class TestWorkflowOrchestrator:
    def test_executes_all_steps_in_order(self) -> None:
        plan = detect_workflow("Analyze 8.8.8.8")
        orchestrator = WorkflowOrchestrator(executor=_build_executor())
        result = asyncio.run(orchestrator.run(plan))

        assert isinstance(result, WorkflowResult)
        assert [r.tool for r in result.results] == ["shodan", "virustotal"]
        assert result.tools_used == ("shodan", "virustotal")

    def test_mitre_enriches_successful_results(self) -> None:
        plan = detect_workflow("Analyze 8.8.8.8")
        orchestrator = WorkflowOrchestrator(executor=_build_executor())
        result = asyncio.run(orchestrator.run(plan))

        for r in result.results:
            assert r.success
            assert "mitre" in r.metadata

    def test_on_progress_called_per_step(self) -> None:
        plan = detect_workflow("Analyze 8.8.8.8")
        orchestrator = WorkflowOrchestrator(executor=_build_executor())

        progress: list[tuple[str, bool]] = []

        def _cb(step: PlannedStep, success: bool) -> None:
            progress.append((step.tool_name, success))

        asyncio.run(orchestrator.run(plan, on_progress=_cb))
        assert progress == [("shodan", True), ("virustotal", True)]

    def test_generates_report_when_requested(self) -> None:
        plan = detect_workflow("Analyze 8.8.8.8")
        report_service = ReportService(executor=_build_executor())
        orchestrator = WorkflowOrchestrator(
            executor=_build_executor(),
            report_service=report_service,
        )
        result = asyncio.run(orchestrator.run(plan))

        assert result.report is not None
        assert "incident_title" in result.report
        assert result.report["incident_title"] == "Security Incident"

    def test_failed_step_does_not_crash_orchestrator(self) -> None:
        plan = WorkflowPlan(
            message="Analyze 8.8.8.8",
            steps=[
                PlannedStep(tool_name="shodan", input_data={"query": "8.8.8.8"}),
                PlannedStep(tool_name="nmap", input_data={"host": "8.8.8.8"}),
            ],
            intent="threat_intel",
        )
        # A registry without threatintel:read permission blocks shodan.
        registry = ToolRegistry()
        registry.register(_FakeNmapTool())
        executor = ToolExecutor(registry)

        orchestrator = WorkflowOrchestrator(executor=executor)
        result = asyncio.run(
            orchestrator.run(plan, user_permissions={"tools:execute"})
        )
        assert result.results[0].success is False
        assert result.results[1].success is True


# ---------------------------------------------------------------------------
# ToolCoordinator plan_and_execute bridge
# ---------------------------------------------------------------------------


class TestPlanAndExecute:
    def test_multi_tool_returns_aggregated_result(self) -> None:
        coordinator = ToolCoordinator(_build_executor())
        workflow = coordinator.plan_and_execute(
            "Analyze 8.8.8.8",
            user_permissions=ADMIN_TOOL_PERMISSIONS,
        )
        assert workflow is not None
        assert [r.tool for r in workflow.results] == ["shodan", "virustotal"]

    def test_single_tool_falls_back_to_legacy_path(self) -> None:
        coordinator = ToolCoordinator(_build_executor())
        workflow = coordinator.plan_and_execute(
            "Scan host 192.168.1.15",
            user_permissions={*(ADMIN_TOOL_PERMISSIONS), "tools:execute"},
        )
        assert workflow is not None
        assert workflow.results[0].tool == "nmap"
        assert workflow.results[0].success is True

    def test_no_intent_returns_none(self) -> None:
        coordinator = ToolCoordinator(_build_executor())
        assert coordinator.plan_and_execute("What is the weather?") is None


# ---------------------------------------------------------------------------
# Kernel pipeline multi-tool integration
# ---------------------------------------------------------------------------


class TestKernelPipelineMultiTool:
    def test_multi_tool_workflow_reports_all_tools_used(self) -> None:
        pipeline = build_kernel_pipeline(tool_executor=_build_executor())
        response = pipeline.run(
            conversation_id="planner-1",
            message="Analyze 8.8.8.8",
            user_permissions=ADMIN_TOOL_PERMISSIONS,
        )
        assert isinstance(response, KernelResponse)
        assert response.content
        assert "shodan" in response.tools_used
        assert "virustotal" in response.tools_used

    def test_plain_message_no_tools(self) -> None:
        pipeline = build_kernel_pipeline(tool_executor=_build_executor())
        response = pipeline.run(
            conversation_id="planner-2",
            message="What is a SIEM?",
            user_permissions=ADMIN_TOOL_PERMISSIONS,
        )
        assert response.tools_used == ()
        assert response.content
