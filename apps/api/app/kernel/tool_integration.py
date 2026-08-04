"""Tool integration — connect the Tool Engine to the Kernel decision pipeline.

:class:`ToolCoordinator` is the application seam that lets the kernel detect
when a user message should trigger a tool, route the request to the Tool
Router, execute the selected tool, and return the result so the pipeline can
feed it back into the prompt builder.

The coordinator is deliberately conservative: it recognises a small set of
tool intents (filesystem, python, terminal, nmap) using deterministic keyword
matching, and always resolves through the existing
``ToolExecutor``/``ToolRouter``/``ToolRegistry`` stack. Only the registered
mock tools are ever executed — real command execution is out of scope until a
real sandbox is added.
"""

from __future__ import annotations

import asyncio
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.tools.base import ToolResult
from app.tools.executor import ToolExecutor

#: Default values used when a user message implies a tool but does not
#: contain a concrete command/code/path to extract.
_DEFAULT_COMMAND = "whoami"
_DEFAULT_CODE = "print('hello')"
_DEFAULT_PATH = "/documents/report.txt"
_DEFAULT_HOST = "127.0.0.1"


@dataclass(frozen=True)
class ToolDecision:
    """A detected request to invoke a tool."""

    tool_name: str
    input: dict[str, Any]
    confidence: float = 0.0
    reason: str = ""

    def to_dict(self) -> dict[str, object]:
        """Serialize the decision for logging/debugging."""
        return {
            "tool": self.tool_name,
            "input": self.input,
            "confidence": self.confidence,
            "reason": self.reason,
        }


# ---------------------------------------------------------------------------
# Best-effort extraction helpers (mock-grade, deterministic)
# ---------------------------------------------------------------------------


def _extract_quoted(text: str, pattern: re.Pattern[str]) -> str | None:
    """Return the first capture group of ``pattern`` in ``text``, if any."""
    match = pattern.search(text)
    return match.group(1).strip() if match else None


def _extract_path(message: str) -> str:
    """Best-effort extraction of a file path from a user message."""
    quoted = _extract_quoted(message, re.compile(r"""["']([^"']+)["']"""))
    if quoted:
        return quoted
    slash = re.search(r"[\w\-./\\]+\.(?:txt|log|pdf|md|csv|json|py)", message)
    if slash:
        return slash.group(0)
    return _DEFAULT_PATH


def _extract_command(message: str) -> str:
    """Best-effort extraction of a shell command from a user message."""
    quoted = _extract_quoted(message, re.compile(r"`([^`]+)`"))
    if quoted:
        return quoted
    match = re.search(
        r"(?:run|execute)\s+(?:the\s+)?command\s+([a-z0-9 ._/\-]+)",
        message,
        re.IGNORECASE,
    )
    if match:
        return match.group(1).strip()
    return _DEFAULT_COMMAND


def _extract_host(message: str) -> str:
    """Best-effort extraction of a scan target (IP, hostname, or CIDR)."""
    quoted = _extract_quoted(message, re.compile(r"""["']([^"']+)["']"""))
    if quoted:
        return quoted
    match = re.search(
        r"(\d{1,3}(?:\.\d{1,3}){3}(?:/\d{1,2})?|"
        r"[a-zA-Z0-9](?:[a-zA-Z0-9\-.]{0,252}[a-zA-Z0-9]))",
        message,
    )
    if match:
        return match.group(1).strip()
    return _DEFAULT_HOST


def _extract_code(message: str) -> str:
    """Best-effort extraction of a python snippet from a user message."""
    fenced = re.search(r"```(?:python)?\s*\n(.*?)```", message, re.DOTALL)
    if fenced:
        return fenced.group(1).strip()
    quoted = _extract_quoted(message, re.compile(r"""["']([^"']+)["']"""))
    if quoted:
        return quoted
    return _DEFAULT_CODE


