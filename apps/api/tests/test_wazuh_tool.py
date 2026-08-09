"""Unit tests for the Sentrix Wazuh security-alert tool.

All HTTP requests are mocked via ``httpx.MockTransport`` — no real network
access is ever performed. Covers: authentication (JWT), each supported
operation (recent_alerts, alert, agent, rule), retry/backoff, error handling,
health, schema, and permissions.
"""

from __future__ import annotations

import asyncio

import httpx

from app.tools.base import ToolPermission
from app.tools.wazuh_tool import (
    WazuhTool,
    _normalize_alert,
    _recommendations_for_level,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_TOKEN = "fake-jwt-token"


def _make_response(
    *,
    status_code: int = 200,
    payload: dict | None = None,
    headers: dict | None = None,
) -> httpx.Response:
    """Build a fake HTTP response."""
    return httpx.Response(
        status_code=status_code,
        json=payload or {},
        headers=headers or {},
    )


def _auth_payload() -> dict:
    """A realistic Wazuh auth response containing a JWT token."""
    return {"data": {"token": _FAKE_TOKEN}}


def _alert_record() -> dict:
    """A realistic Wazuh alert record."""
    return {
        "id": "001",
        "status": "active",
        "timestamp": "2025-01-01T00:00:00.000Z",
        "description": "Host-based intrusion detection alert",
        "agent": {"id": "001", "name": "agent-01", "ip": "10.0.0.5", "groups": ["default"]},
        "rule": {
            "id": "1001",
            "level": 12,
            "description": "C2 beacon detected",
            "groups": ["command_control", "c2"],
            "mitre": ["T1071.001"],
        },
    }


def _alerts_payload() -> dict:
    """A realistic Wazuh recent-alerts response."""
    return {"data": {"affected_items": [_alert_record()]}}


def _agent_payload() -> dict:
    """A realistic Wazuh agent response."""
    return {
        "data": {
            "id": "001",
            "name": "agent-01",
            "ip": "10.0.0.5",
            "status": "active",
            "groups": ["default"],
            "os": {"name": "Linux"},
        }
    }


def _rule_payload() -> dict:
    """A realistic Wazuh rule response."""
    return {
        "data": {
            "id": "1001",
            "level": 12,
            "description": "C2 beacon detected",
            "groups": ["command_control", "c2"],
            "mitre": ["T1071.001"],
        }
    }


def _with_auth(data_handler):
    """Wrap a data handler so the auth endpoint is answered first."""

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/security/user/authenticate":
            return _make_response(payload=_auth_payload())
        return data_handler(request)

    return handler


def _make_tool(handler) -> WazuhTool:
    """Build a WazuhTool with a mocked transport handler."""

    async def _client_factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return WazuhTool(
        url="https://wazuh-manager:55000",
        username="wazuh-user",
        password="wazuh-pass",
        client_factory=_client_factory,
    )


# ---------------------------------------------------------------------------
# Authentication
# ---------------------------------------------------------------------------


class TestAuthentication:
    def test_authenticates_with_basic_auth(self) -> None:
        seen_auth: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/security/user/authenticate":
                seen_auth.append(request.headers.get("Authorization", ""))
                return _make_response(payload=_auth_payload())
            return _make_response(payload=_alerts_payload())

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(operation="recent_alerts"))
        assert result.success is True
        assert seen_auth
        assert seen_auth[0].startswith("Basic ")

    def test_uses_bearer_token_for_data(self) -> None:
        seen_auth: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/security/user/authenticate":
                return _make_response(payload=_auth_payload())
            seen_auth.append(request.headers.get("Authorization", ""))
            return _make_response(payload=_alerts_payload())

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(operation="recent_alerts"))
        assert result.success is True
        assert seen_auth
        assert seen_auth[0] == f"Bearer {_FAKE_TOKEN}"

    def test_invalid_credentials(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return _make_response(status_code=401)

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(operation="recent_alerts"))
        assert result.success is False
        assert "401" in (result.error or "")

    def test_auth_returns_no_token(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return _make_response(payload={"data": {}})

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(operation="recent_alerts"))
        assert result.success is False
        assert "no token" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# Operations
