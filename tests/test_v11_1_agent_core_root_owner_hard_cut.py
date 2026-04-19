from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DELETED_AGENT_CORE_ROOT_PATH = Path("src/mini_agent/agent_core/kernel_state.py")
DELETED_AGENT_CORE_ROOT_MODULE = "mini_agent.agent_core.kernel_state"


def test_deleted_agent_core_root_owner_path_is_absent() -> None:
    assert not (REPO_ROOT / DELETED_AGENT_CORE_ROOT_PATH).exists(), (
        f"{DELETED_AGENT_CORE_ROOT_PATH} should be removed by the v11.1 hard cut"
    )


def test_deleted_agent_core_root_owner_module_is_not_importable() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(DELETED_AGENT_CORE_ROOT_MODULE)


def test_active_source_tree_does_not_import_deleted_agent_core_root_owner() -> None:
    violations: list[str] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        relative = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == DELETED_AGENT_CORE_ROOT_MODULE:
                        violations.append(f"{relative}:{node.lineno}: forbidden import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module == DELETED_AGENT_CORE_ROOT_MODULE:
                    violations.append(f"{relative}:{node.lineno}: forbidden from-import {node.module}")

    assert not violations, (
        "Active source files must not depend on deleted agent-core root owners:\n"
        + "\n".join(sorted(violations))
    )
