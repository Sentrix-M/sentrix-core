"""Prompt building for the Sentrix Kernel.

``PromptBuilder`` composes the final prompt sent to a provider from the
conversation context, the system instruction, and a templated instruction
set. It is format-agnostic — providers that need a different serialization
(e.g. chat turns vs. raw text) can wrap the resulting structure.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Protocol

from app.kernel.context_builder import ContextMessage, ConversationContext


@dataclass(frozen=True)
class Prompt:
    """The fully assembled prompt for a provider."""

    system: str
    instruction: str
    context: ConversationContext
    messages: tuple[ContextMessage, ...] = field(default_factory=tuple)
    citations: tuple[dict[str, object], ...] = field(default_factory=tuple)
    tool_results: tuple[dict[str, object], ...] = field(default_factory=tuple)

    def to_text(self) -> str:
        """Serialize the prompt to a single text block.

        Intended for simple/text-completion providers. Chat-style providers
        can consume ``system``/``messages`` directly instead.
        """
        blocks: list[str] = []

        if self.system:
            blocks.append(self.system)
        current = self.context.user_message
        if current.content:
            blocks.append(f"User: {current.content}")
        if self.context.prior_messages:
            history = "\n".join(
                f"{message.role}: {message.content}" for message in self.context.prior_messages
            )
            blocks.append(f"Conversation history:\n{history}")

        # Inject retrieved RAG chunks as context
        if self.context.retrieved_chunks:
            ctx_lines = ["Retrieved context:"]
            for i, chunk in enumerate(self.context.retrieved_chunks, 1):
                text = chunk.get("text", "")
                source = chunk.get("filename", "unknown")
                page = chunk.get("page_number", "?")
                ctx_lines.append(
                    f"[{i}] (Source: {source}, Page: {page})\n{text}"
                )
            ctx_lines.append(
                "Use the retrieved context above to answer the user's question. "
                "If the context is not relevant, answer based on your knowledge. "
                "Always cite the source filename and page number when using retrieved context."
            )
            blocks.append("\n".join(ctx_lines))

        # Inject tool results as context for the provider to explain naturally.
        if self.tool_results:
            tool_lines = ["Tool results:"]
            for i, result in enumerate(self.tool_results, 1):
                tool_name = result.get("tool", "unknown")
                success = bool(result.get("success", False))
                status = "succeeded" if success else "failed"
                tool_lines.append(f"[{i}] {tool_name} {status}")
                if success:
                    output = result.get("output")
                    if output is not None:
                        tool_lines.append(f"Output: {output}")
                error = result.get("error")
                if error:
                    tool_lines.append(f"Error: {error}")
            tool_lines.append(
                "Use the tool results above to answer the user's request naturally "
                "and accurately. When a tool failed, explain what happened and "
                "suggest a next step."
            )
            blocks.append("\n".join(tool_lines))

        if self.instruction:
            blocks.append(f"Instruction: {self.instruction}")

        return "\n\n".join(blocks)


class PromptBuilder(Protocol):
    """Interface for components that build the final prompt."""

    def build(
        self,
        *,
        context: ConversationContext,
        system: str,
        instruction: str,
        tool_results: tuple[dict[str, object], ...] = (),
    ) -> Prompt:
        """Assemble a :class:`Prompt` from context and directives."""
        ...


class DefaultPromptBuilder:
    """Builds a :class:`Prompt` from context and static directives.

    The resulting prompt is deterministic and pure — no I/O, no state — so it
    is trivial to unit-test and safe to reuse across providers.
    """

    def build(
        self,
        *,
        context: ConversationContext,
        system: str,
        instruction: str,
        tool_results: tuple[dict[str, object], ...] = (),
    ) -> Prompt:
        """Assemble the prompt.

        :param context: Collected conversation context (the current turn and
            any prior messages).
        :param system: The system prompt/instructions for the provider.
        :param instruction: The task-specific instruction for this turn.
        :param tool_results: Optional tool outputs to inject into the prompt.
        """
        messages: list[ContextMessage] = [context.user_message]
        messages.extend(context.prior_messages)

        return Prompt(
            system=system,
            instruction=instruction,
            context=context,
            messages=tuple(messages),
            citations=tuple(context.citations),
            tool_results=tuple(tool_results),
        )


def build_prompt(
    context: ConversationContext,
    system: str,
    instruction: str,
    builders: Iterable[PromptBuilder] | None = None,
) -> Prompt:
    """Convenience helper: run the first available prompt builder.

    :param builders: Optional ordered list of builders. Defaults to a single
        :class:`DefaultPromptBuilder`.
    """
    selected = list(builders) if builders is not None else [DefaultPromptBuilder()]
    if not selected:
        raise ValueError("At least one prompt builder is required.")
    return selected[0].build(
        context=context,
        system=system,
        instruction=instruction,
    )


__all__ = ["DefaultPromptBuilder", "Prompt", "PromptBuilder", "build_prompt"]
