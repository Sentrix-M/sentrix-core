"""MITRE ATT&CK mapper — translate tool results into ATT&CK mappings.

:class:`MitreMapper` is the core of the Phase 11 mapping engine. It consumes
a :class:`~app.tools.base.ToolResult` (or any object exposing ``tool``,
``success``, and ``output``) and returns a :class:`~app.mitre.models.MitreMapping`
with:

- matched ATT&CK techniques (ID, name, tactic, mitigation, detection)
- an overall confidence score
- the source tool name

Mapping dispatch
----------------
The mapper is tool-aware and dispatches to a dedicated extraction routine for
each supported tool:

- ``nmap`` — maps exposed services and OS detection
- ``virustotal`` — maps tags, categories, and malicious verdicts
- ``shodan`` — maps services, CVEs, tags, and risk signals
- ``wazuh`` — maps security alerts, rule groups, and MITRE IDs

Unknown/failed results fall back to :meth:`_map_generic`, which applies
behavioral keyword matching against the serialized output. This keeps the
engine resilient and offline by design (no external MITRE API).
"""

from __future__ import annotations

from typing import Any

from app.mitre.knowledge_base import MitreKnowledgeBase, TechniqueEntry
from app.mitre.models import MitreMapping, MitreTechnique

#: Confidence awarded when a technique is matched from a specific CVE.
_CVE_CONFIDENCE = 0.95
#: Confidence awarded when a technique is matched from a known service.
_SERVICE_CONFIDENCE = 0.8
#: Confidence awarded when a technique is matched from a malware label.
_MALWARE_CONFIDENCE = 0.85
#: Confidence awarded when a technique is matched from a behavior keyword.
_BEHAVIOR_CONFIDENCE = 0.6
#: Confidence awarded when a technique is matched from an explicit MITRE ID.
_MITRE_ID_CONFIDENCE = 0.9
#: Confidence awarded for a generic mapping fallback.
_GENERIC_CONFIDENCE = 0.4


def _techniques(
    entries: list[TechniqueEntry],
    *,
    evidence: str,
    confidence: float,
) -> list[MitreTechnique]:
    """Convert knowledge-base entries into :class:`MitreTechnique` objects."""
    return [
        MitreTechnique(
            technique_id=e.technique_id,
            name=e.name,
            tactic=e.tactic,
            mitigation=e.mitigation,
            detection=e.detection,
            evidence=evidence,
            confidence=confidence,
        )
        for e in entries
    ]


def _average(items: list[float]) -> float:
    """Return the mean of ``items`` (0.0 for an empty list)."""
    if not items:
        return 0.0
    return round(sum(items) / len(items), 3)


