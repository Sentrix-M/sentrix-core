"""Memory strategies for the Sentrix Memory Layer.

Strategies are pluggable compaction/selection functions that transform an
aggregated :class:`MemoryContext` before it reaches the kernel.  This
allows future optimisation (e.g. summarising old conversation turns or
filtering irrelevant project context) without changing the memory manager
or the stores.
"""

from __future__ import annotations

from typing import Protocol

from app.memory.models import MemoryContext


class MemoryStrategy(Protocol):
    """Interface for memory compaction/selection strategies."""

    def compact(self, context: MemoryContext) -> MemoryContext:
        """Transform and return the memory context.

        Implementations may add, remove, or summarise any tier.  The
        returned context is what the kernel sees.
        """
        ...


class DefaultMemoryStrategy:
    """Default pass-through strategy — no compaction is applied.

    This is the safe default for development and testing.  Future
    strategies (e.g. rolling window summarisation, relevance filtering)
    can be registered here without changing the manager.
    """

    def compact(self, context: MemoryContext) -> MemoryContext:
        """Return the context unchanged."""
        return context


__all__ = [
    "DefaultMemoryStrategy",
    "MemoryStrategy",
]
