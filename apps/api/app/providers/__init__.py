"""Sentrix AI Provider Layer.

Contains the provider abstraction (:class:`BaseProvider`), the deterministic
offline :class:`MockProvider`, and the :class:`ProviderFactory` used to create
and substitute providers. The factory is the integration seam into the kernel:
providers it creates conform to the kernel's ``ProviderClient`` protocol and
can be registered with a kernel :class:`~app.kernel.pipeline.ProviderRegistry`.

No external AI SDKs are imported anywhere in this package — future providers
(OpenAI, Gemini, Claude, Ollama) plug in via the factory's registry.
"""

from app.providers.base import BaseProvider
from app.providers.factory import DEFAULT_PROVIDER, ProviderFactory
from app.providers.mock import MockProvider

__all__ = [
    "DEFAULT_PROVIDER",
    "BaseProvider",
    "MockProvider",
    "ProviderFactory",
]
