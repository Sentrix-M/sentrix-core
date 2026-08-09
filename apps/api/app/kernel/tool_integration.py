"""Tool integration — connect the Tool Engine to the Kernel decision pipeline.

:class:`ToolCoordinator` is the application seam that lets the kernel detect
when a user message should trigger a tool, route the request to the Tool
Router, execute the selected tool, and return the result so the pipeline can
feed it back into the prompt builder.

The coordinator is deliberately conservative: it recognises a small set of
tool intents (filesystem, python, terminal, nmap, virustotal, shodan, wazuh)
using deterministic keyword matching, and always resolves through the existing
``ToolExecutor``/``ToolRouter``/``ToolRegistry`` stack. Only the registered
tools are ever executed.
"""

from __future__ import annotations

import asyncio
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from app.mitre.integration import enrich_tool_result
from app.mitre.mapper import MitreMapper
from app.planner.engine import detect_workflow
from app.planner.models import WorkflowPlan, WorkflowResult
from app.planner.orchestrator import WorkflowOrchestrator
from app.tools.base import ToolResult
from app.tools.executor import ToolExecutor

if TYPE_CHECKING:
    from app.memory.service import MemoryService
    from app.reports.service import ReportService

#: Default values used when a user message implies a tool but does not
#: contain a concrete command/code/path to extract.
_DEFAULT_COMMAND = "whoami"
_DEFAULT_CODE = "print('hello')"
_DEFAULT_PATH = "/documents/report.txt"
_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_VT_QUERY = "44d88612fea8a8f36de82e1278abb02f"
_DEFAULT_SHODAN_QUERY = "1.1.1.1"
_DEFAULT_WAZUH_OPERATION = "recent_alerts"
_DEFAULT_REPORT_TITLE = "Security Incident"


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


def _extract_vt_query(message: str) -> str:
    """Best-effort extraction of a security indicator for VirusTotal lookup.

    Recognises, in order: MD5/SHA1/SHA256 hashes, IPv4/IPv6 addresses,
    URLs, and domains. Falls back to a known test hash.
    """
    quoted = _extract_quoted(message, re.compile(r"""["']([^"']+)["']"""))
    if quoted:
        return quoted

    hash_match = re.search(
        r"\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b",
        message,
    )
    if hash_match:
        return hash_match.group(0)

    ip_match = re.search(
        r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|1?\d?\d)\b",
        message,
    )
    if ip_match:
        return ip_match.group(0)

    url_match = re.search(r"https?://[^\s]+", message)
    if url_match:
        return url_match.group(0)

    domain_match = re.search(
        r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+"
        r"[a-zA-Z]{2,}",
        message,
    )
    if domain_match:
        return domain_match.group(0)

    return _DEFAULT_VT_QUERY


def _extract_shodan_query(message: str) -> str:
    """Best-effort extraction of an internet-exposure target for Shodan.

    Recognises IPv4/IPv6 addresses, hostnames, and domains. Falls back to a
    known public test IP.
    """
    quoted = _extract_quoted(message, re.compile(r"""["']([^"']+)["']"""))
    if quoted:
        return quoted

    ip_match = re.search(
        r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
        r"(?:25[0-5]|2[0-4]\d|1?\d?\d)\b",
        message,
    )
    if ip_match:
        return ip_match.group(0)

    domain_match = re.search(
        r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+"
        r"[a-zA-Z]{2,}",
        message,
    )
    if domain_match:
        return domain_match.group(0)

    return _DEFAULT_SHODAN_QUERY


