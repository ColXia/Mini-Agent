from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DELETED_SESSION_OWNERS = {
    "mini_agent.session.binding": Path("src/mini_agent/session/binding.py"),
    "mini_agent.session.conversation_binding_port": Path(
        "src/mini_agent/session/conversation_binding_port.py"
    ),
    "mini_agent.session.conversation_binding_service": Path(
        "src/mini_agent/session/conversation_binding_service.py"
    ),
    "mini_agent.session.default_session": Path("src/mini_agent/session/default_session.py"),
    "mini_agent.session.feedback_service": Path("src/mini_agent/session/feedback_service.py"),
    "mini_agent.session.projection": Path("src/mini_agent/session/projection.py"),
    "mini_agent.session.recovery_feedback_service": Path(
        "src/mini_agent/session/recovery_feedback_service.py"
    ),
}


def test_deleted_session_owner_paths_are_absent() -> None:
    missing = [
        str(path)
        for path in DELETED_SESSION_OWNERS.values()
        if (REPO_ROOT / path).exists()
    ]
    assert missing == [], (
        "Deleted session owners must stay absent after the v11.1 hard cut:\n"
        + "\n".join(sorted(missing))
    )


@pytest.mark.parametrize("module_name", sorted(DELETED_SESSION_OWNERS))
def test_deleted_session_owner_modules_are_not_importable(module_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_active_source_tree_does_not_import_deleted_session_owners() -> None:
    violations: list[str] = []
    deleted_modules = set(DELETED_SESSION_OWNERS)
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
        "Active source files must not depend on deleted session owners:\n"
        + "\n".join(sorted(violations))
    )
