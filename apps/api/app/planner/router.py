"""Intent routing for the Sentrix Workflow Planner.

This module exposes deterministic, keyword-based intent detection that maps a
user message to a high-level SOC workflow intent. It mirrors the conservative
style used by :class:`~app.kernel.tool_integration.ToolCoordinator` but at a
coarser granularity: rather than selecting a single tool, it classifies the
*type* of investigation the user is asking for so the planner can decide which
set of tools to chain.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Intent labels the router can produce.
INTENT_SCAN = "network_scan"
INTENT_THREAT_INTEL = "threat_intel"
INTENT_ALERT = "alert_review"
INTENT_REPORT = "report"
INTENT_UNKNOWN = "unknown"

#: Keyword markers for a network-scan intent (nmap).
_SCAN_MARKERS: tuple[str, ...] = (
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

#: Keyword markers for a threat-intel intent (virustotal/shodan).
_THREAT_INTEL_MARKERS: tuple[str, ...] = (
    "analyze",
    "investigate",
    "reputation",
    "virustotal",
    "virus total",
    "shodan",
    "threat intelligence",
    "look up",
    "lookup",
    "check ip",
    "check the ip",
    "check hash",
    "check the hash",
    "check domain",
    "check the domain",
    "check url",
    "check the url",
    "internet exposure",
    "open ports",
    "exposed services",
)

#: Keyword markers for a security-alert intent (wazuh).
_ALERT_MARKERS: tuple[str, ...] = (
    "wazuh",
    "security alert",
    "security alerts",
    "siem alert",
    "siem alerts",
    "recent alerts",
    "check alerts",
    "investigate the alert",
    "investigate alert",
)

#: Keyword markers for a report-generation intent.
_REPORT_MARKERS: tuple[str, ...] = (
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

#: Pattern for an IPv4 address (also used for CIDR prefixes).
_IPV4_CIDR_RE = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1?\d?\d)(?:/\d{1,2})?\b"
)

#: Pattern for a domain or hostname (subdomains + TLD).
_DOMAIN_RE = re.compile(
    r"(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,}"
)

#: Pattern for MD5/SHA1/SHA256 hashes.
_HASH_RE = re.compile(r"\b[a-fA-F0-9]{32}\b|\b[a-fA-F0-9]{40}\b|\b[a-fA-F0-9]{64}\b")


@dataclass(frozen=True)
class Intent:
    """A detected workflow intent plus the extracted target, if any.

    :param label: One of the ``INTENT_*`` constants.
    :param target: The extracted indicator/host for tool inputs, or ``None``.
    :param confidence: A 0..1 confidence estimate.
    """

    label: str
    target: str | None = None
    confidence: float = 0.0


def _extract_target(message: str) -> str | None:
    """Best-effort extraction of an IP/CIDR, domain, or hash from ``message``."""
    quoted = re.search(r"""["']([^"']+)["']""", message)
    if quoted:
        candidate = quoted.group(1).strip()
        if candidate:
            return candidate

    ip_match = _IPV4_CIDR_RE.search(message)
    if ip_match:
        return ip_match.group(0)

    hash_match = _HASH_RE.search(message)
    if hash_match:
        return hash_match.group(0)

    domain_match = _DOMAIN_RE.search(message)
    if domain_match:
        return domain_match.group(0)

    return None


def detect_intent(message: str) -> Intent:
    """Classify a user message into a workflow intent.

    Detection is deterministic and keyword-based. Report intent takes
    precedence (it is the most explicit), followed by alert, scan, and
    threat-intel. The target indicator is extracted regardless of intent so
    the planner can populate tool inputs.
    """
    lower = (message or "").lower()
    target = _extract_target(message)

    if any(marker in lower for marker in _REPORT_MARKERS):
        return Intent(INTENT_REPORT, target, 0.95)

    if any(marker in lower for marker in _ALERT_MARKERS):
        return Intent(INTENT_ALERT, target, 0.9)

    if any(marker in lower for marker in _SCAN_MARKERS):
        return Intent(INTENT_SCAN, target, 0.9)

    if any(marker in lower for marker in _THREAT_INTEL_MARKERS):
        return Intent(INTENT_THREAT_INTEL, target, 0.85)

    return Intent(INTENT_UNKNOWN, target, 0.0)


class IntentRouter:
    """Route a user message to a workflow intent.

    Thin wrapper around :func:`detect_intent` so callers receive a stable,
    introspectable object that is easy to substitute in tests.
    """

    def route(self, message: str) -> Intent:
        """Return the :class:`Intent` for ``message``."""
        return detect_intent(message)


__all__ = [
    "INTENT_ALERT",
    "INTENT_REPORT",
    "INTENT_SCAN",
    "INTENT_THREAT_INTEL",
    "INTENT_UNKNOWN",
    "Intent",
    "IntentRouter",
    "detect_intent",
]
