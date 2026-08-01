"""Unit tests for the Sentrix Kernel foundation.

Covers the router, context builder, prompt builder, response builder, and the
pipeline orchestration. No real AI provider is used — a stub adapter stands in
for provider I/O.
"""

from __future__ import annotations

import pytest

from app.kernel.context_builder import (
    ContextMessage,
    ConversationContext,
    InMemoryContextProvider,
)
from app.kernel.pipeline import (
    KernelPipeline,
    ProviderNotConfiguredError,
    ProviderRegistry,
)
from app.kernel.prompt_builder import DefaultPromptBuilder, Prompt, build_prompt
from app.kernel.response_builder import (
    DefaultResponseBuilder,
    KernelResponse,
    ProviderOutput,
    ResponseBuildError,
)
from app.kernel.router import (
    Capability,
    DefaultProviderRouter,
    KernelRequest,
    NoProviderAvailableError,
    ProviderProfile,
    Route,
)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class TestDefaultProviderRouter:
    def test_routes_to_eligible_highest_priority(self) -> None:
        router = DefaultProviderRouter(
            [
                ProviderProfile("general", (Capability.GENERAL,), priority=1),
                ProviderProfile(
                    "security",
                    (Capability.GENERAL, Capability.SECURITY),
                    priority=5,
                ),
            ]
        )
        request = KernelRequest(
            prompt=Prompt(system="", instruction="", context=_empty_context(), messages=()),
            capabilities=(Capability.SECURITY,),
        )
        assert router.route(request) == Route("security", (Capability.GENERAL, Capability.SECURITY))

    def test_preferred_provider_wins(self) -> None:
        router = DefaultProviderRouter(
            [
                ProviderProfile("general", (Capability.GENERAL,), priority=1),
                ProviderProfile(
                    "security",
                    (Capability.GENERAL, Capability.SECURITY),
                    priority=5,
                ),
            ]
        )
        request = KernelRequest(
            prompt=Prompt(system="", instruction="", context=_empty_context(), messages=()),
            preferred_provider="general",
        )
        assert router.route(request) == Route("general", (Capability.GENERAL,))

    def test_preferred_unknown_raises(self) -> None:
        router = DefaultProviderRouter([ProviderProfile("general", (Capability.GENERAL,))])
        request = KernelRequest(
            prompt=Prompt(system="", instruction="", context=_empty_context(), messages=()),
            preferred_provider="missing",
        )
        with pytest.raises(NoProviderAvailableError):
            router.route(request)

    def test_no_eligible_raises(self) -> None:
        router = DefaultProviderRouter([ProviderProfile("general", (Capability.GENERAL,))])
        request = KernelRequest(
            prompt=Prompt(system="", instruction="", context=_empty_context(), messages=()),
            capabilities=(Capability.SECURITY,),
        )
        with pytest.raises(NoProviderAvailableError):
            router.route(request)

    def test_general_fallback(self) -> None:
        router = DefaultProviderRouter([ProviderProfile("general", (Capability.GENERAL,))])
        request = KernelRequest(
            prompt=Prompt(system="", instruction="", context=_empty_context(), messages=())
        )
        assert router.route(request) == Route("general", (Capability.GENERAL,))

    def test_register_replaces_profile(self) -> None:
        router = DefaultProviderRouter()
        router.register(ProviderProfile("a", (Capability.GENERAL,), priority=1))
        router.register(ProviderProfile("a", (Capability.SECURITY,), priority=2))
        assert len(router.profiles) == 1
        assert router.profiles[0].priority == 2


# ---------------------------------------------------------------------------
# Context builder
# ---------------------------------------------------------------------------


class TestInMemoryContextProvider:
    def test_first_turn_has_no_prior_messages(self) -> None:
        provider = InMemoryContextProvider()
        context = provider.get_context(
            conversation_id="conv-1",
            message="Hello",
        )
        assert context.conversation_id == "conv-1"
        assert context.user_message.role == "user"
        assert context.user_message.content == "Hello"
        assert context.prior_messages == ()

    def test_second_turn_sees_first_as_history(self) -> None:
        provider = InMemoryContextProvider()
        provider.get_context(conversation_id="conv-1", message="Hello")
        context = provider.get_context(conversation_id="conv-1", message="Analyze")
        assert [m.content for m in context.prior_messages] == ["Hello"]

    def test_history_limit(self) -> None:
        provider = InMemoryContextProvider(history_limit=2)
        for i in range(5):
            provider.get_context(conversation_id="conv-1", message=f"m{i}")
        context = provider.get_context(conversation_id="conv-1", message="last")
        assert len(context.prior_messages) == 2
        assert [m.content for m in context.prior_messages] == ["m3", "m4"]

    def test_clear_resets_history(self) -> None:
        provider = InMemoryContextProvider()
        provider.get_context(conversation_id="conv-1", message="Hello")
        provider.clear()
        context = provider.get_context(conversation_id="conv-1", message="Again")
        assert context.prior_messages == ()


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


