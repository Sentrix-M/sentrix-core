"""Shodan threat-intelligence tool for the Sentrix Tool Engine.

:class:`ShodanTool` implements the existing :class:`~app.tools.base.BaseTool`
interface and queries the official Shodan REST API for internet-exposure and
host intelligence on IP addresses (IPv4/IPv6) and domains/hostnames.

Indicator type is inferred automatically from the query string — the user
simply types ``Analyze 8.8.8.8`` or ``Analyze microsoft.com`` and the tool
figures out the rest.

Multi-source host intelligence
------------------------------
For IP inputs the tool queries the Shodan ``/shodan/host/{ip}`` endpoint
directly. For domains/hostnames it first resolves the name to one or more IP
addresses via ``/dns/resolve``, then queries ``/shodan/host/{ip}`` for each
resolved address. Both the original hostname and the resolved IP(s) are
preserved in the response so the AI, dashboard, RAG, and reporting layers have
full context.

Output
------
The tool returns a rich, structured JSON payload designed to feed the
dashboard, memory, RAG, reporting, and AI-reasoning layers:

.. code-block:: json

    {
      "query": "microsoft.com",
      "indicator_type": "domain",
      "ip": "13.107.246.", "...",
      "organization": "...",
      "isp": "...",
      "asn": "...",
      "country": "...",
      "city": "...",
      "hostnames": [],
      "domains": [],
      "ports": [],
      "services": [{"port": 443, "transport": "tcp", "product": "...",
                    "version": "...", "banner": "..."}],
      "vulnerabilities": [],
      "tags": [],
      "operating_system": "...",
      "risk_score": "...",
      "last_update": "...",
      "permalink": "...",
      "raw": {}
    }

If the API key is missing, the indicator is invalid, or the API returns an
error (rate limit, not found, network failure), the tool returns a clear,
structured error via :meth:`ToolResult.fail` and :meth:`health` reports the
tool as unavailable.
"""

from __future__ import annotations

import asyncio
import contextlib
import ipaddress
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar, TypeVar

import httpx

from app.config.settings import Settings, get_settings
from app.tools.base import (
    ToolHealth,
    ToolPermission,
    ToolResult,
)

logger = logging.getLogger(__name__)

#: Type variable for retry operation results (host dicts, DNS lists, etc.).
_RetryResult = TypeVar("_RetryResult")

#: Default timeout (seconds) for each Shodan HTTP request.
DEFAULT_TIMEOUT = 15.0

#: Maximum number of retries for transient failures (429/5xx).
MAX_RETRIES = 3

#: Base backoff delay (seconds) for the first retry.
BASE_BACKOFF = 1.0

#: Upper bound for the backoff delay (seconds) to avoid runaway waits.
MAX_BACKOFF = 20.0

#: Default API key used when the caller does not inject one.
DEFAULT_API_KEY = ""

#: Regex for a domain or hostname (subdomains allowed, TLD required).
#: Matches the examples "microsoft.com" and "scanme.shodan.io".
_DOMAIN_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,}$"
)


#: Callable that returns an httpx.AsyncClient (used for tests).
AsyncClientFactory = Callable[[], Awaitable[httpx.AsyncClient]]


def detect_indicator_type(query: str) -> str:
    """Infer the indicator type from a query string.

    Returns one of ``"ip"``, ``"domain"``, or ``"hostname"``.

    - IPv4 / IPv6 literals are classified as ``"ip"``.
    - Strings that are valid domains (e.g. ``microsoft.com``) are ``"domain"``.
    - Everything else that looks like a single-label or dotted hostname is
      classified as ``"hostname"``.
    """
    value = (query or "").strip()
    if not value:
        return "hostname"

    # IP detection (IPv4 or IPv6) — the most specific form.
    try:
        ipaddress.ip_address(value)
        return "ip"
    except ValueError:
        pass

    # Domain detection (requires a TLD).
    if _DOMAIN_RE.match(value):
        return "domain"

    # Hostname fallback (single label or dotted name without a TLD).
    if re.match(r"^[a-zA-Z0-9](?:[a-zA-Z0-9\-_.]{0,252}[a-zA-Z0-9])?$", value):
        return "hostname"

    return "hostname"


def _url_path(value: str) -> str:
    """Return the URL-encoded path segment for ``value`` as a string.

    ``httpx.URL(...).raw_path`` is ``bytes``; decode it so it is never
    interpolated into a URL as its ``b'...'`` repr.
    """
    return httpx.URL(value).raw_path.decode()


