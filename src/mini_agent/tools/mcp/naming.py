"""Shared naming helpers for runtime-exposed MCP tools."""

from __future__ import annotations

import re


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "").strip().lower())
    return normalized.strip("_") or "mcp"


def mcp_tool_alias(server_name: str, tool_name: str) -> str:
    """Build deterministic namespaced alias for an MCP tool."""
    return f"mcp_{_slug(server_name)}_{_slug(tool_name)}"


def reserve_mcp_tool_alias(
    server_name: str,
    tool_name: str,
    reserved_aliases: set[str] | None = None,
) -> str:
    """Reserve one unique alias, suffixing when slug collisions happen."""
    aliases = reserved_aliases if reserved_aliases is not None else set()
    base = mcp_tool_alias(server_name, tool_name)
    candidate = base
    suffix = 2
    while candidate in aliases:
        candidate = f"{base}_{suffix}"
        suffix += 1
    aliases.add(candidate)
    return candidate


def format_mcp_tool_label(alias_name: str, raw_name: str | None = None) -> str:
    """Render one operator/model-facing MCP tool label."""
    normalized_alias = str(alias_name or "").strip()
    normalized_raw = str(raw_name or "").strip()
    if normalized_raw and normalized_raw != normalized_alias:
        return f"{normalized_alias} <- {normalized_raw}"
    return normalized_alias or normalized_raw


__all__ = [
    "format_mcp_tool_label",
    "mcp_tool_alias",
    "reserve_mcp_tool_alias",
]
