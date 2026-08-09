"""Wazuh security-alert tool for the Sentrix Tool Engine.

:class:`WazuhTool` implements the existing :class:`~app.tools.base.BaseTool`
interface and interrogates a Wazuh manager via the official Wazuh REST API.
It lets Sentrix ingest, analyse, and explain Wazuh security alerts.

Authentication
--------------
The tool reads ``WAZUH_URL`` (the full API base URL, e.g.
``https://wazuh-manager:55000``), ``WAZUH_USERNAME`` and ``WAZUH_PASSWORD``
from :class:`~app.config.settings.Settings`. It authenticates once with the
official ``/security/user/authenticate`` endpoint and stores the returned JWT
token in memory. When the token expires or the API returns ``401``, the token
is refreshed transparently by re-authenticating.

Supported operations
--------------------
- ``recent_alerts`` — fetch the most recent alerts (optionally filtered by
  ``rule_level`` severity).
- ``alert`` — fetch a single alert by its ID.
- ``agent`` — fetch agent details or status by agent ID.
- ``rule`` — fetch a rule definition by rule ID.

Every request is made over async ``httpx`` with a configurable timeout, retry
with exponential backoff for transient failures (429/5xx), and respect for the
``Retry-After`` header.

Output
------
Native Wazuh alert data is returned in a structured shape without duplicating
MITRE mappings (the kernel's :class:`~app.mitre.mapper.MitreMapper` enrichment
pipeline attaches ``metadata["mitre"]`` separately):

.. code-block:: json

    {
      "operation": "recent_alerts",
      "agent": {},
      "alert": {},
      "rule": {},
      "groups": [],
      "severity": 10,
      "timestamp": "...",
      "recommendations": [],
      "raw": {}
    }

MITRE IDs already present in the Wazuh rule are preserved verbatim in
``rule.mitre`` so the downstream mapper can honour them.
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import logging
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

#: Default timeout (seconds) for each Wazuh HTTP request.
DEFAULT_TIMEOUT = 15.0

#: Maximum number of retries for transient failures (429/5xx).
MAX_RETRIES = 3

#: Base backoff delay (seconds) for the first retry.
BASE_BACKOFF = 1.0

#: Upper bound for the backoff delay (seconds).
MAX_BACKOFF = 20.0

#: Supported operations exposed by the tool.
SUPPORTED_OPERATIONS = ("recent_alerts", "alert", "agent", "rule")


#: Callable that returns an httpx.AsyncClient (used for tests).
AsyncClientFactory = Callable[[], Awaitable[httpx.AsyncClient]]


def _auth_basic(username: str, password: str) -> str:
    """Return the HTTP Basic auth header value for Wazuh authentication."""
    token = base64.b64encode(f"{username}:{password}".encode()).decode("utf-8")
    return f"Basic {token}"


def _recommendations_for_level(level: int) -> list[str]:
    """Return basic recommendations based on a Wazuh rule level.

    Wazuh rule levels range 0-15; levels >= 12 are highly critical. Detailed
    investigation guidance is left to Gemini downstream - this only produces
    coarse, deterministic recommendations from the alert severity.
    """
    if level >= 12:
        return [
            "Immediately isolate the affected agent and preserve evidence.",
            "Treat this as a critical security incident and escalate to incident response.",
        ]
    if level >= 8:
        return [
            "Review the affected agent and correlate with other alerts.",
            "Verify whether the event matches known-good behaviour.",
        ]
    if level >= 5:
        return [
            "Investigate the alert details and confirm the affected agent.",
            "Check for related events that may indicate a broader pattern.",
        ]
    return [
        "Monitor the alert and review if any action is required.",
    ]


def _mitre_ids(mitre: Any) -> list[str]:
    """Normalize a Wazuh MITRE field (list or dict) into a list of IDs."""
    if isinstance(mitre, list):
        return [str(m) for m in mitre]
    if isinstance(mitre, dict):
        # Wazuh sometimes returns mitre as a dict of ids -> names.
        return [str(k) for k in mitre]
    return []


def _extract_rule_info(data: dict[str, Any]) -> dict[str, Any]:
    """Return a compact, serialisable rule summary from an alert record."""
    rule = data.get("rule", {})
    if not isinstance(rule, dict):
        return {}
    return {
        "rule_id": rule.get("id"),
        "level": rule.get("level"),
        "description": rule.get("description"),
        "groups": rule.get("groups", []),
        "mitre": _mitre_ids(rule.get("mitre", [])),
    }


def _extract_agent_info(data: dict[str, Any]) -> dict[str, Any]:
    """Return a compact agent summary from an alert record."""
    agent = data.get("agent", {})
    if not isinstance(agent, dict):
        return {}
    return {
        "id": agent.get("id"),
        "name": agent.get("name"),
        "ip": agent.get("ip"),
        "groups": agent.get("groups", []),
    }


def _normalize_alert(operation: str, record: dict[str, Any]) -> dict[str, Any]:
    """Normalize a single Wazuh alert record into the structured output shape."""
    rule_info = _extract_rule_info(record)
    try:
        level = int(rule_info.get("level") or 0)
    except (TypeError, ValueError):
        level = 0

    return {
        "operation": operation,
        "agent": _extract_agent_info(record),
        "alert": {
            "id": record.get("id"),
            "status": record.get("status"),
            "timestamp": record.get("timestamp"),
            "description": record.get("description")
            or rule_info.get("description"),
        },
        "rule": rule_info,
        "groups": [
            str(g) for g in (rule_info.get("groups") or []) if g
        ],
        "severity": level,
        "timestamp": record.get("timestamp"),
        "recommendations": _recommendations_for_level(level),
        "raw": record,
    }


class WazuhTool:
    """Real Wazuh security-alert tool exposing the ``BaseTool`` contract.

    :param url: Full Wazuh API base URL (e.g. ``https://wazuh-manager:55000``).
        Defaults to the value from :class:`Settings.wazuh_url`.
    :param username: Wazuh API username. Defaults to
        :class:`Settings.wazuh_username`.
    :param password: Wazuh API password. Defaults to
        :class:`Settings.wazuh_password`.
    :param client_factory: Optional callable returning an ``httpx.AsyncClient``.
        Provided for tests; when omitted, a client is constructed without a
        default auth header (auth is performed via the authenticate endpoint).
    :param timeout: Request timeout in seconds.
    """

    name = "wazuh"
    description = (
        "Query a Wazuh manager for security alerts, agent info, and rule "
        "definitions via the official Wazuh REST API."
    )
    version = "0.1.0"
    permissions: ClassVar[set[ToolPermission]] = {
        ToolPermission(resource="siem", action="read"),
    }

    def __init__(
        self,
        *,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        client_factory: AsyncClientFactory | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        cfg: Settings = get_settings()
        self._url = (url if url is not None else cfg.wazuh_url).rstrip("/")
        self._username = username if username is not None else cfg.wazuh_username
        self._password = password if password is not None else cfg.wazuh_password
        self._client_factory = client_factory
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._token: str | None = None

    # ------------------------------------------------------------------
    # BaseTool contract
    # ------------------------------------------------------------------

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema describing the accepted lookup input."""
        return {
            "type": "object",
            "properties": {
                "operation": {
                    "type": "string",
                    "enum": list(SUPPORTED_OPERATIONS),
                    "description": (
                        "Operation to perform: recent_alerts, alert, agent, or rule."
                    ),
                },
                "alert_id": {
                    "type": "string",
                    "description": "Alert ID (for the 'alert' operation).",
                },
                "agent_id": {
                    "type": "string",
                    "description": "Agent ID (for the 'agent' operation).",
                },
                "rule_id": {
                    "type": "string",
                    "description": "Rule ID (for the 'rule' operation).",
                },
                "rule_level": {
                    "type": "integer",
                    "description": (
                        "Minimum rule level (severity) filter for recent_alerts."
                    ),
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum number of recent alerts to return.",
                },
            },
            "required": ["operation"],
        }

    @property
    def output_schema(self) -> dict[str, Any]:
        """JSON Schema describing the structured lookup output."""
        return {
            "type": "object",
            "properties": {
                "operation": {"type": "string"},
                "agent": {"type": "object"},
                "alert": {"type": "object"},
                "rule": {"type": "object"},
                "groups": {"type": "array", "items": {"type": "string"}},
                "severity": {"type": "integer"},
                "timestamp": {"type": "string"},
                "recommendations": {"type": "array", "items": {"type": "string"}},
                "raw": {"type": "object"},
            },
        }

    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute a Wazuh operation and return structured alert data.

        :param operation: One of :data:`SUPPORTED_OPERATIONS` (required).
        :param alert_id: Alert ID for the ``alert`` operation.
        :param agent_id: Agent ID for the ``agent`` operation.
        :param rule_id: Rule ID for the ``rule`` operation.
        :param rule_level: Minimum severity for ``recent_alerts``.
        :param limit: Maximum alerts to return for ``recent_alerts``.
        """
        operation = (kwargs.get("operation") or "").strip().lower()
        if operation not in SUPPORTED_OPERATIONS:
            return ToolResult.fail(
                self.name,
                f"Unsupported operation '{operation}'. "
                f"Supported: {', '.join(SUPPORTED_OPERATIONS)}.",
            )

        if not self._url:
            return ToolResult.fail(
                self.name,
                "WAZUH_URL is not configured. "
                "Set it in the environment or .env to enable Wazuh lookups.",
            )
        if not self._username or not self._password:
            return ToolResult.fail(
                self.name,
                "WAZUH_USERNAME / WAZUH_PASSWORD are not configured. "
                "Set them in the environment or .env to enable Wazuh lookups.",
            )

        try:
            if operation == "recent_alerts":
                output = await self._recent_alerts(kwargs)
            elif operation == "alert":
                output = await self._alert(kwargs)
            elif operation == "agent":
                output = await self._agent(kwargs)
            else:  # 'rule'
                output = await self._rule(kwargs)
            return ToolResult.ok(self.name, output)
        except WazuhError as exc:
            return ToolResult.fail(self.name, exc.message)
        except Exception as exc:  # noqa: BLE001 - surface as structured failure
            logger.exception("Wazuh operation '%s' failed.", operation)
            return ToolResult.fail(
                self.name,
                f"Wazuh operation failed: {exc}",
            )

    async def health(self) -> ToolHealth:
        """Report whether the Wazuh manager is configured."""
        if not self._url:
            return ToolHealth(ok=False, message="WAZUH_URL is not configured.")
        if not self._username or not self._password:
            return ToolHealth(
                ok=False,
                message="WAZUH_USERNAME / WAZUH_PASSWORD are not configured.",
            )
        return ToolHealth(
            ok=True,
            message="Wazuh manager is configured.",
        )

    # ------------------------------------------------------------------
    # Operations
    # ------------------------------------------------------------------

    async def _recent_alerts(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Fetch recent alerts, optionally filtered by severity."""
        limit = int(kwargs.get("limit") or 20)
        rule_level = kwargs.get("rule_level")
        params: dict[str, Any] = {"limit": limit}
        if rule_level is not None:
            params["q"] = f"rule.level>={int(rule_level)}"

        data = await self._get_json("/alerts", params=params)
        records = data.get("data", {}).get("affected_items", [])
        if not isinstance(records, list):
            records = []

        alerts = [
            _normalize_alert("recent_alerts", r)
            for r in records
            if isinstance(r, dict)
        ]
        return {
            "operation": "recent_alerts",
            "alerts": alerts,
            "count": len(alerts),
            "raw": data,
        }

    async def _alert(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Fetch a single alert by its ID."""
        alert_id = (kwargs.get("alert_id") or "").strip()
        if not alert_id:
            raise WazuhError("Missing required input 'alert_id' for operation 'alert'.")

        data = await self._get_json(f"/alerts/{alert_id}")
        record = data.get("data", {})
        if not isinstance(record, dict) or not record:
            raise WazuhError(f"Alert '{alert_id}' not found.")
        return _normalize_alert("alert", record)

    async def _agent(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Fetch agent details or status by agent ID."""
        agent_id = (kwargs.get("agent_id") or "").strip()
        if not agent_id:
            raise WazuhError("Missing required input 'agent_id' for operation 'agent'.")

        data = await self._get_json(f"/agents/{agent_id}")
        record = data.get("data", {})
        if not isinstance(record, dict) or not record:
            raise WazuhError(f"Agent '{agent_id}' not found.")
        return {
            "operation": "agent",
            "agent": {
                "id": record.get("id"),
                "name": record.get("name"),
                "ip": record.get("ip"),
                "status": record.get("status"),
                "groups": record.get("groups", []),
                "os": record.get("os", {}),
            },
            "raw": record,
        }

    async def _rule(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Fetch a rule definition by rule ID."""
        rule_id = (kwargs.get("rule_id") or "").strip()
        if not rule_id:
            raise WazuhError("Missing required input 'rule_id' for operation 'rule'.")

        data = await self._get_json(f"/rules/{rule_id}")
        record = data.get("data", {})
        if not isinstance(record, dict) or not record:
            raise WazuhError(f"Rule '{rule_id}' not found.")
        return {
            "operation": "rule",
            "rule": {
                "rule_id": record.get("id"),
                "level": record.get("level"),
                "description": record.get("description"),
                "groups": record.get("groups", []),
                "mitre": _mitre_ids(record.get("mitre", [])),
            },
            "raw": record,
        }

    # ------------------------------------------------------------------
    # Internals - HTTP, auth, retry
    # ------------------------------------------------------------------

    async def _client_instance(self) -> httpx.AsyncClient:
        """Return a lazily-constructed (and cached) async HTTP client."""
        if self._client is None:
            if self._client_factory is not None:
                self._client = await self._client_factory()
            else:
                self._client = httpx.AsyncClient(
                    timeout=self._timeout,
                    verify=False,  # Wazuh default self-signed TLS certs
                )
        return self._client

    async def _get_json(
        self,
        path: str,
        *,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Perform an authenticated GET against the Wazuh API.

        Ensures a valid token is present, re-authenticating if the current
        token has expired or the API returns a ``401``.
        """
        client = await self._client_instance()
        url = f"{self._url}{path}"
        attempt = 0
        while True:
            await self._ensure_token(client)
            try:
                response = await client.get(
                    url,
                    params=params,
                    headers={"Authorization": f"Bearer {self._token}"},
                )
            except httpx.HTTPError as exc:
                if attempt >= MAX_RETRIES:
                    raise WazuhError(
                        f"Network error contacting Wazuh after {attempt + 1} attempts: {exc}"
                    ) from exc
                attempt += 1
                await asyncio.sleep(min(BASE_BACKOFF * (2 ** (attempt - 1)), MAX_BACKOFF))
                continue

            if response.status_code == 200:
                return response.json()

            if response.status_code == 401:
                # Token expired or invalid - force re-auth and retry once.
                self._token = None
                if attempt >= MAX_RETRIES:
                    raise WazuhError(
                        "Wazuh authentication failed after re-authenticating "
                        "(HTTP 401)."
                    )
                attempt += 1
                continue

            if response.status_code in (429, 500, 502, 503, 504):
                if attempt >= MAX_RETRIES:
                    raise WazuhError(
                        f"Wazuh API error after {attempt + 1} attempts: HTTP {response.status_code}."
                    )
                retry_after = response.headers.get("Retry-After")
                delay = min(BASE_BACKOFF * (2 ** attempt), MAX_BACKOFF)
                if retry_after:
                    with contextlib.suppress(ValueError):
                        delay = min(float(retry_after), MAX_BACKOFF)
                attempt += 1
                await asyncio.sleep(delay)
                continue

            if response.status_code == 404:
                raise WazuhError("Resource not found on Wazuh (HTTP 404).")

            raise WazuhError(f"Wazuh API returned HTTP {response.status_code}.")

    async def _ensure_token(self, client: httpx.AsyncClient) -> None:
        """Ensure a valid JWT token is cached, authenticating if needed."""
        if self._token:
            return
        url = f"{self._url}/security/user/authenticate"
        try:
            response = await client.post(
                url,
                headers={"Authorization": _auth_basic(self._username, self._password)},
            )
        except httpx.HTTPError as exc:
            raise WazuhError(
                f"Unable to reach Wazuh for authentication: {exc}"
            ) from exc

        if response.status_code == 401:
            raise WazuhError(
                "Wazuh authentication failed: invalid WAZUH_USERNAME or WAZUH_PASSWORD (HTTP 401)."
            )
        if response.status_code != 200:
            raise WazuhError(
                f"Wazuh authentication endpoint returned HTTP {response.status_code}."
            )

        payload = response.json()
        token = payload.get("data", {}).get("token")
        if not token:
            raise WazuhError("Wazuh authentication returned no token.")
        self._token = token


class WazuhError(Exception):
    """Raised when a Wazuh operation cannot be completed."""

    def __init__(self, message: str) -> None:
        self.message = message
        super().__init__(message)


__all__ = [
    "DEFAULT_TIMEOUT",
    "SUPPORTED_OPERATIONS",
    "WazuhError",
    "WazuhTool",
]
