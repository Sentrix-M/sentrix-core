"""Orchestrate Server-Sent Events for the Sentrix kernel.

:class:`StreamingManager` is the application seam between the streaming HTTP
endpoint and the kernel pipeline. It yields pre-serialised SSE blocks: a
connection heartbeat, ``status`` events (thinking / generating), ``token``
events for each streamed chunk, and a terminal ``completed`` + ``done`` pair.
Errors are captured into ``error`` events so the client always receives a
well-formed, terminal stream.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from time import perf_counter
from typing import TYPE_CHECKING

from app.kernel.integration import build_kernel_pipeline
from app.kernel.pipeline import KernelPipeline
from app.schemas.conversation import ConversationMessageRequest
from app.streaming.events import (
    completed_event,
    done_event,
    error_event,
    status_event,
    token_event,
)
from app.streaming.formatter import format_event, heartbeat
from app.tools.executor import ToolExecutor

if TYPE_CHECKING:
    from app.memory.service import MemoryService

#: Default inter-token delay (seconds) used to simulate a live provider stream.
DEFAULT_TOKEN_DELAY_SECONDS = 0.015


class StreamingManager:
    """Compose and emit an SSE stream for a single conversation turn.

    The manager owns a :class:`KernelPipeline` (built with the offline
    ``MockProvider`` by default) and reuses its canonical, fully-assembled
    :class:`KernelResponse`. The response content is then replayed as
    word-level ``token`` events so the client receives the exact same text
    incrementally — no provider-specific logic leaks into the HTTP layer.

    ``asyncio.to_thread`` keeps the synchronous kernel run off the event
    loop so the streaming endpoint stays responsive with real providers too.
    """

    def __init__(
        self,
        *,
        pipeline: KernelPipeline | None = None,
        token_delay_seconds: float = DEFAULT_TOKEN_DELAY_SECONDS,
        tool_executor: ToolExecutor | None = None,
        memory_service: MemoryService | None = None,
    ) -> None:
        """Create the manager.

        :param pipeline: Kernel pipeline to use; defaults to a fresh pipeline
            from :func:`build_kernel_pipeline` (offline mock provider).
        :param token_delay_seconds: Simulated delay between token events.
            Pass ``0`` in tests to make streams run instantly.
        :param tool_executor: Optional :class:`ToolExecutor` used to build a
            tool-aware kernel pipeline so the stream can execute mock tools
            and surface ``tools_used`` in the ``completed`` event.
        :param memory_service: Optional :class:`MemoryService` passed through
            to the kernel pipeline for long-term memory context (best-effort).
        """
        self._pipeline = pipeline or build_kernel_pipeline(
            tool_executor=tool_executor,
            memory_service=memory_service,
        )
        self._token_delay_seconds = token_delay_seconds

    async def stream(
        self,
        request: ConversationMessageRequest,
        *,
        user_permissions: set[str] | None = None,
    ) -> AsyncIterator[str]:
        """Yield serialised SSE blocks for ``request``.

        Event sequence: ``heartbeat`` → ``status: thinking`` →
        ``status: generating`` → ``token``* → ``completed`` → ``done``.
        On failure, an ``error`` event precedes ``done`` so the stream always
        terminates with a well-formed block.

        :param user_permissions: Optional permission strings used to authorize
            mock tool execution inside the kernel pipeline.
        """
        started = perf_counter()
        yield heartbeat()
        yield format_event(
            status_event(
                "thinking",
                detail="Assembling context and routing to the best provider.",
            )
        )

        try:
            # The kernel run is synchronous (mock today); run it in a worker
            # thread so the event loop keeps serving the SSE connection.
            response = await asyncio.to_thread(
                self._pipeline.run,
                conversation_id=request.conversation_id,
                message=request.message,
                user_permissions=user_permissions,
            )

            yield format_event(
                status_event(
                    "generating",
                    detail="Streaming the assistant reply token by token.",
                )
            )

            for token in response.content.split(" "):
                yield format_event(token_event(token))
                if self._token_delay_seconds > 0:
                    await asyncio.sleep(self._token_delay_seconds)

            execution_time_ms = int((perf_counter() - started) * 1000)
            yield format_event(
                completed_event(
                    provider=response.provider,
                    model=response.model,
                    content=response.content,
                    execution_time_ms=execution_time_ms,
                    citations=list(response.citations) if response.citations else None,
                    tools_used=list(response.tools_used) if response.tools_used else None,
                )
            )
        except asyncio.CancelledError:
            # Client disconnected or pressed Stop — end the stream cleanly.
            raise
        except Exception as exc:
            yield format_event(error_event(f"Streaming failed: {exc}"))
        finally:
            yield format_event(done_event())


__all__ = ["DEFAULT_TOKEN_DELAY_SECONDS", "StreamingManager"]