# ---------------------------------------------------------------------------


class TestRecentAlerts:
    def test_fetches_recent_alerts(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/alerts"
            return _make_response(payload=_alerts_payload())

        tool = _make_tool(_with_auth(handler))
        result = asyncio.run(tool.execute(operation="recent_alerts"))
        assert result.success is True
        output = result.output
        assert output["operation"] == "recent_alerts"
        assert output["count"] == 1
        assert output["alerts"][0]["severity"] == 12
        assert output["alerts"][0]["rule"]["mitre"] == ["T1071.001"]
        assert "recommendations" in output["alerts"][0]

    def test_applies_rule_level_filter(self) -> None:
        seen_params: list[str] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_params.append(request.url.params.get("q", ""))
            return _make_response(payload=_alerts_payload())

        tool = _make_tool(_with_auth(handler))
        result = asyncio.run(
            tool.execute(operation="recent_alerts", rule_level=10)
        )
        assert result.success is True
        assert seen_params
        assert "rule.level>=10" in seen_params[0]


class TestAlert:
    def test_fetches_single_alert(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/alerts/001"
            return _make_response(payload={"data": _alert_record()})

        tool = _make_tool(_with_auth(handler))
        result = asyncio.run(tool.execute(operation="alert", alert_id="001"))
        assert result.success is True
        assert result.output["operation"] == "alert"
        assert result.output["alert"]["id"] == "001"

    def test_requires_alert_id(self) -> None:
        tool = _make_tool(_with_auth(lambda _request: _make_response()))
        result = asyncio.run(tool.execute(operation="alert"))
        assert result.success is False
        assert "alert_id" in (result.error or "")

    def test_alert_not_found(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return _make_response(status_code=404)

        tool = _make_tool(_with_auth(handler))
        result = asyncio.run(tool.execute(operation="alert", alert_id="999"))
        assert result.success is False
        assert "404" in (result.error or "")


class TestAgent:
    def test_fetches_agent(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/agents/001"
            return _make_response(payload=_agent_payload())

        tool = _make_tool(_with_auth(handler))
        result = asyncio.run(tool.execute(operation="agent", agent_id="001"))
        assert result.success is True
        assert result.output["operation"] == "agent"
        assert result.output["agent"]["id"] == "001"
        assert result.output["agent"]["status"] == "active"

    def test_requires_agent_id(self) -> None:
        tool = _make_tool(_with_auth(lambda _request: _make_response()))
        result = asyncio.run(tool.execute(operation="agent"))
        assert result.success is False
        assert "agent_id" in (result.error or "")


class TestRule:
    def test_fetches_rule(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert request.url.path == "/rules/1001"
            return _make_response(payload=_rule_payload())

        tool = _make_tool(_with_auth(handler))
        result = asyncio.run(tool.execute(operation="rule", rule_id="1001"))
        assert result.success is True
        assert result.output["operation"] == "rule"
        assert result.output["rule"]["mitre"] == ["T1071.001"]

    def test_requires_rule_id(self) -> None:
        tool = _make_tool(_with_auth(lambda _request: _make_response()))
        result = asyncio.run(tool.execute(operation="rule"))
        assert result.success is False
        assert "rule_id" in (result.error or "")


# ---------------------------------------------------------------------------
# Input validation / configuration
# ---------------------------------------------------------------------------


class TestValidation:
    def test_unsupported_operation(self) -> None:
        tool = _make_tool(_with_auth(lambda _request: _make_response()))
        result = asyncio.run(tool.execute(operation="bogus"))
        assert result.success is False
        assert "Unsupported operation" in (result.error or "")

    def test_missing_url(self) -> None:
        tool = WazuhTool(
            url="",
            username="u",
            password="p",
            client_factory=lambda: _make_async_client(_with_auth(lambda _r: _make_response())),
        )
        result = asyncio.run(tool.execute(operation="recent_alerts"))
        assert result.success is False
        assert "WAZUH_URL" in (result.error or "")

    def test_missing_credentials(self) -> None:
        tool = WazuhTool(
            url="https://wazuh-manager:55000",
            username="",
            password="",
            client_factory=lambda: _make_async_client(_with_auth(lambda _r: _make_response())),
        )
        result = asyncio.run(tool.execute(operation="recent_alerts"))
        assert result.success is False
        assert "WAZUH_USERNAME" in (result.error or "")


async def _make_async_client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


# ---------------------------------------------------------------------------
# Retry / backoff
# ---------------------------------------------------------------------------


class TestRetry:
    def test_retries_on_429(self) -> None:
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/security/user/authenticate":
                return _make_response(payload=_auth_payload())
            calls["count"] += 1
            if calls["count"] < 3:
                return _make_response(status_code=429, headers={"Retry-After": "0"})
            return _make_response(payload=_alerts_payload())

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(operation="recent_alerts"))
        assert result.success is True
        assert calls["count"] == 3

    def test_retries_on_500(self) -> None:
        calls = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/security/user/authenticate":
                return _make_response(payload=_auth_payload())
            calls["count"] += 1
            if calls["count"] < 2:
                return _make_response(status_code=500)
            return _make_response(payload=_alerts_payload())

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(operation="recent_alerts"))
        assert result.success is True
        assert calls["count"] == 2

    def test_retries_exhausted(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/security/user/authenticate":
                return _make_response(payload=_auth_payload())
            return _make_response(status_code=503)

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(operation="recent_alerts"))
        assert result.success is False
        assert "503" in (result.error or "")

    def test_network_failure(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Network unreachable")

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(operation="recent_alerts"))
        assert result.success is False
        assert "Network unreachable" in (result.error or "")


# ---------------------------------------------------------------------------
# Health, schema, permissions
# ---------------------------------------------------------------------------


class TestHealthSchemaPermissions:
    def test_health_configured(self) -> None:
        tool = WazuhTool(url="https://wazuh:55000", username="u", password="p")
        health = asyncio.run(tool.health())
        assert health.ok is True

    def test_health_missing_url(self) -> None:
        tool = WazuhTool(url="", username="u", password="p")
        health = asyncio.run(tool.health())
        assert health.ok is False
        assert "WAZUH_URL" in health.message

    def test_health_missing_credentials(self) -> None:
        tool = WazuhTool(url="https://wazuh:55000", username="", password="")
        health = asyncio.run(tool.health())
        assert health.ok is False
        assert "WAZUH_USERNAME" in health.message

    def test_input_schema(self) -> None:
        tool = WazuhTool(url="https://wazuh:55000", username="u", password="p")
        schema = tool.input_schema
        assert "operation" in schema["properties"]
        assert "operation" in schema["required"]

    def test_output_schema(self) -> None:
        tool = WazuhTool(url="https://wazuh:55000", username="u", password="p")
        schema = tool.output_schema
        assert "operation" in schema["properties"]
        assert "severity" in schema["properties"]
        assert "raw" in schema["properties"]

    def test_permissions(self) -> None:
        assert ToolPermission(resource="siem", action="read") in WazuhTool.permissions

    def test_name_and_version(self) -> None:
        tool = WazuhTool(url="https://wazuh:55000", username="u", password="p")
        assert tool.name == "wazuh"
        assert tool.version == "0.1.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestHelpers:
    def test_recommendations_critical(self) -> None:
        recs = _recommendations_for_level(13)
        assert any("isolate" in r.lower() for r in recs)

    def test_recommendations_high(self) -> None:
        recs = _recommendations_for_level(9)
        assert any("correlate" in r.lower() for r in recs)

    def test_recommendations_low(self) -> None:
        recs = _recommendations_for_level(2)
        assert any("monitor" in r.lower() for r in recs)

    def test_normalize_alert_shape(self) -> None:
        normalized = _normalize_alert("alert", _alert_record())
        assert normalized["operation"] == "alert"
        assert normalized["severity"] == 12
        assert normalized["rule"]["mitre"] == ["T1071.001"]
        assert normalized["groups"] == ["command_control", "c2"]
        assert normalized["agent"]["id"] == "001"

