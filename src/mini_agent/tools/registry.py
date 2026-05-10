"""Tool registry for managing tool specifications.

This module provides the ToolRegistry for registering and querying ToolSpecs.
It supports namespace-based organization and capability discovery.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mini_agent.tools.contracts import ToolOperationKind, ToolRiskLevel, ToolSpec
from mini_agent.utils.text import safe_text


def _safe_text(value: Any) -> str:
    return safe_text(value)


@dataclass(slots=True)
class ToolRegistry:
    """Registry for tool specifications organized by namespace.

    This registry manages the static tool definitions that belong to the Agent.
    Tools are organized by namespace (e.g., 'core', 'mcp', 'skill') and can
    be queried by name, namespace, or capability.
    """

    _specs: dict[str, ToolSpec] = field(default_factory=dict)
    _namespace_index: dict[str, set[str]] = field(default_factory=dict)

    def register(self, spec: ToolSpec) -> ToolSpec:
        """Register a tool specification.

        Args:
            spec: The ToolSpec to register

        Returns:
            The registered ToolSpec

        Raises:
            ValueError: If a tool with the same full_name already exists
        """
        full_name = spec.full_name
        if full_name in self._specs:
            raise ValueError(f"Tool already registered: {full_name}")
        self._specs[full_name] = spec
        namespace = spec.namespace
        if namespace not in self._namespace_index:
            self._namespace_index[namespace] = set()
        self._namespace_index[namespace].add(full_name)
        return spec

    def unregister(self, tool_name: str, namespace: str | None = None) -> ToolSpec | None:
        """Unregister a tool specification.

        Args:
            tool_name: The tool name (without namespace prefix)
            namespace: Optional namespace; if None, searches all namespaces

        Returns:
            The removed ToolSpec, or None if not found
        """
        if namespace is not None:
            full_name = f"{namespace}.{tool_name}"
            spec = self._specs.pop(full_name, None)
            if spec is not None:
                self._namespace_index.get(namespace, set()).discard(full_name)
            return spec

        for full_name, spec in list(self._specs.items()):
            if spec.tool_name == tool_name:
                self._specs.pop(full_name)
                self._namespace_index.get(spec.namespace, set()).discard(full_name)
                return spec
        return None

    def get(self, tool_name: str, namespace: str | None = None) -> ToolSpec | None:
        """Get a tool specification by name.

        Args:
            tool_name: The tool name (with or without namespace prefix)
            namespace: Optional namespace for disambiguation

        Returns:
            The ToolSpec, or None if not found
        """
        normalized_name = _safe_text(tool_name)
        if not normalized_name:
            return None

        if "." in normalized_name and namespace is None:
            return self._specs.get(normalized_name)

        if namespace is not None:
            full_name = f"{namespace}.{normalized_name}"
            return self._specs.get(full_name)

        for full_name, spec in self._specs.items():
            if spec.tool_name == normalized_name:
                return spec
        return None

    def list_by_namespace(self, namespace: str) -> list[ToolSpec]:
        """List all tools in a namespace.

        Args:
            namespace: The namespace to query

        Returns:
            List of ToolSpecs in the namespace
        """
        normalized_namespace = _safe_text(namespace)
        if not normalized_namespace:
            return []
        full_names = self._namespace_index.get(normalized_namespace, set())
        return [self._specs[full_name] for full_name in full_names if full_name in self._specs]

    def list_by_operation_kind(self, operation_kind: ToolOperationKind) -> list[ToolSpec]:
        """List all tools of a specific operation kind.

        Args:
            operation_kind: The operation kind to filter by

        Returns:
            List of ToolSpecs matching the operation kind
        """
        return [spec for spec in self._specs.values() if spec.operation_kind == operation_kind]

    def list_by_risk_level(self, risk_level: ToolRiskLevel) -> list[ToolSpec]:
        """List all tools of a specific risk level.

        Args:
            risk_level: The risk level to filter by

        Returns:
            List of ToolSpecs matching the risk level
        """
        return [spec for spec in self._specs.values() if spec.default_risk_level == risk_level]

    def list_mutation_tools(self) -> list[ToolSpec]:
        """List all tools that can mutate workspace state.

        Returns:
            List of ToolSpecs that are mutation tools
        """
        return [spec for spec in self._specs.values() if spec.is_mutation]

    def list_all(self) -> list[ToolSpec]:
        """List all registered tools.

        Returns:
            List of all ToolSpecs
        """
        return list(self._specs.values())

    def list_namespaces(self) -> list[str]:
        """List all registered namespaces.

        Returns:
            List of namespace names
        """
        return list(self._namespace_index.keys())

    def has_tool(self, tool_name: str, namespace: str | None = None) -> bool:
        """Check if a tool is registered.

        Args:
            tool_name: The tool name
            namespace: Optional namespace

        Returns:
            True if the tool is registered
        """
        return self.get(tool_name, namespace) is not None

    def clear(self) -> None:
        """Clear all registered tools."""
        self._specs.clear()
        self._namespace_index.clear()

    def __len__(self) -> int:
        """Return the number of registered tools."""
        return len(self._specs)

    def __contains__(self, tool_name: str) -> bool:
        """Check if a tool is registered."""
        return self.has_tool(tool_name)


def build_core_tool_specs() -> list[ToolSpec]:
    """Build the core tool specifications for the main agent.

    Returns:
        List of ToolSpecs for core file/shell/code tools
    """
    return [
        ToolSpec(
            tool_name="read_file",
            namespace="core",
            description="Read file contents from the filesystem with line numbers",
            operation_kind=ToolOperationKind.READ,
            requires_workspace_runtime=True,
            supports_outside_workspace=True,
            supports_mutation_tracking=True,
            default_risk_level=ToolRiskLevel.LOW,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file"},
                    "offset": {"type": "integer", "description": "Starting line number"},
                    "limit": {"type": "integer", "description": "Number of lines to read"},
                },
                "required": ["path"],
            },
        ),
        ToolSpec(
            tool_name="write_file",
            namespace="core",
            description="Write content to a file, overwriting existing content",
            operation_kind=ToolOperationKind.WRITE,
            requires_workspace_runtime=True,
            supports_outside_workspace=False,
            supports_mutation_tracking=True,
            default_risk_level=ToolRiskLevel.MEDIUM,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file"},
                    "content": {"type": "string", "description": "Content to write"},
                },
                "required": ["path", "content"],
            },
        ),
        ToolSpec(
            tool_name="edit_file",
            namespace="core",
            description="Edit a file by replacing exact text",
            operation_kind=ToolOperationKind.EDIT,
            requires_workspace_runtime=True,
            supports_outside_workspace=False,
            supports_mutation_tracking=True,
            default_risk_level=ToolRiskLevel.MEDIUM,
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the file"},
                    "old_str": {"type": "string", "description": "Text to find and replace"},
                    "new_str": {"type": "string", "description": "Replacement text"},
                },
                "required": ["path", "old_str", "new_str"],
            },
        ),
        ToolSpec(
            tool_name="bash",
            namespace="core",
            description="Execute shell commands in the workspace",
            operation_kind=ToolOperationKind.EXECUTE,
            requires_workspace_runtime=True,
            supports_outside_workspace=False,
            supports_mutation_tracking=True,
            default_risk_level=ToolRiskLevel.HIGH,
            input_schema={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Shell command to execute"},
                    "timeout": {"type": "integer", "description": "Timeout in seconds"},
                },
                "required": ["command"],
            },
            timeout_seconds=300,
        ),
    ]


_SHARED_REGISTRY: ToolRegistry | None = None


def shared_tool_registry() -> ToolRegistry:
    """Return the process-local shared tool registry."""
    global _SHARED_REGISTRY
    if _SHARED_REGISTRY is None:
        _SHARED_REGISTRY = ToolRegistry()
        for spec in build_core_tool_specs():
            _SHARED_REGISTRY.register(spec)
    return _SHARED_REGISTRY


def clear_shared_tool_registry() -> None:
    """Clear the process-local shared tool registry."""
    global _SHARED_REGISTRY
    if _SHARED_REGISTRY is not None:
        _SHARED_REGISTRY.clear()
    _SHARED_REGISTRY = None


__all__ = [
    "build_core_tool_specs",
    "clear_shared_tool_registry",
    "shared_tool_registry",
    "ToolRegistry",
]