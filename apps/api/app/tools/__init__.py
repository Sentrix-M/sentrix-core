"""Sentrix Tool Engine.

Provides the tool abstraction, registry, router, executor, sandbox, and
mock tool implementations for the Sentrix AI cybersecurity platform.

The tool engine is a standalone foundation. The next sprint will connect
the Tool Router to the Kernel pipeline.
"""

from app.tools.base import BaseTool, ToolHealth, ToolPermission, ToolResult, ToolStatus
from app.tools.executor import (
    ToolCancelledError,
    ToolExecutionError,
    ToolExecutor,
    ToolPermissionError,
    ToolTimeoutError,
)
from app.tools.mock_tools import (
    MockFilesystemTool,
    MockPythonTool,
    MockTerminalTool,
)
from app.tools.nmap_tool import NmapTool
from app.tools.registry import ToolRegistry
from app.tools.report_generator_tool import ReportGeneratorTool
from app.tools.router import ToolRouter
from app.tools.sandbox import MockSandbox, Sandbox
from app.tools.shodan_tool import ShodanTool
from app.tools.virustotal_tool import VirusTotalTool
from app.tools.wazuh_tool import WazuhTool

__all__ = [
    "BaseTool",
    "MockFilesystemTool",
    "MockPythonTool",
    "MockSandbox",
    "MockTerminalTool",
    "NmapTool",
    "ReportGeneratorTool",
    "Sandbox",
    "ShodanTool",
    "VirusTotalTool",
    "WazuhTool",
    "ToolCancelledError",
    "ToolExecutionError",
    "ToolExecutor",
    "ToolHealth",
    "ToolPermission",
    "ToolPermissionError",
    "ToolRegistry",
    "ToolResult",
    "ToolRouter",
    "ToolStatus",
    "ToolTimeoutError",
]
