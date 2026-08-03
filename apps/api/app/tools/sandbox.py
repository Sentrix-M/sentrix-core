"""Sandbox abstraction for the Sentrix Tool Engine.

The :class:`Sandbox` protocol defines the contract for isolating tool
execution. The :class:`MockSandbox` is a no-op implementation used during
development — it does NOT execute any real commands.

Real sandbox implementations (Docker, subprocess with seccomp, gVisor, …)
will be added in a future sprint.
"""

from __future__ import annotations

from typing import Any, Protocol


class Sandbox(Protocol):
    """Isolated execution environment for tool calls.

    A sandbox restricts what a tool can do (filesystem, network, process
    creation) so that even if a tool misbehaves, the host is protected.
    """

    async def execute(self, command: str, **kwargs: Any) -> tuple[int, str, str]:
        """Run ``command`` inside the sandbox.

        :returns: ``(exit_code, stdout, stderr)``.
        """
        ...

    async def write_file(self, path: str, content: str) -> None:
        """Write ``content`` to ``path`` inside the sandbox."""
        ...

    async def read_file(self, path: str) -> str:
        """Read and return the contents of ``path`` inside the sandbox."""
        ...

    async def cleanup(self) -> None:
        """Release all sandbox resources."""
        ...


class MockSandbox:
    """No-op sandbox for development and testing.

    Does NOT execute any real commands. All operations log a warning and
    return safe defaults.
    """

    def __init__(self) -> None:
        self._files: dict[str, str] = {}

    async def execute(self, command: str, **kwargs: Any) -> tuple[int, str, str]:  # noqa: ARG002 — mock
        """Mock execution — returns empty output."""
        return 0, "", ""

    async def write_file(self, path: str, content: str) -> None:
        """Store content in-memory (no real filesystem access)."""
        self._files[path] = content

    async def read_file(self, path: str) -> str:
        """Read from in-memory store."""
        return self._files.get(path, "")

    async def cleanup(self) -> None:
        """Clear in-memory state."""
        self._files.clear()


__all__ = ["MockSandbox", "Sandbox"]