def _build_host_url(base_url: str, ip: str) -> str:
    """Build the Shodan ``/shodan/host/{ip}`` URL for an IP address."""
    return f"{base_url.rstrip('/')}/shodan/host/{_url_path(ip)}"


def _build_resolve_url(base_url: str, hostname: str) -> str:
    """Build the Shodan ``/dns/resolve`` URL for a hostname."""
    return f"{base_url.rstrip('/')}/dns/resolve?hostnames={_url_path(hostname)}"


def _extract_services(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Normalize the Shodan ``data`` array into a compact service list."""
    services: list[dict[str, Any]] = []
    for entry in data.get("data", []) if isinstance(data.get("data"), list) else []:
        if not isinstance(entry, dict):
            continue
        services.append(
            {
                "port": entry.get("port"),
                "transport": entry.get("transport", ""),
                "product": entry.get("product", ""),
                "version": entry.get("version", ""),
                "banner": (entry.get("data") or "").strip()[:500],
            }
        )
    return services


def _extract_vulnerabilities(data: dict[str, Any]) -> list[str]:
    """Return the CVE/CPE identifiers from a Shodan host response."""
    vulns: list[str] = []
    for entry in data.get("vulns", []):
        if isinstance(entry, dict):
            cve = entry.get("cve", [])
            if isinstance(cve, list):
                vulns.extend(str(c) for c in cve)
            elif cve:
                vulns.append(str(cve))
        elif isinstance(entry, str):
            vulns.append(entry)
    return sorted(set(vulns))


def _compute_risk_score(data: dict[str, Any]) -> str:
    """Derive a qualitative risk score from host data.

    Uses the count of open ports, known vulnerabilities, and whether the
    host appears on any Shodan blacklist. Returns one of
    ``"high"``/``"medium"``/``"low"``.
    """
    ports = data.get("ports", []) if isinstance(data.get("ports"), list) else []
    vulns = _extract_vulnerabilities(data)
    flagged = bool(data.get("hostnames") and "(blacklist)" in str(data.get("hostnames", "")))

    if len(vulns) > 0 or flagged or len(ports) >= 25:
        return "high"
    if len(ports) >= 10:
        return "medium"
    return "low"


def _normalize_host_response(
    *,
    query: str,
    indicator_type: str,
    ip: str,
    hostname_input: str | None,
    data: dict[str, Any],
) -> dict[str, Any]:
    """Normalize a Shodan host response into the structured output shape."""
    hostnames = [str(h) for h in data.get("hostnames", []) if h]
    domains = [str(d) for d in data.get("domains", []) if d]
    ports = [int(p) for p in data.get("ports", []) if isinstance(p, int)]
    asn = data.get("asn", "")
    if not asn:
        asn = (data.get("as_owner", "") or "").split(" ", 1)[0]

    # Preserve the original hostname input alongside the resolved IP.
    if hostname_input and hostname_input not in hostnames:
        hostnames.insert(0, hostname_input)

    return {
        "query": query,
        "indicator_type": indicator_type,
        "ip": ip,
        "organization": data.get("org", ""),
        "isp": data.get("isp", ""),
        "asn": asn,
        "country": data.get("country_name", "") or data.get("country_code", ""),
        "city": data.get("city", ""),
        "hostnames": hostnames,
        "domains": domains,
        "ports": ports,
        "services": _extract_services(data),
        "vulnerabilities": _extract_vulnerabilities(data),
        "tags": [str(t) for t in data.get("tags", []) if t],
        "operating_system": data.get("os", ""),
        "risk_score": _compute_risk_score(data),
        "last_update": data.get("last_update", ""),
        "permalink": f"https://www.shodan.io/host/{ip}",
        "raw": data,
    }


async def _resolve_hostname(base_url: str, hostname: str, client: httpx.AsyncClient) -> list[str]:
    """Resolve a hostname to one or more IP addresses via Shodan DNS.

    :raises ShodanError: When resolution fails or returns no addresses.
    """
    url = _build_resolve_url(base_url, hostname)
    response = await client.get(url)
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ShodanError("Shodan DNS resolve returned an unexpected shape.")
    entry = payload.get(hostname)
    if not isinstance(entry, dict):
        raise ShodanError(f"Shodan could not resolve hostname '{hostname}'.")
    address = entry.get("value")
    if not address:
        raise ShodanError(f"Shodan returned no address for '{hostname}'.")
    return [address]


class ShodanTool:
    """Real Shodan internet-exposure tool exposing the ``BaseTool`` contract.

    :param api_key: Shodan API key. Defaults to the value from
        :class:`Settings.shodan_api_key`.
    :param base_url: Base URL of the Shodan REST API.
    :param client_factory: Optional callable returning an ``httpx.AsyncClient``.
        Provided for tests; when omitted, a client is constructed with the
        configured API key header.
    :param timeout: Request timeout in seconds.
    """

    name = "shodan"
    description = (
        "Query Shodan for internet-exposure and host intelligence on IP "
        "addresses, domains, and hostnames."
    )
    version = "0.1.0"
    permissions: ClassVar[set[ToolPermission]] = {
        ToolPermission(resource="threatintel", action="read"),
    }

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        client_factory: AsyncClientFactory | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        cfg: Settings = get_settings()
        self._api_key = api_key if api_key is not None else cfg.shodan_api_key
        self._base_url = base_url or cfg.shodan_base_url
        self._client_factory = client_factory
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None

    # ------------------------------------------------------------------
    # BaseTool contract
    # ------------------------------------------------------------------

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema describing the accepted lookup input."""
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "IP address (IPv4/IPv6), domain, or hostname to "
                        "investigate. The type is inferred automatically."
                    ),
                },
                "indicator_type": {
                    "type": "string",
                    "enum": ["ip", "domain", "hostname"],
                    "description": (
                        "Optional explicit indicator type. When omitted, it is "
                        "inferred from the query."
                    ),
                },
            },
            "required": ["query"],
        }

    @property
    def output_schema(self) -> dict[str, Any]:
        """JSON Schema describing the structured lookup output."""
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "indicator_type": {"type": "string"},
                "ip": {"type": "string"},
                "organization": {"type": "string"},
                "isp": {"type": "string"},
                "asn": {"type": "string"},
                "country": {"type": "string"},
                "city": {"type": "string"},
                "hostnames": {"type": "array", "items": {"type": "string"}},
                "domains": {"type": "array", "items": {"type": "string"}},
                "ports": {"type": "array", "items": {"type": "integer"}},
                "services": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "port": {"type": "integer"},
                            "transport": {"type": "string"},
                            "product": {"type": "string"},
                            "version": {"type": "string"},
                            "banner": {"type": "string"},
                        },
                    },
                },
                "vulnerabilities": {"type": "array", "items": {"type": "string"}},
                "tags": {"type": "array", "items": {"type": "string"}},
                "operating_system": {"type": "string"},
                "risk_score": {"type": "string"},
                "last_update": {"type": "string"},
                "permalink": {"type": "string"},
                "raw": {"type": "object"},
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Investigate an IP, domain, or hostname on Shodan.

        :param query: The indicator to investigate (required).
        :param indicator_type: Optional explicit type; inferred when omitted.
        """
        query = (kwargs.get("query") or "").strip()
        if not query:
            return ToolResult.fail(
                self.name,
                "Missing required input 'query'.",
            )

        if not self._api_key.strip():
            return ToolResult.fail(
                self.name,
                "SHODAN_API_KEY is not configured. "
                "Set it in the environment or .env to enable Shodan lookups.",
            )

        indicator_type = kwargs.get("indicator_type") or detect_indicator_type(query)
        if indicator_type not in ("ip", "domain", "hostname"):
            return ToolResult.fail(
                self.name,
                f"Unsupported indicator type '{indicator_type}'. "
                "Supported: ip, domain, hostname.",
            )

        try:
            client = await self._client_instance()

            if indicator_type == "ip":
                ip = query
                data = await self._fetch_host_with_retry(client, ip)
                output = _normalize_host_response(
                    query=query,
                    indicator_type="ip",
                    ip=ip,
                    hostname_input=None,
                    data=data,
                )
            else:
                # Domain/hostname → resolve to IP(s), then query host info.
                try:
                    resolved = await self._run_with_retry(
                        client,
                        lambda: _resolve_hostname(self._base_url, query, client),
                    )
                except ShodanError as exc:
                    return ToolResult.fail(self.name, exc.message)
                ip = resolved[0]
                data = await self._fetch_host_with_retry(client, ip)
                output = _normalize_host_response(
                    query=query,
                    indicator_type=indicator_type,
                    ip=ip,
                    hostname_input=query,
                    data=data,
                )

            return ToolResult.ok(self.name, output)
        except ShodanError as exc:
            return ToolResult.fail(self.name, exc.message)
        except Exception as exc:  # noqa: BLE001 - surface as structured failure
            logger.exception("Shodan lookup failed for %s.", query)
            return ToolResult.fail(
                self.name,
                f"Shodan lookup failed: {exc}",
            )

    async def health(self) -> ToolHealth:
        """Report whether the Shodan API key is configured."""
        if not self._api_key.strip():
            return ToolHealth(
                ok=False,
                message="SHODAN_API_KEY is not configured.",
            )
        return ToolHealth(
            ok=True,
            message="SHODAN_API_KEY is configured.",
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    async def _client_instance(self) -> httpx.AsyncClient:
        """Return a lazily-constructed (and cached) async HTTP client."""
        if self._client is None:
            if self._client_factory is not None:
                self._client = await self._client_factory()
            else:
                self._client = httpx.AsyncClient(
                    timeout=self._timeout,
                    headers={"x-api-key": self._api_key},
                )
        return self._client

    async def _fetch_host_with_retry(self, client: httpx.AsyncClient, ip: str) -> dict[str, Any]:
        """Fetch host info for ``ip`` with exponential-backoff retry."""
        url = _build_host_url(self._base_url, ip)
        return await self._run_with_retry(
            client,
            lambda: self._request_host(client, url),
        )

    async def _request_host(self, client: httpx.AsyncClient, url: str) -> dict[str, Any]:
        """Perform a single Shodan host request and normalize the response."""
        response = await client.get(url)
        if response.status_code == 200:
            payload = response.json()
            if not isinstance(payload, dict):
                raise ShodanError("Shodan host returned an unexpected response shape.")
            return payload
        if response.status_code == 401:
            raise ShodanError("Shodan API key is invalid or unauthorized (HTTP 401).")
        if response.status_code == 403:
            raise ShodanError("Shodan API key lacks permission (HTTP 403).")
        if response.status_code == 404:
            raise ShodanError("Host not found on Shodan (HTTP 404).")
        if response.status_code in (429, 500, 502, 503, 504):
            raise _RetryableHttpError(response.status_code, headers=response.headers)
        raise ShodanError(f"Shodan API returned HTTP {response.status_code}.")

    async def _run_with_retry(
        self,
        _client: httpx.AsyncClient,
        operation: Callable[[], Awaitable[_RetryResult]],
    ) -> _RetryResult:
        """Run ``operation`` with exponential-backoff retry on transient errors.

        :raises ShodanError: For non-retryable errors and when the retry
            budget is exhausted.
        """
        attempt = 0
        while True:
            try:
                return await operation()
            except _RetryableHttpError as exc:
                if attempt >= MAX_RETRIES:
                    raise ShodanError(
                        f"Shodan API error after {attempt + 1} attempts: HTTP {exc.status_code}."
                    ) from exc
                retry_after = exc.headers.get("Retry-After")
                delay = min(BASE_BACKOFF * (2 ** attempt), MAX_BACKOFF)
                if retry_after:
                    with contextlib.suppress(ValueError):
                        delay = min(float(retry_after), MAX_BACKOFF)
                attempt += 1
                await asyncio.sleep(delay)
                continue
            except httpx.HTTPError as exc:
                if attempt >= MAX_RETRIES:
                    raise ShodanError(
                        f"Network error contacting Shodan after {attempt + 1} attempts: {exc}"
                    ) from exc
                attempt += 1
                await asyncio.sleep(min(BASE_BACKOFF * (2 ** (attempt - 1)), MAX_BACKOFF))
                continue


class ShodanError(Exception):
    """Raised when a Shodan lookup cannot be completed."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


class _RetryableHttpError(Exception):
    """Internal marker for retryable HTTP status codes (429/5xx)."""

    def __init__(self, status_code: int, headers: Any) -> None:
        self.status_code = status_code
        self.headers = headers
        super().__init__(f"HTTP {status_code}")


__all__ = [
    "DEFAULT_TIMEOUT",
    "MAX_BACKOFF",
    "ShodanError",
    "ShodanTool",
    "detect_indicator_type",
]
