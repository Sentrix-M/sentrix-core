"""Kernel integration — compose providers into a ready-to-run pipeline.

This module is the application-layer seam that ties the provider layer to the
kernel. ``build_kernel_pipeline`` constructs a :class:`KernelPipeline` wired
with an ``InMemoryContextProvider``, the capability router, the default
prompt/response builders, and a provider registry seeded from the
:class:`~app.providers.factory.ProviderFactory`.

Because the factory returns ``MockProvider`` by default, the pipeline runs
fully offline and deterministically. Future providers are wired here — and
nowhere else — by registering their constructors with the factory and adding
a matching :class:`ProviderProfile` to the router.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.kernel.context_builder import (
    ContextProvider,
    InMemoryContextProvider,
)
from app.kernel.pipeline import KernelPipeline, ProviderRegistry
from app.kernel.prompt_builder import DefaultPromptBuilder
from app.kernel.response_builder import DefaultResponseBuilder
from app.kernel.router import Capability, DefaultProviderRouter, ProviderProfile
from app.providers.base import BaseProvider
from app.providers.factory import DEFAULT_PROVIDER, ProviderFactory

if TYPE_CHECKING:
    from app.memory.manager import MemoryManager

#: System prompt used by the default Sentrix pipeline.
SYSTEM_PROMPT = (
    "You are Sentrix, an enterprise AI-powered cybersecurity copilot. "
    "Provide concise, accurate, security-focused analysis and always "
    "flag uncertainty rather than guessing."
)

#: How many prior messages to retain in the in-memory context window.
CONTEXT_HISTORY_LIMIT = 20


def build_kernel_pipeline(
    *,
    factory: ProviderFactory | None = None,
    provider: str | None = None,
    system_prompt: str = SYSTEM_PROMPT,
    memory_manager: MemoryManager | None = None,
) -> KernelPipeline:
    """Compose a :class:`KernelPipeline` wired with a provider from ``factory``.

    :param factory: Provider factory to source the provider from. Defaults to
        a new :class:`ProviderFactory` (which returns ``MockProvider``).
    :param provider: Provider name to use; defaults to
        :data:`~app.providers.factory.DEFAULT_PROVIDER`.
    :param system_prompt: System instructions for the pipeline.
    :param memory_manager: Optional :class:`MemoryManager` used as the kernel
        context builder.  When omitted, an :class:`InMemoryContextProvider`
        is used (backwards-compatible default).
    """
    provider_factory = factory or ProviderFactory()
    provider_name = provider or DEFAULT_PROVIDER
    provider_instance = provider_factory.create(provider_name)

    registry = ProviderRegistry()
    registry.register(provider_instance)

    router = DefaultProviderRouter(
        [
            ProviderProfile(
                name=provider_name,
                capabilities=(Capability.GENERAL, Capability.SECURITY),
                priority=1,
            )
        ]
    )

    context_builder: ContextProvider
    if memory_manager is not None:
        context_builder = memory_manager
    else:
        context_builder = InMemoryContextProvider(
            history_limit=CONTEXT_HISTORY_LIMIT,
        )

    return KernelPipeline(
        context_builder=context_builder,
        router=router,
        prompt_builder=DefaultPromptBuilder(),
        response_builder=DefaultResponseBuilder(),
        registry=registry,
        system_prompt=system_prompt,
    )


def get_kernel_provider(factory: ProviderFactory | None = None) -> BaseProvider:
    """Return the default provider instance from ``factory``.

    Convenience helper for callers that need direct access to the provider
    (e.g. health checks) without building a full pipeline.
    """
    return (factory or ProviderFactory()).create(DEFAULT_PROVIDER)


__all__ = [
    "CONTEXT_HISTORY_LIMIT",
    "SYSTEM_PROMPT",
    "build_kernel_pipeline",
    "get_kernel_provider",
]
