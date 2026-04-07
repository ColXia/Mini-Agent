"""MCP config discovery and normalization."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .types import (
    MCPServerDefinition,
    MCPServerPolicy,
    determine_connection_type,
    parse_policy,
    resolve_env_vars,
    to_float_or_none,
)


def resolve_mcp_config_path(config_path: str) -> Path | None:
    """Resolve MCP config path with fallback to `mcp-example.json`."""
    config_file = Path(config_path)
    if config_file.exists():
        return config_file

    if config_file.name == "mcp.json":
        example_file = config_file.parent / "mcp-example.json"
        if example_file.exists():
            print(f"mcp.json not found, using template: {example_file}")
            return example_file
    return None


def load_mcp_config(config_path: str) -> tuple[Path | None, dict[str, Any]]:
    config_file = resolve_mcp_config_path(config_path)
    if config_file is None:
        return None, {}

    with open(config_file, encoding="utf-8-sig") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        return config_file, {}
    return config_file, payload


def discover_servers(config_path: str) -> tuple[Path | None, list[MCPServerDefinition]]:
    config_file, config = load_mcp_config(config_path)
    if config_file is None:
        return None, []

    mcp_servers = config.get("mcpServers", {})
    if not isinstance(mcp_servers, dict):
        return config_file, []

    global_policy = parse_policy(config.get("policy") if isinstance(config.get("policy"), dict) else {})
    definitions: list[MCPServerDefinition] = []

    for server_name, raw_config in mcp_servers.items():
        if not isinstance(raw_config, dict):
            continue
        if raw_config.get("disabled", False):
            print(f"Skipping disabled server: {server_name}")
            continue

        conn_type = determine_connection_type(raw_config)
        url = raw_config.get("url")
        command = raw_config.get("command")

        if conn_type == "stdio" and not command:
            print(f"No command specified for STDIO server: {server_name}")
            continue
        if conn_type in ("sse", "http", "streamable_http") and not url:
            print(f"No url specified for {conn_type.upper()} server: {server_name}")
            continue

        local_policy_source = raw_config.get("policy") if isinstance(raw_config.get("policy"), dict) else raw_config
        policy = parse_policy(local_policy_source, default=global_policy)
        if conn_type == "stdio" and not policy.trust:
            # Local stdio servers are treated as trusted by default unless explicitly disabled.
            policy = MCPServerPolicy(
                allow=policy.allow,
                exclude=policy.exclude,
                trust=True,
                enable_resources=policy.enable_resources,
            )

        definition = MCPServerDefinition(
            name=str(server_name),
            connection_type=conn_type,
            command=str(command) if command is not None else None,
            args=[str(item) for item in raw_config.get("args", [])] if isinstance(raw_config.get("args"), list) else [],
            env=resolve_env_vars(raw_config.get("env", {}) if isinstance(raw_config.get("env"), dict) else {}),
            url=str(url) if url is not None else None,
            headers={
                str(k): str(v)
                for k, v in (raw_config.get("headers", {}) if isinstance(raw_config.get("headers"), dict) else {}).items()
            },
            connect_timeout=to_float_or_none(raw_config.get("connect_timeout")),
            execute_timeout=to_float_or_none(raw_config.get("execute_timeout")),
            sse_read_timeout=to_float_or_none(raw_config.get("sse_read_timeout")),
            policy=policy,
        )
        definitions.append(definition)

    return config_file, definitions

