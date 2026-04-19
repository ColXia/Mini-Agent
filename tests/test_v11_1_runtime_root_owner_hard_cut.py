from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DELETED_RUNTIME_ROOT_OWNERS = {
    "mini_agent.runtime.main_agent_runtime_contracts": Path(
        "src/mini_agent/runtime/main_agent_runtime_contracts.py"
    ),
    "mini_agent.runtime.session_diagnostics_service": Path(
        "src/mini_agent/runtime/session_diagnostics_service.py"
    ),
    "mini_agent.runtime.session_state": Path(
        "src/mini_agent/runtime/session_state.py"
    ),
    "mini_agent.runtime.session_runtime_persistence": Path(
        "src/mini_agent/runtime/session_runtime_persistence.py"
    ),
    "mini_agent.runtime.workspace_runtime_adapter": Path(
        "src/mini_agent/runtime/workspace_runtime_adapter.py"
    ),
}


def test_deleted_runtime_root_owner_paths_are_absent() -> None:
    missing = [
        str(path)
        for path in DELETED_RUNTIME_ROOT_OWNERS.values()
        if (REPO_ROOT / path).exists()
    ]
    assert missing == [], (
        "Deleted runtime root owners must stay absent after the v11.1 hard cut:\n"
        + "\n".join(sorted(missing))
    )


@pytest.mark.parametrize("module_name", sorted(DELETED_RUNTIME_ROOT_OWNERS))
def test_deleted_runtime_root_owner_modules_are_not_importable(module_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_active_source_tree_does_not_import_deleted_runtime_root_owners() -> None:
    violations: list[str] = []
    deleted_modules = set(DELETED_RUNTIME_ROOT_OWNERS)
    for path in (REPO_ROOT / "src").rglob("*.py"):
        relative = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in deleted_modules:
                        violations.append(
                            f"{relative}:{node.lineno}: forbidden import {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "") in deleted_modules:
                    violations.append(
                        f"{relative}:{node.lineno}: forbidden from-import {node.module}"
                    )

    assert violations == [], (
        "Active source files must not depend on deleted runtime root owners:\n"
        + "\n".join(sorted(violations))
    )
