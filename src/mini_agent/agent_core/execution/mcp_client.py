"""Agent-core execution MCP client baseline (discovery + invocation + wrapper)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from mini_agent.agent_core.execution.mcp_tools import build_declarative_mcp_registry
from mini_agent.agent_core.execution.tools.builder import DeclarativeTool
from mini_agent.tools.base import Tool, ToolResult
from mini_agent.tools.mcp.discovery import discover_servers
from mini_agent.tools.mcp.registry import MCPServerConnection
from mini_agent.tools.mcp.types import MCPServerDefinition


@dataclass(frozen=True)
class MCPToolDescriptor:
    """Compact MCP tool metadata used by agent execution flows."""

    server_name: str
    tool_name: str
    description: str
    schema: dict[str, Any]


DiscoveryFn = Callable[[str], tuple[Path | None, list[MCPServerDefinition]]]
ConnectionFactory = Callable[..., MCPServerConnection]


class ExecutionMCPClient:
    """Lean MCP client manager for agent-core execution workflows."""

    def __init__(
        self,
        *,
        config_path: str = "mcp.json",
        discover_fn: DiscoveryFn = discover_servers,
        connection_factory: ConnectionFactory = MCPServerConnection,
    ) -> None:
        self.config_path = config_path
        self._discover_fn = discover_fn
        self._connection_factory = connection_factory
        self._connections: dict[str, MCPServerConnection] = {}

    @property
    def connections(self) -> dict[str, MCPServerConnection]:
        return dict(self._connections)

    async def connect(self) -> dict[str, bool]:
        """Connect all configured MCP servers and return status by name."""
        _, definitions = self._discover_fn(self.config_path)
        statuses: dict[str, bool] = {}

        for server in definitions:
            connection = self._connection_factory(
                name=server.name,
                connection_type=server.connection_type,
                command=server.command,
                args=server.args,
                env=server.env,
                url=server.url,
                headers=server.headers,
                connect_timeout=server.connect_timeout,
                execute_timeout=server.execute_timeout,
                sse_read_timeout=server.sse_read_timeout,
                policy=server.policy,
            )
            success = await connection.connect()
            statuses[server.name] = success
            if success:
                self._connections[server.name] = connection
        return statuses

    async def disconnect(self) -> None:
        """Disconnect all active MCP servers managed by this client."""
        for connection in list(self._connections.values()):
            await connection.disconnect()
        self._connections.clear()

    def list_tools(self, server_name: str | None = None) -> list[MCPToolDescriptor]:
        """List MCP tools for one server or all connected servers."""
        descriptors: list[MCPToolDescriptor] = []
        for current_server, connection in self._connections.items():
            if server_name and current_server != server_name:
                continue
            for tool in connection.tools:
                descriptors.append(
                    MCPToolDescriptor(
                        server_name=current_server,
                        tool_name=tool.name,
                        description=tool.description,
                        schema=dict(tool.parameters),
                    )
                )
        return descriptors

    def list_runtime_tools(self, server_name: str | None = None) -> list[Tool]:
        """Expose raw runtime MCP tools."""
        tools: list[Tool] = []
        for current_server, connection in self._connections.items():
            if server_name and current_server != server_name:
                continue
            tools.extend(connection.tools)
        return tools

    async def call_tool(
        self,
        *,
        server_name: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
    ) -> ToolResult:
        """Invoke one MCP tool from an active server."""
        connection = self._connections.get(server_name)
        if connection is None:
            return ToolResult(success=False, content="", error=f"MCP server not connected: {server_name}")

        tool = next((item for item in connection.tools if item.name == tool_name), None)
        if tool is None:
            return ToolResult(
                success=False,
                content="",
                error=f"MCP tool '{tool_name}' not found on server '{server_name}'.",
            )

        try:
            return await tool.execute(**dict(arguments or {}))
        except Exception as exc:
            return ToolResult(success=False, content="", error=f"MCP tool invocation failed: {exc}")

    def build_declarative_registry(self, server_name: str | None = None) -> dict[str, DeclarativeTool]:
        """Build namespaced declarative wrappers for connected MCP tools."""
        registry: dict[str, DeclarativeTool] = {}
        for current_server, connection in self._connections.items():
            if server_name and current_server != server_name:
                continue
            registry.update(build_declarative_mcp_registry(current_server, connection.tools))
        return registry
