from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

from mini_agent.runtime.handlers.session_context_policy_handler import (
    RuntimeSessionContextPolicyHandler,
)
from mini_agent.runtime.handlers.session_control_command_handler import (
    RuntimeSessionControlCommandHandler,
)
from mini_agent.runtime.handlers.session_memory_handler import RuntimeSessionMemoryHandler
from mini_agent.runtime.handlers.session_skill_handler import RuntimeSessionSkillHandler


REPO_ROOT = Path(__file__).resolve().parents[1]
DELETED_RUNTIME_OPERATOR_OWNERS = {
    "mini_agent.runtime.handlers.session_operator_handler": Path(
        "src/mini_agent/runtime/handlers/session_operator_handler.py"
    ),
}


def test_deleted_runtime_operator_owner_paths_are_absent() -> None:
    missing = [
        str(path)
        for path in DELETED_RUNTIME_OPERATOR_OWNERS.values()
        if (REPO_ROOT / path).exists()
    ]
    assert missing == [], (
        "Deleted runtime-operator owners must stay absent after the v11.1 hard cut:\n"
        + "\n".join(sorted(missing))
    )


@pytest.mark.parametrize("module_name", sorted(DELETED_RUNTIME_OPERATOR_OWNERS))
def test_deleted_runtime_operator_owner_modules_are_not_importable(module_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_active_source_tree_does_not_import_deleted_runtime_operator_owners() -> None:
    violations: list[str] = []
    deleted_modules = set(DELETED_RUNTIME_OPERATOR_OWNERS)
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
        "Active source files must not depend on deleted runtime-operator owners:\n"
        + "\n".join(sorted(violations))
    )


def test_runtime_operator_owners_have_explicit_replacements() -> None:
    assert RuntimeSessionControlCommandHandler.__module__ == (
        "mini_agent.runtime.handlers.session_control_command_handler"
    )
    assert RuntimeSessionContextPolicyHandler.__module__ == (
        "mini_agent.runtime.handlers.session_context_policy_handler"
    )
    assert RuntimeSessionMemoryHandler.__module__ == (
        "mini_agent.runtime.handlers.session_memory_handler"
    )
    assert RuntimeSessionSkillHandler.__module__ == (
        "mini_agent.runtime.handlers.session_skill_handler"
    )
    assert hasattr(RuntimeSessionControlCommandHandler, "control_session")
    assert hasattr(RuntimeSessionContextPolicyHandler, "update_context_policy")
    assert hasattr(RuntimeSessionMemoryHandler, "manage_memory")
    assert hasattr(RuntimeSessionSkillHandler, "manage_skills")
