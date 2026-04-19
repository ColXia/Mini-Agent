from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DELETED_ROOT_PATHS = (
    Path("src/mini_agent/launcher"),
    Path("src/mini_agent/code_agent"),
    Path("src/mini_agent/interaction"),
)
DELETED_ROOT_MODULES = (
    "mini_agent.launcher",
    "mini_agent.code_agent",
    "mini_agent.interaction",
)
FORBIDDEN_MODULE_IMPORTS = frozenset(DELETED_ROOT_MODULES)


def test_deleted_root_shell_paths_are_absent() -> None:
    for relative_path in DELETED_ROOT_PATHS:
        assert not (REPO_ROOT / relative_path).exists(), (
            f"{relative_path} should be removed by the v11.1 root-shell hard cut"
        )


@pytest.mark.parametrize("module_name", DELETED_ROOT_MODULES)
def test_deleted_root_shell_modules_are_not_importable(module_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_active_source_tree_does_not_import_deleted_root_shell_modules() -> None:
    violations: list[str] = []
    for path in (REPO_ROOT / "src").rglob("*.py"):
        relative = path.relative_to(REPO_ROOT)
        tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_MODULE_IMPORTS:
                        violations.append(f"{relative}:{node.lineno}: forbidden import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module in FORBIDDEN_MODULE_IMPORTS:
                    violations.append(f"{relative}:{node.lineno}: forbidden from-import {node.module}")

    assert not violations, (
        "Active source files must not depend on deleted root-shell modules:\n"
        + "\n".join(sorted(violations))
    )
