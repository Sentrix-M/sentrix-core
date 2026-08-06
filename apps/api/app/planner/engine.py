"""Planner engine — select and order tools for a workflow intent.

:class:`PlannerEngine` is the core of the Phase 14 workflow layer. Given a
user message, it:

1. Routes the message to an :class:`~app.planner.router.Intent`.
2. Selects the ordered set of tools that satisfy the intent.
3. Builds the per-tool input dicts (passing the extracted target through).
4. Decides whether the workflow should auto-generate an incident report.

The engine is deterministic, offline, and reuses the *existing* tool input
conventions (``host`` for nmap, ``query`` for virustotal/shodan,
``operation`` for wazuh) so the resulting :class:`PlannedStep` list can be
executed directly through the existing :class:`~app.tools.executor.ToolExecutor`.
"""

from __future__ import annotations

from typing import Any

from app.planner.models import PlannedStep, WorkflowPlan
from app.planner.router import (
    INTENT_ALERT,
    INTENT_REPORT,
    INTENT_SCAN,
    INTENT_THREAT_INTEL,
    Intent,
    detect_intent,
)

#: Default target used when a message implies a tool but no concrete
#: indicator/host can be extracted. Mirrors the coordinator defaults.
DEFAULT_TARGET = "127.0.0.1"

#: Default Wazuh operation when the message does not name one.
DEFAULT_WAZUH_OPERATION = "recent_alerts"

#: Default incident title used for auto-generated reports.
DEFAULT_INCIDENT_TITLE = "Security Incident"


def _step(tool_name: str, input_data: dict[str, Any], reason: str) -> PlannedStep:
    """Build a :class:`PlannedStep`."""
    return PlannedStep(tool_name=tool_name, input_data=input_data, reason=reason)


class PlannerEngine:
    """Turn a user message into an ordered :class:`WorkflowPlan`."""

    def plan(self, message: str) -> WorkflowPlan:
        """Build a :class:`WorkflowPlan` for ``message``.

        :param message: The user's request.
        :returns: A :class:`WorkflowPlan`. When the intent is unknown, the
            plan has no steps and ``generate_report`` is ``False``.
        """
        intent = detect_intent(message)
        steps = self._select_steps(intent)

        generate_report, incident_title = self._report_decision(intent, steps)
        return WorkflowPlan(
            message=message,
            steps=steps,
            intent=intent.label,
            generate_report=generate_report,
            incident_title=incident_title,
        )

    # ------------------------------------------------------------------
    # Tool selection
    # ------------------------------------------------------------------

    def _select_steps(self, intent: Intent) -> list[PlannedStep]:
        """Select the ordered tool steps for ``intent``."""
        target = intent.target or DEFAULT_TARGET
        lower_target = target.lower()

        if intent.label == INTENT_SCAN:
            return [
                _step(
                    "nmap",
                    {"host": target},
                    f"Network/port scan requested for {target}.",
                ),
            ]

        if intent.label == INTENT_ALERT:
            operation = self._resolve_wazuh_operation(intent)
            return [
                _step(
                    "wazuh",
                    {"operation": operation},
                    f"Security alert review requested (operation={operation}).",
                ),
            ]

        if intent.label == INTENT_THREAT_INTEL:
            steps: list[PlannedStep] = []
            query = {"query": target}

            # IP/CIDR/host indicators: expose internet presence first, then
            # reputation. Domains/hashes skip Shodan host data.
            if _looks_like_ip_or_cidr(lower_target) or _looks_like_hostname(lower_target):
                steps.append(
                    _step(
                        "shodan",
                        dict(query),
                        f"Shodan internet-exposure lookup for {target}.",
                    )
                )
            steps.append(
                _step(
                    "virustotal",
                    dict(query),
                    f"VirusTotal threat-intel lookup for {target}.",
                )
            )
            return steps

        if intent.label == INTENT_REPORT:
            return []

        return []

    # ------------------------------------------------------------------
    # Report decision
    # ------------------------------------------------------------------

    def _report_decision(
        self,
        intent: Intent,
        steps: list[PlannedStep],
    ) -> tuple[bool, str]:
        """Decide whether to auto-generate a report after the steps run.

        Threat-intel and alert workflows produce evidence worth codifying into
        an incident report. Network-scan workflows stop at findings unless the
        user explicitly asked for a report (handled by the coordinator's
        single-tool path). Unknown intents never generate a report here.
        """
        if intent.label == INTENT_REPORT:
            return True, intent.target or DEFAULT_INCIDENT_TITLE
        if intent.label in (INTENT_THREAT_INTEL, INTENT_ALERT) and steps:
            return True, DEFAULT_INCIDENT_TITLE
        return False, ""

    # ------------------------------------------------------------------
    # Misc
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_wazuh_operation(intent: Intent) -> str:
        """Pick the Wazuh operation from the message keywords."""
        if intent.target and intent.target.lower() in (
            "recent alerts",
            "recent_alert",
            "latest alerts",
        ):
            return "recent_alerts"
        message = (getattr(intent, "message", "") or "").lower()
        if any(w in message for w in ("agent", "agents")):
            return "agent"
        if "rule" in message:
            return "rule"
        if "alert" in message:
            return "alert"
        return DEFAULT_WAZUH_OPERATION


def _looks_like_ip_or_cidr(value: str) -> bool:
    """Return whether ``value`` is an IPv4/CIDR literal."""
    try:
        import ipaddress  # noqa: PLC0415

        ipaddress.ip_address(value.split("/")[0])
        return True
    except ValueError:
        return False


def _looks_like_hostname(value: str) -> bool:
    """Return whether ``value`` looks like a hostname/domain (not a hash)."""
    if not value:
        return False
    # Hashes are all-hex of a fixed length; not hostnames.
    if _HASH_LIKE(value):
        return False
    # A bare single label or dotted hostname with no spaces.
    import re  # noqa: PLC0415

    return bool(
        re.match(r"^[a-zA-Z0-9](?:[a-zA-Z0-9\-_.]{0,252}[a-zA-Z0-9])?$", value)
    )


def _HASH_LIKE(value: str) -> bool:
    """Return whether ``value`` is MD5/SHA1/SHA256 shaped (all hex)."""
    value = value.strip()
    if len(value) not in (32, 40, 64):
        return False
    return all(c in "0123456789abcdefABCDEF" for c in value)


def detect_workflow(message: str) -> WorkflowPlan:
    """Convenience: build a plan directly from a message.

    Equivalent to ``PlannerEngine().plan(message)`` and provided so the
    coordinator/streaming layers can compose a plan without instantiating
    the engine explicitly.
    """
    return PlannerEngine().plan(message)


__all__ = [
    "DEFAULT_INCIDENT_TITLE",
    "DEFAULT_TARGET",
    "DEFAULT_WAZUH_OPERATION",
    "PlannerEngine",
    "detect_workflow",
]

