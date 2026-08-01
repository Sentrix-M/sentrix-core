"""Provider factory — the composition seam for the Sentrix AI Provider Layer.

``ProviderFactory`` creates providers by name and returns the deterministic
:class:`~app.providers.mock.MockProvider` by default. Real providers (OpenAI,
Gemini, Claude, Ollama) can be registered lazily in the future without
touching the kernel or the routers — the factory only needs to know how to
construct them.
"""

from __future__ import annotations

from typing import Protocol

from app.providers.base import BaseProvider
from app.providers.mock import MockProvider

#: Provider name used by the factory when no explicit provider is requested.
DEFAULT_PROVIDER = "mock"


class ProviderConstructor(Protocol):
    """Callable that builds a :class:`BaseProvider` instance."""

    def __call__(self) -> BaseProvider:
        """Return a configured provider instance."""
        ...


class ProviderFactory:
    """Creates provider instances by name.

    The factory is deliberately synchronous and dependency-free. Future
    providers register a constructor (usually a lambda) with
    :meth:`register`; the factory then resolves them lazily on first access.
    """

    def __init__(self) -> None:
        self._constructors: dict[str, ProviderConstructor] = {
            DEFAULT_PROVIDER: MockProvider,
        }

    def register(self, name: str, constructor: ProviderConstructor) -> None:
        """Register a provider constructor under ``name``.

        Calling this replaces any existing constructor for ``name``.
        """
        self._constructors[name] = constructor

    def create(self, name: str | None = None) -> BaseProvider:
        """Return a new provider instance.

        :param name: Provider name. Defaults to :data:`DEFAULT_PROVIDER`.
        :raises KeyError: When ``name`` is not a registered provider.
        """
        provider_name = name or DEFAULT_PROVIDER
        try:
            constructor = self._constructors[provider_name]
        except KeyError:
            raise KeyError(
                f"Unknown provider '{provider_name}'. "
                f"Registered providers: {', '.join(sorted(self._constructors))}."
            ) from None
        return constructor()

    def names(self) -> tuple[str, ...]:
        """Names of the registered provider constructors."""
        return tuple(self._constructors)

    def __contains__(self, name: str) -> bool:
        return name in self._constructors


__all__ = ["DEFAULT_PROVIDER", "ProviderFactory"]
