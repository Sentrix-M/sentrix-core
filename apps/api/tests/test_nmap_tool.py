"""Unit tests for the Sentrix Nmap Tool.

Covers the :class:`NmapTool` implementation: argument building, XML parsing,
schema, permission contract, health reporting, and structured error handling.
No real ``nmap`` binary is required — tests inject a fake runner and use the
same ``asyncio.run`` pattern as the rest of the suite.
"""

from __future__ import annotations

import asyncio

from app.tools.base import ToolHealth, ToolResult
from app.tools.nmap_tool import (
    DEFAULT_PORTS,
    DEFAULT_PROFILE,
    PROFILE_FLAGS,
    NmapTool,
    _build_args,
    _parse_nmap_xml,
)

# ---------------------------------------------------------------------------
# Sample Nmap XML fixtures
# ---------------------------------------------------------------------------


def _single_host_xml() -> str:
    """A minimal ``-oX`` document with one host and two open ports."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<nmaprun scanner="nmap" start="1699999999">
  <host>
    <status state="up" reason="syn-ack"/>
    <address addr="192.168.1.10" addrtype="ipv4"/>
    <hostnames><hostname name="lab-07.internal" type="PTR"/></hostnames>
    <ports>
      <port protocol="tcp" portid="22">
        <state state="open" reason="syn-ack"/>
        <service name="ssh" product="OpenSSH" version="9.6"/>
      </port>
      <port protocol="tcp" portid="443">
        <state state="open" reason="syn-ack"/>
        <service name="https" product="" version=""/>
      </port>
    </ports>
    <os>
      <osmatch name="Linux 5.x" accuracy="89">
        <osclass type="general purpose" vendor="Linux" osfamily="Linux" osgen="5.x"/>
      </osmatch>
    </os>
  </host>
  <runstats><finished elapsed="12.4"/></runstats>
</nmaprun>"""


def _multi_host_xml() -> str:
    """A document with two hosts (one up, one down)."""
    return """<?xml version="1.0" encoding="UTF-8"?>
<nmaprun scanner="nmap" start="1700000000">
  <host>
    <status state="up" reason="syn-ack"/>
    <address addr="10.0.0.1" addrtype="ipv4"/>
    <hostnames><hostname name="gw-01.corp" type="PTR"/></hostnames>
    <ports>
      <port protocol="tcp" portid="80">
        <state state="open" reason="syn-ack"/>
        <service name="http" product="nginx" version="1.24"/>
      </port>
    </ports>
  </host>
  <host>
    <status state="down" reason="no-response"/>
    <address addr="10.0.0.2" addrtype="ipv4"/>
    <hostnames/>
    <ports/>
  </host>
  <runstats><finished elapsed="3.2"/></runstats>
</nmaprun>"""


async def _fake_runner_success(args, *, timeout=None):  # noqa: ARG001
    return 0, _single_host_xml(), ""


# ---------------------------------------------------------------------------
# Argument building
# ---------------------------------------------------------------------------


class TestBuildArgs:
    def test_default_profile_and_ports(self) -> None:
        args = _build_args(host="192.168.1.10", ports=None, profile="")
        assert args[0] == "nmap"
        assert "-oX" in args
        assert "-" in args
        assert "-F" in args  # quick default profile
        assert "-p" in args
        assert DEFAULT_PORTS in args
        assert "192.168.1.10" in args

    def test_service_profile(self) -> None:
        args = _build_args(host="10.0.0.1", ports="22,443", profile="service")
        assert "-sV" in args
        assert "22,443" in args

    def test_os_profile(self) -> None:
        args = _build_args(host="10.0.0.1", ports="80", profile="os")
        assert "-O" in args

    def test_full_profile(self) -> None:
        args = _build_args(host="10.0.0.1", ports="1-1000", profile="full")
        assert "-A" in args

    def test_unknown_profile_ignored(self) -> None:
        args = _build_args(host="10.0.0.1", ports="80", profile="bogus")
        assert "-F" not in args
        assert "-sV" not in args
        assert "80" in args

    def test_profile_flags_mapping(self) -> None:
        assert PROFILE_FLAGS["quick"] == ("-F",)
        assert PROFILE_FLAGS["service"] == ("-sV",)
        assert PROFILE_FLAGS["os"] == ("-O",)
        assert PROFILE_FLAGS["full"] == ("-A",)

    def test_default_profile_constant(self) -> None:
        assert DEFAULT_PROFILE == "quick"


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------