class MitreMapper:
    """Maps tool results to MITRE ATT&CK techniques.

    :param knowledge_base: Optional :class:`MitreKnowledgeBase`. Defaults to a
        fresh instance so the mapper is self-contained and offline by default.
    """

    def __init__(self, knowledge_base: MitreKnowledgeBase | None = None) -> None:
        self._kb = knowledge_base or MitreKnowledgeBase()

    @property
    def knowledge_base(self) -> MitreKnowledgeBase:
        """The underlying knowledge base (for inspection/extension)."""
        return self._kb

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def map(self, tool_result: Any) -> MitreMapping:
        """Map a tool result to a :class:`MitreMapping`.

        :param tool_result: A :class:`ToolResult` (or any object with
            ``tool``/``success``/``output`` attributes).
        :returns: A populated :class:`MitreMapping`. When the tool result is
            a failure or empty, the mapping is empty with ``confidence=0``.
        """
        source = getattr(tool_result, "tool", "unknown")
        success = bool(getattr(tool_result, "success", False))
        output = getattr(tool_result, "output", None)

        techniques: list[MitreTechnique] = []
        if success:
            techniques.extend(self._dispatch(source, output))

        confidence = _average([t.confidence for t in techniques]) if techniques else 0.0
        return MitreMapping(
            techniques=techniques,
            confidence=confidence,
            source=source,
        )

    # ------------------------------------------------------------------
    # Dispatch
    # ------------------------------------------------------------------

    def _dispatch(self, source: str, output: Any) -> list[MitreTechnique]:
        """Route to the tool-specific extraction routine."""
        dispatcher = {
            "nmap": self._map_nmap,
            "virustotal": self._map_virustotal,
            "shodan": self._map_shodan,
            "wazuh": self._map_wazuh,
        }.get(source, self._map_generic)

        if not isinstance(output, dict):
            return []

        try:
            return dispatcher(output)
        except Exception:  # noqa: BLE001 - mapping must never raise
            return []

    # ------------------------------------------------------------------
    # Tool-specific mappers
    # ------------------------------------------------------------------

    def _map_nmap(self, output: dict[str, Any]) -> list[MitreTechnique]:
        """Map an Nmap scan result to ATT&CK techniques.

        Exposed services on open ports map to the techniques an attacker
        gains by abusing them. Unknown services still map to the generic
        network-service-discovery technique.
        """
        techniques: list[MitreTechnique] = []
        hosts = output.get("hosts", [])
        if not isinstance(hosts, list):
            hosts = []

        services_seen: set[str] = set()
        for host in hosts:
            if not isinstance(host, dict):
                continue
            ports = host.get("open_ports", [])
            if not isinstance(ports, list):
                continue
            for port in ports:
                if not isinstance(port, dict):
                    continue
                service = str(port.get("service", "") or "").strip().lower()
                if not service or service in services_seen:
                    continue
                services_seen.add(service)
                entries = self._kb.techniques_for_service(service)
                if entries:
                    techniques.extend(
                        _techniques(
                            entries,
                            evidence=(
                                f"Open {port.get('protocol', 'tcp')} port "
                                f"{port.get('port')} exposes service '{service}'."
                            ),
                            confidence=_SERVICE_CONFIDENCE,
                        )
                    )

        # If open ports were found but none mapped to a specific technique,
        # add the generic discovery technique.
        found_any = bool(techniques)
        if services_seen and not found_any:
            entries = self._kb.techniques_for_behavior("scanning")
            techniques.extend(
                _techniques(
                    entries,
                    evidence=(
                        f"Nmap discovered open ports on {output.get('target', 'target')}."
                    ),
                    confidence=_BEHAVIOR_CONFIDENCE,
                )
            )
        return techniques

    def _map_virustotal(self, output: dict[str, Any]) -> list[MitreTechnique]:
        """Map a VirusTotal lookup result to ATT&CK techniques.

        Uses the malicious verdict, tags, and categories to infer the likely
        malware behaviour. A malicious verdict on a file/hash maps to the
        execution technique; matching tags map to behaviour-specific
        techniques.
        """
        techniques: list[MitreTechnique] = []
        malicious = int(output.get("malicious", 0) or 0)
        tags = output.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        categories = output.get("categories", {})
        if not isinstance(categories, dict):
            categories = {}

        evidence_base = (
            f"VirusTotal verdict for '{output.get('query')}' "
            f"({output.get('indicator_type')})."
        )

        if malicious > 0:
            entries = self._kb.techniques_for_malware("trojan")
            techniques.extend(
                _techniques(
                    entries,
                    evidence=f"{evidence_base} Reported by {malicious} engines as malicious.",
                    confidence=_MALWARE_CONFIDENCE,
                )
            )

        # Match tags against malware-family labels.
        for tag in tags:
            label = str(tag).strip().lower()
            entries = self._kb.techniques_for_malware(label)
            if entries:
                techniques.extend(
                    _techniques(
                        entries,
                        evidence=f"{evidence_base} Tag '{tag}' indicates {label}.",
                        confidence=_MALWARE_CONFIDENCE,
                    )
                )

        # Match category values against behavior keywords.
        lowered_categories_text = " ".join(str(v) for v in categories.values()).lower()
        for keyword in self._kb._behaviors:  # noqa: SLF001 - internal lookup
            if keyword in lowered_categories_text:
                entries = self._kb.techniques_for_behavior(keyword)
                techniques.extend(
                    _techniques(
                        entries,
                        evidence=f"{evidence_base} Category references '{keyword}'.",
                        confidence=_BEHAVIOR_CONFIDENCE,
                    )
                )
        return techniques

    def _map_shodan(self, output: dict[str, Any]) -> list[MitreTechnique]:
        """Map a Shodan host-intelligence result to ATT&CK techniques.

        Uses discovered services, known CVEs/vulnerabilities, tags, and the
        risk score. A high risk score or the presence of vulnerabilities
        boosts confidence.
        """
        techniques: list[MitreTechnique] = []
        services = output.get("services", [])
        if not isinstance(services, list):
            services = []
        vulnerabilities = output.get("vulnerabilities", [])
        if not isinstance(vulnerabilities, list):
            vulnerabilities = []
        tags = output.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        risk_score = str(output.get("risk_score", "") or "").lower()

        evidence_base = f"Shodan host intelligence for '{output.get('query')}'."

        # Map exposed services.
        service_names_seen: set[str] = set()
        for service in services:
            if not isinstance(service, dict):
                continue
            name = str(service.get("product", "") or "").strip().lower()
            if not name:
                name = str(service.get("transport", "") or "").strip().lower()
            if not name or name in service_names_seen:
                continue
            service_names_seen.add(name)
            entries = self._kb.techniques_for_service(name)
            if entries:
                techniques.extend(
                    _techniques(
                        entries,
                        evidence=(
                            f"{evidence_base} Port {service.get('port')} runs "
                            f"'{name}'."
                        ),
                        confidence=_SERVICE_CONFIDENCE,
                    )
                )

        # Map known CVEs/vulnerabilities.
        for cve in vulnerabilities:
            entries = self._kb.techniques_for_cve(cve)
            if entries:
                techniques.extend(
                    _techniques(
                        entries,
                        evidence=f"{evidence_base} Host is affected by {cve}.",
                        confidence=_CVE_CONFIDENCE,
                    )
                )

        # Map tags against malware/behavior labels.
        for tag in tags:
            label = str(tag).strip().lower()
            malware_entries = self._kb.techniques_for_malware(label)
            if malware_entries:
                techniques.extend(
                    _techniques(
                        malware_entries,
                        evidence=f"{evidence_base} Tag '{tag}' indicates {label}.",
                        confidence=_MALWARE_CONFIDENCE,
                    )
                )
                continue
            behavior_entries = self._kb.techniques_for_behavior(label)
            if behavior_entries:
                techniques.extend(
                    _techniques(
                        behavior_entries,
                        evidence=f"{evidence_base} Tag '{tag}' indicates {label}.",
                        confidence=_BEHAVIOR_CONFIDENCE,
                    )
                )

        # High risk score without a specific technique → generic discovery.
        if risk_score == "high" and not techniques:
            entries = self._kb.techniques_for_behavior("scanning")
            techniques.extend(
                _techniques(
                    entries,
                    evidence=f"{evidence_base} Host has a high-risk exposure profile.",
                    confidence=_BEHAVIOR_CONFIDENCE,
                )
            )
        return techniques

    def _map_wazuh(self, output: dict[str, Any]) -> list[MitreTechnique]:
        """Map a Wazuh security-alert result to ATT&CK techniques.

        Mapping strategy:
        1. Honour MITRE IDs already present in the Wazuh rule — these are
           authoritative and carry the highest confidence. Each ID is looked
           up in the knowledge base and mapped with dedicated evidence.
        2. Map the alert's rule groups and description against known
           behaviors (c2, beacon, exfil, brute force, scanning, ...).
        3. Map the alert's severity: high rule levels (>= 12) map to the
           generic impact/execution technique when nothing more specific was
           matched.
        """
        techniques: list[MitreTechnique] = []
        seen: set[str] = set()

        # 1. Explicit MITRE technique IDs from the Wazuh rule.
        rule = output.get("rule", {})
        if not isinstance(rule, dict):
            rule = {}
        mitre_ids = rule.get("mitre", [])
        if isinstance(mitre_ids, str):
            mitre_ids = [mitre_ids]
        if not isinstance(mitre_ids, list):
            mitre_ids = []

        for mitre_id in mitre_ids:
            mid = str(mitre_id).strip()
            if not mid or mid.upper() in seen:
                continue
            entry = self._kb.technique_by_id(mid)
            if entry is not None:
                seen.add(mid.upper())
                techniques.extend(
                    _techniques(
                        [entry],
                        evidence=(
                            f"Wazuh rule '{rule.get('description', rule.get('rule_id'))}' "
                            f"references ATT&CK technique {mid}."
                        ),
                        confidence=_MITRE_ID_CONFIDENCE,
                    )
                )

        # 2. Behavior keyword matching over groups + description.
        groups = [str(g) for g in (rule.get("groups") or []) if g]
        description = str(
            rule.get("description")
            or output.get("alert", {}).get("description")
            or ""
        )
        haystack = (" ".join(groups) + " " + description).lower()
        for keyword in self._kb._behaviors:  # noqa: SLF001 - internal lookup
            if keyword in haystack and keyword not in seen:
                seen.add(keyword)
                entries = self._kb.techniques_for_behavior(keyword)
                techniques.extend(
                    _techniques(
                        entries,
                        evidence=(
                            f"Wazuh alert references behavior '{keyword}' "
                            f"(rule groups: {groups})."
                        ),
                        confidence=_BEHAVIOR_CONFIDENCE,
                    )
                )

        # 3. High-severity fallback.
        try:
            severity = int(output.get("severity", 0) or 0)
        except (TypeError, ValueError):
            severity = 0
        if severity >= 12 and not techniques:
            entries = self._kb.techniques_for_malware("trojan")
            techniques.extend(
                _techniques(
                    entries,
                    evidence=(
                        f"Wazuh alert has critical rule level {severity}; "
                        "no specific technique matched, defaulting to execution."
                    ),
                    confidence=_BEHAVIOR_CONFIDENCE,
                )
            )
        return techniques

    # ------------------------------------------------------------------
    # Generic / behavioral fallback
    # ------------------------------------------------------------------

    def _map_generic(self, output: dict[str, Any]) -> list[MitreTechnique]:
        """Map an unknown tool's output using behavior-keyword matching.

        Serializes the output to text and matches known behavior keywords
        (c2, beacon, exfil, brute force, scanning, ...). Deterministic and
        offline.
        """
        flat = _flatten_to_text(output).lower()
        techniques: list[MitreTechnique] = []
        matched: set[str] = set()

        for keyword in self._kb._behaviors:  # noqa: SLF001 - internal lookup
            if keyword in flat and keyword not in matched:
                matched.add(keyword)
                entries = self._kb.techniques_for_behavior(keyword)
                techniques.extend(
                    _techniques(
                        entries,
                        evidence=f"Output references behavior '{keyword}'.",
                        confidence=_BEHAVIOR_CONFIDENCE,
                    )
                )
        return techniques


def _flatten_to_text(value: Any) -> str:
    """Best-effort flattening of a nested structure into lowercase text."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    if isinstance(value, dict):
        return " ".join(_flatten_to_text(v) for v in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten_to_text(v) for v in value)
    return str(value)


__all__ = ["MitreMapper"]
