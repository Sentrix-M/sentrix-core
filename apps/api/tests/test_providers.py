"""Unit tests for the Sentrix AI Provider Layer.

Covers :class:`BaseProvider`/``ProviderHealth``, the deterministic
:class:`MockProvider`, the :class:`ProviderFactory`, and the kernel
integration helper (``build_kernel_pipeline`` / ``get_kernel_provider``).
No network access is used anywhere.
"""

from __future__ import annotations

import pytest

from app.kernel.context_builder import ContextMessage, ConversationContext
from app.kernel.pipeline import ProviderRegistry
from app.kernel.prompt_builder import DefaultPromptBuilder, Prompt
from app.kernel.router import Capability
from app.providers.base import BaseProvider, ProviderHealth, check_health
from app.providers.factory import DEFAULT_PROVIDER, ProviderFactory
from app.providers.mock import MockProvider

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_prompt(message: str = "Analyze the log file") -> Prompt:
    context = ConversationContext(
        conversation_id="conv-test",
        user_message=ContextMessage(role="user", content=message),
        prior_messages=(),
    )
    return DefaultPromptBuilder().build(
        context=context,
        system="You are a SOC analyst.",
        instruction="Be concise.",
    )


class _StubProvider:
    """Minimal BaseProvider-compatible stub for factory testing."""

    name = "stub"

    def generate(self, prompt: Prompt):  # noqa: ARG002 - stub ignores prompt
        from app.kernel.response_builder import ProviderOutput

        return ProviderOutput(text="stub output", model="stub-model")

    def stream(self, prompt: Prompt) -> list[str]:  # noqa: ARG002 - stub ignores prompt
        raise NotImplementedError

    def health(self) -> ProviderHealth:
        return ProviderHealth(ok=True, message="stub healthy")


# ---------------------------------------------------------------------------
# ProviderHealth
# ---------------------------------------------------------------------------


class TestProviderHealth:
    def test_constructs_with_defaults(self) -> None:
        health = ProviderHealth(ok=True)
        assert health.ok is True
        assert health.message == ""

    def test_equality(self) -> None:
        assert ProviderHealth(ok=True, message="x") == ProviderHealth(ok=True, message="x")
        assert ProviderHealth(ok=True) != ProviderHealth(ok=False)

    def test_repr(self) -> None:
        assert "ok=True" in repr(ProviderHealth(ok=True))


class TestCheckHealth:
    def test_returns_health_when_healthy(self) -> None:
        provider = _StubProvider()
        result = check_health(provider)
        assert result.ok is True
        assert result.message == "stub healthy"

    def test_catches_exceptions(self) -> None:
        class _BrokenProvider(_StubProvider):
            def health(self) -> ProviderHealth:
                raise RuntimeError("boom")

        result = check_health(_BrokenProvider())
        assert result.ok is False
        assert "boom" in result.message


# ---------------------------------------------------------------------------
# MockProvider
# ---------------------------------------------------------------------------


class TestMockProvider:
    def test_implements_base_provider_protocol(self) -> None:
        provider: BaseProvider = MockProvider()
        assert provider.name == "mock"

    def test_generate_returns_normalized_output(self) -> None:
        provider = MockProvider()
        output = provider.generate(_make_prompt())
        assert output.text
        assert output.model == "sentrix-mock-0.1"
        assert output.reasoning
        assert output.metadata["provider"] == "mock"

    def test_generate_is_deterministic(self) -> None:
        provider = MockProvider()
        prompt = _make_prompt("Investigate the beacon pattern on LAB-07")
        first = provider.generate(prompt).text
        second = provider.generate(prompt).text
        assert first == second

    def test_generate_returns_security_analysis_for_beacon(self) -> None:
        provider = MockProvider()
        output = provider.generate(_make_prompt("Beacon on host LAB-07"))
        assert "C2" in output.text
        assert "T1071" in output.text

    def test_generate_returns_log_analysis_for_logs(self) -> None:
        provider = MockProvider()
        output = provider.generate(_make_prompt("Show me Suricata logs"))
        assert "Suricata" in output.text or "log" in output.text.lower()

    def test_generate_returns_default_for_unmatched(self) -> None:
        provider = MockProvider()
        output = provider.generate(_make_prompt("Hello there"))
        assert "Acknowledged" in output.text

    def test_stream_returns_word_chunks(self) -> None:
        provider = MockProvider()
        chunks = provider.stream(_make_prompt("Beacon detected"))
        assert isinstance(chunks, list)
        assert chunks
        assert " ".join(chunks) == provider.generate(_make_prompt("Beacon detected")).text

    def test_health_reports_available(self) -> None:
        provider = MockProvider()
        health = provider.health()
        assert health.ok is True
        assert "available" in health.message.lower()


