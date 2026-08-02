"""Provider factory — the composition seam for the Sentrix AI Provider Layer.

``ProviderFactory`` creates providers by name and returns the deterministic
:class:`~app.providers.mock.MockProvider` by default. Real providers (OpenAI,
Gemini, Claude, Ollama) can be registered lazily in the future without
touching the kernel or the routers — the factory only needs to know how to
construct them.

Auto-fallback
-------------
The factory reads ``AI_PROVIDER`` from the application settings to determine
the default provider name. When the configured provider is unavailable (e.g.
the Gemini API key is missing), the factory gracefully falls back to the
offline :class:`MockProvider` so the pipeline never fails at composition time.
"""

from __future__ import annotations

import logging
from typing import Protocol

from app.providers.base import BaseProvider
from app.providers.mock import MockProvider

logger = logging.getLogger(__name__)

#: Provider name used by the factory when no explicit provider is requested
#: or when the configured provider fails to initialise.
DEFAULT_PROVIDER = "mock"


class ProviderConstructor(Protocol):
    """Callable that builds a :class:`BaseProvider` instance."""

    def __call__(self) -> BaseProvider:
        """Return a configured provider instance."""
        ...


def _build_gemini_provider() -> BaseProvider:
    """Construct a :class:`~app.providers.gemini.GeminiProvider`.

    If the configuration is invalid (missing or empty API key) the provider's
    constructor raises :class:`GeminiNotConfiguredError`, which is caught by
    the factory caller and triggers a transparent fallback to ``MockProvider``.
    """
    from app.providers.gemini import GeminiProvider

    return GeminiProvider()


class ProviderFactory:
    """Creates provider instances by name.

    The factory is deliberately synchronous and dependency-free. Future
    providers register a constructor (usually a lambda) with
    :meth:`register`; the factory then resolves them lazily on first access.
    """

    def __init__(self) -> None:
        self._constructors: dict[str, ProviderConstructor] = {
            DEFAULT_PROVIDER: MockProvider,
            "gemini": _build_gemini_provider,
        }

    def register(self, name: str, constructor: ProviderConstructor) -> None:
        """Register a provider constructor under ``name``.

        Calling this replaces any existing constructor for ``name``.
        """
        self._constructors[name] = constructor

    def create(self, name: str | None = None) -> BaseProvider:
        """Return a new provider instance.

        When the requested provider raises a :class:`GeminiNotConfiguredError`
        during construction, the factory logs a warning and falls back to the
        offline :class:`MockProvider` so the pipeline never fails to compose.

        :param name: Provider name. Defaults to the ``AI_PROVIDER`` setting
            or :data:`DEFAULT_PROVIDER`.
        :raises KeyError: When ``name`` is not a registered provider and a
            fallback is not available.
        """
        provider_name = name or self._resolve_default()
        try:
            constructor = self._constructors[provider_name]
        except KeyError:
            raise KeyError(
                f"Unknown provider '{provider_name}'. "
                f"Registered providers: {', '.join(sorted(self._constructors))}."
            ) from None

        try:
            return constructor()
        except Exception as exc:  # noqa: BLE001 - catch Gemini init errors
            if provider_name == DEFAULT_PROVIDER:
                # The default provider itself failed — re-raise.
                raise
            logger.warning(
                "Provider '%s' failed to initialise: %s. Falling back to '%s'.",
                provider_name,
                exc,
                DEFAULT_PROVIDER,
            )
            # Fall back to the mock provider.
            return MockProvider()

    def _resolve_default(self) -> str:
        """Read the default provider name from application settings."""
        try:
            from app.config.settings import get_settings

            return get_settings().ai_provider or DEFAULT_PROVIDER
        except Exception:  # noqa: BLE001 - settings not available
            return DEFAULT_PROVIDER

    def names(self) -> tuple[str, ...]:
        """Names of the registered provider constructors."""
        return tuple(self._constructors)

    def __contains__(self, name: str) -> bool:
        return name in self._constructors


__all__ = ["DEFAULT_PROVIDER", "ProviderFactory"]
