"""Tests for MCP profile import/export mapping and atomic writes."""

import json
from pathlib import Path

import pytest

from mini_agent.tools.mcp_profile_sync import (
    atomic_write_mcp_profile,
    export_mcp_profile,
    load_mcp_profile,
    normalize_mcp_profile,
    update_mcp_profile,
)


def test_normalize_gemini_profile_to_internal():
    gemini_payload = {
        "servers": [
            {
                "name": "memory",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-memory"],
                "disabled": True,
            }
        ]
    }

    normalized = normalize_mcp_profile(gemini_payload, source="gemini")
    assert "mcpServers" in normalized
    assert "memory" in normalized["mcpServers"]
    assert normalized["mcpServers"]["memory"]["command"] == "npx"


def test_export_internal_to_gemini_profile():
    internal = {
        "mcpServers": {
            "demo": {
                "command": "uvx",
                "args": ["demo-server"],
            }
        }
    }

    exported = export_mcp_profile(internal, target="gemini")
    assert isinstance(exported.get("servers"), list)
    assert exported["servers"][0]["name"] == "demo"
    assert exported["servers"][0]["command"] == "uvx"


def test_atomic_write_mcp_profile_with_backup(tmp_path: Path):
    profile_path = tmp_path / "mcp.json"
    profile_path.write_text(json.dumps({"mcpServers": {"a": {"command": "npx"}}}), encoding="utf-8")

    backup_path = atomic_write_mcp_profile(
        profile_path,
        {"mcpServers": {"b": {"command": "uvx"}}},
        backup=True,
    )

    assert backup_path is not None
    assert backup_path.exists()

    loaded = load_mcp_profile(profile_path)
    assert "b" in loaded["mcpServers"]


def test_update_mcp_profile_applies_transform(tmp_path: Path):
    profile_path = tmp_path / "mcp.json"
    profile_path.write_text(json.dumps({"mcpServers": {}}), encoding="utf-8")

    update_mcp_profile(
        profile_path,
        lambda payload: {
            "mcpServers": {
                **payload.get("mcpServers", {}),
                "new_server": {"command": "npx", "args": ["-y", "demo"]},
            }
        },
    )

    updated = load_mcp_profile(profile_path)
    assert "new_server" in updated["mcpServers"]


def test_normalize_profile_rejects_unknown_format():
    with pytest.raises(ValueError):
        normalize_mcp_profile({"foo": "bar"}, source="auto")
