"""Pydantic schemas for the Tool Engine API.

Request/response models for tool execution, listing, and health checks.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ToolExecuteRequest(BaseModel):
    """Payload for executing a tool."""

    tool: str = Field(
        ...,
        description="Name of the tool to execute.",
        min_length=1,
    )
    input: dict[str, Any] = Field(
        default_factory=dict,
        description="Parameters to pass to the tool.",
    )
    timeout: int | None = Field(
        default=None,
        description="Max execution time in seconds. Defaults to provider timeout.",
        ge=1,
        le=300,
    )


class ToolExecuteResponse(BaseModel):
    """Standard response from a tool execution."""

    success: bool
    tool: str
    output: Any = None
    error: str | None = None
    metadata: dict[str, Any] = Field(
        default_factory=lambda: {
            "execution_time_ms": 0,
            "timestamp": "",
        }
    )


class ToolInfo(BaseModel):
    """Public metadata about a registered tool."""

    name: str
    description: str
    version: str
    enabled: bool
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)


class ToolListResponse(BaseModel):
    """Response listing all registered tools."""

    tools: list[ToolInfo]
    total: int


__all__ = [
    "ToolExecuteRequest",
    "ToolExecuteResponse",
    "ToolInfo",
    "ToolListResponse",
]
