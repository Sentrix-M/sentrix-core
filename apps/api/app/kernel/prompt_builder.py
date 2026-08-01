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
    ) -> Prompt:
        """Assemble the prompt.

        :param context: Collected conversation context (the current turn and
            any prior messages).
        :param system: The system prompt/instructions for the provider.
        :param instruction: The task-specific instruction for this turn.
        """
        messages: list[ContextMessage] = [context.user_message]
        messages.extend(context.prior_messages)

        return Prompt(
            system=system,
            instruction=instruction,
            context=context,
            messages=tuple(messages),
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
