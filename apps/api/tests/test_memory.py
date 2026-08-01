"""Unit tests for the Sentrix Memory Layer.

Covers the memory models, the in-memory stores, the default strategy, and the
:class:`MemoryManager` — including its integration into the kernel pipeline.
Everything is in-memory: no persistence, no vector database, no embeddings.
"""

from __future__ import annotations

import pytest

from app.kernel.context_builder import ConversationContext
from app.kernel.pipeline import KernelPipeline
from app.memory.manager import MemoryManager
from app.memory.models import (
    ConversationMemory,
    LongTermMemory,
    MemoryContext,
    MemoryItem,
    ProjectMemory,
    WorkingMemory,
)
from app.memory.store import InMemoryConversationStore, InMemoryProjectStore
from app.memory.strategy import DefaultMemoryStrategy

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class TestMemoryModels:
    def test_memory_item_defaults(self) -> None:
        item = MemoryItem(content="hello")
        assert item.role == "user"
        assert item.timestamp is None
        assert item.metadata == {}

    def test_memory_item_is_frozen(self) -> None:
        item = MemoryItem(content="hello")
        with pytest.raises(AttributeError):
            item.content = "world"  # type: ignore[misc]

    def test_working_memory(self) -> None:
        working = WorkingMemory(message="scan host", intent="THREAT_HUNT")
        assert working.message == "scan host"
        assert working.intent == "THREAT_HUNT"
        assert working.entities == ()

    def test_conversation_memory(self) -> None:
        conv = ConversationMemory(
            conversation_id="conv-1",
            history=(MemoryItem(content="hi"),),
        )
        assert conv.conversation_id == "conv-1"
        assert len(conv.history) == 1

    def test_project_memory(self) -> None:
        project = ProjectMemory(project_id="p1", context={"env": "prod"})
        assert project.project_id == "p1"
        assert project.context == {"env": "prod"}

    def test_long_term_memory_placeholder(self) -> None:
        lt = LongTermMemory()
        assert lt.summary == ""
        assert lt.tags == ()
        lt2 = LongTermMemory(summary="knowledge", tags=("mitre",))
        assert lt2.summary == "knowledge"
        assert lt2.tags == ("mitre",)

    def test_memory_context_aggregates_tiers(self) -> None:
        context = MemoryContext(
            working=WorkingMemory(message="m"),
            conversation=ConversationMemory(conversation_id="c"),
        )
        assert context.working.message == "m"
        assert context.conversation.conversation_id == "c"
        assert context.project.project_id == "default"
        assert context.long_term.summary == ""


# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------


class TestInMemoryConversationStore:
    def test_append_and_get_history(self) -> None:
        store = InMemoryConversationStore(history_limit=10)
        store.append("c1", MemoryItem(content="first"))
        store.append("c1", MemoryItem(content="second", role="assistant"))
        conv = store.get_history("c1")
        assert conv.conversation_id == "c1"
        assert [item.content for item in conv.history] == ["first", "second"]
        assert conv.history[1].role == "assistant"

    def test_unknown_conversation_returns_empty(self) -> None:
        store = InMemoryConversationStore()
        conv = store.get_history("missing")
        assert conv.history == ()

    def test_history_respects_limit(self) -> None:
        store = InMemoryConversationStore(history_limit=2)
        for i in range(5):
            store.append("c1", MemoryItem(content=f"m{i}"))
        conv = store.get_history("c1")
        assert [item.content for item in conv.history] == ["m3", "m4"]

    def test_get_history_limit_argument(self) -> None:
        store = InMemoryConversationStore(history_limit=20)
        for i in range(5):
            store.append("c1", MemoryItem(content=f"m{i}"))
        conv = store.get_history("c1", limit=2)
        assert [item.content for item in conv.history] == ["m3", "m4"]

    def test_clear_by_conversation(self) -> None:
        store = InMemoryConversationStore()
        store.append("c1", MemoryItem(content="a"))
        store.append("c2", MemoryItem(content="b"))
        store.clear("c1")
        assert store.get_history("c1").history == ()
        assert len(store.get_history("c2").history) == 1

    def test_clear_all(self) -> None:
        store = InMemoryConversationStore()
        store.append("c1", MemoryItem(content="a"))
        store.append("c2", MemoryItem(content="b"))
        store.clear()
        assert store.get_history("c1").history == ()
        assert store.get_history("c2").history == ()

    def test_history_limit_property(self) -> None:
        store = InMemoryConversationStore(history_limit=7)
        assert store.history_limit == 7


class TestInMemoryProjectStore:
    def test_get_unknown_project_returns_empty(self) -> None:
        store = InMemoryProjectStore()
        project = store.get("missing")
        assert project.project_id == "missing"
        assert project.context == {}

    def test_set_and_get_context(self) -> None:
        store = InMemoryProjectStore()
        store.set_context("p1", "env", "prod")
        store.set_context("p1", "region", "eu-west-1")
        project = store.get("p1")
        assert project.context == {"env": "prod", "region": "eu-west-1"}

    def test_set_overwrites_existing_key(self) -> None:
        store = InMemoryProjectStore()
        store.set_context("p1", "env", "prod")
        store.set_context("p1", "env", "staging")
        assert store.get("p1").context == {"env": "staging"}

    def test_clear_by_project(self) -> None:
        store = InMemoryProjectStore()
        store.set_context("p1", "env", "prod")
        store.set_context("p2", "env", "staging")
        store.clear("p1")
        assert store.get("p1").context == {}
        assert store.get("p2").context == {"env": "staging"}

    def test_clear_all(self) -> None:
        store = InMemoryProjectStore()
        store.set_context("p1", "env", "prod")
        store.clear()
        assert store.get("p1").context == {}


