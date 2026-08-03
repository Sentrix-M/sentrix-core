"""Tool Registry — dynamic registration and lookup of tools.

The :class:`ToolRegistry` manages the lifecycle of tool instances:

- Register new tools (by name)
- Look up tools by name
- List all available tools
- Enable / disable tools at runtime
- Deregister tools
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class ToolRegistry:
    """Registry of available tools.

    Thread-safe design: all mutations are synchronous and guarded by a
    single lock. The registry is created once at application startup and
    shared via dependency injection.
    """

    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}
        self._enabled: set[str] = set()

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def register(self, tool: BaseTool) -> None:
        """Register a tool instance.

        Replaces any existing tool with the same name. Newly registered
        tools are enabled by default.
        """
        self._tools[tool.name] = tool
        self._enabled.add(tool.name)
        logger.info("Tool registered: %s v%s", tool.name, tool.version)

    def deregister(self, name: str) -> None:
        """Remove a tool from the registry."""
        self._tools.pop(name, None)
        self._enabled.discard(name)
        logger.info("Tool deregistered: %s", name)

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def get(self, name: str) -> BaseTool | None:
        """Return the tool instance by name, or ``None``."""
        return self._tools.get(name)

    def require(self, name: str) -> BaseTool:
        """Return the tool instance by name, or raise :class:`KeyError`."""
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' is not registered.")
        return tool

    def list_tools(self) -> list[dict[str, str | bool]]:
        """Return a summary of all registered tools."""
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "version": tool.version,
                "enabled": tool.name in self._enabled,
            }
            for tool in self._tools.values()
        ]

    # ------------------------------------------------------------------
    # Enable / disable
    # ------------------------------------------------------------------

    def enable(self, name: str) -> None:
        """Enable a registered tool."""
        if name not in self._tools:
            raise KeyError(f"Cannot enable unknown tool '{name}'.")
        self._enabled.add(name)

    def disable(self, name: str) -> None:
        """Disable a registered tool."""
        self._enabled.discard(name)

    def is_enabled(self, name: str) -> bool:
        """Check whether a tool is enabled."""
        return name in self._enabled

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def names(self) -> tuple[str, ...]:
        """Names of all registered tools."""
        return tuple(self._tools)

    def __contains__(self, name: str) -> bool:
        return name in self._tools

    def __len__(self) -> int:
        return len(self._tools)


__all__ = ["ToolRegistry"]
