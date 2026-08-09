"""Integration helpers for the Sentrix MITRE ATT&CK mapping engine.

This module ties the mapper back into the Tool Engine / Kernel flow without
changing any existing contracts. :func:`enrich_tool_result` runs the mapper
over a :class:`~app.tools.base.ToolResult` and returns the serialized
:class:`~app.mitre.models.MitreMapping` dict for injection into tool result
metadata (which the prompt builder and providers then surface to the AI).
"""

from __future__ import annotations

from typing import Any

from app.mitre.mapper import MitreMapper
from app.tools.base import ToolResult


def enrich_tool_result(
    tool_result: ToolResult,
    mapper: MitreMapper | None = None,
) -> dict[str, Any]:
    """Map ``tool_result`` to MITRE and return the serialized mapping.

    :param tool_result: The tool result to map.
    :param mapper: Optional :class:`MitreMapper`. Defaults to a fresh
        instance so the helper is self-contained.
    :returns: The :meth:`~app.mitre.models.MitreMapping.to_dict` output for
        ``tool_result`` (may be empty when the result is a failure or unknown).
    """
    effective = mapper or MitreMapper()
    return effective.map(tool_result).to_dict()


__all__ = ["enrich_tool_result"]
