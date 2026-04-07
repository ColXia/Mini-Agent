"""MCP profile import/export mapping and safe config writes."""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Literal


MCPProfileFormat = Literal["auto", "internal", "codex", "claude", "gemini"]


def _now_suffix() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")


def _normalize_server_config(raw: dict[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    for key in [
        "type",
        "command",
        "args",
        "env",
        "url",
        "headers",
        "disabled",
        "connect_timeout",
        "execute_timeout",
        "sse_read_timeout",
        "policy",
    ]:
        if key in raw:
            normalized[key] = raw[key]
    return normalized


def normalize_mcp_profile(payload: dict[str, Any], source: MCPProfileFormat = "auto") -> dict[str, Any]:
    """Normalize profile payload into internal `{mcpServers:{...}}` format."""
    if source in {"auto", "internal", "codex", "claude"} and isinstance(payload.get("mcpServers"), dict):
        servers = payload.get("mcpServers", {})
        return {
            "mcpServers": {
                str(name): _normalize_server_config(config if isinstance(config, dict) else {})
                for name, config in servers.items()
            }
        }

    if source in {"auto", "gemini"} and isinstance(payload.get("servers"), list):
        servers_map: dict[str, dict[str, Any]] = {}
        for item in payload["servers"]:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str) or not name.strip():
                continue
            server_config = dict(item)
            server_config.pop("name", None)
            servers_map[name] = _normalize_server_config(server_config)
        return {"mcpServers": servers_map}

    raise ValueError("Unsupported MCP profile format.")


def export_mcp_profile(payload: dict[str, Any], target: MCPProfileFormat) -> dict[str, Any]:
    """Export internal profile payload to target format."""
    normalized = normalize_mcp_profile(payload, source="auto")
    servers = normalized.get("mcpServers", {})

    if target in {"internal", "codex", "claude"}:
        return {"mcpServers": servers}

    if target == "gemini":
        server_list = []
        for name, config in servers.items():
            row = {"name": name}
            if isinstance(config, dict):
                row.update(config)
            server_list.append(row)
        return {"servers": server_list}

    raise ValueError(f"Unsupported target profile format: {target}")


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def atomic_write_mcp_profile(
    path: str | Path,
    payload: dict[str, Any],
    *,
    backup: bool = True,
) -> Path | None:
    """Write MCP config atomically with optional backup rollback anchor."""
    file_path = Path(path).expanduser().resolve()
    backup_path: Path | None = None

    if backup and file_path.exists():
        backup_path = file_path.with_suffix(file_path.suffix + f".bak.{_now_suffix()}")
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(file_path, backup_path)

    try:
        _atomic_write_text(file_path, json.dumps(payload, ensure_ascii=False, indent=2))
    except Exception:
        # If write fails after backup creation, best effort rollback.
        if backup_path and backup_path.exists():
            try:
                shutil.copy2(backup_path, file_path)
            except Exception:
                pass
        raise

    return backup_path


def load_mcp_profile(path: str | Path) -> dict[str, Any]:
    """Load MCP profile JSON with UTF-8/UTF-8-BOM tolerance."""
    file_path = Path(path).expanduser().resolve()
    with open(file_path, encoding="utf-8-sig") as f:
        payload = json.load(f)
    if not isinstance(payload, dict):
        raise ValueError("MCP profile must be a JSON object.")
    return payload


def update_mcp_profile(
    path: str | Path,
    updater: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    backup: bool = True,
) -> Path | None:
    """Read-update-write MCP profile atomically."""
    current = load_mcp_profile(path)
    updated = updater(current)
    if not isinstance(updated, dict):
        raise ValueError("Updater must return a JSON object.")
    return atomic_write_mcp_profile(path, updated, backup=backup)

