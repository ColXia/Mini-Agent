"""Declarative tool builder and schema-first runtime registry helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Mapping

from mini_agent.code_agent.tools.attributes import DeclarativeToolAttributes, ToolKind
from mini_agent.code_agent.tools.invocation import ToolInvocation
from mini_agent.tools.base import Tool, ToolResult


_READ_ONLY_TOOL_NAMES = {
    "read_file",
    "recall_notes",
    "get_skill",
    "bash_output",
    "list_dir",
    "glob",
    "grep",
}

_DESTRUCTIVE_TOOL_NAMES = {
    "write_file",
    "edit_file",
    "bash_kill",
}

_CONCURRENCY_SAFE_TOOL_NAMES = {
    "read_file",
    "recall_notes",
    "bash_output",
    "list_dir",
    "glob",
    "grep",
}

_ALWAYS_LOAD_TOOL_NAMES = {
    "read_file",
    "bash",
}

_TOOL_KIND_BY_NAME: dict[str, ToolKind] = {
    "read_file": ToolKind.READ,
    "write_file": ToolKind.WRITE,
    "edit_file": ToolKind.EDIT,
    "bash": ToolKind.EXECUTE,
    "bash_output": ToolKind.READ,
    "bash_kill": ToolKind.EXECUTE,
    "record_note": ToolKind.EDIT,
    "recall_notes": ToolKind.READ,
    "user_modeling": ToolKind.EDIT,
    "get_skill": ToolKind.READ,
}


def infer_attributes_from_tool_name(tool_name: str) -> DeclarativeToolAttributes:
    """Infer lightweight declarative attributes from a tool name."""
    normalized_name = tool_name.strip().lower()
    kind = _TOOL_KIND_BY_NAME.get(normalized_name, ToolKind.OTHER)
    read_only = normalized_name in _READ_ONLY_TOOL_NAMES
    return DeclarativeToolAttributes(
        kind=kind,
        is_read_only=read_only,
        concurrency_safe=normalized_name in _CONCURRENCY_SAFE_TOOL_NAMES,
        destructive=normalized_name in _DESTRUCTIVE_TOOL_NAMES,
        always_load=normalized_name in _ALWAYS_LOAD_TOOL_NAMES,
    ).normalized()


@dataclass(frozen=True)
class DeclarativeTool:
    """Schema-first tool contract with invocation builder."""

    name: str
    description: str
    schema: dict[str, Any]
    attributes: DeclarativeToolAttributes = field(default_factory=DeclarativeToolAttributes)
    executor: Any = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Declarative tool name must not be empty.")
        if not isinstance(self.schema, dict):
            raise TypeError("Declarative tool schema must be a dict.")
        if self.executor is None:
            raise ValueError("Declarative tool executor is required.")

    def build(self, params: Mapping[str, Any]) -> ToolInvocation:
        """Build a concrete invocation from raw arguments."""
        return ToolInvocation(
            tool_name=self.name,
            schema=self.schema,
            arguments=dict(params),
            executor=self.executor,
            attributes=self.attributes.normalized(),
        )

    def to_openai_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.schema,
            },
        }

    def to_anthropic_schema(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.schema,
        }


class ToolBuilder:
    """Builder helpers for declarative tool contracts."""

    @staticmethod
    def from_tool(tool: Tool, *, attributes: DeclarativeToolAttributes | None = None) -> DeclarativeTool:
        inferred = attributes or infer_attributes_from_tool_name(tool.name)

        async def _execute(arguments: dict[str, Any]) -> ToolResult:
            return await tool.execute(**arguments)

        return DeclarativeTool(
            name=tool.name,
            description=tool.description,
            schema=dict(tool.parameters),
            attributes=inferred.normalized(),
            executor=_execute,
        )

    @staticmethod
    def from_callable(
        *,
        name: str,
        description: str,
        schema: Mapping[str, Any],
        execute: Any,
        attributes: DeclarativeToolAttributes | None = None,
    ) -> DeclarativeTool:
        return DeclarativeTool(
            name=name,
            description=description,
            schema=dict(schema),
            attributes=(attributes or DeclarativeToolAttributes()).normalized(),
            executor=execute,
        )


def build_declarative_registry(tools: Iterable[Tool]) -> dict[str, DeclarativeTool]:
    """Build a declarative tool registry keyed by tool name."""
    registry: dict[str, DeclarativeTool] = {}
    for tool in tools:
        declarative_tool = ToolBuilder.from_tool(tool)
        registry[declarative_tool.name] = declarative_tool
    return registry
