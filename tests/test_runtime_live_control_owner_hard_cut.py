from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest

import mini_agent.runtime.live_control.session_pending_approval_state_handler as session_pending_approval_module
import mini_agent.runtime.live_control.session_recovery_reset_handler as session_recovery_reset_module
import mini_agent.runtime.live_control.session_transcript_state_handler as session_transcript_state_module
import mini_agent.runtime.live_control.session_turn_scope_handler as session_turn_scope_module
from mini_agent.runtime.live_control.session_pending_approval_state_handler import (
    RuntimeSessionPendingApprovalStateHandler,
)
from mini_agent.runtime.live_control.session_recovery_reset_handler import (
    RuntimeSessionRecoveryResetHandler,
)
from mini_agent.runtime.live_control.session_transcript_state_handler import (
    RuntimeSessionTranscriptStateHandler,
)
from mini_agent.runtime.live_control.session_turn_scope_handler import (
    RuntimeSessionTurnScopeHandler,
)


REPO_ROOT = Path(__file__).resolve().parents[1]
DELETED_RUNTIME_LIVE_CONTROL_OWNERS: dict[str, Path] = {
    "mini_agent.runtime.live_control.session_live_state_handler": Path(
        "src/mini_agent/runtime/live_control/session_live_state_handler.py"
    ),
}


def test_deleted_runtime_live_control_owner_paths_are_absent() -> None:
    missing = [
        str(path)
        for path in DELETED_RUNTIME_LIVE_CONTROL_OWNERS.values()
        if (REPO_ROOT / path).exists()
    ]
    assert missing == [], (
        "Deleted runtime live-control owners must stay absent after the v11.1 hard cut:\n"
        + "\n".join(sorted(missing))
    )


@pytest.mark.parametrize("module_name", sorted(DELETED_RUNTIME_LIVE_CONTROL_OWNERS))
def test_deleted_runtime_live_control_owner_modules_are_not_importable(module_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_active_source_tree_does_not_import_deleted_runtime_live_control_owners() -> None:
    violations: list[str] = []
    deleted_modules = set(DELETED_RUNTIME_LIVE_CONTROL_OWNERS)
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
        "Active source files must not depend on deleted runtime live-control owners:\n"
        + "\n".join(sorted(violations))
    )


def test_live_control_active_owners_are_physically_split_after_hard_cut() -> None:
    assert RuntimeSessionPendingApprovalStateHandler.__module__ == (
        "mini_agent.runtime.live_control.session_pending_approval_state_handler"
    )
    assert RuntimeSessionRecoveryResetHandler.__module__ == (
        "mini_agent.runtime.live_control.session_recovery_reset_handler"
    )
    assert RuntimeSessionTranscriptStateHandler.__module__ == (
        "mini_agent.runtime.live_control.session_transcript_state_handler"
    )
    assert RuntimeSessionTurnScopeHandler.__module__ == (
        "mini_agent.runtime.live_control.session_turn_scope_handler"
    )
    assert session_pending_approval_module.__all__ == ["RuntimeSessionPendingApprovalStateHandler"]
    assert session_recovery_reset_module.__all__ == ["RuntimeSessionRecoveryResetHandler"]
    assert session_transcript_state_module.__all__ == ["RuntimeSessionTranscriptStateHandler"]
    assert session_turn_scope_module.__all__ == ["RuntimeSessionTurnScopeHandler"]
