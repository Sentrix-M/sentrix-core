"""Unit tests for the Sentrix Tool Engine.

Covers:
- Tool interface (ToolResult, ToolPermission, ToolHealth)
- ToolRegistry (register, list, enable/disable)
- ToolRouter (resolve, permissions, input validation)
- ToolExecutor (execute, timeout, cancellation, errors)
- Mock tools (filesystem, terminal, python)
- API endpoint (POST /api/v1/tools/execute)
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from fastapi import status
from fastapi.testclient import TestClient

from app.main import app
from app.tools.base import (
    ToolHealth,
    ToolPermission,
    ToolResult,
)
from app.tools.executor import ToolExecutor
from app.tools.mock_tools import (
    MockFilesystemTool,
    MockPythonTool,
    MockTerminalTool,
)
from app.tools.registry import ToolRegistry
from app.tools.router import ToolRouter

# Matches the seed admin configured in app.config.settings.
ADMIN_EMAIL = "admin@sentrix.io"
ADMIN_PASSWORD = "ChangeMe_123!"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def client() -> TestClient:
    """Return a TestClient with the lifespan executed."""
    with TestClient(app) as c:
        yield c


@pytest.fixture(scope="module")
def auth_token(client: TestClient) -> str:
    """Return an access token for the seeded admin user."""
    response = client.post(
        "/api/v1/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
    )
    assert response.status_code == 200
    return response.json()["access_token"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _StubTool:
    """Minimal tool stub for registry/router testing."""

    name = "stub"
    description = "A stub tool"
    version = "0.1.0"
    permissions = {ToolPermission(resource="stub", action="execute")}

    @property
    def input_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {"type": "string"},
                "count": {"type": "integer"},
            },
            "required": ["message"],
        }

    @property
    def output_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {"echo": {"type": "string"}}}

    async def execute(self, **kwargs: Any) -> ToolResult:
        return ToolResult.ok(self.name, {"echo": kwargs.get("message", "")})

    async def health(self) -> ToolHealth:
        return ToolHealth(ok=True, message="Stub healthy")


class _SlowTool:
    """Tool that takes longer than the default timeout."""

    name = "slow"
    description = "A slow tool"
    version = "0.1.0"
    permissions = set()

    @property
    def input_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    @property
    def output_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, **kwargs: Any) -> ToolResult:  # noqa: ARG002
        await asyncio.sleep(10)
        return ToolResult.ok(self.name, {"done": True})

    async def health(self) -> ToolHealth:
        return ToolHealth(ok=True, message="Slow tool healthy")


# ---------------------------------------------------------------------------
# ToolResult
# ---------------------------------------------------------------------------


class TestToolResult:
    def test_ok(self) -> None:
        result = ToolResult.ok("test", {"data": 1})
        assert result.success is True
        assert result.tool == "test"
        assert result.output == {"data": 1}
        assert result.error is None
        assert "execution_time_ms" in result.metadata
        assert "timestamp" in result.metadata

    def test_fail(self) -> None:
        result = ToolResult.fail("test", "something went wrong")
        assert result.success is False
        assert result.tool == "test"
        assert result.error == "something went wrong"
        assert result.output is None

    def test_ok_with_extra_metadata(self) -> None:
        result = ToolResult.ok("test", "output", extra="value")
        assert result.metadata["extra"] == "value"


# ---------------------------------------------------------------------------
# ToolPermission
# ---------------------------------------------------------------------------


class TestToolPermission:
    def test_permission_string(self) -> None:
        perm = ToolPermission(resource="filesystem", action="read")
        assert perm.permission_string == "filesystem:read"
        assert str(perm) == "filesystem:read"

    def test_hashable(self) -> None:
        perms = {
            ToolPermission(resource="filesystem", action="read"),
            ToolPermission(resource="filesystem", action="write"),
        }
        assert len(perms) == 2


# ---------------------------------------------------------------------------
# ToolHealth
# ---------------------------------------------------------------------------


class TestToolHealth:
    def test_constructs_with_defaults(self) -> None:
        health = ToolHealth(ok=True)
        assert health.ok is True
        assert health.message == ""

    def test_equality(self) -> None:
        assert ToolHealth(ok=True, message="x") == ToolHealth(ok=True, message="x")
        assert ToolHealth(ok=True) != ToolHealth(ok=False)

    def test_repr(self) -> None:
        assert "ok=True" in repr(ToolHealth(ok=True))


# ---------------------------------------------------------------------------
# ToolRegistry
# ---------------------------------------------------------------------------


class TestToolRegistry:
    def test_register_and_get(self) -> None:
        registry = ToolRegistry()
        stub = _StubTool()
        registry.register(stub)
        assert registry.get("stub") is stub
        assert "stub" in registry

    def test_register_replaces_existing(self) -> None:
        registry = ToolRegistry()
        registry.register(_StubTool())

        class _StubV2(_StubTool):
            version = "0.2.0"

        v2 = _StubV2()
        registry.register(v2)
        assert registry.get("stub").version == "0.2.0"

    def test_deregister(self) -> None:
        registry = ToolRegistry()
        registry.register(_StubTool())
        registry.deregister("stub")
        assert registry.get("stub") is None
        assert "stub" not in registry

    def test_require_raises_for_unknown(self) -> None:
        registry = ToolRegistry()
        with pytest.raises(KeyError):
            registry.require("nonexistent")

    def test_list_tools(self) -> None:
        registry = ToolRegistry()
        registry.register(_StubTool())
        tools = registry.list_tools()
        assert len(tools) == 1
        assert tools[0]["name"] == "stub"
        assert tools[0]["enabled"] is True

    def test_enable_disable(self) -> None:
        registry = ToolRegistry()
        registry.register(_StubTool())
        assert registry.is_enabled("stub") is True
        registry.disable("stub")
        assert registry.is_enabled("stub") is False
        registry.enable("stub")
        assert registry.is_enabled("stub") is True

    def test_enable_unknown_raises(self) -> None:
        registry = ToolRegistry()
        with pytest.raises(KeyError):
            registry.enable("nonexistent")

    def test_names_and_len(self) -> None:
        registry = ToolRegistry()
        registry.register(_StubTool())
        assert registry.names() == ("stub",)
        assert len(registry) == 1


# ---------------------------------------------------------------------------
# ToolRouter
# ---------------------------------------------------------------------------


class TestToolRouter:
    def test_resolve_returns_tool(self) -> None:
        registry = ToolRegistry()
        stub = _StubTool()
        registry.register(stub)
        router = ToolRouter(registry)
        assert router.resolve("stub") is stub

    def test_resolve_unknown_raises(self) -> None:
        router = ToolRouter(ToolRegistry())
        with pytest.raises(KeyError):
            router.resolve("nonexistent")

    def test_resolve_disabled_raises(self) -> None:
        registry = ToolRegistry()
        registry.register(_StubTool())
        registry.disable("stub")
        router = ToolRouter(registry)
        with pytest.raises(RuntimeError):
            router.resolve("stub")

    def test_validate_permissions_passes(self) -> None:
        router = ToolRouter(ToolRegistry())
        tool = _StubTool()
        router.validate_permissions(tool, {"stub:execute"})

    def test_validate_permissions_fails(self) -> None:
        router = ToolRouter(ToolRegistry())
        tool = _StubTool()
        with pytest.raises(PermissionError):
            router.validate_permissions(tool, set())

    def test_validate_input_passes(self) -> None:
        router = ToolRouter(ToolRegistry())
        tool = _StubTool()
        router.validate_input(tool, {"message": "hello"})

    def test_validate_input_missing_required(self) -> None:
        router = ToolRouter(ToolRegistry())
        tool = _StubTool()
        with pytest.raises(ValueError, match="Missing required field 'message'"):
            router.validate_input(tool, {})

    def test_validate_input_wrong_type(self) -> None:
        router = ToolRouter(ToolRegistry())
        tool = _StubTool()
        with pytest.raises(ValueError, match="Field 'message' for tool 'stub' expected string"):
            router.validate_input(tool, {"message": 42})


# ---------------------------------------------------------------------------
# ToolExecutor
# ---------------------------------------------------------------------------


class TestToolExecutor:
    def test_execute_success(self) -> None:
        registry = ToolRegistry()
        registry.register(_StubTool())
        executor = ToolExecutor(registry)
        result = asyncio.run(executor.execute("stub", {"message": "hello"}))
        assert result.success is True
        assert result.tool == "stub"
        assert result.output == {"echo": "hello"}
        assert result.metadata["execution_time_ms"] >= 0

    def test_execute_unknown_tool(self) -> None:
        executor = ToolExecutor(ToolRegistry())
        result = asyncio.run(executor.execute("nonexistent", {}))
        assert result.success is False
        assert "not registered" in (result.error or "")

    def test_execute_with_permissions(self) -> None:
        registry = ToolRegistry()
        registry.register(_StubTool())
        executor = ToolExecutor(registry)
        result = asyncio.run(
            executor.execute("stub", {"message": "hi"}, user_permissions={"stub:execute"})
        )
        assert result.success is True

    def test_execute_without_permissions(self) -> None:
        registry = ToolRegistry()
        registry.register(_StubTool())
        executor = ToolExecutor(registry)
        result = asyncio.run(
            executor.execute("stub", {"message": "hi"}, user_permissions=set())
        )
        assert result.success is False
        assert "permission" in (result.error or "").lower()

    def test_execute_timeout(self) -> None:
        registry = ToolRegistry()
        registry.register(_SlowTool())
        executor = ToolExecutor(registry)
        result = asyncio.run(
            executor.execute("slow", {}, timeout=0.1)
        )
        assert result.success is False
        assert result.metadata.get("status") == "timeout"

    def test_execute_validation_error(self) -> None:
        registry = ToolRegistry()
        registry.register(_StubTool())
        executor = ToolExecutor(registry)
        result = asyncio.run(executor.execute("stub", {}))
        assert result.success is False
        assert "Missing required field" in (result.error or "")

    def test_execute_disabled_tool(self) -> None:
        registry = ToolRegistry()
        registry.register(_StubTool())
        registry.disable("stub")
        executor = ToolExecutor(registry)
        result = asyncio.run(executor.execute("stub", {"message": "hi"}))
        assert result.success is False
        assert "disabled" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# MockFilesystemTool
# ---------------------------------------------------------------------------


class TestMockFilesystemTool:
    def test_name(self) -> None:
        assert MockFilesystemTool().name == "filesystem"

    def test_read_returns_empty(self) -> None:
        tool = MockFilesystemTool()
        result = asyncio.run(tool.execute(action="read", path="/tmp/test.txt"))
        assert result.success is True
        assert result.output["content"] == ""

    def test_write_and_read(self) -> None:
        tool = MockFilesystemTool()
        asyncio.run(tool.execute(action="write", path="/tmp/test.txt", content="hello"))
        result = asyncio.run(tool.execute(action="read", path="/tmp/test.txt"))
        assert result.output["content"] == "hello"

    def test_list(self) -> None:
        tool = MockFilesystemTool()
        asyncio.run(tool.execute(action="write", path="/tmp/a.txt", content="a"))
        asyncio.run(tool.execute(action="write", path="/tmp/b.txt", content="b"))
        result = asyncio.run(tool.execute(action="list", path="/tmp"))
        assert result.output["count"] == 2

    def test_delete(self) -> None:
        tool = MockFilesystemTool()
        asyncio.run(tool.execute(action="write", path="/tmp/del.txt", content="x"))
        result = asyncio.run(tool.execute(action="delete", path="/tmp/del.txt"))
        assert result.output["deleted"] is True

    def test_unknown_action(self) -> None:
        tool = MockFilesystemTool()
        result = asyncio.run(tool.execute(action="unknown", path="/tmp"))
        assert result.success is False

    def test_health(self) -> None:
        tool = MockFilesystemTool()
        health = asyncio.run(tool.health())
        assert health.ok is True

    def test_permissions(self) -> None:
        assert len(MockFilesystemTool.permissions) == 2

    def test_schema(self) -> None:
        tool = MockFilesystemTool()
        assert "action" in tool.input_schema["properties"]
        assert "path" in tool.input_schema["required"]


# ---------------------------------------------------------------------------
# MockTerminalTool
# ---------------------------------------------------------------------------


class TestMockTerminalTool:
    def test_name(self) -> None:
        assert MockTerminalTool().name == "terminal"

    def test_execute_known_command(self) -> None:
        tool = MockTerminalTool()
        result = asyncio.run(tool.execute(command="whoami"))
        assert result.success is True
        assert "sentrix-user" in result.output["stdout"]

    def test_execute_canned_by_prefix(self) -> None:
        tool = MockTerminalTool()
        result = asyncio.run(tool.execute(command="ls -la /home"))
        assert result.success is True
        assert result.output["stdout"]

    def test_execute_unknown_command(self) -> None:
        tool = MockTerminalTool()
        result = asyncio.run(tool.execute(command="some_random_command_12345"))
        assert result.success is True
        assert "executed successfully" in result.output["stdout"]

    def test_execute_with_args(self) -> None:
        tool = MockTerminalTool()
        result = asyncio.run(tool.execute(command="echo", args=["hello"]))
        assert result.success is True
        assert result.output["exit_code"] == 0

    def test_health(self) -> None:
        tool = MockTerminalTool()
        health = asyncio.run(tool.health())
        assert health.ok is True

    def test_schema(self) -> None:
        tool = MockTerminalTool()
        assert "command" in tool.input_schema["required"]


# ---------------------------------------------------------------------------
# MockPythonTool
# ---------------------------------------------------------------------------


class TestMockPythonTool:
    def test_name(self) -> None:
        assert MockPythonTool().name == "python"

    def test_execute_print(self) -> None:
        tool = MockPythonTool()
        result = asyncio.run(tool.execute(code="print('hello')"))
        assert result.success is True

    def test_execute_import(self) -> None:
        tool = MockPythonTool()
        result = asyncio.run(tool.execute(code="import os"))
        assert result.success is True
        assert "imported successfully" in result.output["stdout"]

    def test_execute_math(self) -> None:
        tool = MockPythonTool()
        result = asyncio.run(tool.execute(code="1+1"))
        assert result.success is True
        assert result.output["result"] == "2" or result.output["stdout"]

    def test_execute_empty(self) -> None:
        tool = MockPythonTool()
        result = asyncio.run(tool.execute(code="x = 1"))
        assert result.success is True
        assert "executed successfully" in result.output["stdout"]

    def test_health(self) -> None:
        tool = MockPythonTool()
        health = asyncio.run(tool.health())
        assert health.ok is True

    def test_schema(self) -> None:
        tool = MockPythonTool()
        assert "code" in tool.input_schema["required"]


# ---------------------------------------------------------------------------
# API endpoint
# ---------------------------------------------------------------------------


class TestToolApi:
    """Integration tests for the tool API endpoint."""

    def test_execute_tool_requires_auth(self, client: TestClient) -> None:
        """POST /api/v1/tools/execute without auth returns 401."""
        response = client.post(
            "/api/v1/tools/execute",
            json={"tool": "filesystem", "input": {"action": "list", "path": "/tmp"}},
        )
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_execute_tool_with_auth(self, client: TestClient, auth_token: str) -> None:
        """POST /api/v1/tools/execute with auth returns 200."""
        response = client.post(
            "/api/v1/tools/execute",
            json={"tool": "filesystem", "input": {"action": "read", "path": "/tmp/test.txt"}},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert data["tool"] == "filesystem"

    def test_execute_unknown_tool(self, client: TestClient, auth_token: str) -> None:
        """POST /api/v1/tools/execute with unknown tool returns 200 with error."""
        response = client.post(
            "/api/v1/tools/execute",
            json={"tool": "nonexistent", "input": {}},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is False
        assert "not registered" in (data.get("error") or "")

    def test_list_tools_requires_auth(self, client: TestClient) -> None:
        """GET /api/v1/tools without auth returns 401."""
        response = client.get("/api/v1/tools")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_tools_with_auth(self, client: TestClient, auth_token: str) -> None:
        """GET /api/v1/tools with auth returns tool list."""
        response = client.get(
            "/api/v1/tools",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert "tools" in data
        assert data["total"] >= 3  # filesystem, terminal, python
        tool_names = {t["name"] for t in data["tools"]}
        assert "filesystem" in tool_names
        assert "terminal" in tool_names
        assert "python" in tool_names

    def test_get_tool_details(self, client: TestClient, auth_token: str) -> None:
        """GET /api/v1/tools/{name} returns tool metadata."""
        response = client.get(
            "/api/v1/tools/filesystem",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["name"] == "filesystem"
        assert data["description"]
        assert data["version"]
        assert data["enabled"] is True
        assert "input_schema" in data

    def test_get_tool_not_found(self, client: TestClient, auth_token: str) -> None:
        """GET /api/v1/tools/{name} for unknown tool returns 404."""
        response = client.get(
            "/api/v1/tools/nonexistent",
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_execute_terminal_tool(self, client: TestClient, auth_token: str) -> None:
        """POST /api/v1/tools/execute terminal command."""
        response = client.post(
            "/api/v1/tools/execute",
            json={"tool": "terminal", "input": {"command": "whoami"}},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
        assert "sentrix-user" in data["output"]["stdout"]

    def test_execute_python_tool(self, client: TestClient, auth_token: str) -> None:
        """POST /api/v1/tools/execute python code."""
        response = client.post(
            "/api/v1/tools/execute",
            json={"tool": "python", "input": {"code": "1+1"}},
            headers={"Authorization": f"Bearer {auth_token}"},
        )
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert data["success"] is True