def _run_async_from_sync(factory: Callable[[], Any]) -> Any:
    """Run an async callable to completion from a synchronous context.

    Safe both outside and inside a running event loop: when a loop is already
    running (e.g. inside an async test) the coroutine is executed in a
    dedicated worker thread with its own event loop so the caller thread is
    never blocked on a nested ``asyncio.run``.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(factory())

    result_box: dict[str, Any] = {}
    error_box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            result_box["value"] = asyncio.run(factory())
        except BaseException as exc:  # noqa: BLE001 - re-raised in caller thread
            error_box["error"] = exc

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    thread.join()
    if "error" in error_box:
        raise error_box["error"]
    return result_box["value"]


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class ToolCoordinator:
    """Detect tool intents and execute them through the Tool Engine.

    :param executor: The :class:`ToolExecutor` that resolves and runs tools.
    """

    #: Message patterns that trigger the filesystem *list* intent.
    FILESYSTEM_LIST_MARKERS: tuple[str, ...] = (
        "list uploaded documents",
        "list documents",
        "list files",
        "show filesystem",
        "list filesystem",
        "show files",
    )

    #: Message patterns that trigger the filesystem *read* intent.
    FILESYSTEM_READ_MARKERS: tuple[str, ...] = (
        "read file",
        "show file",
        "open file",
    )

    #: Message patterns that trigger the python *execute* intent.
    PYTHON_MARKERS: tuple[str, ...] = (
        "run python",
        "execute python",
        "run python code",
        "execute python code",
        "run a python",
    )

    #: Message patterns that trigger the terminal *execute* intent.
    TERMINAL_MARKERS: tuple[str, ...] = (
        "execute terminal",
        "run terminal",
        "execute terminal command",
        "run command",
        "execute command",
        "shell command",
        "run shell",
    )

    #: Message patterns that trigger the nmap *scan* intent.
    NMAP_MARKERS: tuple[str, ...] = (
        "scan host",
        "scan the host",
        "port scan",
        "nmap scan",
        "run nmap",
        "scan network",
        "scan 10.",
        "scan 192.168",
        "scan 172.",
        "scan the ip",
        "scan the address",
    )

    def __init__(self, executor: ToolExecutor) -> None:
        self._executor = executor

    @property
    def executor(self) -> ToolExecutor:
        """The wrapped tool executor."""
        return self._executor

    # ------------------------------------------------------------------
    # Detection
    # ------------------------------------------------------------------

    def detect(self, message: str) -> ToolDecision | None:
        """Return a :class:`ToolDecision` for ``message``, or ``None``.

        Detection is keyword-based and deterministic. It runs *before* the
        prompt is built so the tool result can be fed into the prompt.
        """
        lower = (message or "").lower()

        if any(marker in lower for marker in self.FILESYSTEM_LIST_MARKERS):
            return ToolDecision(
                tool_name="filesystem",
                input={"action": "list", "path": "/documents"},
                confidence=0.95,
                reason="User asked to list files or the filesystem.",
            )
        if any(marker in lower for marker in self.FILESYSTEM_READ_MARKERS):
            return ToolDecision(
                tool_name="filesystem",
                input={"action": "read", "path": _extract_path(message)},
                confidence=0.9,
                reason="User asked to read or open a file.",
            )
        if any(marker in lower for marker in self.PYTHON_MARKERS):
            return ToolDecision(
                tool_name="python",
                input={"code": _extract_code(message)},
                confidence=0.95,
                reason="User asked to run or execute Python code.",
            )
        if any(marker in lower for marker in self.TERMINAL_MARKERS):
            return ToolDecision(
                tool_name="terminal",
                input={"command": _extract_command(message)},
                confidence=0.95,
                reason="User asked to run a terminal or shell command.",
            )
        if any(marker in lower for marker in self.NMAP_MARKERS):
            return ToolDecision(
                tool_name="nmap",
                input={"host": _extract_host(message)},
                confidence=0.95,
                reason="User asked to run a network or port scan.",
            )
        return None

    # ------------------------------------------------------------------
    # Execution
    # ------------------------------------------------------------------

    async def execute(
        self,
        decision: ToolDecision,
        *,
        user_permissions: set[str] | None = None,
        timeout: float | None = None,
    ) -> ToolResult:
        """Execute a detected tool decision through the Tool Engine."""
        return await self._executor.execute(
            tool_name=decision.tool_name,
            input_data=decision.input,
            user_permissions=user_permissions,
            timeout=timeout,
        )

    def execute_sync(
        self,
        decision: ToolDecision,
        *,
        user_permissions: set[str] | None = None,
        timeout: float | None = None,
    ) -> ToolResult:
        """Execute a tool decision synchronously (kernel-friendly bridge).

        The kernel pipeline is synchronous; this bridge runs the async
        executor in a loop-safe way (see :func:`_run_async_from_sync`).
        """
        return _run_async_from_sync(
            lambda: self.execute(
                decision,
                user_permissions=user_permissions,
                timeout=timeout,
            )
        )

    def detect_and_execute(
        self,
        message: str,
        *,
        user_permissions: set[str] | None = None,
    ) -> tuple[ToolDecision, ToolResult] | None:
        """Detect intent and execute the tool in one call (sync).

        Returns ``None`` when no tool intent is detected; otherwise a tuple
        of the :class:`ToolDecision` and its :class:`ToolResult`.
        """
        decision = self.detect(message)
        if decision is None:
            return None
        result = self.execute_sync(decision, user_permissions=user_permissions)
        return decision, result


__all__ = ["ToolCoordinator", "ToolDecision"]
