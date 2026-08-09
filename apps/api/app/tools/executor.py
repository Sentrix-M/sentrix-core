"""Tool Executor — execute tool calls with timeout and metadata tracking.

The :class:`ToolExecutor` orchestrates the full execution lifecycle:

1. Resolve the tool via :class:`~app.tools.router.ToolRouter`.
2. Validate permissions and input schema.
3. Execute the tool with a configurable timeout.
4. Capture structured results with timing metadata.
5. Handle timeout, cancellation, and execution errors gracefully.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from app.tools.base import ToolResult, ToolStatus
from app.tools.registry import ToolRegistry
from app.tools.router import ToolRouter

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Raised when a tool execution fails."""

    def __init__(self, tool: str, message: str) -> None:
        self.tool = tool
        self.message = message
        super().__init__(f"Tool '{tool}' execution failed: {message}")


class ToolTimeoutError(Exception):
    """Raised when a tool execution exceeds its timeout."""

    def __init__(self, tool: str, timeout: float) -> None:
        self.tool = tool
        self.timeout = timeout
        super().__init__(f"Tool '{tool}' timed out after {timeout}s.")


class ToolPermissionError(Exception):
    """Raised when the caller lacks permissions for a tool."""

    def __init__(self, tool: str, message: str) -> None:
        self.tool = tool
        self.message = message
        super().__init__(f"Tool '{tool}' permission denied: {message}")


class ToolCancelledError(Exception):
    """Raised when a tool execution is cancelled."""

    def __init__(self, tool: str) -> None:
        self.tool = tool
        super().__init__(f"Tool '{tool}' execution was cancelled.")


class ToolExecutor:
    """Executes tool calls with timeout, cancellation, and metadata."""

    #: Default timeout in seconds.
    DEFAULT_TIMEOUT: float = 30.0

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry
        self._router = ToolRouter(registry)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def execute(
        self,
        tool_name: str,
        input_data: dict[str, Any],
        user_permissions: set[str] | None = None,
        timeout: float | None = None,
    ) -> ToolResult:
        """Execute a tool and return a structured result.

        :param tool_name: Name of the tool to execute.
        :param input_data: Parameters to pass to the tool.
        :param user_permissions: Permission strings for the caller.
            When ``None``, permission checks are skipped.
        :param timeout: Maximum execution time in seconds.
            Defaults to :attr:`DEFAULT_TIMEOUT`.
        :returns: A :class:`ToolResult` with execution metadata.
        """
        start_time = datetime.now(timezone.utc)
        effective_timeout = timeout if timeout is not None else self.DEFAULT_TIMEOUT

        try:
            # 1. Resolve tool.
            tool = self._router.resolve(tool_name)

            # 2. Validate permissions.
            if user_permissions is not None:
                self._router.validate_permissions(tool, user_permissions)

            # 3. Validate input schema.
            self._router.validate_input(tool, input_data)

            # 4. Execute with timeout.
            try:
                result = await asyncio.wait_for(
                    tool.execute(**input_data),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                end_time = datetime.now(timezone.utc)
                duration = int((end_time - start_time).total_seconds() * 1000)
                return ToolResult.fail(
                    tool=tool_name,
                    error=f"Tool timed out after {effective_timeout}s.",
                    execution_time_ms=duration,
                    timestamp=end_time.isoformat(),
                    status=ToolStatus.TIMEOUT.value,
                )
            except asyncio.CancelledError:
                end_time = datetime.now(timezone.utc)
                duration = int((end_time - start_time).total_seconds() * 1000)
                return ToolResult.fail(
                    tool=tool_name,
                    error="Tool execution was cancelled.",
                    execution_time_ms=duration,
                    timestamp=end_time.isoformat(),
                    status=ToolStatus.CANCELLED.value,
                )

            # 5. Attach execution metadata.
            end_time = datetime.now(timezone.utc)
            duration = int((end_time - start_time).total_seconds() * 1000)
            result.metadata["execution_time_ms"] = duration
            result.metadata["timestamp"] = end_time.isoformat()
            result.metadata["status"] = (
                ToolStatus.SUCCESS.value if result.success else ToolStatus.FAILURE.value
            )
            return result

        except KeyError as exc:
            return ToolResult.fail(
                tool=tool_name,
                error=str(exc),
                execution_time_ms=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                status=ToolStatus.ERROR.value,
            )
        except PermissionError as exc:
            return ToolResult.fail(
                tool=tool_name,
                error=str(exc),
                execution_time_ms=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                status=ToolStatus.ERROR.value,
            )
        except ValueError as exc:
            return ToolResult.fail(
                tool=tool_name,
                error=str(exc),
                execution_time_ms=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                status=ToolStatus.ERROR.value,
            )
        except RuntimeError as exc:
            return ToolResult.fail(
                tool=tool_name,
                error=str(exc),
                execution_time_ms=0,
                timestamp=datetime.now(timezone.utc).isoformat(),
                status=ToolStatus.ERROR.value,
            )
        except Exception as exc:  # noqa: BLE001 — catch-all for unexpected errors
            logger.exception("Unexpected error executing tool '%s'.", tool_name)
            end_time = datetime.now(timezone.utc)
            duration = int((end_time - start_time).total_seconds() * 1000)
            return ToolResult.fail(
                tool=tool_name,
                error=f"Unexpected error: {exc}",
                execution_time_ms=duration,
                timestamp=end_time.isoformat(),
                status=ToolStatus.ERROR.value,
            )

    def get_router(self) -> ToolRouter:
        """Return the internal router (for testing/inspection)."""
        return self._router


__all__ = [
    "ToolCancelledError",
    "ToolExecutionError",
    "ToolExecutor",
    "ToolPermissionError",
    "ToolTimeoutError",
]
