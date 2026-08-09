"""Unit tests for the :class:`ReportGeneratorTool`.

Covers the tool's BaseTool contract (name/version/permissions/schemas), its
``execute`` flow (default vs. custom incident title, format resolution,
tool-input resolution, and failure handling), and its ``health`` probe. All
tests are offline: the tool is wired to a :class:`ReportService` backed by a
fake tool executor, so no real network or external tool calls are made.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from app.main import app  # noqa: F401 - must import first to break import cycles
from app.reports.models import ReportFormat
from app.reports.service import ReportService
from app.tools.base import ToolPermission, ToolResult
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry
from app.tools.report_generator_tool import (
    DEFAULT_TOOL_INPUTS,
    ReportGeneratorTool,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _FakeTool:
    """A minimal tool that returns a successful Nmap result."""

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
        return ToolResult.ok(
            "fake",
            {
                "target": "10.0.0.5",
                "hosts": [
                    {
                        "ip": "10.0.0.5",
                        "open_ports": [
                            {"port": 22, "protocol": "tcp", "service": "ssh"}
                        ],
                    }
                ],
            },
        )

    async def health(self) -> Any:
        from app.tools.base import ToolHealth

        return ToolHealth(ok=True, message="ok")


class _BoomTool:
    """A tool that always fails, to exercise the report failure path."""

    name = "boom"
    description = "boom"
    version = "0.1.0"
    permissions: set = set()

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    @property
    def output_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> ToolResult:  # noqa: ARG002
        return ToolResult.fail(self.name, "simulated failure")

    async def health(self) -> Any:
        from app.tools.base import ToolHealth

        return ToolHealth(ok=True, message="ok")


def _build_tool(*, with_boom: bool = False) -> ReportGeneratorTool:
    """Build a ReportGeneratorTool wired to a fake-executor service."""
    registry = ToolRegistry()
    registry.register(_BoomTool() if with_boom else _FakeTool())
    executor = ToolExecutor(registry)
    service = ReportService(executor=executor)
    return ReportGeneratorTool(service=service)


# ---------------------------------------------------------------------------
# Contract
# ---------------------------------------------------------------------------


class TestReportGeneratorToolContract:
    def test_name(self) -> None:
        assert _build_tool().name == "report_generator"

    def test_version(self) -> None:
        assert _build_tool().version == "0.1.0"

    def test_permissions(self) -> None:
        assert (
            ToolPermission(resource="reports", action="generate")
            in _build_tool().permissions
        )

    def test_input_schema(self) -> None:
        tool = _build_tool()
        props = tool.input_schema["properties"]
        assert "incident_title" in props
        assert "tool_inputs" in props
        assert "format" in props
        assert "rag_query" in props

    def test_output_schema(self) -> None:
        tool = _build_tool()
        props = tool.output_schema["properties"]
        assert "format" in props
        assert "incident_title" in props
        assert "severity" in props
        assert "content" in props


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------


class TestReportGeneratorToolExecute:
    def test_default_title_and_format(self) -> None:
        tool = _build_tool()
        result = asyncio.run(tool.execute())
        assert result.success is True
        assert result.output["incident_title"] == "Security Incident"
        assert result.output["format"] == "markdown"
        assert result.output["severity"] == "Low"
        assert "report" in result.output

    def test_custom_title(self) -> None:
        tool = _build_tool()
        result = asyncio.run(tool.execute(incident_title="Custom Incident"))
        assert result.success is True
        assert result.output["incident_title"] == "Custom Incident"

    def test_json_format(self) -> None:
        tool = _build_tool()
        result = asyncio.run(tool.execute(format="json"))
        assert result.success is True
        assert result.output["format"] == "json"
        # The report dict is JSON-serializable.
        json.dumps(result.output["report"])

    def test_pdf_format(self) -> None:
        tool = _build_tool()
        result = asyncio.run(tool.execute(format="pdf"))
        assert result.success is True
        assert result.output["format"] == "pdf"
        assert "bytes of pdf data" in result.output["content"]

    def test_custom_tool_inputs(self) -> None:
        tool = _build_tool()
        result = asyncio.run(
            tool.execute(tool_inputs=[["fake", {"host": "10.0.0.9"}]])
        )
        assert result.success is True

    def test_rag_query_passthrough(self) -> None:
        tool = _build_tool()
        result = asyncio.run(tool.execute(rag_query="ransomware"))
        assert result.success is True

    def test_failing_tool_is_tolerated(self) -> None:
        tool = _build_tool(with_boom=True)
        result = asyncio.run(tool.execute(tool_inputs=[["boom", {}]]))
        assert result.success is True
        assert result.output["incident_title"] == "Security Incident"


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestReportGeneratorToolHealth:
    def test_health_ok(self) -> None:
        tool = _build_tool()
        health = asyncio.run(tool.health())
        assert health.ok is True
        assert "available" in health.message.lower()


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------


class TestDefaults:
    def test_default_tool_inputs(self) -> None:
        assert isinstance(DEFAULT_TOOL_INPUTS, list)
        assert DEFAULT_TOOL_INPUTS  # non-empty
        name, data = DEFAULT_TOOL_INPUTS[0]
        assert isinstance(name, str)
        assert isinstance(data, dict)

    def test_resolve_format_accepts_string(self) -> None:
        tool = _build_tool()
        assert tool._resolve_format("json") == ReportFormat.JSON  # noqa: SLF001
        assert tool._resolve_format("pdf") == ReportFormat.PDF  # noqa: SLF001

    def test_resolve_tool_inputs_fallback(self) -> None:
        tool = _build_tool()
        assert tool._resolve_tool_inputs(None) == DEFAULT_TOOL_INPUTS  # noqa: SLF001
        assert tool._resolve_tool_inputs("nope") == DEFAULT_TOOL_INPUTS  # noqa: SLF001
