"""Declarative tool system primitives for agent-core execution."""

from mini_agent.agent_core.execution.tools.attributes import (
    DeclarativeToolAttributes,
    InterruptBehavior,
    ToolKind,
)
from mini_agent.agent_core.execution.tools.builder import (
    DeclarativeTool,
    ToolBuilder,
    build_declarative_registry,
    infer_attributes_from_tool_name,
)
from mini_agent.agent_core.execution.tools.invocation import ToolInvocation
from mini_agent.agent_core.execution.tools.runtime_adapter import (
    DeclarativeToolAdapter,
    adapt_declarative_tools,
    build_runtime_adapter_path,
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
