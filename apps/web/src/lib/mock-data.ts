/**
 * Sentrix Command Center — mock data.
 *
 * Pure UI scaffolding data. All values are static and self-contained;
 * there is intentionally NO backend integration.
 */

export type Severity = "critical" | "high" | "medium" | "low";

export type ToolStatus = "online" | "busy" | "degraded" | "offline";

export type ServiceState = "operational" | "degraded" | "offline";

export type Alert = {
  id: string;
  severity: Severity;
  title: string;
  source: string;
  time: string;
  agent: string;
};

export type Tool = {
  id: string;
  name: string;
  kind: string;
  status: ToolStatus;
  version: string;
  load: number;
};

export type Conversation = {
  id: string;
  title: string;
  preview: string;
  time: string;
  agent: string;
  pinned?: boolean;
};

export type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  time: string;
  reasoning?: string;
  evidence?: string[];
  sources?: string[];
  toolsUsed?: string[];
  executionTime?: string;
};

export type Agent = {
  id: string;
  name: string;
  role: string;
  status: "idle" | "active" | "standby";
  load: number;
};

export type QuickAction = {
  id: string;
  label: string;
  description: string;
  icon: "logs" | "alerts" | "hunt" | "file" | "scan";
};

/* ------------------------------------------------------------------ */
/* Kernel status                                                       */
/* ------------------------------------------------------------------ */

export const kernelStatus = {
  state: "ONLINE",
  version: "sentrix-kernel v2.4.1",
  uptime: "72h 14m",
  sinceLabel: "Core services stabilized",
};

/* ------------------------------------------------------------------ */
/* AI status panel                                                     */
/* ------------------------------------------------------------------ */

export type AiStatusItem = {
  key: string;
  label: string;
  value: number;
  caption: string;
  icon: "cpu" | "memory" | "brain" | "connection" | "database" | "voice" | "target";
  tone: "cyan" | "emerald" | "violet";
};

export const aiStatusItems: AiStatusItem[] = [
  {
    key: "kernel",
    label: "Kernel Status",
    value: 100,
    caption: "Operational",
    icon: "cpu",
    tone: "emerald",
  },
  {
    key: "memory",
    label: "Memory",
    value: 78,
    caption: "Context window 62%",
    icon: "memory",
    tone: "cyan",
  },
  {
    key: "reasoning",
    label: "Reasoning",
    value: 92,
    caption: "Deep analysis mode",
    icon: "brain",
    tone: "violet",
  },
  {
    key: "tools",
    label: "Connected Tools",
    value: 86,
    caption: "12 / 14 available",
    icon: "connection",
    tone: "emerald",
  },
  {
    key: "knowledge",
    label: "Knowledge",
    value: 96,
    caption: "RAG synced · 1.2M docs",
    icon: "database",
    tone: "cyan",
  },
{
    key: "voice",
    label: "Voice",
    value: 92,
    caption: "STT + TTS ready",
    icon: "voice",
    tone: "violet",
  },
  {
    key: "confidence",
    label: "Confidence",
    value: 94,
    caption: "High confidence pacing",
    icon: "target",
    tone: "emerald",
  },
];

export const activeModel = {
  name: "Sentrix Core-2",
  provider: "self-hosted · local",
  latency: "240ms",
};

/* ------------------------------------------------------------------ */
/* System health                                                       */
/* ------------------------------------------------------------------ */

export type SystemMetric = {
  key: string;
  label: string;
  value: number;
  usageLabel: string;
  series: number[];
};

export const systemMetrics: SystemMetric[] = [
  {
    key: "cpu",
    label: "CPU",
    value: 42,
    usageLabel: "8.2 / 16 cores",
    series: [28, 35, 30, 45, 52, 41, 49, 42],
  },
  {
    key: "memory",
    label: "Memory",
    value: 66,
    usageLabel: "42 / 64 GB",
    series: [50, 55, 48, 60, 68, 62, 70, 66],
  },
  {
    key: "disk",
    label: "Disk",
    value: 58,
    usageLabel: "2.9 / 5 TB",
    series: [52, 53, 55, 54, 56, 57, 58, 58],
  },
  {
    key: "network",
    label: "Network",
    value: 71,
    usageLabel: "3.4 Gbps in · 1.1 out",
    series: [40, 65, 55, 80, 60, 75, 50, 71],
  },
];

export const servicesHealth: { name: string; state: ServiceState }[] = [
  { name: "API Gateway", state: "operational" },
  { name: "AI Orchestrator", state: "operational" },
  { name: "Agent Runtime", state: "operational" },
  { name: "Vector DB (Chroma)", state: "operational" },
  { name: "Message Bus", state: "degraded" },
  { name: "Ingest Pipeline", state: "operational" },
];

/* ------------------------------------------------------------------ */
/* Alerts                                                              */
/* ------------------------------------------------------------------ */

export const alerts: Alert[] = [
  {
    id: "al-101",
    severity: "critical",
    title: "Possible C2 beacon detected — endpoint LAB-07",
    source: "Zeek · suricata",
    time: "just now",
    agent: "SOC Agent",
  },
  {
    id: "al-102",
    severity: "high",
    title: "Brute-force pattern on SSH gateway",
    source: "nmap · auth log",
    time: "2m ago",
    agent: "Threat Hunt",
  },
  {
    id: "al-103",
    severity: "high",
    title: "YARA hit: suspicious payload in /tmp",
    source: "yara",
    time: "9m ago",
    agent: "Malware Agent",
  },
  {
    id: "al-104",
    severity: "medium",
    title: "Unusual outbound TLS to new domain",
    source: "suricata",
    time: "18m ago",
    agent: "SOC Agent",
  },
  {
    id: "al-105",
    severity: "low",
    title: "Policy drift on firewall group core-vpc",
    source: "wazuh",
    time: "41m ago",
    agent: "Compliance",
  },
];

