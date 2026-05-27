"""MCP tool loader facade backed by the modular MCP package.

This module provides a stable import surface for MCP functionality.
It is intentionally kept as a facade to avoid breaking 16+ import sites
across production code, tests, and scripts.

Import from here for external consumers; internal MCP code should import
directly from tools/mcp/* subpackage.
"""

from __future__ import annotations

from .mcp.discovery import resolve_mcp_config_path
from .mcp.lifecycle import cleanup_mcp_connections, get_mcp_timeout_config, set_mcp_timeout_config
from .mcp.registry import MCPServerConnection, load_mcp_tools_async
from .mcp.types import MCPTimeoutConfig, determine_connection_type


def _determine_connection_type(server_config: dict):
    return determine_connection_type(server_config)


def _resolve_mcp_config_path(config_path: str):
    return resolve_mcp_config_path(config_path)


__all__ = [
    "MCPServerConnection",
    "MCPTimeoutConfig",
    "_determine_connection_type",
    "_resolve_mcp_config_path",
    "cleanup_mcp_connections",
    "get_mcp_timeout_config",
    "load_mcp_tools_async",
    "set_mcp_timeout_config",
]

