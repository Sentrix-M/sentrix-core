"""Tool interface for the Sentrix Tool Engine.

Every tool must implement :class:`BaseTool` (a Protocol) exposing:

- ``name`` — unique tool identifier
- ``description`` — human-readable purpose
- ``version`` — semver string
- ``permissions`` — set of required permission strings
- ``input_schema`` — JSON Schema dict for input validation
- ``output_schema`` — JSON Schema dict for output shape
- ``execute()`` — run the tool logic
- ``health()`` — report tool availability
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Protocol


class ToolStatus(enum.Enum):
    """Execution status of a tool."""

    SUCCESS = "success"
    FAILURE = "failure"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    ERROR = "error"


@dataclass
class ToolResult:
    """Structured result returned by every tool execution."""

    success: bool
    tool: str
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def ok(cls, tool: str, output: Any, **metadata: Any) -> ToolResult:
        """Create a successful result."""
        return cls(
            success=True,
            tool=tool,
            output=output,
            metadata={
                "execution_time_ms": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **metadata,
            },
        )

    @classmethod
    def fail(cls, tool: str, error: str, **metadata: Any) -> ToolResult:
        """Create a failure result."""
        return cls(
            success=False,
            tool=tool,
            error=error,
            metadata={
                "execution_time_ms": 0,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                **metadata,
            },
        )


@dataclass(frozen=True)
class ToolPermission:
    """Permission required to invoke a tool."""

    resource: str
    action: str  # e.g. "read", "write", "execute"

    @property
    def permission_string(self) -> str:
        return f"{self.resource}:{self.action}"

    def __str__(self) -> str:
        return self.permission_string

    def __hash__(self) -> int:
        return hash((self.resource, self.action))


class ToolHealth:
    """Health status for a tool."""

    def __init__(self, *, ok: bool, message: str = "") -> None:
        self.ok = ok
        self.message = message

    def __repr__(self) -> str:
        return f"<ToolHealth ok={self.ok} message={self.message!r}>"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ToolHealth):
            return NotImplemented
        return self.ok == other.ok and self.message == other.message


class BaseTool(Protocol):
    """Contract implemented by every Sentrix tool."""

    name: str
    description: str
    version: str
    permissions: set[ToolPermission]

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema describing the expected input."""
        ...

    @property
    def output_schema(self) -> dict[str, Any]:
        """JSON Schema describing the returned output."""
        ...

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with the given parameters."""
        ...

    async def health(self) -> ToolHealth:
        """Report tool availability."""
        ...


__all__ = [
    "BaseTool",
    "ToolHealth",
    "ToolPermission",
    "ToolResult",
    "ToolStatus",
]
