from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DELETED_TURN_SCOPE_OWNER = {
    "mini_agent.runtime.orchestration.session_turn_scope_handler": Path(
        "src/mini_agent/runtime/orchestration/session_turn_scope_handler.py"
    ),
}


def test_deleted_turn_scope_owner_path_is_absent() -> None:
    missing = [
        str(path)
        for path in DELETED_TURN_SCOPE_OWNER.values()
        if (REPO_ROOT / path).exists()
    ]
    assert missing == [], (
        "Deleted turn-scope owner must stay absent after the v11.1 hard cut:\n"
        + "\n".join(sorted(missing))
    )


@pytest.mark.parametrize("module_name", sorted(DELETED_TURN_SCOPE_OWNER))
def test_deleted_turn_scope_owner_module_is_not_importable(module_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_active_source_tree_does_not_import_deleted_turn_scope_owner() -> None:
    violations: list[str] = []
    deleted_modules = set(DELETED_TURN_SCOPE_OWNER)
    for path in (REPO_ROOT / "src").rglob("*.py"):
        relative = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in deleted_modules:
                        violations.append(f"{relative}:{node.lineno}: forbidden import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "") in deleted_modules:
                    violations.append(f"{relative}:{node.lineno}: forbidden from-import {node.module}")

    assert violations == [], (
        "Active source files must not depend on the deleted turn-scope owner:\n"
        + "\n".join(sorted(violations))
    )
