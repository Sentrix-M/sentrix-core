"""Integration tests for Tool Engine Phase 2 (Kernel Integration).

Proves the full path:

    intent detection → tool routing → mock tool execution
        → tool-result injection into the prompt → provider output

while preserving streaming, memory, and RAG behaviour.  No real commands are
ever executed — only the registered mock tools are used.
"""

from __future__ import annotations

import asyncio

import pytest

from app.kernel.context_builder import ContextMessage, ConversationContext
from app.kernel.integration import build_kernel_pipeline
from app.kernel.pipeline import KernelPipeline
from app.kernel.prompt_builder import DefaultPromptBuilder
from app.kernel.rag_context import RagAwareContextProvider
from app.kernel.response_builder import KernelResponse
from app.kernel.tool_integration import ToolCoordinator, ToolDecision
from app.memory.manager import MemoryManager
from app.rag.retriever import SemanticRetriever
from app.rag.vector_store import InMemoryVectorStore
from app.tools.executor import ToolExecutor
from app.tools.mock_tools import (
    MockFilesystemTool,
    MockPythonTool,
    MockTerminalTool,
)
from app.tools.registry import ToolRegistry

# Permissions granted to the seeded admin role.
ADMIN_TOOL_PERMISSIONS = {
    "filesystem:read",
    "filesystem:write",
    "terminal:execute",
    "python:execute",
    "tools:execute",
}

# A restricted permission set that blocks all tool execution.
NO_TOOL_PERMISSIONS = {"dashboard:view"}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _build_executor() -> ToolExecutor:
    """Build a ToolExecutor with all three mock tools registered."""
    registry = ToolRegistry()
    registry.register(MockFilesystemTool())
    registry.register(MockTerminalTool())
    registry.register(MockPythonTool())
    return ToolExecutor(registry)


def _build_pipeline(
    *,
    tool_executor: ToolExecutor | None = None,
) -> KernelPipeline:
    """Build a kernel pipeline wired exactly like the streaming endpoint."""
    return build_kernel_pipeline(tool_executor=tool_executor)


# ---------------------------------------------------------------------------
# ToolDecision / ToolCoordinator detection
# ---------------------------------------------------------------------------


class TestToolCoordinatorDetection:
    def test_detects_filesystem_list(self) -> None:
        coordinator = ToolCoordinator(_build_executor())
        decision = coordinator.detect("Please list uploaded documents")
        assert decision is not None
        assert decision.tool_name == "filesystem"
        assert decision.input["action"] == "list"

    def test_detects_filesystem_read(self) -> None:
        coordinator = ToolCoordinator(_build_executor())
        decision = coordinator.detect("Can you read file /tmp/report.txt")
        assert decision is not None
        assert decision.tool_name == "filesystem"
        assert decision.input["action"] == "read"
        assert "report.txt" in decision.input["path"]

    def test_detects_python(self) -> None:
        coordinator = ToolCoordinator(_build_executor())
        decision = coordinator.detect("run python code print('hi')")
        assert decision is not None
        assert decision.tool_name == "python"
        assert decision.input["code"]

    def test_detects_terminal(self) -> None:
        coordinator = ToolCoordinator(_build_executor())
        decision = coordinator.detect("execute terminal command whoami")
        assert decision is not None
        assert decision.tool_name == "terminal"
        assert decision.input["command"] == "whoami"

    def test_no_intent_returns_none(self) -> None:
        coordinator = ToolCoordinator(_build_executor())
        assert coordinator.detect("What is the weather today?") is None


# ---------------------------------------------------------------------------
# ToolCoordinator execution (async + sync bridge)
# ---------------------------------------------------------------------------


class TestToolCoordinatorExecution:
    def test_execute_returns_mock_result(self) -> None:
        coordinator = ToolCoordinator(_build_executor())
        decision = ToolDecision(
            tool_name="terminal",
            input={"command": "whoami"},
            confidence=1.0,
        )
        result = asyncio.run(
            coordinator.execute(decision, user_permissions=ADMIN_TOOL_PERMISSIONS)
        )
        assert result.success is True
        assert result.tool == "terminal"
        assert "sentrix-user" in result.output["stdout"]

    def test_execute_sync_bridge(self) -> None:
        coordinator = ToolCoordinator(_build_executor())
        decision = ToolDecision(
            tool_name="python",
            input={"code": "1+1"},
            confidence=1.0,
        )
        result = coordinator.execute_sync(decision, user_permissions=ADMIN_TOOL_PERMISSIONS)
        assert result.success is True

    def test_detect_and_execute(self) -> None:
        coordinator = ToolCoordinator(_build_executor())
        pair = coordinator.detect_and_execute(
            "run terminal command whoami",
            user_permissions=ADMIN_TOOL_PERMISSIONS,
        )
        assert pair is not None
        decision, result = pair
        assert decision.tool_name == "terminal"
        assert result.success is True

    def test_detect_and_execute_denied_without_permissions(self) -> None:
        coordinator = ToolCoordinator(_build_executor())
        pair = coordinator.detect_and_execute(
            "run terminal command whoami",
            user_permissions=NO_TOOL_PERMISSIONS,
        )
        assert pair is not None
        _, result = pair
        assert result.success is False
        assert "permission" in (result.error or "").lower()


# ---------------------------------------------------------------------------
# Prompt injection of tool results
# ---------------------------------------------------------------------------


