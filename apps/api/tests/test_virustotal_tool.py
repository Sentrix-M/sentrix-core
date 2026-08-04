"""Unit tests for the Sentrix VirusTotal threat-intelligence tool.

All HTTP requests are mocked via ``httpx.MockTransport`` — no real network
access is ever performed. Covers: indicator type detection, hash/IP/domain/URL
lookups, missing/invalid API key, rate limits, network failures, health,
schema, and permissions.
"""

from __future__ import annotations

import asyncio

import httpx

from app.tools.base import ToolPermission
from app.tools.virustotal_tool import (
    VirusTotalTool,
    detect_indicator_type,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_vt_response(
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


def _make_tool(handler) -> VirusTotalTool:
    """Build a VirusTotalTool with a mocked transport handler."""

    async def _client_factory() -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(handler))

    return VirusTotalTool(
        api_key="test-api-key",
        base_url="https://www.virustotal.com/api/v3",
        client_factory=_client_factory,
    )


def _file_payload() -> dict:
    """A realistic VirusTotal file-analysis response."""
    return {
        "data": {
            "attributes": {
                "last_analysis_stats": {
                    "malicious": 2,
                    "suspicious": 1,
                    "harmless": 0,
                    "undetected": 57,
                },
                "reputation": 5,
                "categories": {"AV": "trojan"},
                "tags": ["peexe", "packed"],
                "type_description": "PE32 executable",
            },
            "id": "44d88612fea8a8f36de82e1278abb02f",
        }
    }


def _ip_payload() -> dict:
    """A realistic VirusTotal IP-analysis response."""
    return {
        "data": {
            "attributes": {
                "last_analysis_stats": {
                    "malicious": 0,
                    "suspicious": 0,
                    "harmless": 50,
                    "undetected": 10,
                },
                "reputation": 0,
                "country": "US",
                "as_owner": "GOOGLE",
                "tags": ["malicious-host"],
            },
            "id": "8.8.8.8",
        }
    }


def _domain_payload() -> dict:
    """A realistic VirusTotal domain-analysis response."""
    return {
        "data": {
            "attributes": {
                "last_analysis_stats": {
                    "malicious": 1,
                    "suspicious": 0,
                    "harmless": 20,
                    "undetected": 30,
                },
                "reputation": -1,
                "categories": {"AV": "malware"},
                "tags": ["malicious"],
            },
            "id": "google.com",
        }
    }


def _url_payload() -> dict:
    """A realistic VirusTotal URL-analysis response."""
    return {
        "data": {
            "attributes": {
                "last_analysis_stats": {
                    "malicious": 3,
                    "suspicious": 2,
                    "harmless": 0,
                    "undetected": 45,
                },
                "reputation": -3,
                "categories": {"AV": "phishing"},
                "tags": ["phishing"],
            },
            "id": "https://evil.example.com",
        }
    }


# ---------------------------------------------------------------------------
# Indicator type detection
# ---------------------------------------------------------------------------


class TestDetectIndicatorType:
    def test_detects_md5(self) -> None:
        assert detect_indicator_type("44d88612fea8a8f36de82e1278abb02f") == "hash"

    def test_detects_sha1(self) -> None:
        assert detect_indicator_type("a" * 40) == "hash"

    def test_detects_sha256(self) -> None:
        assert detect_indicator_type("a" * 64) == "hash"

    def test_detects_ipv4(self) -> None:
        assert detect_indicator_type("8.8.8.8") == "ip"

    def test_detects_ipv6(self) -> None:
        assert detect_indicator_type("2001:4860:4860::8888") == "ip"

    def test_detects_domain(self) -> None:
        assert detect_indicator_type("google.com") == "domain"

    def test_detects_url(self) -> None:
        assert detect_indicator_type("https://example.com") == "url"

    def test_falls_back_to_hash(self) -> None:
        assert detect_indicator_type("not-an-indicator") == "hash"


# ---------------------------------------------------------------------------
# File hash lookup
# ---------------------------------------------------------------------------


class TestFileHashLookup:
    def test_hash_lookup(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert "/files/" in request.url.path
            return _make_vt_response(payload=_file_payload())

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(query="44d88612fea8a8f36de82e1278abb02f"))
        assert result.success is True
        assert result.output["indicator_type"] == "hash"
        assert result.output["malicious"] == 2
        assert result.output["suspicious"] == 1
        assert result.output["reputation"] == 5
        assert result.output["permalink"] == (
            "https://www.virustotal.com/gui/hash/44d88612fea8a8f36de82e1278abb02f"
        )
        assert "raw" in result.output


# ---------------------------------------------------------------------------
# IP lookup
# ---------------------------------------------------------------------------


class TestIpLookup:
    def test_ip_lookup(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert "/ip_addresses/" in request.url.path
            return _make_vt_response(payload=_ip_payload())

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(query="8.8.8.8"))
        assert result.success is True
        assert result.output["indicator_type"] == "ip"
        assert result.output["country"] == "US"
        assert result.output["asn"] == "GOOGLE"
        assert result.output["malicious"] == 0


# ---------------------------------------------------------------------------
# Domain lookup
# ---------------------------------------------------------------------------


class TestDomainLookup:
    def test_domain_lookup(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert "/domains/" in request.url.path
            return _make_vt_response(payload=_domain_payload())

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(query="google.com"))
        assert result.success is True
        assert result.output["indicator_type"] == "domain"
        assert result.output["reputation"] == -1
        assert result.output["malicious"] == 1


# ---------------------------------------------------------------------------
# URL lookup
# ---------------------------------------------------------------------------


class TestUrlLookup:
    def test_url_lookup(self) -> None:
        def handler(request: httpx.Request) -> httpx.Response:
            assert "/urls/" in request.url.path
            return _make_vt_response(payload=_url_payload())

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(query="https://evil.example.com"))
        assert result.success is True
        assert result.output["indicator_type"] == "url"
        assert result.output["malicious"] == 3


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestErrorHandling:
    def test_missing_query(self) -> None:
        tool = _make_tool(lambda _request: _make_vt_response())
        result = asyncio.run(tool.execute(query=""))
        assert result.success is False
        assert "Missing required input" in (result.error or "")

    def test_missing_api_key(self) -> None:
        tool = VirusTotalTool(api_key="")
        result = asyncio.run(tool.execute(query="8.8.8.8"))
        assert result.success is False
        assert "VIRUSTOTAL_API_KEY" in (result.error or "")

    def test_invalid_indicator_type(self) -> None:
        tool = _make_tool(lambda _request: _make_vt_response())
        result = asyncio.run(tool.execute(query="8.8.8.8", indicator_type="bogus"))
        assert result.success is False
        assert "Unsupported indicator type" in (result.error or "")

    def test_rate_limit_with_retry_after(self) -> None:
        calls = {"count": 0}

        def handler(_request: httpx.Request) -> httpx.Response:
            calls["count"] += 1
            if calls["count"] < 3:
                return _make_vt_response(
                    status_code=429,
                    headers={"Retry-After": "0"},
                )
            return _make_vt_response(payload=_ip_payload())

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(query="8.8.8.8"))
        assert result.success is True
        assert calls["count"] == 3

    def test_rate_limit_exhausted(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return _make_vt_response(status_code=429)

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(query="8.8.8.8"))
        assert result.success is False
        assert "429" in (result.error or "")

    def test_unauthorized(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return _make_vt_response(status_code=401)

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(query="8.8.8.8"))
        assert result.success is False
        assert "401" in (result.error or "")

    def test_not_found(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            return _make_vt_response(status_code=404)

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(query="8.8.8.8"))
        assert result.success is False
        assert "404" in (result.error or "")

    def test_network_failure(self) -> None:
        def handler(_request: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("Network unreachable")

        tool = _make_tool(handler)
        result = asyncio.run(tool.execute(query="8.8.8.8"))
        assert result.success is False
        assert "Network error" in (result.error or "")


# ---------------------------------------------------------------------------
# Health, schema, permissions
# ---------------------------------------------------------------------------


class TestHealthSchemaPermissions:
    def test_health_configured(self) -> None:
        tool = VirusTotalTool(api_key="test-key")
        health = asyncio.run(tool.health())
        assert health.ok is True

    def test_health_missing_key(self) -> None:
        tool = VirusTotalTool(api_key="")
        health = asyncio.run(tool.health())
        assert health.ok is False
        assert "VIRUSTOTAL_API_KEY" in health.message

    def test_input_schema(self) -> None:
        tool = VirusTotalTool(api_key="test-key")
        schema = tool.input_schema
        assert "query" in schema["properties"]
        assert "query" in schema["required"]

    def test_output_schema(self) -> None:
        tool = VirusTotalTool(api_key="test-key")
        schema = tool.output_schema
        assert "query" in schema["properties"]
        assert "indicator_type" in schema["properties"]
        assert "malicious" in schema["properties"]
        assert "raw" in schema["properties"]

    def test_permissions(self) -> None:
        assert (
            ToolPermission(resource="threatintel", action="read")
            in VirusTotalTool.permissions
        )

    def test_name_and_version(self) -> None:
        tool = VirusTotalTool(api_key="test-key")
        assert tool.name == "virustotal"
        assert tool.version == "0.1.0"