class TestParseNmapXml:
    def test_parses_single_host(self) -> None:
        hosts = _parse_nmap_xml(_single_host_xml())
        assert len(hosts) == 1
        host = hosts[0]
        assert host["status"] == "up"
        assert host["hostname"] == "lab-07.internal"
        assert host["ip"] == "192.168.1.10"

    def test_parses_multiple_open_ports(self) -> None:
        hosts = _parse_nmap_xml(_single_host_xml())
        ports = hosts[0]["open_ports"]
        assert len(ports) == 2
        assert ports[0]["port"] == 22
        assert ports[0]["protocol"] == "tcp"
        assert ports[0]["service"] == "ssh"
        assert ports[0]["product"] == "OpenSSH"
        assert ports[0]["version"] == "9.6"
        assert ports[0]["state"] == "open"
        assert ports[1]["port"] == 443
        assert ports[1]["service"] == "https"

    def test_parses_os_detection(self) -> None:
        hosts = _parse_nmap_xml(_single_host_xml())
        os_detection = hosts[0]["os_detection"]
        assert "matches" in os_detection
        assert os_detection["matches"][0]["name"] == "Linux 5.x"
        assert os_detection["matches"][0]["accuracy"] == "89"

    def test_parses_multiple_hosts(self) -> None:
        hosts = _parse_nmap_xml(_multi_host_xml())
        assert len(hosts) == 2
        assert hosts[0]["status"] == "up"
        assert hosts[0]["ip"] == "10.0.0.1"
        assert hosts[1]["status"] == "down"
        assert hosts[1]["ip"] == "10.0.0.2"
        assert hosts[1]["open_ports"] == []

    def test_handles_empty_ports(self) -> None:
        hosts = _parse_nmap_xml(_multi_host_xml())
        assert hosts[1]["open_ports"] == []


# ---------------------------------------------------------------------------
# ToolResult / permission / schema contract
# ---------------------------------------------------------------------------


class TestNmapToolContract:
    def test_name_and_version(self) -> None:
        tool = NmapTool(binary=None)
        assert tool.name == "nmap"
        assert tool.version == "0.1.0"

    def test_permissions_include_network_scan(self) -> None:
        tool = NmapTool(binary=None)
        perms = {p.permission_string for p in tool.permissions}
        assert "network:scan" in perms

    def test_input_schema_requires_host(self) -> None:
        tool = NmapTool(binary=None)
        schema = tool.input_schema
        assert "host" in schema["required"]
        assert "host" in schema["properties"]

    def test_output_schema_shape(self) -> None:
        tool = NmapTool(binary=None)
        schema = tool.output_schema
        assert "open_ports" in schema["properties"]


# ---------------------------------------------------------------------------
# execute() with injected runner
# ---------------------------------------------------------------------------


class TestNmapToolExecute:
    def test_returns_structured_result(self) -> None:
        tool = NmapTool(binary="nmap", runner=_fake_runner_success)
        result: ToolResult = asyncio.run(tool.execute(host="192.168.1.10"))
        assert result.success is True
        assert result.tool == "nmap"
        output = result.output
        assert output["target"] == "192.168.1.10"
        assert output["hosts"][0]["ip"] == "192.168.1.10"
        assert output["hosts"][0]["open_ports"][0]["port"] == 22

    def test_returns_failure_when_missing_host(self) -> None:
        async def fake_runner(args, *, timeout=None):  # noqa: ARG001
            return 0, "", ""

        tool = NmapTool(binary="nmap", runner=fake_runner)
        result = asyncio.run(tool.execute())
        assert result.success is False
        assert "host" in (result.error or "").lower()

    def test_returns_failure_when_binary_absent(self, monkeypatch) -> None:
        import app.tools.nmap_tool as nmap_module

        async def fake_runner(args, *, timeout=None):  # noqa: ARG001
            return 0, "", ""

        monkeypatch.setattr(nmap_module.shutil, "which", lambda _: None)
        tool = NmapTool(binary="nmap", runner=fake_runner)
        result = asyncio.run(tool.execute(host="10.0.0.1"))
        assert result.success is False
        assert "not available" in (result.error or "").lower()

    def test_returns_failure_on_nonzero_exit(self) -> None:
        async def fake_runner(args, *, timeout=None):  # noqa: ARG001
            return 1, "", "permission denied"

        tool = NmapTool(binary="nmap", runner=fake_runner)
        result = asyncio.run(tool.execute(host="10.0.0.1"))
        assert result.success is False
        assert "permission denied" in (result.error or "")

    def test_returns_failure_on_runner_exception(self) -> None:
        async def fake_runner(args, *, timeout=None):  # noqa: ARG001
            raise RuntimeError("boom")

        tool = NmapTool(binary="nmap", runner=fake_runner)
        result = asyncio.run(tool.execute(host="10.0.0.1"))
        assert result.success is False
        assert "boom" in (result.error or "")

    def test_returns_failure_on_invalid_xml(self) -> None:
        async def fake_runner(args, *, timeout=None):  # noqa: ARG001
            return 0, "<<<not xml>>>", ""

        tool = NmapTool(binary="nmap", runner=fake_runner)
        result = asyncio.run(tool.execute(host="10.0.0.1"))
        assert result.success is False
        assert "parse" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# health()
# ---------------------------------------------------------------------------


class TestNmapToolHealth:
    def test_health_true_when_binary_available(self, monkeypatch) -> None:
        import app.tools.nmap_tool as nmap_module

        monkeypatch.setattr(nmap_module.shutil, "which", lambda _: "/usr/bin/nmap")
        tool = NmapTool(binary="nmap")
        health: ToolHealth = asyncio.run(tool.health())
        assert health.ok is True

    def test_health_false_when_binary_absent(self, monkeypatch) -> None:
        import app.tools.nmap_tool as nmap_module

        monkeypatch.setattr(nmap_module.shutil, "which", lambda _: None)
        tool = NmapTool(binary="nmap")
        health = asyncio.run(tool.health())
        assert health.ok is False
        assert "not installed" in health.message.lower()
