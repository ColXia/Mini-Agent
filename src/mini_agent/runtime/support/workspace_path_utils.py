"""Workspace path identity helpers used by runtime and workspace-runtime owners."""

from __future__ import annotations

import os
from pathlib import Path


def workspace_path_key(path: Path) -> str:
    resolved = str(Path(path).expanduser().resolve())
    return resolved.lower() if os.name == "nt" else resolved


def same_workspace_path(left: Path, right: Path) -> bool:
    return workspace_path_key(left) == workspace_path_key(right)


__all__ = ["same_workspace_path", "workspace_path_key"]
