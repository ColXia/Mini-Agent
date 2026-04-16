"""Backward-compatible tool facade over agent-core execution tools."""

from mini_agent.agent_core.execution.tools import (
    DeclarativeTool,
    DeclarativeToolAdapter,
    DeclarativeToolAttributes,
    InterruptBehavior,
    ToolBuilder,
    ToolInvocation,
    ToolKind,
    adapt_declarative_tools,
    build_declarative_registry,
    build_runtime_adapter_path,
    infer_attributes_from_tool_name,
)

__all__ = [
    "ToolKind",
    "InterruptBehavior",
    "DeclarativeToolAttributes",
    "ToolInvocation",
    "DeclarativeTool",
    "ToolBuilder",
    "infer_attributes_from_tool_name",
    "build_declarative_registry",
    "DeclarativeToolAdapter",
    "adapt_declarative_tools",
    "build_runtime_adapter_path",
]
