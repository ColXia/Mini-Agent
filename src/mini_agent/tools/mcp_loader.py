"""MCP tool loader facade backed by the modular MCP package."""

from __future__ import annotations

from .mcp.discovery import resolve_mcp_config_path
from .mcp.lifecycle import cleanup_mcp_connections, get_mcp_timeout_config, set_mcp_timeout_config
from .mcp.registry import MCPServerConnection, load_mcp_tools_async
from .mcp.types import MCPTimeoutConfig, determine_connection_type, resolve_env_vars


def _determine_connection_type(server_config: dict):
    return determine_connection_type(server_config)


def _resolve_env_vars(env_config: dict):
    return resolve_env_vars(env_config)


def _resolve_mcp_config_path(config_path: str):
    return resolve_mcp_config_path(config_path)


__all__ = [
    "MCPServerConnection",
    "MCPTimeoutConfig",
    "_determine_connection_type",
    "_resolve_env_vars",
    "_resolve_mcp_config_path",
    "cleanup_mcp_connections",
    "get_mcp_timeout_config",
    "load_mcp_tools_async",
    "set_mcp_timeout_config",
]

