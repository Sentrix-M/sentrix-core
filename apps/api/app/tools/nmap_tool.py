"""Nmap integration tool for the Sentrix Tool Engine.

:class:`NmapTool` implements the existing :class:`~app.tools.base.BaseTool`
interface and executes the real ``nmap`` binary when it is installed. It
builds the argument list safely (never ``shell=True``) and runs it via
``asyncio.create_subprocess_exec``.

Scan profiles
-------------
The tool supports named profiles that map to common Nmap flag sets:

- ``quick``  → ``-F`` (fast scan of common ports)
- ``service`` → ``-sV`` (service/version detection)
- ``os``  → ``-O`` (OS detection)
- ``full`` → ``-A`` (aggressive: OS + service + script)

Output
------
The XML output (``-oX -``) is parsed into a rich, structured JSON payload
that later feeds the RAG layer, reporting, MITRE mapping, and the dashboard:

.. code-block:: json

    {
      "target": "...",
      "status": "up",
      "hostname": "...",
      "ip": "...",
      "open_ports": [
        {"port": 22, "protocol": "tcp", "service": "ssh",
         "product": "...", "version": "...", "state": "open"}
      ],
      "os_detection": {},
      "execution_time": ...
    }

If ``nmap`` is not installed, the tool returns a clear, structured error via
:meth:`ToolResult.fail` and :meth:`health` reports the tool as unavailable.
"""

from __future__ import annotations

import asyncio
import shutil
import xml.etree.ElementTree as ET
from collections.abc import Callable, Sequence
from typing import Any, ClassVar

from app.tools.base import (
    ToolHealth,
    ToolPermission,
    ToolResult,
)

#: Name of the ``nmap`` binary looked up on ``PATH``.
NMAP_BINARY = "nmap"

#: Mapping of scan profile → Nmap flag set.
PROFILE_FLAGS: dict[str, tuple[str, ...]] = {
    "quick": ("-F",),
    "service": ("-sV",),
    "os": ("-O",),
    "full": ("-A",),
}

#: Default profile used when the caller does not specify one.
DEFAULT_PROFILE = "quick"

#: Default ports passed to ``-p`` when the caller does not specify any.
DEFAULT_PORTS = "1-1000"

#: XML namespace prefix used by Nmap's ``-oX`` output.
_NMAP_NS = "{http://nmap.org/run/1}"


def _tag(name: str) -> str:
    """Prefix a tag name with the Nmap XML namespace.

    Returns the namespace-qualified tag. When the root element is not in the
    Nmap namespace (e.g. test fixtures or unusual output), callers should use
    :func:`_local_name` to compare against the unqualified tag name.
    """
    return f"{_NMAP_NS}{name}"


def _local_name(tag: str) -> str:
    """Strip any ``{namespace}`` prefix from a tag name."""
    if tag.startswith("{"):
        return tag.split("}", 1)[1]
    return tag


def _find(element: ET.Element, name: str) -> ET.Element | None:
    """Return the first direct child tagged ``name`` (namespace-aware).

    Matches both the Nmap-namespaced tag and the unqualified tag name so the
    parser works with real Nmap output and namespace-less test fixtures.
    """
    for child in element:
        if _local_name(child.tag) == name:
            return child
    return None


def _findall(element: ET.Element, name: str) -> list[ET.Element]:
    """Return all direct children tagged ``name`` (namespace-aware)."""
    return [child for child in element if _local_name(child.tag) == name]


def _parse_open_ports(host_el: ET.Element) -> list[dict[str, Any]]:
    """Extract the list of open ports and their service details."""
    ports: list[dict[str, Any]] = []
    ports_el = _find(host_el, "ports")
    if ports_el is None:
        return ports
    for port_el in _findall(ports_el, "port"):
        port_id = port_el.get("portid")
        if port_id is None:
            continue
        protocol = port_el.get("protocol", "tcp")
        state = "unknown"
        for state_el in _findall(port_el, "state"):
            state = state_el.get("state", "unknown")
            break

        entry: dict[str, Any] = {
            "port": int(port_id),
            "protocol": protocol,
            "service": "",
            "product": "",
            "version": "",
            "state": state,
        }
        for service_el in _findall(port_el, "service"):
            entry["service"] = service_el.get("name", "")
            entry["product"] = service_el.get("product", "")
            entry["version"] = service_el.get("version", "")
        ports.append(entry)
    return ports


