"""MCP loader package split into discovery/registry/executor/lifecycle."""

from .discovery import discover_servers, load_mcp_config, resolve_mcp_config_path
from .lifecycle import (
    cleanup_mcp_connections,
    get_mcp_timeout_config,
    set_mcp_timeout_config,
)
from .registry import MCPServerConnection, load_mcp_tools_async
from .types import (
    ConnectionType,
    MCPServerDefinition,
    MCPServerPolicy,
    MCPTimeoutConfig,
    determine_connection_type,
    parse_policy,
    resolve_env_vars,
)

__all__ = [
    "ConnectionType",
    "MCPServerConnection",
    "MCPServerDefinition",
    "MCPServerPolicy",
    "MCPTimeoutConfig",
    "cleanup_mcp_connections",
    "determine_connection_type",
    "discover_servers",
    "get_mcp_timeout_config",
    "load_mcp_config",
    "load_mcp_tools_async",
    "parse_policy",
    "resolve_env_vars",
    "resolve_mcp_config_path",
    "set_mcp_timeout_config",
]