/* ------------------------------------------------------------------ */
/* Tools                                                               */
/* ------------------------------------------------------------------ */

export const tools: Tool[] = [
  { id: "nmap", name: "Nmap", kind: "Network Scanner", status: "online", version: "7.95", load: 12 },
  { id: "wireshark", name: "Wireshark", kind: "Packet Analysis", status: "busy", version: "4.4.2", load: 47 },
  { id: "metasploit", name: "Metasploit", kind: "Exploitation", status: "online", version: "6.4.8", load: 8 },
  { id: "burp", name: "Burp Suite", kind: "Web App Testing", status: "online", version: "2025.6", load: 19 },
  { id: "sqlmap", name: "SQLMap", kind: "Injection Testing", status: "degraded", version: "1.8.12", load: 64 },
  { id: "hashcat", name: "Hashcat", kind: "Password Cracking", status: "busy", version: "7.0.0", load: 83 },
  { id: "yara", name: "YARA", kind: "Malware Rules", status: "online", version: "4.5.2", load: 5 },
  { id: "zeek", name: "Zeek", kind: "Network Monitor", status: "online", version: "6.2.1", load: 21 },
  { id: "suricata", name: "Suricata", kind: "IDS/IPS", status: "online", version: "7.0.7", load: 33 },
  { id: "wazuh", name: "Wazuh", kind: "SIEM / XDR", status: "online", version: "4.11.2", load: 26 },
  { id: "velociraptor", name: "Velociraptor", kind: "DFIR", status: "degraded", version: "0.73.1", load: 58 },
  { id: "volatility", name: "Volatility", kind: "Memory Forensics", status: "offline", version: "3.0.0", load: 0 },
];

/* ------------------------------------------------------------------ */
/* Conversations                                                       */
/* ------------------------------------------------------------------ */

export const conversations: Conversation[] = [
  {
    id: "cv-1",
    title: "Analyze suspicious channel on LAB-07",
    preview: "Correlated 3 Zeek flows with a YARA hit; beacon interval ~47s.",
    time: "5m",
    agent: "SOC Agent",
    pinned: true,
  },
  {
    id: "cv-2",
    title: "Mapped brute-force to 5 source IPs",
    preview: "geolocation + ASN enrichment complete. Blocklist proposed.",
    time: "22m",
    agent: "Threat Hunt",
  },
  {
    id: "cv-3",
    title: "Memory dump triage — workstation W-22",
    preview: "Volatility plugin scan found 3 suspicious processes.",
    time: "1h",
    agent: "DFIR",
  },
  {
    id: "cv-4",
    title: "MITRE mapping for latest alert batch",
    preview: "Tactic tags applied across 7 signatures. Coverage report ready.",
    time: "3h",
    agent: "Compliance",
  },
  {
    id: "cv-5",
    title: "OSINT enrichment for phishing domain",
    preview: "Registry, WHOIS, and certificate fingerprints captured.",
    time: "yesterday",
    agent: "OSINT",
  },
];

/* ------------------------------------------------------------------ */
/* Chat thread                                                         */
/* ------------------------------------------------------------------ */

export const chatMessages: ChatMessage[] = [
  {
    id: "m1",
    role: "user",
    content:
      "Investigate the outbound beacon pattern detected on LAB-07 and map it to MITRE ATT&CK.",
    time: "09:41",
  },
  {
    id: "m2",
    role: "assistant",
    content:
      "I correlated the LAB-07 beacon pattern across Zeek, Suricata, and the EDR log feed. The traffic matches a periodic C2 check-in with a ~47s interval to a single unclassified external endpoint. Below is my reasoning and the evidence trail.",
    time: "09:41",
    reasoning:
      "1. Filtered flows to LAB-07 (dst port 443/TCP) for the last 3h.\n2. Applied periodic-connection heuristic → interval ≈ 47s, jitter < 6%.\n3. Cross-referenced Suricata TLS SNI against threat-intel tags.\n4. Mapped result to ATT&CK TA0011 (C2), T1071.001 (Web Protocols).",
    evidence: [
      "zeek: conn.log — 47s cadence to 203.0.113.24:443",
      "suricata: tls.log — SNI 'update-cdn-static.net' with unsigned cert",
      "edr: LAB-07 spawned 1 process chain → /usr/bin/curl every 47s",
    ],
    sources: [
      "MITRE ATT&CK · T1071.001",
      "CVE lookup — no known match",
      "VirusTotal passive DNS — no hits",
    ],
    toolsUsed: ["Zeek", "Suricata", "YARA", "MITRE Map"],
    executionTime: "4.2s",
  },
];

export const suggestedPrompts = [
  "Summarize today's critical alerts",
  "Hunt for lateral movement in the last 24h",
  "Correlate this hash across knowledge base",
  "Generate a SOC handoff report",
];

/* ------------------------------------------------------------------ */
/* Quick actions                                                       */
/* ------------------------------------------------------------------ */

export const quickActions: QuickAction[] = [
  {
    id: "qa-1",
    label: "Analyze Logs",
    description: "Parse and correlate log sources",
    icon: "logs",
  },
  {
    id: "qa-2",
    label: "Investigate Alerts",
    description: "Triage the latest alert batch",
    icon: "alerts",
  },
  {
    id: "qa-3",
    label: "Hunt Threats",
    description: "Proactive threat-hunting run",
    icon: "hunt",
  },
  {
    id: "qa-4",
    label: "Analyze File",
    description: "Static + dynamic malware analysis",
    icon: "file",
  },
  {
    id: "qa-5",
    label: "Scan Target",
    description: "Recon and surface scanning",
    icon: "scan",
  },
];