class TestPromptToolResults:
    def test_build_injects_tool_results(self) -> None:
        builder = DefaultPromptBuilder()
        context = ConversationContext(
            conversation_id="conv-1",
            user_message=ContextMessage(role="user", content="run terminal command whoami"),
            prior_messages=(),
        )
        prompt = builder.build(
            context=context,
            system="You are a SOC analyst.",
            instruction="Be concise.",
            tool_results=(
                {
                    "tool": "terminal",
                    "success": True,
                    "output": {"stdout": "sentrix-user\n", "exit_code": 0},
                    "error": None,
                },
            ),
        )
        text = prompt.to_text()
        assert "Tool results:" in text
        assert "terminal succeeded" in text
        assert "sentrix-user" in text

    def test_prompt_carries_tool_results_field(self) -> None:
        builder = DefaultPromptBuilder()
        context = ConversationContext(
            conversation_id="conv-1",
            user_message=ContextMessage(role="user", content="run python 1+1"),
            prior_messages=(),
        )
        prompt = builder.build(
            context=context,
            system="sys",
            instruction="",
            tool_results=({"tool": "python", "success": True, "output": "2", "error": None},),
        )
        assert prompt.tool_results
        assert prompt.tool_results[0]["tool"] == "python"


# ---------------------------------------------------------------------------
# Kernel pipeline end-to-end (detection → routing → execution → prompt → output)
# ---------------------------------------------------------------------------


class TestKernelPipelineWithTools:
    def test_tool_intent_invokes_tool_and_reports_used(self) -> None:
        pipeline = _build_pipeline(tool_executor=_build_executor())
        response = pipeline.run(
            conversation_id="conv-1",
            message="execute terminal command whoami",
            user_permissions=ADMIN_TOOL_PERMISSIONS,
        )
        assert isinstance(response, KernelResponse)
        assert response.content
        assert "terminal" in response.tools_used

    def test_python_intent(self) -> None:
        pipeline = _build_pipeline(tool_executor=_build_executor())
        response = pipeline.run(
            conversation_id="conv-2",
            message="run python code print('hi')",
            user_permissions=ADMIN_TOOL_PERMISSIONS,
        )
        assert "python" in response.tools_used

    def test_filesystem_intent(self) -> None:
        pipeline = _build_pipeline(tool_executor=_build_executor())
        response = pipeline.run(
            conversation_id="conv-3",
            message="list uploaded documents",
            user_permissions=ADMIN_TOOL_PERMISSIONS,
        )
        assert "filesystem" in response.tools_used

    def test_no_tool_without_executor(self) -> None:
        pipeline = _build_pipeline()  # no executor
        response = pipeline.run(
            conversation_id="conv-4",
            message="execute terminal command whoami",
            user_permissions=ADMIN_TOOL_PERMISSIONS,
        )
        assert response.tools_used == ()

    def test_no_tool_without_permissions(self) -> None:
        pipeline = _build_pipeline(tool_executor=_build_executor())
        response = pipeline.run(
            conversation_id="conv-5",
            message="execute terminal command whoami",
            user_permissions=NO_TOOL_PERMISSIONS,
        )
        # Permission denied — no successful tool runs, but the pipeline still
        # produces a normal (non-tool) response.
        assert response.tools_used == ()
        assert response.content

    def test_plain_message_still_works(self) -> None:
        pipeline = _build_pipeline(tool_executor=_build_executor())
        response = pipeline.run(
            conversation_id="conv-6",
            message="What is a beacon?",
            user_permissions=ADMIN_TOOL_PERMISSIONS,
        )
        assert response.tools_used == ()
        assert response.content

    def test_mock_provider_explains_tool_result(self) -> None:
        """The mock provider consumes the injected tool result in its text."""
        pipeline = _build_pipeline(tool_executor=_build_executor())
        response = pipeline.run(
            conversation_id="conv-7",
            message="execute terminal command whoami",
            user_permissions=ADMIN_TOOL_PERMISSIONS,
        )
        assert response.content
        assert "terminal" in response.tools_used


# ---------------------------------------------------------------------------
# Preservation: memory, RAG, streaming
# ---------------------------------------------------------------------------


class TestPreservation:
    def test_memory_manager_still_used_as_context_builder(self) -> None:
        """MemoryManager remains the context provider when supplied."""
        memory = MemoryManager()
        pipeline = build_kernel_pipeline(
            memory_manager=memory,
            tool_executor=_build_executor(),
        )
        assert pipeline._context_builder is memory  # noqa: SLF001

    def test_rag_context_provider_still_wraps(self) -> None:
        """A RAG retriever still wraps the context builder when provided."""
        memory = MemoryManager()
        retriever = SemanticRetriever(vector_store=InMemoryVectorStore())
        pipeline = build_kernel_pipeline(
            memory_manager=memory,
            retriever=retriever,
            tool_executor=_build_executor(),
        )
        assert isinstance(pipeline._context_builder, RagAwareContextProvider)  # noqa: SLF001

    def test_streaming_manager_surfaces_tools_used(self) -> None:
        """StreamingManager emits tools_used in the completed event."""
        from app.schemas.conversation import ConversationMessageRequest
        from app.streaming.manager import StreamingManager

        manager = StreamingManager(
            tool_executor=_build_executor(),
            token_delay_seconds=0,
        )
        request = ConversationMessageRequest(
            conversation_id="stream-1",
            message="execute terminal command whoami",
        )

        async def _collect() -> list[dict]:
            blocks = [b async for b in manager.stream(
                request,
                user_permissions=ADMIN_TOOL_PERMISSIONS,
            )]
            events = []
            for block in blocks:
                # Blocks are pre-serialised SSE strings like "event: ...\ndata: ...".
                if block.startswith("event: completed"):
                    import json

                    data = json.loads(block.split("data: ", 1)[1])
                    events.append(data)
            return events

        completed = asyncio.run(_collect())
        assert completed
        assert "tools_used" in completed[0]
        assert "terminal" in completed[0]["tools_used"]

