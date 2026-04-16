"""Runtime adapter path between classic Tool objects and declarative tools."""

from __future__ import annotations

from typing import Iterable

from mini_agent.agent_core.execution.tools.builder import DeclarativeTool, build_declarative_registry
from mini_agent.tools.base import Tool, ToolResult


class DeclarativeToolAdapter(Tool):
    """Adapter that lets a declarative contract run in the classic Tool runtime."""

    def __init__(self, declarative_tool: DeclarativeTool):
        self._declarative_tool = declarative_tool

    @property
    def name(self) -> str:
        return self._declarative_tool.name

    @property
    def description(self) -> str:
        return self._declarative_tool.description

    @property
    def parameters(self) -> dict:
        return self._declarative_tool.schema

    async def execute(self, *args, **kwargs) -> ToolResult:  # type: ignore
        invocation = self._declarative_tool.build(kwargs)
        return await invocation.execute()


def adapt_declarative_tools(tools: Iterable[DeclarativeTool]) -> list[Tool]:
    """Convert declarative tool contracts into runtime Tool adapters."""
    return [DeclarativeToolAdapter(tool) for tool in tools]


def build_runtime_adapter_path(tools: Iterable[Tool]) -> tuple[list[Tool], dict[str, DeclarativeTool]]:
    """Build declarative registry and runtime adapters in one pass."""
    registry = build_declarative_registry(tools)
    adapters = adapt_declarative_tools(registry.values())
    return adapters, registry
