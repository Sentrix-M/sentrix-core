"""Kernel pipeline — orchestrates the Sentrix request flow.

The pipeline composes the context builder, router, prompt builder, provider
client, and response builder into a single, provider-agnostic flow:

    context → route → prompt → provider → response

Providers are registered through :class:`ProviderRegistry` as lightweight
adapter objects implementing :class:`ProviderClient`. No concrete AI vendor
is imported anywhere in the kernel — adapters are injected at composition
time by the application layer.

When an optional :class:`~app.memory.service.MemoryService` is provided
(Phase 15B), recent conversation context is injected into the prompt on a
best-effort basis. When omitted, the pipeline behaves exactly as before
(backward compatible).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

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

if TYPE_CHECKING:
    from app.memory.service import MemoryService


def _tool_result_to_dict(result: Any) -> dict[str, object]:
    """Serialize a :class:`ToolResult` for the prompt builder."""
    return {
        "tool": getattr(result, "tool", "unknown"),
        "success": bool(getattr(result, "success", False)),
        "output": getattr(result, "output", None),
        "error": getattr(result, "error", None),
    }


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
        tool_coordinator: Any | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        """Build the pipeline.

        :param context_builder: Collects conversation context.
        :param router: Selects the provider for each request.
        :param prompt_builder: Assembles the final prompt.
        :param response_builder: Shapes provider output into a response.
        :param registry: Maps provider names to client adapters.
        :param system_prompt: Default system instructions; can be overridden
            per call via ``instruction``.
        :param tool_coordinator: Optional :class:`ToolCoordinator` used to
            detect tool intents, execute mock tools, and feed results into
            the prompt.  When ``None``, tool integration is disabled.
        :param memory_service: Optional :class:`MemoryService` used to inject
            recent conversation context on a best-effort basis. When omitted
            (default), no memory context is injected (backward compatible).
        """
        self._context_builder = context_builder
        self._router = router
        self._prompt_builder = prompt_builder
        self._response_builder = response_builder
        self._registry = registry
        self._system_prompt = system_prompt
        self._tool_coordinator = tool_coordinator
        self._memory_service = memory_service

    @property
    def registry(self) -> ProviderRegistry:
        """The provider registry (for composition/testing)."""
        return self._registry

    @property
    def tool_coordinator(self) -> Any | None:
        """The tool coordinator, or ``None`` when tool integration is off."""
        return self._tool_coordinator

    @property
    def memory_service(self) -> MemoryService | None:
        """The optional memory service ("None" when not wired)."""
        return self._memory_service

    def run(
        self,
        *,
        conversation_id: str,
        message: str,
        capabilities: tuple = (),
        preferred_provider: str | None = None,
        instruction: str | None = None,
        user_permissions: set[str] | None = None,
    ) -> KernelResponse:
        """Execute the kernel flow for a user message.

        :param conversation_id: Client-generated conversation identifier.
        :param message: The user's current message.
        :param capabilities: Required provider capabilities for this turn.
        :param preferred_provider: Optional explicit provider choice.
        :param instruction: Per-turn instruction; falls back to the pipeline's
            system prompt when omitted.
        :param user_permissions: Optional permission set used to authorize
            tool execution.  When ``None``, tool permissions are not checked.
        """
        context = self._context_builder.get_context(
            conversation_id=conversation_id,
            message=message,
        )

        # Best-effort memory context injection (Phase 15B). Retrieves recent
        # conversation context and appends it to the instruction so the
        # provider can leverage long-term memory without altering the
        # context-builder contract.
        memory_context = self._collect_memory_context(conversation_id)
        effective_instruction = self._merge_instruction(instruction, memory_context)

        # Tool integration: detect intent, execute tools (single or multi-tool
        # workflow), and collect the results so they can be fed into the
        # prompt builder. ``plan_and_execute`` falls back to the legacy
        # single-tool path for 0-1 tool messages (backward compatible).
        tool_results: list[dict[str, object]] = []
        tools_used: list[str] = []
        if self._tool_coordinator is not None:
            workflow = self._tool_coordinator.plan_and_execute(
                message,
                user_permissions=user_permissions,
            )
            if workflow is not None:
                for result in workflow.results:
                    tool_results.append(_tool_result_to_dict(result))
                    if result.success:
                        tools_used.append(result.tool)

        route = self._route(context, capabilities, preferred_provider)
        prompt = self._build_prompt(context, effective_instruction, tool_results)
        output = self._invoke(route, prompt, tools_used)
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

    def _build_prompt(
        self,
        context: ConversationContext,
        instruction: str | None,
        tool_results: list[dict[str, object]] | None = None,
    ) -> Prompt:
        """Build the final prompt from context, instruction, and tool results."""
        return self._prompt_builder.build(
            context=context,
            system=self._system_prompt,
            instruction=instruction or "",
            tool_results=tuple(tool_results or ()),
        )

    def _invoke(
        self,
        route: Route,
        prompt: Prompt,
        tools_used: list[str] | None = None,
    ) -> ProviderOutput:
        """Invoke the provider client for a route."""
        client = self._registry.get(route.provider)
        output = client.generate(prompt)
        if tools_used:
            output = ProviderOutput(
                text=output.text,
                reasoning=output.reasoning,
                evidence=output.evidence,
                sources=output.sources,
                tools_used=tuple(tools_used) + tuple(
                    t for t in output.tools_used if t not in tools_used
                ),
                model=output.model,
                metadata=dict(output.metadata),
                citations=output.citations,
            )
        return output

    # ------------------------------------------------------------------
    # Memory integration (Phase 15B)
    # ------------------------------------------------------------------

    def _collect_memory_context(self, conversation_id: str) -> str:
        """Return recent conversation context as a compact text block.

        Best-effort: returns ``""`` when no memory service is wired, the
        retrieval fails, or there is no stored history.
        """
        if self._memory_service is None:
            return ""
        try:
            records = self._memory_service.get_conversation_messages(
                conversation_id=conversation_id,
                limit=10,
            )
        except Exception:  # noqa: BLE001 - memory must never break the turn
            return ""
        if not records:
            return ""
        lines = [
            f"{record.role}: {record.content}"
            for record in reversed(records)
        ]
        return "\n".join(lines)

    @staticmethod
    def _merge_instruction(instruction: str | None, memory_context: str) -> str | None:
        """Append memory context to the per-turn instruction, if any."""
        if not memory_context:
            return instruction
        base = instruction or ""
        if base:
            return f"{base}\n\n[Long-term memory context]\n{memory_context}"
        return f"[Long-term memory context]\n{memory_context}"


__all__ = [
    "KernelPipeline",
    "ProviderClient",
    "ProviderNotConfiguredError",
    "ProviderRegistry",
]
