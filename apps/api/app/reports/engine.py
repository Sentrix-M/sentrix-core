"""Report Engine — assemble an :class:`IncidentReport` from investigation data.

The :class:`ReportEngine` is the core of the Phase 13 reporting feature. It
consumes :

- structured tool results (:class:`~app.tools.base.ToolResult` from Nmap,
  VirusTotal, Shodan, Wazuh)
- a MITRE ATT&CK mapping (:class:`~app.mitre.models.MitreMapping`)
- optional RAG context (:class:`SearchResultItem` list)
- an AI provider summary (:class:`~app.providers.base.BaseProvider`)

and produces a single structured :class:`IncidentReport`.

Extensibility
-------------
The engine is tool-agnostic by design: it inspects each result's ``tool`` name
and routes it to a per-tool extractor. Future tools (DNS, WHOIS, GeoIP, Sigma,
YARA, Suricata) can contribute by adding a small extractor function and
registering it in the :data:`_extractors` dispatch table — no change to the
engine's core flow.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.kernel.prompt_builder import Prompt
from app.kernel.response_builder import ProviderOutput
from app.mitre.mapper import MitreMapper
from app.mitre.models import MitreMapping
from app.providers.base import BaseProvider
from app.rag.schemas import SearchResultItem
from app.reports.models import (
    AffectedAsset,
    IncidentReport,
    IndicatorOfCompromise,
    RiskAssessment,
    Severity,
    TimelineEvent,
)
from app.tools.base import ToolResult

#: Default system instruction used when asking the provider for an executive summary.
_EXECUTIVE_SUMMARY_PROMPT = (
    "You are a senior SOC analyst. Write a concise, professional executive "
    "summary of the cybersecurity incident described by the following "
    "investigation data. Highlight the confirmed impact, the likely "
    "adversary behaviour, and the recommended containment steps. Use plain "
    "language suitable for management."
)

#: Mapping of tool name → extractor callable. Extend to add new tools.
_Extractor = Callable[[dict[str, Any]], dict[str, Any]]


def _extract_affected_assets(output: dict[str, Any]) -> list[AffectedAsset]:
    """Extract affected assets from any tool output."""
    assets: list[AffectedAsset] = []
    # Nmap hosts + Shodan IP/hostnames + Wazuh agent.
    for host in output.get("hosts", []) if isinstance(output.get("hosts"), list) else []:
        if isinstance(host, dict):
            ip = host.get("ip") or host.get("target")
            if ip:
                assets.append(AffectedAsset(asset_type="host", value=str(ip)))
            if host.get("hostname"):
                assets.append(
                    AffectedAsset(
                        asset_type="hostname",
                        value=str(host["hostname"]),
                    )
                )
    ip = output.get("ip")
    if ip:
        assets.append(AffectedAsset(asset_type="ip", value=str(ip)))
    for hostname in output.get("hostnames", []) if isinstance(output.get("hostnames"), list) else []:
        assets.append(AffectedAsset(asset_type="hostname", value=str(hostname)))
    agent = output.get("agent")
    if isinstance(agent, dict) and agent.get("name"):
        assets.append(
            AffectedAsset(
                asset_type="endpoint",
                value=str(agent["name"]),
                detail=str(agent.get("id", "")),
            )
        )
    return _dedupe_assets(assets)


def _dedupe_assets(assets: list[AffectedAsset]) -> list[AffectedAsset]:
    """Return assets with duplicate (type, value) pairs removed."""
    seen: set[tuple[str, str]] = set()
    unique: list[AffectedAsset] = []
    for asset in assets:
        key = (asset.asset_type, asset.value)
        if key in seen:
            continue
        seen.add(key)
        unique.append(asset)
    return unique


def _extract_iocs(output: dict[str, Any]) -> list[IndicatorOfCompromise]:
    """Extract indicators of compromise from a tool output."""
    iocs: list[IndicatorOfCompromise] = []
    # VirusTotal query.
    query = output.get("query")
    if query:
        iocs.append(
            IndicatorOfCompromise(
                indicator_type=str(output.get("indicator_type", "unknown")),
                value=str(query),
            )
        )
    # Shodan IP/domains/vulnerabilities.
    ip = output.get("ip")
    if ip:
        iocs.append(IndicatorOfCompromise(indicator_type="ip", value=str(ip)))
    for domain in output.get("domains", []) if isinstance(output.get("domains"), list) else []:
        iocs.append(IndicatorOfCompromise(indicator_type="domain", value=str(domain)))
    for cve in output.get("vulnerabilities", []) if isinstance(output.get("vulnerabilities"), list) else []:
        iocs.append(IndicatorOfCompromise(indicator_type="cve", value=str(cve)))
    # Wazuh MITRE ids.
    rule = output.get("rule")
    if isinstance(rule, dict):
        for mid in rule.get("mitre", []) if isinstance(rule.get("mitre"), list) else []:
            iocs.append(IndicatorOfCompromise(indicator_type="mitre", value=str(mid)))
    return iocs


def _extract_nmap(output: dict[str, Any]) -> dict[str, Any]:
    """Extract the Nmap findings section."""
    hosts = output.get("hosts", [])
    if not isinstance(hosts, list):
        hosts = []
    return {
        "target": output.get("target", ""),
        "execution_time": output.get("execution_time", 0),
        "hosts": hosts,
    }


def _extract_virustotal(output: dict[str, Any]) -> dict[str, Any]:
    """Extract the VirusTotal findings section."""
    return {
        "query": output.get("query", ""),
        "indicator_type": output.get("indicator_type", ""),
        "malicious": output.get("malicious", 0),
        "suspicious": output.get("suspicious", 0),
        "harmless": output.get("harmless", 0),
        "permalink": output.get("permalink", ""),
    }


def _extract_shodan(output: dict[str, Any]) -> dict[str, Any]:
    """Extract the Shodan findings section."""
    return {
        "query": output.get("query", ""),
        "ip": output.get("ip", ""),
        "organization": output.get("organization", ""),
        "asn": output.get("asn", ""),
        "country": output.get("country", ""),
        "ports": output.get("ports", []),
        "services": output.get("services", []),
        "vulnerabilities": output.get("vulnerabilities", []),
        "risk_score": output.get("risk_score", ""),
        "permalink": output.get("permalink", ""),
    }


def _extract_wazuh(output: dict[str, Any]) -> dict[str, Any]:
    """Extract the Wazuh findings section (single alert or recent-alerts list)."""
    if "alerts" in output and isinstance(output.get("alerts"), list):
        return {
            "operation": output.get("operation", "recent_alerts"),
            "count": output.get("count", len(output["alerts"])),
            "alerts": output["alerts"],
        }
    return {
        "operation": output.get("operation", "alert"),
        "alert": output.get("alert", {}),
        "rule": output.get("rule", {}),
        "severity": output.get("severity", 0),
        "timestamp": output.get("timestamp", ""),
        "recommendations": output.get("recommendations", []),
    }


#: Dispatch table mapping tool name → extractor for the tool-specific sections.
_EXTRACTORS: dict[str, _Extractor] = {
    "nmap": _extract_nmap,
    "virustotal": _extract_virustotal,
    "shodan": _extract_shodan,
    "wazuh": _extract_wazuh,
}


class ReportEngine:
    """Assembles an :class:`IncidentReport` from investigation context.

    :param provider: Optional :class:`BaseProvider` used to generate the
        executive summary. When omitted, ``self.provider`` is ``None`` and
        the summary is left empty (callers may fill it later).
    :param mitre_mapper: Optional :class:`MitreMapper`. Defaults to a fresh
        instance so the engine is self-contained and offline by default.
    :param generated_by: Label stamped into the report's ``generated_by``.
    """

    def __init__(
        self,
        *,
        provider: BaseProvider | None = None,
        mitre_mapper: MitreMapper | None = None,
        generated_by: str = "Sentrix Incident Report Generator",
    ) -> None:
        self._provider = provider
        self._mitre_mapper = mitre_mapper or MitreMapper()
        self._generated_by = generated_by

    @property
    def provider(self) -> BaseProvider | None:
        """The configured AI provider (may be ``None``)."""
        return self._provider

    @property
    def mitre_mapper(self) -> MitreMapper:
        """The MITRE mapper used for enrichment."""
        return self._mitre_mapper

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        *,
        incident_title: str,
        tool_results: list[ToolResult],
        rag_context: list[SearchResultItem] | None = None,
        query: str | None = None,
        analyst_notes: list[str] | None = None,
        recommendations: list[str] | None = None,
    ) -> IncidentReport:
        """Build an :class:`IncidentReport` from investigation context.

        :param incident_title: Short title for the incident.
        :param tool_results: Tool results from the Tool Engine.
        :param rag_context: Optional RAG search results to include.
        :param query: Override the RAG/AI query. When omitted one is built
            automatically from the tool data.
        :param analyst_notes: Optional analyst observations.
        :param recommendations: Optional remediation recommendations.
        :returns: A populated :class:`IncidentReport`.
        """
        # Collect tool findings + aggregate model data.
        (
            findings,
            assets,
            iocs,
            timeline,
            recommendations_from_tools,
        ) = self._collect(tool_results)

        effective_recs = self._merge_strings(
            recommendations_from_tools, recommendations or []
        )

        # MITRE mapping across all successful tool results.
        mitre_mapping = self._collect_mitre(tool_results)

        # RAG context query (override or auto-built from evidence).
        rag_results = rag_context or []
        rag_query = query or self._build_rag_query(
            incident_title, findings, iocs, mitre_mapping
        )

        # Severity derived from multiple evidence sources.
        severity = self._calculate_severity(tool_results, mitre_mapping)

        # Executive summary via the configured provider (provider-agnostic).
        summary = self._generate_summary(
            incident_title,
            severity,
            findings,
            iocs,
            mitre_mapping,
            rag_results,
            rag_query,
        )

        return IncidentReport(
            incident_title=incident_title,
            severity=severity,
            executive_summary=summary,
            timeline=timeline,
            affected_assets=assets,
            iocs=iocs,
            mitre_mapping=mitre_mapping,
            nmap_findings=findings.get("nmap", []),
            virustotal_findings=findings.get("virustotal", []),
            shodan_findings=findings.get("shodan", []),
            wazuh_alerts=findings.get("wazuh", []),
            risk_assessment=self._risk_assessment(severity),
            recommendations=effective_recs,
            analyst_notes=analyst_notes or [],
            rag_context=[r.model_dump(mode="json") for r in rag_results],
            generated_by=self._generated_by,
        )

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    def _collect(
        self, tool_results: list[ToolResult]
    ) -> tuple[dict[str, list[dict[str, Any]]], list[AffectedAsset], list[IndicatorOfCompromise], list[TimelineEvent], list[str]]:
        """Collect findings, assets, IOCs, timeline, and recommendations."""
        findings: dict[str, list[dict[str, Any]]] = {
            "nmap": [],
            "virustotal": [],
            "shodan": [],
            "wazuh": [],
        }
        assets: list[AffectedAsset] = []
        iocs: list[IndicatorOfCompromise] = []
        timeline: list[TimelineEvent] = []
        recommendations: list[str] = []

        for result in tool_results:
            if not result.success:
                continue
            output = result.output
            if not isinstance(output, dict):
                continue
            tool = result.tool
            extractor = _EXTRACTORS.get(tool)
            if extractor is not None:
                section = extractor(output)
                findings.setdefault(tool, []).append(section)
            assets.extend(_extract_affected_assets(output))
            iocs.extend(_extract_iocs(output))

            # Wazuh recommendations become remediation suggestions.
            if tool == "wazuh":
                recommendations.extend(output.get("recommendations", []))

            # Timeline: nmap timestamp, virustotal, wazuh alert timestamp.
            ts = output.get("timestamp")
            if tool == "wazuh" and ts:
                timeline.append(
                    TimelineEvent(
                        timestamp=str(ts),
                        description="Wazuh security alert detected.",
                    )
                )

        return findings, _dedupe_assets(assets), _dedupe_iocs(iocs), timeline, _dedupe_list(recommendations)

    def _collect_mitre(self, tool_results: list[ToolResult]) -> dict[str, Any]:
        """Map all successful tool results to a single MITRE mapping dict.

        Combines the exposed technique lists from each mapping, deduplicating
        by technique ID, and recomputes the overall confidence.
        """
        combined: dict[str, Any] = {
            "techniques": [],
            "tactics": [],
            "mitigations": [],
            "detections": [],
            "confidence": 0.0,
        }
        techniques: list[dict[str, Any]] = []
        confidences: list[float] = []
        for result in tool_results:
            if not result.success:
                continue
            mapping: MitreMapping = self._mitre_mapper.map(result)
            data = mapping.to_dict()
            for technique in data.get("techniques", []):
                techniques.append(technique)
            confidences.append(mapping.confidence)

        if techniques:
            seen: set[str] = set()
            unique: list[dict[str, Any]] = []
            for technique in techniques:
                tid = technique.get("technique_id", "")
                if tid in seen:
                    continue
                seen.add(tid)
                unique.append(technique)
            combined["techniques"] = unique
            combined["tactics"] = sorted(
                {t.get("tactic", "") for t in unique if t.get("tactic")}
            )
            combined["mitigations"] = sorted(
                {t.get("mitigation", "") for t in unique if t.get("mitigation")}
            )
            combined["detections"] = sorted(
                {t.get("detection", "") for t in unique if t.get("detection")}
            )
            combined["confidence"] = round(
                sum(confidences) / len(confidences), 3
            )
        return combined

    # ------------------------------------------------------------------
    # RAG query + summary
    # ------------------------------------------------------------------

    def _build_rag_query(
        self,
        incident_title: str,
        findings: dict[str, list[dict[str, Any]]],
        iocs: list[IndicatorOfCompromise],
        mitre_mapping: dict[str, Any],
    ) -> str:
        """Build a RAG search query from the incident evidence."""
        terms: list[str] = [incident_title]

        # VirusTotal tags/categories.
        for vt in findings.get("virustotal", []):
            if isinstance(vt, dict):
                tags = vt.get("tags") or []
                if isinstance(tags, list):
                    terms.extend(str(t) for t in tags[:5])

        # Shodan services / CVEs.
        for shodan in findings.get("shodan", []):
            if isinstance(shodan, dict):
                services = shodan.get("services") or []
                for service in services if isinstance(services, list) else []:
                    if isinstance(service, dict) and service.get("product"):
                        terms.append(str(service["product"]))
                vulns = shodan.get("vulnerabilities") or []
                if isinstance(vulns, list):
                    terms.extend(str(v) for v in vulns[:5])

        # MITRE technique names.
        for technique in mitre_mapping.get("techniques", []):
            if isinstance(technique, dict) and technique.get("name"):
                terms.append(str(technique["name"]))

        # IOCs.
        terms.extend(ioc.value for ioc in iocs[:5])

        # Deduplicate and cap.
        seen: set[str] = set()
        cleaned: list[str] = []
        for term in terms:
            term = str(term).strip()
            if not term or term.lower() in seen:
                continue
            seen.add(term.lower())
            cleaned.append(term)
        return " ".join(cleaned[:20])

    def _generate_summary(
        self,
        incident_title: str,
        severity: Severity,
        findings: dict[str, list[dict[str, Any]]],
        iocs: list[IndicatorOfCompromise],
        mitre_mapping: dict[str, Any],
        rag_results: list[SearchResultItem],
        rag_query: str,
    ) -> str:
        """Generate an executive summary via the configured provider.

        Falls back to a deterministic local summary when no provider is
        configured or the provider returns an empty response.
        """
        if self._provider is None:
            return self._fallback_summary(incident_title, severity, findings, iocs)

        evidence = self._evidence_text(findings, iocs, mitre_mapping, rag_results)
        instruction = (
            f"Incident: {incident_title}\n"
            f"Severity: {severity.value}\n"
            f"Investigation data:\n{evidence}\n"
            f"RAG query used: {rag_query}"
        )
        prompt = Prompt(
            system=_EXECUTIVE_SUMMARY_PROMPT,
            instruction=instruction,
            context=_empty_context(),
        )
        try:
            output: ProviderOutput = self._provider.generate(prompt)
            text = (output.text or "").strip()
        except Exception:  # noqa: BLE001 - summary must never raise
            text = ""
        return text or self._fallback_summary(incident_title, severity, findings, iocs)

    def _fallback_summary(
        self,
        incident_title: str,
        severity: Severity,
        findings: dict[str, list[dict[str, Any]]],
        iocs: list[IndicatorOfCompromise],
    ) -> str:
        """Deterministic summary used when no provider is configured."""
        parts = [
            f"{severity.value} severity incident: {incident_title}.",
        ]
        if findings.get("wazuh"):
            parts.append("Wazuh security alerts were detected.")
        if findings.get("virustotal"):
            parts.append("VirusTotal flagged indicators as potentially malicious.")
        if findings.get("nmap"):
            parts.append("Nmap identified exposed services.")
        if findings.get("shodan"):
            parts.append("Shodan reported internet-exposure findings.")
        if iocs:
            parts.append(f"{len(iocs)} indicator(s) of compromise were identified.")
        return " ".join(parts)

    # ------------------------------------------------------------------
    # Severity + risk
    # ------------------------------------------------------------------

    def _calculate_severity(
        self,
        tool_results: list[ToolResult],
        mitre_mapping: dict[str, Any],
    ) -> Severity:
        """Derive overall severity from multiple evidence sources."""
        score = 0.0

        for result in tool_results:
            if not result.success:
                continue
            output = result.output
            if not isinstance(output, dict):
                continue
            if result.tool == "wazuh":
                try:
                    level = int(output.get("severity", 0) or 0)
                except (TypeError, ValueError):
                    level = 0
                score = max(score, min(level / 15.0, 1.0))
            elif result.tool == "virustotal":
                malicious = int(output.get("malicious", 0) or 0)
                if malicious >= 10:
                    score = max(score, 1.0)
                elif malicious >= 5:
                    score = max(score, 0.8)
                elif malicious >= 1:
                    score = max(score, 0.6)
            elif result.tool == "shodan":
                risk = str(output.get("risk_score", "")).lower()
                if risk == "high":
                    score = max(score, 0.8)
                elif risk == "medium":
                    score = max(score, 0.5)
            elif result.tool == "nmap":
                open_ports = sum(
                    len(host.get("open_ports", []))
                    for host in output.get("hosts", [])
                    if isinstance(host, dict)
                )
                if open_ports >= 10:
                    score = max(score, 0.6)
                elif open_ports >= 1:
                    score = max(score, 0.3)

        # MITRE confidence contribution.
        confidence = float(mitre_mapping.get("confidence", 0) or 0)
        score = max(score, confidence * 0.7)

        if score >= 0.8:
            return Severity.CRITICAL
        if score >= 0.55:
            return Severity.HIGH
        if score >= 0.3:
            return Severity.MEDIUM
        return Severity.LOW

    def _risk_assessment(self, severity: Severity) -> RiskAssessment:
        """Map a severity to a qualitative risk assessment."""
        if severity == Severity.CRITICAL:
            return RiskAssessment(likelihood="High", impact="High", score=0.9)
        if severity == Severity.HIGH:
            return RiskAssessment(likelihood="High", impact="Medium", score=0.7)
        if severity == Severity.MEDIUM:
            return RiskAssessment(likelihood="Medium", impact="Medium", score=0.5)
        return RiskAssessment(likelihood="Low", impact="Low", score=0.2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _evidence_text(
        self,
        findings: dict[str, list[dict[str, Any]]],
        iocs: list[IndicatorOfCompromise],
        mitre_mapping: dict[str, Any],
        rag_results: list[SearchResultItem],
    ) -> str:
        """Serialize the investigation evidence into a compact text block."""
        blocks: list[str] = []
        for section_name in ("nmap", "virustotal", "shodan", "wazuh"):
            items = findings.get(section_name, [])
            if items:
                blocks.append(f"{section_name}: {items}")
        if iocs:
            blocks.append("iocs: " + str([i.model_dump() for i in iocs]))
        if mitre_mapping.get("techniques"):
            blocks.append("mitre: " + str(mitre_mapping["techniques"]))
        if rag_results:
            blocks.append(
                "rag_context: "
                + str([r.model_dump(mode="json") for r in rag_results])
            )
        return "\n".join(blocks)

    @staticmethod
    def _merge_strings(*lists: list[str]) -> list[str]:
        """Merge and deduplicate string lists, preserving order."""
        seen: set[str] = set()
        result: list[str] = []
        for items in lists:
            for item in items:
                item = str(item).strip()
                if item and item.lower() not in seen:
                    seen.add(item.lower())
                    result.append(item)
        return result


def _dedupe_iocs(iocs: list[IndicatorOfCompromise]) -> list[IndicatorOfCompromise]:
    """Return IOCs with duplicate (type, value) pairs removed."""
    seen: set[tuple[str, str]] = set()
    unique: list[IndicatorOfCompromise] = []
    for ioc in iocs:
        key = (ioc.indicator_type, ioc.value)
        if key in seen:
            continue
        seen.add(key)
        unique.append(ioc)
    return unique


def _dedupe_list(items: list[str]) -> list[str]:
    """Return a case-insensitive deduplicated list, preserving order."""
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        item = str(item).strip()
        if item and item.lower() not in seen:
            seen.add(item.lower())
            result.append(item)
    return result


def _empty_context():
    """Build an empty conversation context for the summary prompt."""
    from app.kernel.context_builder import ContextMessage, ConversationContext

    return ConversationContext(
        conversation_id="report-gen",
        user_message=ContextMessage(
            role="user",
            content="Generate an incident report.",
        ),
    )


__all__ = ["ReportEngine", "_EXTRACTORS"]
