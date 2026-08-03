"""Tool Engine routes under ``/api/v1/tools``.

Exposes the tool execution endpoint protected by the existing authentication
dependency. The tool engine is standalone — kernel integration will follow
in a future sprint.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_current_user, get_tool_executor
from app.models.user import User
from app.schemas.tools import (
    ToolExecuteRequest,
    ToolExecuteResponse,
)
from app.tools.executor import ToolExecutor
from app.tools.registry import ToolRegistry

router = APIRouter(prefix="/tools", tags=["tools"])


# ---------------------------------------------------------------------------
# Utility — resolve registry from the executor
# ---------------------------------------------------------------------------


def _get_registry(request: Request) -> ToolRegistry:
    """Return the tool registry stored on application state."""
    executor = getattr(request.app.state, "tool_executor", None)
    if executor is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Tool executor is not initialized.",
        )
    return executor._registry  # noqa: SLF001 — intentional for DI


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get(
    "",
    summary="List all registered tools",
    status_code=status.HTTP_200_OK,
)
async def list_tools(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001 — auth gate
) -> dict:
    """Return metadata about every registered tool."""
    registry = _get_registry(request)
    tools = registry.list_tools()
    return {"tools": tools, "total": len(tools)}


@router.post(
    "/execute",
    response_model=ToolExecuteResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute a tool",
)
async def execute_tool(
    payload: ToolExecuteRequest,
    executor: Annotated[ToolExecutor, Depends(get_tool_executor)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ToolExecuteResponse:
    """Execute the named tool with the provided input.

    The endpoint is protected by the existing authentication dependency.
    Tool permissions are enforced by the executor based on the calling
    user's assigned permissions.
    """
    user_permissions = set(current_user.permissions) if current_user.permissions else set()

    result = await executor.execute(
        tool_name=payload.tool,
        input_data=payload.input,
        user_permissions=user_permissions,
        timeout=payload.timeout,
    )

    return ToolExecuteResponse(
        success=result.success,
        tool=result.tool,
        output=result.output,
        error=result.error,
        metadata=result.metadata,
    )


@router.get(
    "/{tool_name}",
    summary="Get tool metadata",
    status_code=status.HTTP_200_OK,
)
async def get_tool(
    tool_name: str,
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],  # noqa: ARG001 — auth gate
) -> dict:
    """Return metadata about a specific tool."""
    registry = _get_registry(request)
    tool = registry.get(tool_name)
    if tool is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Tool '{tool_name}' not found.",
        )
    return {
        "name": tool.name,
        "description": tool.description,
        "version": tool.version,
        "enabled": registry.is_enabled(tool_name),
        "input_schema": tool.input_schema,
        "output_schema": tool.output_schema,
    }
