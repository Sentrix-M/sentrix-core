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
- [ ] End-to-end: User -> Tool Router -> Nmap Tool -> Parsed JSON -> Gemini explanation -> Streaming response