# ---------------------------------------------------------------------------
# Strategy
# ---------------------------------------------------------------------------


class TestDefaultMemoryStrategy:
    def test_compact_returns_same_context(self) -> None:
        strategy = DefaultMemoryStrategy()
        context = MemoryContext(
            working=WorkingMemory(message="m"),
            conversation=ConversationMemory(conversation_id="c"),
        )
        assert strategy.compact(context) is context


# ---------------------------------------------------------------------------
# MemoryManager
# ---------------------------------------------------------------------------


class TestMemoryManager:
    def test_implements_context_provider(self) -> None:
        manager = MemoryManager()
        context = manager.get_context(conversation_id="conv-1", message="Hello")
        assert isinstance(context, ConversationContext)
        assert context.conversation_id == "conv-1"
        assert context.user_message.content == "Hello"

    def test_first_turn_has_no_prior_messages(self) -> None:
        manager = MemoryManager()
        context = manager.get_context(conversation_id="conv-1", message="Hello")
        assert context.prior_messages == ()

    def test_second_turn_sees_first_as_history(self) -> None:
        manager = MemoryManager()
        manager.get_context(conversation_id="conv-1", message="Hello")
        context = manager.get_context(conversation_id="conv-1", message="Analyze")
        assert [m.content for m in context.prior_messages] == ["Hello"]

    def test_history_includes_roles(self) -> None:
        manager = MemoryManager()
        manager.get_context(conversation_id="conv-1", message="Hello")
        context = manager.get_context(conversation_id="conv-1", message="Analyze")
        assert context.prior_messages[0].role == "user"
        assert context.prior_messages[0].content == "Hello"

    def test_working_memory_is_current_request(self) -> None:
        # Working memory is internal to the manager; verify through the
        # conversation context it produces (the current user message).
        manager = MemoryManager()
        context = manager.get_context(conversation_id="conv-1", message="scan now")
        assert context.user_message.content == "scan now"
        assert context.user_message.role == "user"

    def test_project_memory_resolved_by_proj_prefix(self) -> None:
        manager = MemoryManager()
        manager.project_store.set_context("acme", "env", "prod")
        context = manager.get_context(conversation_id="proj-acme", message="hi")
        assert context.conversation_id == "proj-acme"

    def test_default_project_fallback(self) -> None:
        manager = MemoryManager()
        context = manager.get_context(conversation_id="conv-1", message="hi")
        assert context.conversation_id == "conv-1"

    def test_long_term_is_placeholder(self) -> None:
        manager = MemoryManager()
        memory_context = manager._resolve_long_term()
        assert memory_context == LongTermMemory()

    def test_history_limit_respected(self) -> None:
        manager = MemoryManager(history_limit=2)
        for i in range(5):
            manager.get_context(conversation_id="conv-1", message=f"m{i}")
        context = manager.get_context(conversation_id="conv-1", message="last")
        assert len(context.prior_messages) == 2
        assert [m.content for m in context.prior_messages] == ["m3", "m4"]

    def test_clear_resets_conversation(self) -> None:
        manager = MemoryManager()
        manager.get_context(conversation_id="conv-1", message="Hello")
        manager.clear(conversation_id="conv-1")
        context = manager.get_context(conversation_id="conv-1", message="Again")
        assert context.prior_messages == ()

    def test_clear_all_resets_all(self) -> None:
        manager = MemoryManager()
        manager.get_context(conversation_id="conv-1", message="Hello")
        manager.get_context(conversation_id="conv-2", message="Hi")
        manager.clear()
        assert manager.get_context(conversation_id="conv-1", message="x").prior_messages == ()
        assert manager.get_context(conversation_id="conv-2", message="y").prior_messages == ()

    def test_custom_strategy_applied(self) -> None:
        calls: list[MemoryContext] = []

        class _RecordingStrategy(DefaultMemoryStrategy):
            def compact(self, context: MemoryContext) -> MemoryContext:
                calls.append(context)
                return super().compact(context)

        manager = MemoryManager(strategy=_RecordingStrategy())
        context = manager.get_context(conversation_id="conv-1", message="hi")
        assert isinstance(context, ConversationContext)
        assert len(calls) == 1
        assert calls[0].working.message == "hi"


# ---------------------------------------------------------------------------
# Kernel integration
# ---------------------------------------------------------------------------


class TestMemoryKernelIntegration:
    def test_build_kernel_pipeline_accepts_memory_manager(self) -> None:
        from app.kernel.integration import build_kernel_pipeline

        manager = MemoryManager(history_limit=5)
        pipeline = build_kernel_pipeline(memory_manager=manager)
        assert isinstance(pipeline, KernelPipeline)

    def test_pipeline_uses_memory_manager_context(self) -> None:
        from app.kernel.integration import build_kernel_pipeline

        manager = MemoryManager(history_limit=5)
        pipeline = build_kernel_pipeline(memory_manager=manager)
        pipeline.run(conversation_id="conv-1", message="First")
        response = pipeline.run(conversation_id="conv-1", message="Second")
        assert response.provider == "mock"
        assert response.content

    def test_memory_manager_builds_history_across_turns(self) -> None:
        from app.kernel.integration import build_kernel_pipeline

        manager = MemoryManager(history_limit=10)
        pipeline = build_kernel_pipeline(memory_manager=manager)
        pipeline.run(conversation_id="conv-mem", message="turn one")
        pipeline.run(conversation_id="conv-mem", message="turn two")
        context = manager.get_context(conversation_id="conv-mem", message="turn three")
        assert [m.content for m in context.prior_messages] == [
            "turn one",
            "turn two",
        ]
