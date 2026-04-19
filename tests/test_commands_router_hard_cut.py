from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DELETED_ROUTER_PATH = REPO_ROOT / "src/mini_agent/commands/router.py"
DELETED_ROUTER_MODULE = "mini_agent.commands.router"


def test_deleted_commands_router_path_is_absent() -> None:
    assert not DELETED_ROUTER_PATH.exists(), (
        "commands/router.py must stay deleted after the v11.1 command-tree hard cut"
    )


def test_deleted_commands_router_module_is_not_importable() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(DELETED_ROUTER_MODULE)


def test_active_source_tree_does_not_import_deleted_commands_router() -> None:
    violations: list[str] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        relative = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == DELETED_ROUTER_MODULE:
                        violations.append(
                            f"{relative}:{node.lineno}: forbidden import {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if (node.module or "") == DELETED_ROUTER_MODULE:
                    violations.append(
                        f"{relative}:{node.lineno}: forbidden from-import {node.module}"
                    )

    assert violations == [], (
        "Active source files must not depend on deleted commands.router:\n"
        + "\n".join(sorted(violations))
    )
