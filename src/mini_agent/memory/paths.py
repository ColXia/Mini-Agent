"""Shared filesystem path helpers for memory-related state."""

from __future__ import annotations

import os
from pathlib import Path


def resolve_mini_agent_home() -> Path:
    """Resolve the user-level Mini-Agent home directory."""
    configured = str(os.getenv("MINI_AGENT_HOME", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / ".mini-agent").resolve()


def resolve_global_memory_dir(root: str | Path | None = None) -> Path:
    """Resolve the durable global-memory directory."""
    if root is not None:
        return Path(root).expanduser().resolve()

    configured = str(os.getenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", "") or "").strip()
    if configured:
        return Path(configured).expanduser().resolve()

    return resolve_mini_agent_home() / "global"