class TestDefaultPromptBuilder:
    def test_build_contains_system_and_messages(self) -> None:
        builder = DefaultPromptBuilder()
        context = _empty_context(user_message="What is this?")
        prompt = builder.build(
            context=context,
            system="You are a SOC analyst.",
            instruction="Answer concisely.",
        )
        assert prompt.system == "You are a SOC analyst."
        assert prompt.instruction == "Answer concisely."
        assert [m.content for m in prompt.messages] == ["What is this?"]

    def test_to_text_serializes_prompt(self) -> None:
        builder = DefaultPromptBuilder()
        context = _empty_context(user_message="Hi")
        prompt = builder.build(
            context=context,
            system="System.",
            instruction="Instruct.",
        )
        text = prompt.to_text()
        assert "System." in text
        assert "User: Hi" in text
        assert "Instruction: Instruct." in text

    def test_build_prompt_helper_defaults(self) -> None:
        prompt = build_prompt(
            context=_empty_context(user_message="Help"),
            system="sys",
            instruction="instr",
        )
        assert isinstance(prompt, Prompt)
        assert prompt.system == "sys"

    def test_build_prompt_helper_requires_builder(self) -> None:
        with pytest.raises(ValueError):
            build_prompt(
                context=_empty_context(),
                system="sys",
                instruction="instr",
                builders=[],
            )


# ---------------------------------------------------------------------------
# Response builder
# ---------------------------------------------------------------------------


class TestDefaultResponseBuilder:
    def test_build_maps_output_fields(self) -> None:
        builder = DefaultResponseBuilder()
        output = ProviderOutput(
            text="  Analysis complete.  ",
            reasoning=("step1",),
            evidence=("ev1",),
            sources=("src1",),
            tools_used=("nmap",),
            model="mock-1",
            metadata={"latency_ms": 42},
        )
        response = builder.build(provider="security", output=output)
        assert response.provider == "security"
        assert response.content == "Analysis complete."
        assert response.reasoning == ("step1",)
        assert response.evidence == ("ev1",)
        assert response.sources == ("src1",)
        assert response.tools_used == ("nmap",)
        assert response.model == "mock-1"
        assert response.metadata == {"latency_ms": 42}

    def test_build_empty_text_raises(self) -> None:
        builder = DefaultResponseBuilder()
        with pytest.raises(ResponseBuildError):
            builder.build(provider="p", output=ProviderOutput(text="   "))


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class _StubProviderClient:
    """Provider adapter stub that echoes the prompt as its output."""

    def __init__(self, text: str = "stub response", name: str = "stub") -> None:
        self.name = name
        self._text = text
        self.last_prompt: Prompt | None = None

    def generate(self, prompt: Prompt) -> ProviderOutput:
        self.last_prompt = prompt
        return ProviderOutput(
            text=self._text,
            model="stub-model",
            reasoning=(f"prompt chars: {len(prompt.to_text())}",),
        )


def _make_pipeline(**overrides) -> KernelPipeline:
    context_provider = overrides.get("context_provider") or InMemoryContextProvider()
    router = overrides.get("router") or DefaultProviderRouter(
        [ProviderProfile("stub", (Capability.GENERAL,), priority=1)]
    )
    registry = overrides.get("registry") or ProviderRegistry()
    client = overrides.get("client") or _StubProviderClient()
    registry.register(client)
    return KernelPipeline(
        context_builder=context_provider,
        router=router,
        prompt_builder=DefaultPromptBuilder(),
        response_builder=DefaultResponseBuilder(),
        registry=registry,
        system_prompt="You are Sentrix.",
    )


class TestKernelPipeline:
    def test_run_returns_kernel_response(self) -> None:
        pipeline = _make_pipeline()
        response = pipeline.run(
            conversation_id="conv-1",
            message="Analyze this log.",
        )
        assert isinstance(response, KernelResponse)
        assert response.provider == "stub"
        assert response.content == "stub response"
        assert response.model == "stub-model"
        assert response.reasoning

    def test_run_uses_preferred_provider(self) -> None:
        preferred = _StubProviderClient(text="preferred", name="preferred")
        registry = ProviderRegistry()
        registry.register(preferred)
        router = DefaultProviderRouter(
            [
                ProviderProfile("stub", (Capability.GENERAL,), priority=1),
                ProviderProfile("preferred", (Capability.GENERAL,), priority=0),
            ]
        )
        pipeline = _make_pipeline(registry=registry, client=preferred, router=router)
        response = pipeline.run(
            conversation_id="conv-1",
            message="Hello",
            preferred_provider="preferred",
        )
        assert response.provider == "preferred"
        assert response.content == "preferred"

    def test_run_missing_provider_raises(self) -> None:
        registry = ProviderRegistry()  # no clients
        router = DefaultProviderRouter([ProviderProfile("ghost", (Capability.GENERAL,))])
        pipeline = _make_pipeline(registry=registry, router=router)
        with pytest.raises(ProviderNotConfiguredError):
            pipeline.run(conversation_id="conv-1", message="Hi")

    def test_run_provider_receives_built_prompt(self) -> None:
        client = _StubProviderClient()
        pipeline = _make_pipeline(client=client)
        pipeline.run(
            conversation_id="conv-1",
            message="Scan the endpoint.",
            instruction="Use caution.",
        )
        assert client.last_prompt is not None
        assert client.last_prompt.instruction == "Use caution."
        assert "Scan the endpoint." in client.last_prompt.to_text()

    def test_run_no_provider_available_raises(self) -> None:
        router = DefaultProviderRouter()  # no profiles
        pipeline = _make_pipeline(router=router)
        with pytest.raises(NoProviderAvailableError):
            pipeline.run(conversation_id="conv-1", message="Hi")

    def test_registry_len_and_names(self) -> None:
        registry = ProviderRegistry()
        assert len(registry) == 0
        registry.register(_StubProviderClient())
        assert len(registry) == 1
        assert registry.names() == ("stub",)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_context(user_message: str = "") -> ConversationContext:
    return ConversationContext(
        conversation_id="conv-test",
        user_message=ContextMessage(role="user", content=user_message),
        prior_messages=(),
    )