def _parse_os_detection(host_el: ET.Element) -> dict[str, Any]:
    """Extract OS detection data (when the ``os``/``full`` profile is used)."""
    os_el = _find(host_el, "os")
    if os_el is None:
        return {}
    matches: list[dict[str, Any]] = []
    for match_el in _findall(os_el, "osmatch"):
        match: dict[str, Any] = {
            "name": match_el.get("name", ""),
            "accuracy": match_el.get("accuracy", ""),
        }
        classes: list[dict[str, str]] = []
        for class_el in _findall(match_el, "osclass"):
            classes.append(
                {
                    "type": class_el.get("type", ""),
                    "vendor": class_el.get("vendor", ""),
                    "osfamily": class_el.get("osfamily", ""),
                    "osgen": class_el.get("osgen", ""),
                }
            )
        if classes:
            match["classes"] = classes
        matches.append(match)
    return {"matches": matches}


def _parse_nmap_xml(xml: str) -> list[dict[str, Any]]:
    """Parse an Nmap ``-oX`` XML document into structured host results.

    :param xml: Raw XML output from ``nmap -oX -``.
    :returns: A list of host result dicts (one per scanned host).
    """
    root = ET.fromstring(xml)
    hosts: list[dict[str, Any]] = []
    for host_el in _findall(root, "host"):
        status = "up"
        status_el = _find(host_el, "status")
        if status_el is not None:
            status = status_el.get("state", "up")

        hostname = ""
        for hostname_el in _findall(host_el, "hostnames"):
            for name_el in _findall(hostname_el, "hostname"):
                hostname = name_el.get("name", "")

        ip = ""
        for addr_el in _findall(host_el, "address"):
            if addr_el.get("addrtype") == "ipv4":
                ip = addr_el.get("addr", "")
                break

        hosts.append(
            {
                "target": host_el.get("target", ""),
                "status": status,
                "hostname": hostname,
                "ip": ip,
                "open_ports": _parse_open_ports(host_el),
                "os_detection": _parse_os_detection(host_el),
            }
        )
    return hosts


def _build_args(
    *,
    host: str,
    ports: str | None,
    profile: str,
) -> list[str]:
    """Build the Nmap argument list (no shell, injection-safe).

    ``ports`` defaults to :data:`DEFAULT_PORTS` when not provided, so the
    ``-p`` flag is always emitted with an explicit port range.
    """
    args = [NMAP_BINARY, "-oX", "-", "--no-stylesheet"]
    profile = profile or DEFAULT_PROFILE
    if profile in PROFILE_FLAGS:
        args.extend(PROFILE_FLAGS[profile])
    effective_ports = ports or DEFAULT_PORTS
    args.append("-p")
    args.append(effective_ports)
    args.append(host)
    return args


#: Callable that runs a subprocess and returns (exit_code, stdout, stderr).
Runner = Callable[..., Any]