# ---------------------------------------------------------------------------
# ProviderFactory
# ---------------------------------------------------------------------------


class TestProviderFactory:
    def test_default_provider_is_mock(self) -> None:
        assert DEFAULT_PROVIDER == "mock"
        factory = ProviderFactory()
        provider = factory.create()
        assert isinstance(provider, MockProvider)
        assert provider.name == "mock"

    def test_create_with_explicit_name(self) -> None:
        factory = ProviderFactory()
        provider = factory.create("mock")
        assert isinstance(provider, MockProvider)

    def test_create_unknown_provider_raises(self) -> None:
        factory = ProviderFactory()
        with pytest.raises(KeyError):
            factory.create("openai")

    def test_register_custom_constructor(self) -> None:
        factory = ProviderFactory()
        factory.register("stub", _StubProvider)
        provider = factory.create("stub")
        assert isinstance(provider, _StubProvider)

    def test_register_replaces_existing(self) -> None:
        factory = ProviderFactory()
        original = factory.create("mock")
        factory.register("mock", _StubProvider)
        replaced = factory.create("mock")
        assert isinstance(original, MockProvider)
        assert isinstance(replaced, _StubProvider)

    def test_names(self) -> None:
        factory = ProviderFactory()
        assert "mock" in factory.names()

    def test_contains(self) -> None:
        factory = ProviderFactory()
        assert "mock" in factory
        assert "openai" not in factory


# ---------------------------------------------------------------------------
# Kernel integration
# ---------------------------------------------------------------------------


class TestKernelIntegration:
    def test_build_kernel_pipeline_registers_mock_provider(self) -> None:
        from app.kernel.integration import build_kernel_pipeline

        pipeline = build_kernel_pipeline()
        assert isinstance(pipeline.registry, ProviderRegistry)
        assert "mock" in pipeline.registry.names()

    def test_build_kernel_pipeline_runs_turn(self) -> None:
        from app.kernel.integration import build_kernel_pipeline
        from app.kernel.response_builder import KernelResponse

        pipeline = build_kernel_pipeline()
        response = pipeline.run(
            conversation_id="conv-1",
            message="Beacon detected on endpoint LAB-07",
        )
        assert isinstance(response, KernelResponse)
        assert response.provider == "mock"
        assert response.content

    def test_build_kernel_pipeline_uses_custom_factory(self) -> None:
        from app.kernel.integration import build_kernel_pipeline

        factory = ProviderFactory()
        factory.register("stub", _StubProvider)

        class _StubPipelineProvider(_StubProvider):
            name = "stub"

            def generate(self, prompt: Prompt):  # noqa: ANN401, ARG002 - test stub
                from app.kernel.response_builder import ProviderOutput

                return ProviderOutput(text="stub output", model="stub-model")

        factory.register("stub", _StubPipelineProvider)
        pipeline = build_kernel_pipeline(factory=factory, provider="stub")
        assert "stub" in pipeline.registry.names()
        response = pipeline.run(conversation_id="conv-1", message="Hi")
        assert response.provider == "stub"
        assert response.content == "stub output"

    def test_build_kernel_pipeline_custom_system_prompt(self) -> None:
        from app.kernel.integration import build_kernel_pipeline

        pipeline = build_kernel_pipeline(system_prompt="Custom system prompt")
        response = pipeline.run(conversation_id="conv-1", message="Hello")
        assert response.content

    def test_get_kernel_provider_returns_mock(self) -> None:
        from app.kernel.integration import get_kernel_provider

        provider = get_kernel_provider()
        assert isinstance(provider, MockProvider)

    def test_capability_profile_includes_security(self) -> None:
        from app.kernel.integration import build_kernel_pipeline
        from app.kernel.router import DefaultProviderRouter

        pipeline = build_kernel_pipeline()
        router = pipeline._router  # noqa: SLF001 - testing integration detail
        assert isinstance(router, DefaultProviderRouter)
        profiles = router.profiles
        assert profiles
        assert Capability.SECURITY in profiles[0].capabilities
        assert Capability.GENERAL in profiles[0].capabilities


# ---------------------------------------------------------------------------
# BaseProvider protocol conformance
# ---------------------------------------------------------------------------


class TestBaseProviderProtocol:
    def test_mock_provider_satisfies_base_protocol(self) -> None:
        provider: BaseProvider = MockProvider()
        assert callable(provider.generate)
        assert callable(provider.stream)
        assert callable(provider.health)
