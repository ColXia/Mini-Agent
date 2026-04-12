"""MCP lifecycle state (timeouts + live connections)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .types import MCPTimeoutConfig

if TYPE_CHECKING:
    from .registry import MCPServerConnection


_default_timeout_config = MCPTimeoutConfig()
_mcp_connections: list["MCPServerConnection"] = []


def set_mcp_timeout_config(
    connect_timeout: float | None = None,
    execute_timeout: float | None = None,
    sse_read_timeout: float | None = None,
) -> None:
    if connect_timeout is not None:
        _default_timeout_config.connect_timeout = connect_timeout
    if execute_timeout is not None:
        _default_timeout_config.execute_timeout = execute_timeout
    if sse_read_timeout is not None:
        _default_timeout_config.sse_read_timeout = sse_read_timeout


def get_mcp_timeout_config() -> MCPTimeoutConfig:
    return _default_timeout_config


def register_connection(connection: "MCPServerConnection") -> None:
    _mcp_connections.append(connection)


def clear_registered_connections() -> None:
    _mcp_connections.clear()


def get_registered_connections() -> list["MCPServerConnection"]:
    return list(_mcp_connections)


async def cleanup_mcp_connections() -> None:
    connections = list(_mcp_connections)
    _mcp_connections.clear()
    for connection in connections:
        try:
            await connection.disconnect()
        except asyncio.CancelledError:
            continue
        except Exception:
            continue

