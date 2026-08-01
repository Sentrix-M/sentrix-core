"""Sentrix Kernel.

The kernel is the AI orchestration core of Sentrix. It defines a clean,
provider-agnostic architecture for processing conversation turns:

- :class:`~app.kernel.pipeline.KernelPipeline` orchestrates the request flow.
- :class:`~app.kernel.router.Router` decides which provider handles a request.
- :class:`~app.kernel.prompt_builder.PromptBuilder` prepares the final prompt.
- :class:`~app.kernel.context_builder.ContextBuilder` collects conversation context.
- :class:`~app.kernel.response_builder.ResponseBuilder` shapes provider output.

No concrete AI provider is integrated here. Provider adapters are injected at
composition time through :class:`~app.kernel.pipeline.ProviderRegistry`, which
keeps this package free of vendor SDKs and business logic.
"""

from app.kernel.context_builder import (
    ContextBuilder,
    ContextMessage,
    ContextProvider,
    ConversationContext,
    InMemoryContextProvider,
)
from app.kernel.pipeline import (
    KernelPipeline,
    ProviderClient,
    ProviderNotConfiguredError,
    ProviderRegistry,
)
from app.kernel.prompt_builder import Prompt, PromptBuilder
from app.kernel.response_builder import (
    KernelResponse,
    ProviderOutput,
    ResponseBuilder,
    ResponseBuildError,
)
from app.kernel.router import (
    Capability,
    DefaultProviderRouter,
    KernelError,
    KernelRequest,
    NoProviderAvailableError,
    ProviderProfile,
    Route,
    Router,
)

__all__ = [
    "Capability",
    "ContextBuilder",
    "ContextMessage",
    "ContextProvider",
    "ConversationContext",
    "DefaultProviderRouter",
    "InMemoryContextProvider",
    "KernelError",
    "KernelPipeline",
    "KernelRequest",
    "KernelResponse",
    "NoProviderAvailableError",
    "Prompt",
    "PromptBuilder",
    "ProviderClient",
    "ProviderNotConfiguredError",
    "ProviderOutput",
    "ProviderProfile",
    "ProviderRegistry",
    "ResponseBuildError",
    "ResponseBuilder",
    "Route",
    "Router",
]
