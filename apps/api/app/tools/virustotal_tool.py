"""VirusTotal threat-intelligence tool for the Sentrix Tool Engine.

:class:`VirusTotalTool` implements the existing :class:`~app.tools.base.BaseTool`
interface and queries the official VirusTotal REST API v3 for threat
intelligence on security indicators: file hashes (MD5/SHA1/SHA256), IP
addresses (IPv4/IPv6), domains, and URLs.

The indicator type is inferred automatically from the query string — the user
never has to specify it. Lookups are performed over async ``httpx`` with a
configurable timeout, exponential-backoff retry for transient failures
(429/5xx), and respect for the ``Retry-After`` header.

Output
------
The tool returns a rich, structured JSON payload that can feed the RAG layer,
reporting, MITRE mapping, the dashboard, and memory:

.. code-block:: json

    {
      "query": "8.8.8.8",
      "indicator_type": "ip",
      "reputation": 0,
      "malicious": 0,
      "suspicious": 0,
      "harmless": 0,
      "undetected": 0,
      "last_analysis_stats": {},
      "categories": {},
      "tags": [],
      "country": "",
      "asn": "",
      "owner": "",
      "permalink": "",
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
import logging
import re
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar

import httpx

from app.config.settings import Settings, get_settings
from app.tools.base import (
    ToolHealth,
    ToolPermission,
    ToolResult,
)

logger = logging.getLogger(__name__)

#: Default timeout (seconds) for each VirusTotal HTTP request.
DEFAULT_TIMEOUT = 15.0

#: Maximum number of retries for transient failures (429/5xx).
MAX_RETRIES = 3

#: Base backoff delay (seconds) for the first retry.
BASE_BACKOFF = 1.0

#: Default API key used when the caller does not inject one.
DEFAULT_API_KEY = ""

#: Map of VirusTotal indicator type → API resource path segment.
_INDICATOR_PATH = {
    "hash": "files",
    "ip": "ip_addresses",
    "domain": "domains",
    "url": "urls",
}

#: Regex for IPv4 addresses.
_IPV4_RE = re.compile(
    r"^(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)$"
)

#: Regex for IPv6 addresses (loose, common forms).
_IPV6_RE = re.compile(
    r"^(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}$|"
    r"^(?:[0-9a-fA-F]{1,4}:){1,7}:$|"
    r"^(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}$|"
    r"^(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}$|"
    r"^(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}$|"
    r"^(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}$|"
    r"^(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}$|"
    r"^[0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}$|"
    r"^:(?::[0-9a-fA-F]{1,4}){1,7}$|"
    r"^::$"
)

#: Regex for a URL (scheme://host...).
_URL_RE = re.compile(r"^https?://", re.IGNORECASE)

#: Regex for a domain (subdomains allowed, TLD required).
_DOMAIN_RE = re.compile(
    r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?\.)+"
    r"[a-zA-Z]{2,}$"
)

#: Regex for an MD5 hash.
_MD5_RE = re.compile(r"^[a-fA-F0-9]{32}$")

#: Regex for a SHA1 hash.
_SHA1_RE = re.compile(r"^[a-fA-F0-9]{40}$")

#: Regex for a SHA256 hash.
_SHA256_RE = re.compile(r"^[a-fA-F0-9]{64}$")


#: Callable that returns an httpx.AsyncClient (used for tests).
AsyncClientFactory = Callable[[], Awaitable[httpx.AsyncClient]]


def detect_indicator_type(query: str) -> str:
    """Infer the indicator type from a query string.

    Returns one of ``"hash"``, ``"ip"``, ``"domain"``, or ``"url"``.
    """
    value = (query or "").strip()
    if not value:
        return "hash"

    # URL detection first (it also matches a domain pattern).
    if _URL_RE.match(value):
        return "url"

    # IP detection (IPv4 or IPv6).
    if _IPV4_RE.match(value) or _IPV6_RE.match(value):
        return "ip"

    # Hash detection (MD5, SHA1, SHA256).
    if _MD5_RE.match(value) or _SHA1_RE.match(value) or _SHA256_RE.match(value):
        return "hash"

    # Domain detection.
    if _DOMAIN_RE.match(value):
        return "domain"

    # Fallback: treat as a hash (best-effort).
    return "hash"


def _build_url(base_url: str, indicator_type: str, query: str) -> str:
    """Build the VirusTotal API URL for a lookup."""
    path = _INDICATOR_PATH.get(indicator_type, "files")
    # URL lookups need the URL-encoded value; other types pass through.
    if indicator_type == "url":
        encoded = httpx.URL(query).raw_path
        return f"{base_url.rstrip('/')}/{path}/{encoded}"
    return f"{base_url.rstrip('/')}/{path}/{httpx.URL(query).raw_path}"


def _extract_analysis_stats(data: dict[str, Any]) -> dict[str, Any]:
    """Return the ``last_analysis_stats`` from a VT response."""
    attributes = data.get("attributes", {})
    stats = attributes.get("last_analysis_stats", {})
    return stats if isinstance(stats, dict) else {}


def _extract_reputation(data: dict[str, Any]) -> int:
    """Return the reputation score from a VT response."""
    attributes = data.get("attributes", {})
    try:
        return int(attributes.get("reputation", 0))
    except (TypeError, ValueError):
        return 0


def _extract_categories(data: dict[str, Any]) -> dict[str, Any]:
    """Return the categories (by engine) from a VT response."""
    attributes = data.get("attributes", {})
    categories = attributes.get("categories", {})
    return categories if isinstance(categories, dict) else {}


def _extract_tags(data: dict[str, Any]) -> list[str]:
    """Return the tags from a VT response."""
    attributes = data.get("attributes", {})
    tags = attributes.get("tags", [])
    return [str(t) for t in tags] if isinstance(tags, list) else []


def _extract_permalink(indicator_type: str, query: str) -> str:
    """Build the VirusTotal web permalink for an indicator."""
    if indicator_type == "url":
        return f"https://www.virustotal.com/gui/url/{httpx.URL(query).raw_path}"
    return f"https://www.virustotal.com/gui/{indicator_type}/{query}"


def _normalize_response(indicator_type: str, query: str, data: dict[str, Any]) -> dict[str, Any]:
    """Normalize a VirusTotal API response into the structured output shape."""
    stats = _extract_analysis_stats(data)
    attributes = data.get("attributes", {})
    country = attributes.get("country", "")
    asn = attributes.get("as_owner", "")
    owner = attributes.get("as_owner", "")
    if not owner:
        owner = attributes.get("owner", "")

    return {
        "query": query,
        "indicator_type": indicator_type,
        "reputation": _extract_reputation(data),
        "malicious": int(stats.get("malicious", 0)),
        "suspicious": int(stats.get("suspicious", 0)),
        "harmless": int(stats.get("harmless", 0)),
        "undetected": int(stats.get("undetected", 0)),
        "last_analysis_stats": stats,
        "categories": _extract_categories(data),
        "tags": _extract_tags(data),
        "country": country,
        "asn": asn,
        "owner": owner,
        "permalink": _extract_permalink(indicator_type, query),
        "raw": data,
    }


class VirusTotalTool:
    """Real VirusTotal threat-intelligence tool exposing the ``BaseTool`` contract.

    :param api_key: VirusTotal API key. Defaults to the value from
        :class:`Settings.virustotal_api_key`.
    :param base_url: Base URL of the VirusTotal REST API v3.
    :param client_factory: Optional callable returning an ``httpx.AsyncClient``.
        Provided for tests; when omitted, a client is constructed with the
        configured API key header.
    :param timeout: Request timeout in seconds.
    """

    name = "virustotal"
    description = "Query VirusTotal for threat intelligence on hashes, IPs, domains, and URLs."
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
        self._api_key = api_key if api_key is not None else cfg.virustotal_api_key
        self._base_url = base_url or cfg.virustotal_base_url
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
                        "Indicator to look up: a file hash (MD5/SHA1/SHA256), "
                        "IP (IPv4/IPv6), domain, or URL. The type is inferred "
                        "automatically."
                    ),
                },
                "indicator_type": {
                    "type": "string",
                    "enum": ["hash", "ip", "domain", "url"],
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
                "reputation": {"type": "integer"},
                "malicious": {"type": "integer"},
                "suspicious": {"type": "integer"},
                "harmless": {"type": "integer"},
                "undetected": {"type": "integer"},
                "last_analysis_stats": {"type": "object"},
                "categories": {"type": "object"},
                "tags": {"type": "array", "items": {"type": "string"}},
                "country": {"type": "string"},
                "asn": {"type": "string"},
                "owner": {"type": "string"},
                "permalink": {"type": "string"},
                "raw": {"type": "object"},
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Look up an indicator on VirusTotal and return structured JSON.

        :param query: The indicator to look up (required).
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
                "VIRUSTOTAL_API_KEY is not configured. "
                "Set it in the environment or .env to enable threat intelligence lookups.",
            )

        indicator_type = kwargs.get("indicator_type") or detect_indicator_type(query)
        if indicator_type not in _INDICATOR_PATH:
            return ToolResult.fail(
                self.name,
                f"Unsupported indicator type '{indicator_type}'. "
                "Supported: hash, ip, domain, url.",
            )

        url = _build_url(self._base_url, indicator_type, query)
        try:
            data = await self._fetch_with_retry(url)
        except VirusTotalError as exc:
            return ToolResult.fail(self.name, exc.message)
        except Exception as exc:  # noqa: BLE001 - surface as structured failure
            logger.exception("VirusTotal lookup failed for %s.", query)
            return ToolResult.fail(
                self.name,
                f"VirusTotal lookup failed: {exc}",
            )

        output = _normalize_response(indicator_type, query, data)
        return ToolResult.ok(self.name, output)

    async def health(self) -> ToolHealth:
        """Report whether the VirusTotal API key is configured."""
        if not self._api_key.strip():
            return ToolHealth(
                ok=False,
                message="VIRUSTOTAL_API_KEY is not configured.",
            )
        return ToolHealth(
            ok=True,
            message="VIRUSTOTAL_API_KEY is configured.",
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
                    headers={"x-apikey": self._api_key},
                )
        return self._client

    async def _fetch_with_retry(self, url: str) -> dict[str, Any]:
        """Fetch ``url`` with exponential-backoff retry on transient errors.

        :raises VirusTotalError: For non-retryable HTTP errors and when the
            retry budget is exhausted.
        """
        client = await self._client_instance()
        attempt = 0
        while True:
            try:
                response = await client.get(url)
            except httpx.HTTPError as exc:
                # Network failure — retry unless we've exhausted the budget.
                if attempt >= MAX_RETRIES:
                    raise VirusTotalError(
                        f"Network error contacting VirusTotal after {attempt + 1} attempts: {exc}"
                    ) from exc
                attempt += 1
                await asyncio.sleep(BASE_BACKOFF * (2 ** (attempt - 1)))
                continue

            if response.status_code == 200:
                payload = response.json()
                data = payload.get("data", {})
                if not isinstance(data, dict):
                    raise VirusTotalError("VirusTotal returned an unexpected response shape.")
                return data

            if response.status_code in (429, 500, 502, 503, 504):
                if attempt >= MAX_RETRIES:
                    raise VirusTotalError(
                        f"VirusTotal API error after {attempt + 1} attempts: HTTP {response.status_code}."
                    )
                retry_after = response.headers.get("Retry-After")
                delay = BASE_BACKOFF * (2 ** attempt)
                if retry_after:
                    with contextlib.suppress(ValueError):
                        delay = float(retry_after)
                attempt += 1
                await asyncio.sleep(delay)
                continue

            if response.status_code == 401:
                raise VirusTotalError("VirusTotal API key is invalid or unauthorized (HTTP 401).")

            if response.status_code == 403:
                raise VirusTotalError("VirusTotal API key lacks permission (HTTP 403).")

            if response.status_code == 404:
                raise VirusTotalError("Indicator not found on VirusTotal (HTTP 404).")

            raise VirusTotalError(
                f"VirusTotal API returned HTTP {response.status_code}."
            )


class VirusTotalError(Exception):
    """Raised when a VirusTotal lookup cannot be completed."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


__all__ = [
    "DEFAULT_TIMEOUT",
    "VirusTotalError",
    "VirusTotalTool",
    "detect_indicator_type",
]
