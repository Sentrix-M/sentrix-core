"""Local MITRE ATT&CK knowledge base for the Sentrix mapping engine.

The knowledge base is a data-driven, offline store that maps real-world
security findings to MITRE ATT&CK techniques. It is intentionally kept
versioned and extensible so future ATT&CK updates can be applied without
changing the mapper or the kernel.

Mapping categories
------------------
- **Services** — exposed network services (ssh, rdp, smb, http, ...) to the
  techniques an attacker gains by abusing them.
- **CVEs** — known vulnerabilities (and a generic CVE fallback) to the
  technique used to exploit them.
- **Malware families** — family/behaviour labels (ransomware, coinminer,
  backdoor, ...) to the techniques they typically exhibit.
- **Threat behaviors** — keyword indicators (c2/beacon, exfiltration, brute
  force, scanning, ...) to techniques.

Every entry carries technique ID, name, tactic, mitigation, and detection so
the mapper can produce a fully self-contained mapping dict.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.mitre.models import MitreTechnique


@dataclass(frozen=True)
class TechniqueEntry:
    """A single ATT&CK technique definition in the knowledge base."""

    technique_id: str
    name: str
    tactic: str
    mitigation: str
    detection: str


def _technique(entry: TechniqueEntry, *, evidence: str, confidence: float) -> MitreTechnique:
    """Build a :class:`MitreTechnique` from a knowledge-base entry."""
    return MitreTechnique(
        technique_id=entry.technique_id,
        name=entry.name,
        tactic=entry.tactic,
        mitigation=entry.mitigation,
        detection=entry.detection,
        evidence=evidence,
        confidence=confidence,
    )


#: The ATT&CK revision this knowledge base tracks.
ATTACK_VERSION = "v13.1"


class MitreKnowledgeBase:
    """Data-driven, offline, extensible ATT&CK knowledge base.

    :param version: ATT&CK revision label. Defaults to
        :data:`ATTACK_VERSION`.
    """

    def __init__(self, *, version: str = ATTACK_VERSION) -> None:
        self.version = version

        #: Service name (lowercase) → technique(s).
        self._services: dict[str, list[TechniqueEntry]] = _SERVICES
        #: CVE identifier (lowercase) → technique(s).
        self._cves: dict[str, list[TechniqueEntry]] = _CVES
        #: Malware family / behaviour keyword (lowercase) → technique(s).
        self._malware: dict[str, list[TechniqueEntry]] = _MALWARE
        #: Behavior keyword (lowercase) → technique(s).
        self._behaviors: dict[str, list[TechniqueEntry]] = _BEHAVIORS

    # ------------------------------------------------------------------
    # Public lookups
    # ------------------------------------------------------------------

    def techniques_for_service(self, service: str) -> list[TechniqueEntry]:
        """Return technique entries for an exposed service name."""
        return list(self._services.get((service or "").strip().lower(), []))

    def techniques_for_cve(self, cve: str) -> list[TechniqueEntry]:
        """Return technique entries for a CVE identifier.

        Falls back to the generic "exploit public-facing application"
        technique when the specific CVE is unknown.
        """
        key = (cve or "").strip().lower()
        if key and key in self._cves:
            return list(self._cves[key])
        if key:
            return list(self._cves["_generic_cve"])
        return []

    def techniques_for_malware(self, label: str) -> list[TechniqueEntry]:
        """Return technique entries for a malware family/behaviour label."""
        return list(self._malware.get((label or "").strip().lower(), []))

    def techniques_for_behavior(self, keyword: str) -> list[TechniqueEntry]:
        """Return technique entries for a threat-behavior keyword."""
        return list(self._behaviors.get((keyword or "").strip().lower(), []))

    def technique_by_id(self, technique_id: str) -> TechniqueEntry | None:
        """Return a knowledge-base entry by ATT&CK technique ID.

        Searches all collections (services, CVEs, malware, behaviors) for an
        entry whose ``technique_id`` matches ``technique_id`` (case-insensitive).
        Returns ``None`` when the ID is unknown.
        """
        target = (technique_id or "").strip().upper()
        if not target:
            return None
        for collection in (self._services, self._cves, self._malware, self._behaviors):
            for entries in collection.values():
                for entry in entries:
                    if entry.technique_id.upper() == target:
                        return entry
        return None

    # ------------------------------------------------------------------
    # Extensibility (future ATT&CK updates)
    # ------------------------------------------------------------------

    def register_service(
        self, service: str, entries: list[TechniqueEntry]
    ) -> None:
        """Register technique mappings for a service name."""
        self._services[(service or "").strip().lower()] = list(entries)

    def register_cve(self, cve: str, entries: list[TechniqueEntry]) -> None:
        """Register technique mappings for a CVE identifier."""
        self._cves[(cve or "").strip().lower()] = list(entries)

    def register_malware(self, label: str, entries: list[TechniqueEntry]) -> None:
        """Register technique mappings for a malware family/behaviour."""
        self._malware[(label or "").strip().lower()] = list(entries)

    def register_behavior(self, keyword: str, entries: list[TechniqueEntry]) -> None:
        """Register technique mappings for a behavior keyword."""
        self._behaviors[(keyword or "").strip().lower()] = list(entries)

    def to_dict(self) -> dict[str, Any]:
        """Serialize the knowledge base (for diagnostics/inspection)."""
        return {
            "version": self.version,
            "services": sorted(self._services),
            "cves": sorted(k for k in self._cves if k != "_generic_cve"),
            "malware": sorted(self._malware),
            "behaviors": sorted(self._behaviors),
        }


# ---------------------------------------------------------------------------
# Knowledge-base data (services, CVEs, malware, behaviors)
# ---------------------------------------------------------------------------

_SERVICES: dict[str, list[TechniqueEntry]] = {
    "ssh": [
        TechniqueEntry(
            "T1110",
            "Brute Force",
            "Credential Access",
            "Use multi-factor authentication and enforce strong password policies.",
            "Monitor for many failed authentication attempts and unusual SSH login times.",
        )
    ],
    "rdp": [
        TechniqueEntry(
            "T1021.001",
            "Remote Desktop Protocol",
            "Lateral Movement",
            "Disable RDP on non-essential hosts and restrict via firewall rules.",
            "Monitor RDP logon events (Event ID 4624/4625) and unusual source IPs.",
        )
    ],
    "smb": [
        TechniqueEntry(
            "T1021.002",
            "SMB/Windows Admin Shares",
            "Lateral Movement",
            "Restrict SMB access, apply the principle of least privilege, and disable SMBv1.",
            "Monitor SMB connection events and abnormal file-share access patterns.",
        )
    ],
    "http": [
        TechniqueEntry(
            "T1071.001",
            "Web Protocols",
            "Command & Control",
            "Use allow-listed egress proxies and inspect HTTP traffic.",
            "Monitor for anomalous HTTP/S traffic to known-bad destinations.",
        )
    ],
    "https": [
        TechniqueEntry(
            "T1071.001",
            "Web Protocols",
            "Command & Control",
            "Use allow-listed egress proxies and inspect HTTPS traffic.",
            "Monitor encrypted tunnels and certificate anomalies.",
        )
    ],
    "ftp": [
        TechniqueEntry(
            "T1041",
            "Exfiltration Over C2 Channel",
            "Exfiltration",
            "Block or restrict outbound FTP and require secure file transfer.",
            "Monitor for large outbound FTP transfers and anonymous logins.",
        )
    ],
    "telnet": [
        TechniqueEntry(
            "T1110",
            "Brute Force",
            "Credential Access",
            "Disable telnet and require secure remote-access protocols.",
            "Monitor for repeated failed logins over telnet.",
        )
    ],
    "mysql": [
        TechniqueEntry(
            "T1190",
            "Exploit Public-Facing Application",
            "Initial Access",
            "Patch database servers and restrict database ports to trusted hosts.",
            "Monitor database logs for failed logins and known-exploit signatures.",
        )
    ],
    "postgresql": [
        TechniqueEntry(
            "T1190",
            "Exploit Public-Facing Application",
            "Initial Access",
            "Patch database servers and restrict database ports to trusted hosts.",
            "Monitor database logs for failed logins and known-exploit signatures.",
        )
    ],
    "redis": [
        TechniqueEntry(
            "T1190",
            "Exploit Public-Facing Application",
            "Initial Access",
            "Disable unauthenticated Redis access and bind to trusted interfaces.",
            "Monitor Redis for unauthorized CONFIG commands and data exfiltration.",
        )
    ],
    "mssql": [
        TechniqueEntry(
            "T1190",
            "Exploit Public-Facing Application",
            "Initial Access",
            "Patch database servers and restrict database ports to trusted hosts.",
            "Monitor database logs for failed logins and known-exploit signatures.",
        )
    ],
    "dns": [
        TechniqueEntry(
            "T1071.004",
            "DNS",
            "Command & Control",
            "Use DNS over HTTPS and monitor for DNS tunneling.",
            "Monitor for unusual DNS queries, long subdomains, and TXT record payloads.",
        )
    ],
    "snmp": [
        TechniqueEntry(
            "T1046",
            "Network Service Discovery",
            "Discovery",
            "Restrict SNMP to trusted hosts and use SNMPv3.",
            "Monitor SNMP walk requests and unusual community strings.",
        )
    ],
    "ntp": [
        TechniqueEntry(
            "T1071.004",
            "DNS",
            "Command & Control",
            "Restrict NTP amplification and monitor for abuse.",
            "Monitor for excessive NTP queries from a single source.",
        )
    ],
}

_CVES: dict[str, list[TechniqueEntry]] = {
    "_generic_cve": [
        TechniqueEntry(
            "T1190",
            "Exploit Public-Facing Application",
            "Initial Access",
            "Apply vendor patches promptly and use a web application firewall.",
            "Monitor application logs for exploit attempts and known-vulnerability signatures.",
        )
    ],
    "cve-2014-0160": [  # Heartbleed
        TechniqueEntry(
            "T1190",
            "Exploit Public-Facing Application",
            "Initial Access",
            "Patch OpenSSL and rotate all exposed credentials.",
            "Monitor TLS handshakes for oversized heartbeat requests.",
        )
    ],
    "cve-2017-0144": [  # EternalBlue
        TechniqueEntry(
            "T1210",
            "Exploitation of Remote Services",
            "Lateral Movement",
            "Patch SMB (MS17-010) and disable SMBv1.",
            "Monitor for SMB exploit payloads and abnormal SMB traffic.",
        )
    ],
    "cve-2017-0145": [  # EternalBlue (wannacry)
        TechniqueEntry(
            "T1210",
            "Exploitation of Remote Services",
            "Lateral Movement",
            "Patch SMB (MS17-010) and disable SMBv1.",
            "Monitor for SMB exploit payloads and abnormal SMB traffic.",
        )
    ],
    "cve-2021-44228": [  # Log4Shell
        TechniqueEntry(
            "T1190",
            "Exploit Public-Facing Application",
            "Initial Access",
            "Patch Log4j and restrict outbound JNDI lookups.",
            "Monitor logs for JNDI lookup strings and outbound LDAP/RMI traffic.",
        )
    ],
    "cve-2021-26855": [  # ProxyLogon
        TechniqueEntry(
            "T1190",
            "Exploit Public-Facing Application",
            "Initial Access",
            "Patch Exchange Server and apply hardening guidance.",
            "Monitor Exchange logs for unauthorized webshell creation.",
        )
    ],
}

_MALWARE: dict[str, list[TechniqueEntry]] = {
    "ransomware": [
        TechniqueEntry(
            "T1486",
            "Data Encrypted for Impact",
            "Impact",
            "Maintain offline backups and segment the network.",
            "Monitor for mass file modifications and encryption-in-progress indicators.",
        )
    ],
    "coinminer": [
        TechniqueEntry(
            "T1496",
            "Resource Hijacking",
            "Impact",
            "Restrict compute resources and monitor for unusual CPU usage.",
            "Monitor for cryptocurrency-mining processes and excessive compute.",
        )
    ],
    "backdoor": [
        TechniqueEntry(
            "T1219",
            "Remote Access Software",
            "Command & Control",
            "Block known remote-access tools and monitor for unknown binaries.",
            "Monitor for unexpected remote-access software and outbound connections.",
        )
    ],
    "trojan": [
        TechniqueEntry(
            "T1204",
            "User Execution",
            "Execution",
            "User education and application allow-listing.",
            "Monitor for execution of untrusted binaries and macro-enabled documents.",
        )
    ],
    "worm": [
        TechniqueEntry(
            "T1210",
            "Exploitation of Remote Services",
            "Lateral Movement",
            "Patch known vulnerabilities and segment the network.",
            "Monitor for self-propagating network activity and repeated exploitation.",
        )
    ],
    "botnet": [
        TechniqueEntry(
            "T1071",
            "Application Layer Protocol",
            "Command & Control",
            "Restrict egress traffic and monitor for C2 beacons.",
            "Monitor for periodic beacons and unusual outbound connections.",
        )
    ],
}

_BEHAVIORS: dict[str, list[TechniqueEntry]] = {
    "c2": [
        TechniqueEntry(
            "T1071",
            "Application Layer Protocol",
            "Command & Control",
            "Restrict egress traffic and use allow-listed proxies.",
            "Monitor for periodic beacons and unusual outbound connections.",
        )
    ],
    "beacon": [
        TechniqueEntry(
            "T1071.001",
            "Web Protocols",
            "Command & Control",
            "Use allow-listed egress proxies and inspect HTTP traffic.",
            "Monitor for periodic HTTP beacons and jitter patterns.",
        )
    ],
    "exfil": [
        TechniqueEntry(
            "T1041",
            "Exfiltration Over C2 Channel",
            "Exfiltration",
            "Restrict outbound data transfers and monitor large egress volumes.",
            "Monitor for large outbound transfers during off-hours.",
        )
    ],
    "exfiltration": [
        TechniqueEntry(
            "T1041",
            "Exfiltration Over C2 Channel",
            "Exfiltration",
            "Restrict outbound data transfers and monitor large egress volumes.",
            "Monitor for large outbound transfers during off-hours.",
        )
    ],
    "brute force": [
        TechniqueEntry(
            "T1110",
            "Brute Force",
            "Credential Access",
            "Enforce strong passwords and enable account lockout.",
            "Monitor for many failed authentication attempts.",
        )
    ],
    "bruteforce": [
        TechniqueEntry(
            "T1110",
            "Brute Force",
            "Credential Access",
            "Enforce strong passwords and enable account lockout.",
            "Monitor for many failed authentication attempts.",
        )
    ],
    "scan": [
        TechniqueEntry(
            "T1046",
            "Network Service Discovery",
            "Discovery",
            "Restrict network scanning and use vulnerability management.",
            "Monitor for port scans and service enumeration.",
        )
    ],
    "scanning": [
        TechniqueEntry(
            "T1046",
            "Network Service Discovery",
            "Discovery",
            "Restrict network scanning and use vulnerability management.",
            "Monitor for port scans and service enumeration.",
        )
    ],
    "phishing": [
        TechniqueEntry(
            "T1566",
            "Phishing",
            "Initial Access",
            "Use email filtering and user security awareness training.",
            "Monitor for suspicious emails and reported phishing.",
        )
    ],
    "lateral movement": [
        TechniqueEntry(
            "T1021",
            "Remote Services",
            "Lateral Movement",
            "Segment the network and restrict remote services.",
            "Monitor for lateral movement and unusual remote logons.",
        )
    ],
    "persistence": [
        TechniqueEntry(
            "T1547",
            "Boot or Logon Autostart Execution",
            "Persistence",
            "Monitor registry and startup locations for unauthorized changes.",
            "Monitor for new autostart entries and service modifications.",
        )
    ],
    "privilege escalation": [
        TechniqueEntry(
            "T1068",
            "Exploitation for Privilege Escalation",
            "Privilege Escalation",
            "Patch vulnerabilities and apply least privilege.",
            "Monitor for unexpected privilege elevation and exploit attempts.",
        )
    ],
    "reconnaissance": [
        TechniqueEntry(
            "T1595",
            "Active Scanning",
            "Reconnaissance",
            "Monitor and restrict network scanning from external sources.",
            "Monitor for port scans and service enumeration from untrusted IPs.",
        )
    ],
}


__all__ = ["ATTACK_VERSION", "MitreKnowledgeBase", "TechniqueEntry"]
