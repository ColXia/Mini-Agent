"""Shared MCP loader types and config parsing helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Literal


ConnectionType = Literal["stdio", "sse", "http", "streamable_http"]


@dataclass
class MCPTimeoutConfig:
    """MCP timeout configuration."""

    connect_timeout: float = 10.0
    execute_timeout: float = 60.0
    sse_read_timeout: float = 120.0


@dataclass
class MCPServerPolicy:
    """Per-server policy for MCP loading and exposure."""

    allow: set[str] | None = None
    exclude: set[str] | None = None
    trust: bool = False
    enable_resources: bool = False

    def allows(self, tool_name: str) -> bool:
        if self.allow is not None and tool_name not in self.allow:
            return False
        if self.exclude is not None and tool_name in self.exclude:
            return False
        return True


@dataclass
class MCPServerDefinition:
    """Normalized MCP server config loaded from JSON."""

    name: str
    connection_type: ConnectionType = "stdio"
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    url: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    connect_timeout: float | None = None
    execute_timeout: float | None = None
    sse_read_timeout: float | None = None
    policy: MCPServerPolicy = field(default_factory=MCPServerPolicy)


def determine_connection_type(server_config: dict[str, Any]) -> ConnectionType:
    """Determine connection type from server config."""
    explicit_type = str(server_config.get("type", "")).lower().strip()
    if explicit_type in ("stdio", "sse", "http", "streamable_http"):
        return explicit_type  # type: ignore[return-value]
    if server_config.get("url"):
        return "streamable_http"
    return "stdio"


def resolve_env_vars(env_config: dict[str, Any]) -> dict[str, str]:
    """Resolve env var placeholders in mcp.json env config."""
    resolved: dict[str, str] = {}

    for key, raw_value in env_config.items():
        value = str(raw_value) if raw_value is not None else ""
        ref_name: str | None = None

        if value.startswith("${") and value.endswith("}") and len(value) > 3:
            ref_name = value[2:-1]
        elif value.startswith("$") and len(value) > 1:
            ref_name = value[1:]
        elif value.startswith("%") and value.endswith("%") and len(value) > 2:
            ref_name = value[1:-1]
        elif value in os.environ:
            ref_name = value

        if ref_name and ref_name in os.environ:
            resolved[str(key)] = os.environ[ref_name]
        else:
            resolved[str(key)] = value

    return resolved


def to_float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return None


def _to_string_set(value: Any) -> set[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        parts = [segment.strip() for segment in value.split(",")]
        normalized = {segment for segment in parts if segment}
        return normalized or None
    if isinstance(value, list):
        normalized = {str(item).strip() for item in value if str(item).strip()}
        return normalized or None
    return None


def parse_policy(raw: dict[str, Any] | None, default: MCPServerPolicy | None = None) -> MCPServerPolicy:
    """Parse policy block with optional defaults."""
    default = default or MCPServerPolicy()
    raw = raw or {}

    allow = _to_string_set(raw.get("allow"))
    if allow is None:
        allow = _to_string_set(raw.get("allow_tools"))
    if allow is None:
        allow = default.allow

    exclude = _to_string_set(raw.get("exclude"))
    if exclude is None:
        exclude = _to_string_set(raw.get("exclude_tools"))
    if exclude is None:
        exclude = default.exclude

    trust_raw = raw.get("trust")
    if trust_raw is None:
        trust = default.trust
    elif isinstance(trust_raw, bool):
        trust = trust_raw
    else:
        trust = str(trust_raw).strip().lower() in {"1", "true", "yes", "on"}

    resources_raw = raw.get("enable_resources")
    if resources_raw is None:
        resources_raw = raw.get("resources")
    if resources_raw is None:
        enable_resources = default.enable_resources
    elif isinstance(resources_raw, bool):
        enable_resources = resources_raw
    else:
        enable_resources = str(resources_raw).strip().lower() in {"1", "true", "yes", "on"}

    return MCPServerPolicy(
        allow=allow,
        exclude=exclude,
        trust=trust,
        enable_resources=enable_resources,
    )

