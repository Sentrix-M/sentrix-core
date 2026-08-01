"""Kernel pipeline — orchestrates the Sentrix request flow.

The pipeline composes the context builder, router, prompt builder, provider
client, and response builder into a single, provider-agnostic flow:

    context → route → prompt → provider → response

Providers are registered through :class:`ProviderRegistry` as lightweight
adapter objects implementing :class:`ProviderClient`. No concrete AI vendor
is imported anywhere in the kernel — adapters are injected at composition
time by the application layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.kernel.context_builder import (
    ContextProvider,
    ConversationContext,
)
from app.kernel.prompt_builder import Prompt, PromptBuilder
from app.kernel.response_builder import (
    KernelResponse,
    ProviderOutput,
    ResponseBuilder,
)
from app.kernel.router import KernelRequest, Route, Router


class ProviderNotConfiguredError(Exception):
    """Raised when no provider client is registered for a chosen route."""


class ProviderClient(Protocol):
    """Interface for a provider adapter.

    Adapters are responsible for translating a :class:`Prompt` into the
    provider's native call and normalizing the result into a
    :class:`ProviderOutput`. This keeps vendor SDKs out of the kernel.
    """

    name: str

    def generate(self, prompt: Prompt) -> ProviderOutput:
        """Invoke the provider and return normalized output."""
        ...


@dataclass
class ProviderRegistry:
    """Registry mapping provider names to client adapters."""

    _clients: dict[str, ProviderClient] = field(default_factory=dict)

    def register(self, client: ProviderClient) -> None:
        """Register a provider client by its ``name``."""
        self._clients[client.name] = client

    def unregister(self, name: str) -> None:
        """Remove a provider client (used by tests)."""
        self._clients.pop(name, None)

    def get(self, name: str) -> ProviderClient:
        """Return the client registered as ``name`` or raise."""
        try:
            return self._clients[name]
        except KeyError:
            raise ProviderNotConfiguredError(
                f"Provider client '{name}' is not registered."
            ) from None

    def names(self) -> tuple[str, ...]:
        """Registered provider names."""
        return tuple(self._clients)

    def __len__(self) -> int:
        return len(self._clients)


class KernelPipeline:
    """Orchestrates a single conversation turn through the kernel."""

    def __init__(
        self,
        *,
        context_builder: ContextProvider,
        router: Router,
        prompt_builder: PromptBuilder,
        response_builder: ResponseBuilder,
        registry: ProviderRegistry,
        system_prompt: str = "",
    ) -> None:
        """Build the pipeline.

        :param context_builder: Collects conversation context.
        :param router: Selects the provider for each request.
        :param prompt_builder: Assembles the final prompt.
        :param response_builder: Shapes provider output into a response.
        :param registry: Maps provider names to client adapters.
        :param system_prompt: Default system instructions; can be overridden
            per call via ``instruction``.
        """
        self._context_builder = context_builder
        self._router = router
        self._prompt_builder = prompt_builder
        self._response_builder = response_builder
        self._registry = registry
        self._system_prompt = system_prompt

    @property
    def registry(self) -> ProviderRegistry:
        """The provider registry (for composition/testing)."""
        return self._registry

    def run(
        self,
        *,
        conversation_id: str,
        message: str,
        capabilities: tuple = (),
        preferred_provider: str | None = None,
        instruction: str | None = None,
    ) -> KernelResponse:
        """Execute the kernel flow for a user message.

        :param conversation_id: Client-generated conversation identifier.
        :param message: The user's current message.
        :param capabilities: Required provider capabilities for this turn.
        :param preferred_provider: Optional explicit provider choice.
        :param instruction: Per-turn instruction; falls back to the pipeline's
            system prompt when omitted.
        """
        context = self._context_builder.get_context(
            conversation_id=conversation_id,
            message=message,
        )

        route = self._route(context, capabilities, preferred_provider)
        prompt = self._build_prompt(context, instruction)
        output = self._invoke(route, prompt)
        response = self._response_builder.build(
            provider=route.provider,
            output=output,
        )
        return response

    def _route(
        self,
        context: ConversationContext,
        capabilities: tuple,
        preferred_provider: str | None,
    ) -> Route:
        """Ask the router which provider should handle this turn."""
        request = KernelRequest(
            prompt=self._prompt_builder.build(
                context=context,
                system=self._system_prompt,
                instruction="",
            ),
            capabilities=tuple(capabilities),
            preferred_provider=preferred_provider,
        )
        return self._router.route(request)

    def _build_prompt(self, context: ConversationContext, instruction: str | None) -> Prompt:
        """Build the final prompt from context and instruction."""
        return self._prompt_builder.build(
            context=context,
            system=self._system_prompt,
            instruction=instruction or "",
        )

    def _invoke(self, route: Route, prompt: Prompt) -> ProviderOutput:
        """Invoke the provider client for a route."""
        client = self._registry.get(route.provider)
        return client.generate(prompt)


__all__ = [
    "KernelPipeline",
    "ProviderClient",
    "ProviderNotConfiguredError",
    "ProviderRegistry",
]
