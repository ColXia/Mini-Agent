from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest
import mini_agent.runtime.live_control.run_control_store as run_control_store_module
from mini_agent.runtime.live_control.kernel_state_registry import (
    RuntimeKernelControlBridge,
    RuntimeKernelStateRegistry,
)
from mini_agent.runtime.handlers.session_run_control_handler import RuntimeSessionRunControlHandler
from mini_agent.runtime.live_control.run_control_store import (
    RuntimeSessionRunControlStore,
)
from mini_agent.runtime.read_models.run_projection_builder import RuntimeSessionRunProjectionBuilder


REPO_ROOT = Path(__file__).resolve().parents[1]
DELETED_RUN_CONTROL_OWNERS = {
    "mini_agent.runtime.orchestration.kernel_state_registry": Path(
        "src/mini_agent/runtime/orchestration/kernel_state_registry.py"
    ),
}


def test_deleted_run_control_owner_paths_are_absent() -> None:
    missing = [
        str(path)
        for path in DELETED_RUN_CONTROL_OWNERS.values()
        if (REPO_ROOT / path).exists()
    ]
    assert missing == [], (
        "Deleted run-control owners must stay absent after the v11.1 hard cut:\n"
        + "\n".join(sorted(missing))
    )


@pytest.mark.parametrize("module_name", sorted(DELETED_RUN_CONTROL_OWNERS))
def test_deleted_run_control_owner_modules_are_not_importable(module_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_active_source_tree_does_not_import_deleted_run_control_owners() -> None:
    violations: list[str] = []
    deleted_modules = set(DELETED_RUN_CONTROL_OWNERS)
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
        "Active source files must not depend on deleted run-control owners:\n"
        + "\n".join(sorted(violations))
    )


def test_run_projection_read_models_do_not_move_back_into_run_control_store() -> None:
    assert hasattr(RuntimeSessionRunProjectionBuilder, "build_active_run_projection")
    assert hasattr(RuntimeSessionRunProjectionBuilder, "build_persisted_run_projection")
    assert not hasattr(RuntimeSessionRunControlStore, "build_active_run_projection")
    assert not hasattr(RuntimeSessionRunControlStore, "build_persisted_run_projection")
    assert not hasattr(RuntimeKernelStateRegistry, "build_active_run_projection")
    assert not hasattr(RuntimeKernelStateRegistry, "build_persisted_run_projection")
    assert RuntimeKernelControlBridge.__module__ == "mini_agent.runtime.live_control.kernel_state_registry"
    assert RuntimeKernelStateRegistry.__module__ == "mini_agent.runtime.live_control.kernel_state_registry"
    assert not hasattr(run_control_store_module, "RuntimeKernelControlBridge")
    assert not hasattr(run_control_store_module, "RuntimeKernelStateRegistry")


def test_session_run_control_owner_exports_required_methods() -> None:
    extracted_methods = {
        "cancel_turn",
        "resolve_pending_approval",
        "resolve_run_id_for_session",
        "get_run",
        "interrupt_run",
        "resume_run",
        "cancel_run",
        "resolve_approval_wait",
    }
    assert RuntimeSessionRunControlHandler.__module__ == (
        "mini_agent.runtime.handlers.session_run_control_handler"
    )
    for name in sorted(extracted_methods):
        assert hasattr(RuntimeSessionRunControlHandler, name), (
            f"Run-control owner lost required method {name!r} after the hard cut."
        )
