"""Declarative wrappers for MCP runtime tools."""

from __future__ import annotations

from typing import Iterable

from mini_agent.agent_core.execution.tools.attributes import DeclarativeToolAttributes, ToolKind
from mini_agent.agent_core.execution.tools.builder import DeclarativeTool, ToolBuilder
from mini_agent.tools.base import Tool, ToolResult
from mini_agent.tools.mcp.naming import mcp_tool_alias


def infer_mcp_tool_attributes(tool_name: str) -> DeclarativeToolAttributes:
    """Infer conservative declarative attributes for MCP tools."""
    normalized = tool_name.strip().lower()
    if normalized.endswith("_list_resources") or normalized.endswith("_read_resource"):
        return DeclarativeToolAttributes(
            kind=ToolKind.READ,
            is_read_only=True,
            concurrency_safe=True,
            always_load=False,
        ).normalized()
    return DeclarativeToolAttributes(
        kind=ToolKind.NETWORK,
        is_read_only=False,
        concurrency_safe=False,
        should_defer=True,
        always_load=False,
    ).normalized()


def build_declarative_mcp_registry(server_name: str, tools: Iterable[Tool]) -> dict[str, DeclarativeTool]:
    """Build a namespaced declarative registry for one MCP server."""
    registry: dict[str, DeclarativeTool] = {}
    for tool in tools:
        alias = mcp_tool_alias(server_name, tool.name)
        attributes = infer_mcp_tool_attributes(tool.name)

        async def _execute(arguments: dict, runtime_tool: Tool = tool) -> ToolResult:
            return await runtime_tool.execute(**arguments)

        registry[alias] = ToolBuilder.from_callable(
            name=alias,
            description=f"[MCP:{server_name}] {tool.description}",
            schema=dict(tool.parameters),
            execute=_execute,
            attributes=attributes,
        )
    return registry
