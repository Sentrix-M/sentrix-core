# Sentrix — Active Task Checklist

## Phase 8 — Nmap Tool Integration

### Implementation
- [x] Create `apps/api/app/tools/nmap_tool.py` — `NmapTool` implementing `BaseTool`
  - [x] Scan profiles: quick (-F), service (-sV), os (-O), full (-A)
  - [x] Build args safely (no shell=True), run via `asyncio.create_subprocess_exec`
  - [x] Parse XML (`-oX -`) into rich structured JSON (target, status, hostname, ip, open_ports, os_detection, execution_time)
  - [x] Clear structured error when nmap binary is unavailable
  - [x] Injectable runner for testability
- [x] Create `apps/api/tests/test_nmap_tool.py` — parser + arg + schema + health + error tests
  - [x] Parser tests for multiple hosts and multiple open ports

### Integration
- [x] Register `NmapTool()` in `apps/api/app/main.py` tool registry
- [x] Export `NmapTool` in `apps/api/app/tools/__init__.py`
- [x] Add nmap intent markers + target extraction in `apps/api/app/kernel/tool_integration.py`
- [x] Add `network:scan` permission in `apps/api/app/models/role.py`; grant to admin + RED_TEAM/SECURITY_ENGINEER

### Verification
- [x] Run Ruff on apps/api
- [x] Run full pytest suite (hermetic/offline)

## Phase 9 — VirusTotal Integration

### Implementation
- [ ] Create `apps/api/app/tools/virustotal_tool.py` — `VirusTotalTool` implementing `BaseTool`
  - [ ] Auto-detect indicator type (MD5/SHA1/SHA256/IPv4/IPv6/Domain/URL)
  - [ ] Async httpx client with timeout, retry with exponential backoff (respect Retry-After)
  - [ ] Rich structured output (query, indicator_type, reputation, malicious, suspicious, harmless, undetected, last_analysis_stats, categories, tags, country, asn, owner, permalink, raw)
  - [ ] Graceful handling of missing key, invalid indicator, HTTP errors, network failures, rate limits
  - [ ] Injectable client factory for tests
- [ ] Create `apps/api/tests/test_virustotal_tool.py` — unit tests with mocked HTTP responses
  - [ ] File hash / IP / Domain / URL lookups
  - [ ] Indicator type detection
  - [ ] Missing key, invalid indicator, rate limit, network failure
  - [ ] Health, schema, permissions

### Integration
- [ ] Register `VirusTotalTool()` in `apps/api/app/main.py` tool registry
- [ ] Export `VirusTotalTool` in `apps/api/app/tools/__init__.py`
- [ ] Add `VIRUSTOTAL_API_KEY` to `apps/api/app/config/settings.py` + `.env.example`
- [ ] Add VirusTotal intent markers + auto type detection in `apps/api/app/kernel/tool_integration.py`
- [ ] Add `threatintel:read` permission in `apps/api/app/models/role.py`; grant to admin + SOC_ANALYST/THREAT_HUNTER/RED_TEAM/SECURITY_ENGINEER

### Verification
- [ ] Run Ruff on apps/api
- [ ] Run full pytest suite (hermetic/offline)
- [ ] End-to-end: User -> Tool Router -> VirusTotal Tool -> Tool Executor -> Kernel -> Gemini explanation -> Streaming UI