def _extract_wazuh_operation(message: str) -> str:
    """Best-effort extraction of a Wazuh operation from a user message.

    Returns one of ``recent_alerts``, ``alert``, ``agent``, or ``rule``.
    Falls back to ``recent_alerts`` when no specific operation is named.
    """
    lower = (message or "").lower()

    # "recent alerts" (and variants) should map to recent_alerts before the
    # generic "alert" branch, so phrases like "show recent alerts" resolve to
    # the list operation rather than a single-alert lookup.
    if any(w in lower for w in ("recent alerts", "recent_alert", "latest alerts")):
        return "recent_alerts"

    if "rule" in lower and any(w in lower for w in ("wazuh", "alert", "siem")):
        return "rule"
    if any(w in lower for w in ("agent", "agent status", "agents")):
        return "agent"
    if "rule" in lower:
        return "rule"
    if "alert" in lower:
        return "alert"
    return _DEFAULT_WAZUH_OPERATION


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
    :param mitre_mapper: Optional :class:`MitreMapper` used to enrich
        successful tool results with MITRE ATT&CK mappings. When omitted, a
        default :class:`MitreMapper` is created lazily.
    :param memory_service: Optional :class:`MemoryService` passed through to
        the :class:`WorkflowOrchestrator` so multi-tool executions and
        investigations are recorded to long-term memory (best-effort).
    :param report_service: Optional :class:`ReportService` passed through to
        the :class:`WorkflowOrchestrator` so chat-driven investigations can
        generate and persist incident reports (best-effort).
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

    #: Message patterns that trigger the VirusTotal *threat-intel* intent.
    VIRUSTOTAL_MARKERS: tuple[str, ...] = (
        "analyze hash",
        "analyze the hash",
        "virus total",
        "virustotal",
        "vt lookup",
        "vt scan",
        "check ip reputation",
        "ip reputation",
        "analyze domain",
        "analyze the domain",
        "analyze url",
        "analyze the url",
        "check the hash",
        "check hash",
    )

    #: Message patterns that trigger the Shodan *internet-exposure* intent.
    SHODAN_MARKERS: tuple[str, ...] = (
        "shodan",
        "internet exposure",
        "open ports",
        "port exposure",
        "exposed services",
    )

    #: Message patterns that trigger the Wazuh *security-alert* intent.
    WAZUH_MARKERS: tuple[str, ...] = (
        "wazuh",
        "security alert",
        "security alerts",
        "siem alert",
        "siem alerts",
        "recent alerts",
        "check alerts",
        "wazuh alerts",
        "wazuh alert",
    )

    #: Message patterns that trigger the incident-report *generation* intent.
    REPORT_MARKERS: tuple[str, ...] = (
        "generate an incident report",
        "generate incident report",
        "create incident report",
        "incident report",
        "write a report",
        "open a case report",
        "generate a report",
        "create a report",
        "produce a report",
        "make a report",
    )

    def __init__(
        self,
        executor: ToolExecutor,
        mitre_mapper: MitreMapper | None = None,
        memory_service: MemoryService | None = None,
        report_service: ReportService | None = None,
    ) -> None:
        self._executor = executor
        self._mitre_mapper = mitre_mapper
        self._memory_service = memory_service
        self._report_service = report_service

    @property
    def executor(self) -> ToolExecutor:
        """The wrapped tool executor."""
        return self._executor

    @property
    def mitre_mapper(self) -> MitreMapper:
        """The MITRE mapper used to enrich tool results (lazily created)."""
        if self._mitre_mapper is None:
            self._mitre_mapper = MitreMapper()
        return self._mitre_mapper

    @property
    def memory_service(self) -> MemoryService | None:
        """The optional memory service ("None" when not wired)."""
        return self._memory_service

    @property
    def report_service(self) -> ReportService | None:
        """The optional report service ("None" when not wired)."""
        return self._report_service

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
        if any(marker in lower for marker in self.VIRUSTOTAL_MARKERS):
            return ToolDecision(
                tool_name="virustotal",
                input={"query": _extract_vt_query(message)},
                confidence=0.9,
                reason="User asked to analyze a security indicator on VirusTotal.",
            )
        if any(marker in lower for marker in self.SHODAN_MARKERS):
            return ToolDecision(
                tool_name="shodan",
                input={"query": _extract_shodan_query(message)},
                confidence=0.9,
                reason="User asked to check internet exposure or open ports on Shodan.",
            )
        if any(marker in lower for marker in self.WAZUH_MARKERS):
            return ToolDecision(
                tool_name="wazuh",
                input={"operation": _extract_wazuh_operation(message)},
                confidence=0.9,
                reason="User asked to query Wazuh security alerts.",
            )
        if any(marker in lower for marker in self.REPORT_MARKERS):
            return ToolDecision(
                tool_name="report_generator",
                input={"incident_title": _DEFAULT_REPORT_TITLE},
                confidence=0.9,
                reason="User asked to generate an incident report.",
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
        # Enrich successful tool results with a MITRE ATT&CK mapping so the
        # kernel/prompt can explain the techniques, tactics, and mitigations.
        if result.success:
            result.metadata["mitre"] = enrich_tool_result(
                result, mapper=self.mitre_mapper
            )
        return decision, result

    # ------------------------------------------------------------------
    # Multi-tool (Phase 14 workflow) integration
    # ------------------------------------------------------------------

    def plan_and_execute(
        self,
        message: str,
        *,
        user_permissions: set[str] | None = None,
        timeout: float | None = None,
    ) -> WorkflowResult | None:
        """Detect and execute a multi-tool workflow, falling back gracefully.

        This is the Phase 14 entry point. It builds a :class:`WorkflowPlan`
        from ``message`` via the planner engine. When the plan contains more
        than one tool, the steps are executed through the
        :class:`WorkflowOrchestrator` and the aggregated
        :class:`WorkflowResult` is returned.

        When the plan has zero or one tool(s), the method falls back to the
        existing single-tool :meth:`detect_and_execute` path so behavior is
        identical to pre-Phase-14. A single-tool workflow is wrapped into a
        :class:`WorkflowResult` for a uniform return shape; ``None`` is
        returned only when no tool intent is detected at all.

        :param message: The user's request.
        :param user_permissions: Optional permission set for tool execution.
        :param timeout: Optional per-tool execution timeout.
        :returns: A :class:`WorkflowResult`, or ``None`` when no workflow
            can be derived from ``message``.
        """
        plan = detect_workflow(message)

        # Reinforce the ordering guarantee: the coordinator's single-tool
        # detection is the source of truth for 0-1 tool messages so that
        # legacy behavior (incl. filesystem/python/terminal) is preserved.
        if len(plan.steps) <= 1:
            pair = self.detect_and_execute(message, user_permissions=user_permissions)
            if pair is None:
                return None
            decision, result = pair
            return WorkflowResult(
                plan=_single_tool_plan(message, decision),
                results=[result],
            )

        # Multi-tool workflow: run the orchestrator (MITRE-enriches each
        # successful result and aggregates streaming progress).
        orchestrator = WorkflowOrchestrator(
            executor=self._executor,
            mitre_mapper=self.mitre_mapper,
            memory_service=self._memory_service,
            report_service=self._report_service,
        )
        return _run_async_from_sync(
            lambda: orchestrator.run(
                plan,
                user_permissions=user_permissions,
                timeout=timeout,
            )
        )


def _single_tool_plan(
    message: str,
    decision: ToolDecision,
) -> WorkflowPlan:
    """Build a single-step :class:`WorkflowPlan` for a legacy decision."""
    step = _planned_step(decision)
    return WorkflowPlan(
        message=message,
        steps=[step],
        intent=decision.tool_name,
        generate_report=False,
        incident_title="",
    )


def _planned_step(decision: ToolDecision) -> Any:
    """Wrap a :class:`ToolDecision` as a :class:`PlannedStep`."""
    from app.planner.models import PlannedStep

    return PlannedStep(
        tool_name=decision.tool_name,
        input_data=decision.input,
        reason=decision.reason,
    )


__all__ = ["ToolCoordinator", "ToolDecision"]
