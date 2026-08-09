"""Tool Router — route execution requests to the correct tool.

The :class:`ToolRouter` validates that:

1. The requested tool exists in the registry.
2. The tool is enabled.
3. The caller has the required permissions.
4. The input matches the tool's input schema.

Schema validation uses a lightweight JSON Schema check (required fields,
type checks). Full JSON Schema draft-07 validation can be added later.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.tools.base import BaseTool
    from app.tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class ToolRouter:
    """Routes tool execution requests to the appropriate tool."""

    def __init__(self, registry: ToolRegistry) -> None:
        self._registry = registry

    def resolve(self, name: str) -> BaseTool:
        """Resolve a tool by name.

        :raises KeyError: Tool not found in registry.
        :raises RuntimeError: Tool is disabled.
        """
        tool = self._registry.get(name)
        if tool is None:
            raise KeyError(f"Tool '{name}' is not registered.")
        if not self._registry.is_enabled(name):
            raise RuntimeError(f"Tool '{name}' is disabled.")
        return tool

    def validate_permissions(
        self,
        tool: BaseTool,
        user_permissions: set[str],
    ) -> None:
        """Check that ``user_permissions`` satisfy the tool's requirements.

        :param tool: The tool instance to check.
        :param user_permissions: Set of permission strings e.g. ``{"filesystem:read", "terminal:execute"}``.
        :raises PermissionError: When a required permission is missing.
        """
        required = {str(p) for p in tool.permissions}
        missing = required - user_permissions
        if missing:
            raise PermissionError(
                f"Missing required permissions for tool '{tool.name}': {', '.join(sorted(missing))}."
            )

    def validate_input(self, tool: BaseTool, input_data: dict[str, Any]) -> None:
        """Validate ``input_data`` against the tool's ``input_schema``.

        Performs a basic structural validation:
        - Required fields are present.
        - Field types match the schema (where declared).

        :param tool: The tool instance whose schema to use.
        :param input_data: The input data to validate.
        :raises ValueError: When validation fails.
        """
        schema = tool.input_schema
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        # Check required fields.
        for field_name in required:
            if field_name not in input_data:
                raise ValueError(
                    f"Missing required field '{field_name}' for tool '{tool.name}'."
                )

        # Type-check fields where the schema declares a type.
        type_map: dict[str, type] = {
            "string": str,
            "integer": int,
            "number": float,
            "boolean": bool,
            "array": list,
            "object": dict,
        }
        for field_name, field_schema in properties.items():
            if field_name not in input_data:
                continue
            expected_type_str = field_schema.get("type")
            if expected_type_str is None:
                continue
            expected_type = type_map.get(expected_type_str)
            if expected_type is None:
                continue
            value = input_data[field_name]
            if not isinstance(value, expected_type):
                raise ValueError(
                    f"Field '{field_name}' for tool '{tool.name}' "
                    f"expected {expected_type_str}, got {type(value).__name__}."
                )


__all__ = ["ToolRouter"]
