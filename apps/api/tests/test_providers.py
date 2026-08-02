"""Unit tests for the Sentrix AI Provider Layer.

Covers :class:`BaseProvider`/``ProviderHealth``, the deterministic
:class:`MockProvider`, the :class:`ProviderFactory`, the cloud
:class:`GeminiProvider`, and the kernel integration helper
(``build_kernel_pipeline`` / ``get_kernel_provider``).
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
from app.providers.gemini import (
    GeminiError,
    GeminiNotConfiguredError,
    GeminiProvider,
)
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


# ---------------------------------------------------------------------------
# GeminiProvider
# ---------------------------------------------------------------------------


class _FakeGeminiPart:
    """Stand-in for ``google.genai.types.Part``."""

    def __init__(self, text: str) -> None:
        self.text = text


class _FakeGeminiResponse:
    """Stand-in for ``google.genai.types.GenerateContentResponse``."""

    def __init__(self, text: str) -> None:
        self._text = text

    @property
    def text(self) -> str | None:
        return self._text

    @property
    def parts(self) -> list[_FakeGeminiPart]:
        return [_FakeGeminiPart(self._text)] if self._text else []


class _FakeGeminiModels:
    """Stub for ``client.models`` that records calls."""

    def __init__(self, *, response_text: str, stream_chunks: list[str] | None = None) -> None:
        self.response_text = response_text
        self.stream_chunks = stream_chunks or []
        self.generated_calls: list[tuple[str, list[dict[str, str]]]] = []
        self.stream_calls: list[tuple[str, list[dict[str, str]]]] = []

    def generate_content(self, model: str, contents: list[dict[str, str]]):
        self.generated_calls.append((model, contents))
        return _FakeGeminiResponse(self.response_text)

    def generate_content_stream(self, model: str, contents: list[dict[str, str]]):
        self.stream_calls.append((model, contents))
        return [
            _FakeGeminiResponse(chunk)
            for chunk in self.stream_chunks
            if chunk
        ]


class _FakeGeminiClient:
    """Stand-in for ``google.genai.Client``."""

    def __init__(self, *, response_text: str = "", stream_chunks: list[str] | None = None) -> None:
        self.models = _FakeGeminiModels(
            response_text=response_text,
            stream_chunks=stream_chunks,
        )


class TestGeminiProvider:
    def test_implements_base_provider_protocol(self) -> None:
        provider: BaseProvider = GeminiProvider(
            api_key="test-key",
            client_factory=lambda: None,  # type: ignore[return-value]
        )
        assert provider.name == "gemini"

    def test_raises_when_key_missing(self) -> None:
        with pytest.raises(GeminiNotConfiguredError):
            GeminiProvider(api_key="")

    def test_raises_when_key_whitespace(self) -> None:
        with pytest.raises(GeminiNotConfiguredError):
            GeminiProvider(api_key="   ")

    def test_generate_returns_normalized_output(self) -> None:
        fake = _FakeGeminiClient(response_text="Beacon detected on LAB-07.")
        provider = GeminiProvider(api_key="test-key", client_factory=lambda: fake)
        output = provider.generate(_make_prompt("Investigate the beacon"))
        assert output.text == "Beacon detected on LAB-07."
        assert output.model == "gemini-2.0-flash"
        assert output.metadata["provider"] == "gemini"
        assert output.metadata["mode"] == "cloud"

    def test_generate_passes_model_and_contents(self) -> None:
        fake = _FakeGeminiClient(response_text="ok")
        provider = GeminiProvider(api_key="test-key", client_factory=lambda: fake)
        prompt = _make_prompt("Analyze the log file")
        provider.generate(prompt)
        assert fake.models.generated_calls
        model, contents = fake.models.generated_calls[0]
        assert model == "gemini-2.0-flash"
        assert isinstance(contents, list)
        assert contents

    def test_generate_ranks_parts_with_system(self) -> None:
        fake = _FakeGeminiClient(response_text="ok")
        provider = GeminiProvider(api_key="test-key", client_factory=lambda: fake)
        provider.generate(_make_prompt("Analyze the log file"))
        parts = fake.models.generated_calls[0][1]
        assert parts[0]["role"] == "system"
        assert parts[0]["text"] == "You are a SOC analyst."

    def test_generate_raises_on_empty_response(self) -> None:
        fake = _FakeGeminiClient(response_text="")
        provider = GeminiProvider(api_key="test-key", client_factory=lambda: fake)
        with pytest.raises(GeminiError):
            provider.generate(_make_prompt("Hello"))

    def test_generate_normalizes_sdk_error(self) -> None:
        class _ExplodingModels(_FakeGeminiModels):
            def __init__(self) -> None:
                super().__init__(response_text="")

            def generate_content(self, model: str, contents: list[dict[str, str]]):  # noqa: ARG002
                raise RuntimeError("boom")

        fake = _FakeGeminiClient(response_text="")
        fake.models = _ExplodingModels()
        provider = GeminiProvider(api_key="test-key", client_factory=lambda: fake)
        with pytest.raises(GeminiError):
            provider.generate(_make_prompt("Hello"))

    def test_stream_returns_word_chunks(self) -> None:
        fake = _FakeGeminiClient(
            stream_chunks=["Gemini", " streams", " words"],
            response_text="Gemini streams words",
        )
        provider = GeminiProvider(api_key="test-key", client_factory=lambda: fake)
        chunks = provider.stream(_make_prompt("Beacon detected"))
        assert isinstance(chunks, list)
        assert chunks
        assert " ".join(chunks) == "Gemini streams words"

    def test_stream_joins_fragments(self) -> None:
        fake = _FakeGeminiClient(
            stream_chunks=["Hello", " world", "!"],
            response_text="Hello world!",
        )
        provider = GeminiProvider(api_key="test-key", client_factory=lambda: fake)
        assert " ".join(provider.stream(_make_prompt("Hi"))) == "Hello world!"

    def test_stream_raises_when_empty(self) -> None:
        fake = _FakeGeminiClient(stream_chunks=[], response_text="")
        provider = GeminiProvider(api_key="test-key", client_factory=lambda: fake)
        with pytest.raises(GeminiError):
            provider.stream(_make_prompt("Hi"))

    def test_health_false_when_key_missing(self) -> None:
        # The constructor raises for an empty key; bypass it via __new__ to
        # test the health() path directly.
        provider = GeminiProvider.__new__(GeminiProvider)
        provider.api_key = ""
        provider._client = None
        provider._client_factory = lambda: _FakeGeminiClient()
        provider.model = "gemini-2.0-flash"
        health = provider.health()
        assert health.ok is False
        assert "not configured" in health.message.lower()

    def test_health_true_when_configured(self) -> None:
        provider = GeminiProvider(
            api_key="test-key",
            client_factory=lambda: _FakeGeminiClient(),
        )
        health = provider.health()
        assert health.ok is True
        assert "configured" in health.message.lower()

    def test_health_catches_client_errors(self) -> None:
        class _BrokenClientFactory:
            def __call__(self):
                raise RuntimeError("cannot build client")

        provider = GeminiProvider(
            api_key="test-key",
            client_factory=_BrokenClientFactory(),
        )
        health = provider.health()
        assert health.ok is False
        assert "client error" in health.message.lower()


# ---------------------------------------------------------------------------
# GeminiProvider ↔ ProviderFactory fallback
# ---------------------------------------------------------------------------


class TestGeminiFactoryFallback:
    def test_factory_registers_gemini(self) -> None:
        factory = ProviderFactory()
        assert "gemini" in factory.names()

    def test_factory_falls_back_to_mock_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Without GEMINI_API_KEY, requesting 'gemini' yields MockProvider."""
        monkeypatch.delenv("GEMINI_API_KEY", raising=False)

        # Ensure settings are re-read without a key.
        monkeypatch.setattr(
            "app.config.settings.get_settings",
            lambda: _SettingsWithNoKey(),
        )

        factory = ProviderFactory()
        provider = factory.create("gemini")
        assert isinstance(provider, MockProvider)
        assert provider.name == "mock"

    def test_factory_mock_default_still_works(self, monkeypatch: pytest.MonkeyPatch) -> None:
        factory = ProviderFactory()
        monkeypatch.delenv("AI_PROVIDER", raising=False)
        provider = factory.create()
        assert isinstance(provider, MockProvider)


class _SettingsWithNoKey:
    """Settings stub exposing just the fields the factory reads."""

    ai_provider = "mock"
    gemini_api_key = ""
    gemini_model = "gemini-2.0-flash"