class NmapTool:
    """Real Nmap scanner exposing the :class:`BaseTool` contract.

    :param runner: Optional async callable used to execute the ``nmap``
        process. Defaults to :func:`_run_nmap`. Provided for tests so the
        tool can be exercised without a real ``nmap`` binary.
    :param binary: Path to the ``nmap`` binary. Defaults to lookup via
        :func:`shutil.which`.
    """

    name = "nmap"
    description = "Run a real Nmap port scan and return structured findings."
    version = "0.1.0"
    permissions: ClassVar[set[ToolPermission]] = {
        ToolPermission(resource="network", action="scan"),
    }

    def __init__(
        self,
        *,
        runner: Runner | None = None,
        binary: str | None = None,
    ) -> None:
        self._runner = runner if runner is not None else _run_nmap
        self._binary = binary or shutil.which(NMAP_BINARY) or NMAP_BINARY

    # ------------------------------------------------------------------
    # BaseTool contract
    # ------------------------------------------------------------------

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema describing the accepted scan options."""
        return {
            "type": "object",
            "properties": {
                "host": {
                    "type": "string",
                    "description": "Target host, IP, or CIDR range to scan.",
                },
                "ports": {
                    "type": "string",
                    "description": (
                        "Ports or port range, e.g. '22', '80,443', '1-1000'. "
                        "Defaults to '1-1000'."
                    ),
                },
                "profile": {
                    "type": "string",
                    "enum": list(PROFILE_FLAGS),
                    "description": "Scan profile: quick, service, os, full.",
                },
                "timeout": {
                    "type": "integer",
                    "description": "Max scan time in seconds.",
                },
            },
            "required": ["host"],
        }

    @property
    def output_schema(self) -> dict[str, Any]:
        """JSON Schema describing the structured scan output."""
        return {
            "type": "object",
            "properties": {
                "target": {"type": "string"},
                "status": {"type": "string"},
                "hostname": {"type": "string"},
                "ip": {"type": "string"},
                "open_ports": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "port": {"type": "integer"},
                            "protocol": {"type": "string"},
                            "service": {"type": "string"},
                            "product": {"type": "string"},
                            "version": {"type": "string"},
                            "state": {"type": "string"},
                        },
                    },
                },
                "os_detection": {"type": "object"},
                "execution_time": {"type": "number"},
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute a real Nmap scan and return structured JSON.

        :param host: Target host, IP, or CIDR (required).
        :param ports: Ports/range (optional; defaults to ``1-1000``).
        :param profile: One of ``quick``/``service``/``os``/``full``.
        """
        host = kwargs.get("host")
        if not host:
            return ToolResult.fail(
                self.name,
                "Missing required input 'host'.",
            )
        ports = kwargs.get("ports") or DEFAULT_PORTS
        profile = kwargs.get("profile") or DEFAULT_PROFILE
        timeout = kwargs.get("timeout")

        if not self._is_available():
            return ToolResult.fail(
                self.name,
                "Nmap is not available or not installed. "
                "Install nmap (e.g. 'apt install nmap' or 'brew install nmap') "
                "to enable network scanning.",
            )

        args = _build_args(host=host, ports=ports, profile=profile)
        try:
            exit_code, stdout, stderr = await self._runner(
                args,
                timeout=timeout,
            )
        except Exception as exc:  # noqa: BLE001 - surface as structured failure
            return ToolResult.fail(
                self.name,
                f"Nmap execution failed: {exc}",
            )

        if exit_code != 0:
            return ToolResult.fail(
                self.name,
                f"Nmap exited with code {exit_code}: {stderr.strip()}",
            )

        try:
            hosts = _parse_nmap_xml(stdout)
        except ET.ParseError as exc:
            return ToolResult.fail(
                self.name,
                f"Failed to parse Nmap XML output: {exc}",
            )

        execution_time = self._execution_time(stdout)
        return ToolResult.ok(
            self.name,
            {
                "target": host,
                "execution_time": execution_time,
                "hosts": hosts,
            },
        )

    async def health(self) -> ToolHealth:
        """Report whether the `nmap` binary is available."""
        if not self._is_available():
            return ToolHealth(
                ok=False,
                message="Nmap is not installed or not on PATH.",
            )
        return ToolHealth(ok=True, message="Nmap is available.")

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _is_available(self) -> bool:
        """Return ``True`` when the nmap binary exists on PATH."""
        return shutil.which(self._binary) is not None

    @staticmethod
    def _execution_time(stdout: str) -> float:
        """Best-effort extraction of the scan duration from Nmap XML."""
        import re

        match = re.search(r"<runstats><finished[^>]*elapsed=\"([0-9.]+)\"", stdout)
        if match:
            return round(float(match.group(1)), 3)
        return 0.0


async def _run_nmap(
    args: Sequence[str],
    *,
    timeout: float | None = None,
) -> tuple[int, str, str]:
    """Execute the ``nmap`` process and return ``(exit_code, stdout, stderr)``.

    Uses ``asyncio.create_subprocess_exec`` (never ``shell=True``) so the
    argument list is applied verbatim — no shell interpolation or injection.
    """
    process = await asyncio.create_subprocess_exec(
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        process.kill()
        stdout, stderr = await process.communicate()
        raise RuntimeError(
            f"Nmap scan timed out after {timeout}s."
        ) from None

    return (
        process.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace"),
    )


__all__ = [
    "DEFAULT_PORTS",
    "DEFAULT_PROFILE",
    "NMAP_BINARY",
    "PROFILE_FLAGS",
    "NmapTool",
    "_build_args",
    "_parse_nmap_xml",
]
