from __future__ import annotations

import os
from pathlib import Path

from mini_agent.runtime.workspace_path_utils import (
    same_workspace_path,
    workspace_path_key,
)


def test_workspace_path_key_matches_current_platform_semantics(tmp_path: Path) -> None:
    key = workspace_path_key(tmp_path)
    resolved = str(tmp_path.resolve())

    if os.name == "nt":
        assert key == resolved.lower()
    else:
        assert key == resolved


def test_same_workspace_path_compares_resolved_paths(tmp_path: Path) -> None:
    left = tmp_path
    right = Path(str(tmp_path.resolve()))

    assert same_workspace_path(left, right) is True
