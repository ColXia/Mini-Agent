"""MCP server connection registry and loader orchestration."""

from __future__ import annotations

import asyncio
from contextlib import AsyncExitStack
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.sse import sse_client
from mcp.client.stdio import stdio_client
from mcp.client.streamable_http import streamablehttp_client

from mini_agent.tools.base import Tool

from .discovery import discover_servers
from .executor import MCPResourceListTool, MCPResourceReadTool, MCPTool
from .lifecycle import get_mcp_timeout_config, register_connection
from .naming import reserve_mcp_tool_alias
from .types import ConnectionType, MCPServerPolicy


class MCPServerConnection:
    """Manages connection to a single MCP server."""

    def __init__(
        self,
        name: str,
        connection_type: ConnectionType = "stdio",
        command: str | None = None,
        args: list[str] | None = None,
        env: dict[str, str] | None = None,
        url: str | None = None,
        headers: dict[str, str] | None = None,
        connect_timeout: float | None = None,
        execute_timeout: float | None = None,
        sse_read_timeout: float | None = None,
        policy: MCPServerPolicy | None = None,
    ):
        self.name = name
        self.connection_type = connection_type
        self.command = command
        self.args = args or []
        self.env = env or {}
        self.url = url
        self.headers = headers or {}
        self.connect_timeout = connect_timeout
        self.execute_timeout = execute_timeout
        self.sse_read_timeout = sse_read_timeout
        self.policy = policy or MCPServerPolicy()

        self.session: ClientSession | None = None
        self.exit_stack: AsyncExitStack | None = None
        self.tools: list[MCPTool | MCPResourceListTool | MCPResourceReadTool] = []
        self.last_error: str | None = None

    def _get_connect_timeout(self) -> float:
        return self.connect_timeout or get_mcp_timeout_config().connect_timeout

    def _get_sse_read_timeout(self) -> float:
        return self.sse_read_timeout or get_mcp_timeout_config().sse_read_timeout

    def _get_execute_timeout(self) -> float:
        return self.execute_timeout or get_mcp_timeout_config().execute_timeout

    async def connect(self, *, reserved_aliases: set[str] | None = None) -> bool:
        self.last_error = None
        if self.connection_type in ("sse", "http", "streamable_http") and not self.policy.trust:
            self.last_error = "Untrusted remote MCP server (policy.trust=false)."
            print(f"[WARN] Skipping untrusted remote MCP server '{self.name}'. Set policy.trust=true to enable.")
            return False

        connect_timeout = self._get_connect_timeout()
        try:
            self.exit_stack = AsyncExitStack()
            async with asyncio.timeout(connect_timeout):
                if self.connection_type == "stdio":
                    read_stream, write_stream = await self._connect_stdio()
                elif self.connection_type == "sse":
                    read_stream, write_stream = await self._connect_sse()
                else:
                    read_stream, write_stream = await self._connect_streamable_http()

                session = await self.exit_stack.enter_async_context(ClientSession(read_stream, write_stream))
                self.session = session
                await session.initialize()
                tools_list = await session.list_tools()

            execute_timeout = self._get_execute_timeout()
            alias_reservations = reserved_aliases if reserved_aliases is not None else set()
            for remote_tool in tools_list.tools:
                name = remote_tool.name
                if not self.policy.allows(name):
                    continue
                parameters = remote_tool.inputSchema if hasattr(remote_tool, "inputSchema") else {}
                self.tools.append(
                    MCPTool(
                        server_name=self.name,
                        remote_name=name,
                        description=remote_tool.description or "",
                        parameters=parameters,
                        session=session,
                        execute_timeout=execute_timeout,
                        expose_name=reserve_mcp_tool_alias(
                            self.name,
                            name,
                            alias_reservations,
                        ),
                    )
                )

            if self.policy.enable_resources:
                self.tools.extend(
                    self._resource_tools(
                        session,
                        execute_timeout,
                        reserved_aliases=alias_reservations,
                    )
                )

            conn_info = self.url if self.url else self.command
            print(
                f"[OK] Connected to MCP server '{self.name}' ({self.connection_type}: {conn_info}) "
                f"- loaded {len(self.tools)} tools"
            )
            return True
        except TimeoutError:
            self.last_error = f"Connection timed out after {connect_timeout}s"
            print(f"[WARN] Connection to MCP server '{self.name}' timed out after {connect_timeout}s")
            if self.exit_stack:
                await self.exit_stack.aclose()
                self.exit_stack = None
            return False
        except asyncio.CancelledError:
            self.last_error = f"Connection cancelled while connecting (timeout={connect_timeout}s)"
            print(
                f"[WARN] Connection to MCP server '{self.name}' was cancelled during startup; "
                "skipping this server."
            )
            if self.exit_stack:
                try:
                    await self.exit_stack.aclose()
                except Exception:
                    pass
                self.exit_stack = None
            self.session = None
            return False
        except Exception as exc:
            self.last_error = str(exc)
            print(f"[ERROR] Failed to connect to MCP server '{self.name}': {exc}")
            if self.exit_stack:
                await self.exit_stack.aclose()
                self.exit_stack = None
            return False

    def _resource_tools(
        self,
        session: ClientSession,
        execute_timeout: float,
        *,
        reserved_aliases: set[str] | None = None,
    ) -> list[Tool]:
        if not hasattr(session, "list_resources") or not hasattr(session, "read_resource"):
            return []
        list_tool = MCPResourceListTool(
            server_name=self.name,
            session=session,
            execute_timeout=execute_timeout,
            expose_name=reserve_mcp_tool_alias(
                self.name,
                "list_resources",
                reserved_aliases,
            ),
        )
        read_tool = MCPResourceReadTool(
            server_name=self.name,
            session=session,
            execute_timeout=execute_timeout,
            expose_name=reserve_mcp_tool_alias(
                self.name,
                "read_resource",
                reserved_aliases,
            ),
        )
        return [list_tool, read_tool]

    async def _connect_stdio(self):
        server_params = StdioServerParameters(
            command=self.command,
            args=self.args,
            env=self.env if self.env else None,
        )
        return await self.exit_stack.enter_async_context(stdio_client(server_params))

    async def _connect_sse(self):
        connect_timeout = self._get_connect_timeout()
        sse_read_timeout = self._get_sse_read_timeout()
        return await self.exit_stack.enter_async_context(
            sse_client(
                url=self.url,
                headers=self.headers if self.headers else None,
                timeout=connect_timeout,
                sse_read_timeout=sse_read_timeout,
            )
        )

    async def _connect_streamable_http(self):
        connect_timeout = self._get_connect_timeout()
        sse_read_timeout = self._get_sse_read_timeout()
        read_stream, write_stream, _ = await self.exit_stack.enter_async_context(
            streamablehttp_client(
                url=self.url,
                headers=self.headers if self.headers else None,
                timeout=connect_timeout,
                sse_read_timeout=sse_read_timeout,
            )
        )
        return read_stream, write_stream

    async def disconnect(self) -> None:
        if self.exit_stack:
            try:
                await self.exit_stack.aclose()
            except Exception:
                pass
            finally:
                self.exit_stack = None
                self.session = None


async def load_mcp_tools_async(config_path: str = "mcp.json") -> list[Tool]:
    """Load MCP tools from config file and active server policies."""
    config_file, servers = discover_servers(config_path)
    if config_file is None:
        print(f"MCP config not found: {config_path}")
        return []

    if not servers:
        print("No MCP servers configured")
        return []

    all_tools: list[Tool] = []
    reserved_aliases: set[str] = set()
    for server in servers:
        connection = MCPServerConnection(
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
        success = await connection.connect(reserved_aliases=reserved_aliases)
        if success:
            register_connection(connection)
            all_tools.extend(connection.tools)

    print(f"\nTotal MCP tools loaded: {len(all_tools)}")
    return all_tools
