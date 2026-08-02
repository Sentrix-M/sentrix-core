"""Sentrix AI Provider Layer.

Contains the provider abstraction (:class:`BaseProvider`), the deterministic
offline :class:`MockProvider`, the cloud :class:`GeminiProvider`, and the
:class:`ProviderFactory` used to create and substitute providers. The factory
is the integration seam into the kernel: providers it creates conform to the
kernel's ``ProviderClient`` protocol and can be registered with a kernel
:class:`~app.kernel.pipeline.ProviderRegistry`.

The Gemini provider uses the official ``google-genai`` SDK and is registered
in the factory with an automatic fallback to :class:`MockProvider` when the
``GEMINI_API_KEY`` is missing or invalid — the platform remains fully
functional offline.
"""

from app.providers.base import BaseProvider, ProviderHealth
from app.providers.factory import DEFAULT_PROVIDER, ProviderFactory
from app.providers.gemini import (
    GeminiError,
    GeminiNotConfiguredError,
    GeminiProvider,
)
from app.providers.mock import MockProvider

__all__ = [
    "DEFAULT_PROVIDER",
    "BaseProvider",
    "GeminiError",
    "GeminiNotConfiguredError",
    "GeminiProvider",
    "MockProvider",
    "ProviderFactory",
    "ProviderHealth",
]

