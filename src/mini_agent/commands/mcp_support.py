"""Shared helpers for operator-facing `/mcp` commands."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from mini_agent.config import Config
from mini_agent.tools.mcp.discovery import discover_servers
from mini_agent.tools.mcp.lifecycle import get_registered_connections
from mini_agent.tools.mcp.naming import format_mcp_tool_label
from mini_agent.tools.mcp.types import determine_connection_type, parse_policy


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _connection_tool_label(tool: Any) -> str:
    alias_name = _clean_text(getattr(tool, "name", None))
    raw_name = _clean_text(
        getattr(tool, "remote_name", None)
        or getattr(tool, "raw_name", None)
    )
    return format_mcp_tool_label(alias_name, raw_name)


def resolve_runtime_mcp_config_path(config: Any) -> Path | None:
    raw = _clean_text(getattr(getattr(config, "tools", None), "mcp_config_path", None)) or "mcp.json"
    candidate = Path(raw).expanduser()

    direct_candidates: list[Path] = []
    if candidate.is_absolute():
        direct_candidates.append(candidate)
    else:
        direct_candidates.append((Path.cwd() / candidate).resolve())

    for item in direct_candidates:
        if item.exists():
            return item.resolve()

    found = Config.find_config_file(candidate.name or raw)
    if found is not None:
        return found.resolve()

    if (candidate.name or raw).lower() == "mcp.json":
        example = Config.find_config_file("mcp-example.json")
        if example is not None:
            return example.resolve()

    return None


@dataclass(frozen=True)
class MCPOperatorServerState:
    name: str
    connection_type: str
    disabled: bool
    trust: bool
    active: bool
    tool_names: tuple[str, ...]
    target: str


@dataclass(frozen=True)
class MCPOperatorSnapshot:
    enabled: bool
    config_path: str | None
    using_template: bool
    configured_total: int
    discoverable_total: int
    disabled_total: int
    active_total: int
    tool_total: int
    servers: tuple[MCPOperatorServerState, ...]


def collect_mcp_operator_snapshot(config: Any) -> MCPOperatorSnapshot:
    enabled = bool(getattr(getattr(config, "tools", None), "enable_mcp", False))
    resolved_path = resolve_runtime_mcp_config_path(config)
    using_template = bool(resolved_path and resolved_path.name.lower() == "mcp-example.json")

    raw_servers: dict[str, dict[str, Any]] = {}
    definitions_by_name: dict[str, Any] = {}
    if resolved_path is not None and resolved_path.exists():
        try:
            payload = json.loads(resolved_path.read_text(encoding="utf-8-sig"))
        except Exception:
            payload = {}
        if isinstance(payload, dict) and isinstance(payload.get("mcpServers"), dict):
            raw_servers = {
                str(name): dict(config) if isinstance(config, dict) else {}
                for name, config in payload.get("mcpServers", {}).items()
            }
        _path, definitions = discover_servers(str(resolved_path))
        definitions_by_name = {item.name: item for item in definitions}

    connections = get_registered_connections()
    active_by_name = {str(getattr(item, "name", "")).strip(): item for item in connections}

    server_names = sorted(set(raw_servers) | set(definitions_by_name) | set(active_by_name), key=str.casefold)
    servers: list[MCPOperatorServerState] = []
    for name in server_names:
        raw = raw_servers.get(name, {})
        definition = definitions_by_name.get(name)
        connection = active_by_name.get(name)
        disabled = bool(raw.get("disabled", False))
        connection_type = (
            _clean_text(getattr(definition, "connection_type", None))
            or _clean_text(getattr(connection, "connection_type", None))
            or determine_connection_type(raw if isinstance(raw, dict) else {})
        )
        policy = (
            getattr(definition, "policy", None)
            or parse_policy(raw.get("policy") if isinstance(raw.get("policy"), dict) else raw)
        )
        target = (
            _clean_text(getattr(definition, "url", None))
            or _clean_text(getattr(definition, "command", None))
            or _clean_text(raw.get("url"))
            or _clean_text(raw.get("command"))
        )
        tool_names = tuple(
            _connection_tool_label(tool)
            for tool in list(getattr(connection, "tools", []) or [])
            if _connection_tool_label(tool)
        )
        servers.append(
            MCPOperatorServerState(
                name=name,
                connection_type=connection_type or "stdio",
                disabled=disabled,
                trust=bool(getattr(policy, "trust", False)),
                active=connection is not None,
                tool_names=tool_names,
                target=target,
            )
        )

    disabled_total = sum(1 for item in servers if item.disabled)
    active_total = sum(1 for item in servers if item.active)
    tool_total = sum(len(item.tool_names) for item in servers if item.active)
    discoverable_total = sum(1 for item in servers if not item.disabled)
    return MCPOperatorSnapshot(
        enabled=enabled,
        config_path=str(resolved_path) if resolved_path is not None else None,
        using_template=using_template,
        configured_total=len(servers),
        discoverable_total=discoverable_total,
        disabled_total=disabled_total,
        active_total=active_total,
        tool_total=tool_total,
        servers=tuple(servers),
    )


def format_mcp_status(snapshot: MCPOperatorSnapshot) -> str:
    lines = [
        "MCP Status:",
        f"- enabled {'yes' if snapshot.enabled else 'no'}",
        f"- config {snapshot.config_path or '(missing)'}",
    ]
    if snapshot.using_template:
        lines[-1] += " [template]"
    lines.extend(
        [
            f"- configured {snapshot.configured_total}",
            f"- discoverable {snapshot.discoverable_total}",
            f"- disabled {snapshot.disabled_total}",
            f"- active {snapshot.active_total}",
            f"- exposed tools {snapshot.tool_total}",
        ]
    )
    return "\n".join(lines)


def format_mcp_server_list(snapshot: MCPOperatorSnapshot) -> str:
    if not snapshot.servers:
        return "No MCP servers configured."

    lines = ["MCP Servers:"]
    for item in snapshot.servers:
        status = "active" if item.active else ("disabled" if item.disabled else "configured")
        trust = "trusted" if item.trust else "untrusted"
        lines.append(f"- {item.name} [{item.connection_type}] {status} | {trust}")
        if item.target:
            lines.append(f"  target: {item.target}")
        if item.active and item.tool_names:
            lines.append(f"  tools: {', '.join(item.tool_names)}")
        elif item.active:
            lines.append("  tools: (connected, no exposed tools)")
    return "\n".join(lines)


__all__ = [
    "MCPOperatorServerState",
    "MCPOperatorSnapshot",
    "collect_mcp_operator_snapshot",
    "format_mcp_server_list",
    "format_mcp_status",
    "resolve_runtime_mcp_config_path",
]
