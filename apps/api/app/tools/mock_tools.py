"""Mock tool implementations for the Sentrix Tool Engine.

These tools are deterministic, safe, and do NOT execute any real commands.
They are used during development and testing to simulate tool behaviour.

Available mock tools:

- :class:`MockFilesystemTool` — simulates file read/write/list operations
- :class:`MockTerminalTool` — simulates command execution with canned output
- :class:`MockPythonTool` — simulates Python code evaluation
"""

from __future__ import annotations

from typing import Any, ClassVar

from app.tools.base import (
    ToolHealth,
    ToolPermission,
    ToolResult,
)


class MockFilesystemTool:
    """Mock filesystem tool — reads/writes in-memory, no real disk access."""

    name = "filesystem"
    description = "Read, write, and list files in the sandbox (mock)."
    version = "0.1.0"
    permissions: ClassVar[set[ToolPermission]] = {
        ToolPermission(resource="filesystem", action="read"),
        ToolPermission(resource="filesystem", action="write"),
    }

    def __init__(self) -> None:
        # In-memory "disk" — instance-local so tool instances do not share state.
        self._files: dict[str, str] = {}

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["read", "write", "list", "delete"],
                    "description": "File operation to perform.",
                },
                "path": {
                    "type": "string",
                    "description": "File path (mock, no real filesystem access).",
                },
                "content": {
                    "type": "string",
                    "description": "Content to write (required for 'write' action).",
                },
            },
            "required": ["action", "path"],
        }

    @property
    def output_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "content": {"type": "string"},
                "files": {"type": "array", "items": {"type": "string"}},
                "size": {"type": "integer"},
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute a filesystem operation."""
        action = kwargs.get("action", "read")
        path = kwargs.get("path", "/mock/tmp/file.txt")

        if action == "read":
            content = self._files.get(path, "")
            return ToolResult.ok(
                self.name,
                {"content": content, "path": path, "size": len(content)},
            )

        if action == "write":
            content = kwargs.get("content", "")
            self._files[path] = content
            return ToolResult.ok(
                self.name,
                {"path": path, "size": len(content), "written": True},
            )

        if action == "list":
            files = list(self._files.keys())
            return ToolResult.ok(
                self.name,
                {"files": files, "count": len(files), "path": path},
            )

        if action == "delete":
            removed = self._files.pop(path, None)
            return ToolResult.ok(
                self.name,
                {"path": path, "deleted": removed is not None},
            )

        return ToolResult.fail(
            self.name,
            f"Unknown action '{action}'. Supported: read, write, list, delete.",
        )

    async def health(self) -> ToolHealth:
        """Mock filesystem is always healthy."""
        return ToolHealth(ok=True, message="Mock filesystem is available.")


class MockTerminalTool:
    """Mock terminal tool — returns canned output for known commands."""

    name = "terminal"
    description = "Execute shell commands in a sandboxed environment (mock)."
    version = "0.1.0"
    permissions: ClassVar[set[ToolPermission]] = {
        ToolPermission(resource="terminal", action="execute"),
    }

    #: Canned responses keyed by command prefix.
    CANNED: ClassVar[dict[str, str]] = {
        "whoami": "sentrix-user\n",
        "pwd": "/home/sentrix\n",
        "ls -la": "total 0\ndrwxr-xr-x  2 sentrix sentrix   64 Jan 1 00:00 .\ndrwxr-xr-x  3 sentrix sentrix   96 Jan 1 00:00 ..\n",
        "echo hello": "hello\n",
        "date": "2025-01-01T00:00:00Z\n",
        "uname -a": "Linux sentrix-sandbox 6.1.0 x86_64 GNU/Linux\n",
        "df -h": "Filesystem      Size  Used Avail Use% Mounted on\n/dev/sda1        50G   12G   38G  24% /\n",
        "free -h": "              total        used        free      shared  buff/cache\nMem:           7.8G        2.1G        4.2G        0.1G        1.5G\n",
        "ps aux": "USER       PID  %CPU %MEM    VSZ   RSS TTY      STAT START   TIME COMMAND\nsentrix      1   0.0  0.1  12345  1234 ?        Ss   00:00   0:00 bash\n",
        "netstat -tln": "Active Internet connections (only servers)\nProto Recv-Q Send-Q Local Address           Foreign Address         State\ntcp        0      0 0.0.0.0:80              0.0.0.0:*               LISTEN\n",
    }

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Shell command to execute.",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Command arguments.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max execution time in seconds.",
                },
            },
            "required": ["command"],
        }

    @property
    def output_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "exit_code": {"type": "integer"},
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute a mock terminal command."""
        command = kwargs.get("command", "")
        args = kwargs.get("args", [])

        full_command = f"{command} {' '.join(args)}".strip() if args else command

        # Look for a canned response.
        stdout = ""
        for prefix, response in self.CANNED.items():
            if full_command.startswith(prefix):
                stdout = response
                break

        if not stdout:
            stdout = f"Command '{full_command}' executed successfully (mock).\n"

        return ToolResult.ok(
            self.name,
            {
                "stdout": stdout,
                "stderr": "",
                "exit_code": 0,
            },
        )

    async def health(self) -> ToolHealth:
        """Mock terminal is always healthy."""
        return ToolHealth(ok=True, message="Mock terminal is available.")


class MockPythonTool:
    """Mock Python tool — simulates Python code evaluation.

    Does NOT execute any real Python code. Returns simulated output based on
    known patterns.
    """

    name = "python"
    description = "Execute Python code in a sandboxed interpreter (mock)."
    version = "0.1.0"
    permissions: ClassVar[set[ToolPermission]] = {
        ToolPermission(resource="python", action="execute"),
    }

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": "Python code to evaluate.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max execution time in seconds.",
                },
            },
            "required": ["code"],
        }

    @property
    def output_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "stdout": {"type": "string"},
                "stderr": {"type": "string"},
                "exit_code": {"type": "integer"},
                "result": {"type": "string"},
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute mock Python code."""
        code = kwargs.get("code", "")

        # Simulate common patterns.
        output: dict[str, Any] = {
            "stdout": "",
            "stderr": "",
            "exit_code": 0,
            "result": "",
        }

        if "print" in code:
            output["stdout"] = code  # Simulate that print shows the code

        if "import" in code:
            output["stdout"] = "Module imported successfully (mock).\n"

        if "1+1" in code or "2+2" in code:
            output["result"] = str(eval(code)) if code.strip() in ("1+1", "2+2") else "42"
            output["stdout"] = output["result"] + "\n"

        if not output["stdout"] and not output["result"]:
            output["stdout"] = "Code executed successfully (mock).\n"

        return ToolResult.ok(self.name, output)

    async def health(self) -> ToolHealth:
        """Mock Python interpreter is always healthy."""
        return ToolHealth(ok=True, message="Mock Python interpreter is available.")


__all__ = [
    "MockFilesystemTool",
    "MockPythonTool",
    "MockTerminalTool",
]
