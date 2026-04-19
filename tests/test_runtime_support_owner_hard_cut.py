from __future__ import annotations

import ast
import importlib
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
DELETED_RUNTIME_SUPPORT_OWNERS = {
    "mini_agent.runtime.support.session_backed_run_id": Path(
        "src/mini_agent/runtime/support/session_backed_run_id.py"
    ),
    "mini_agent.runtime.support.session_lineage_registry": Path(
        "src/mini_agent/runtime/support/session_lineage_registry.py"
    ),
    "mini_agent.runtime.support.session_lifecycle": Path(
        "src/mini_agent/runtime/support/session_lifecycle.py"
    ),
    "mini_agent.runtime.support.session_persistence_loader": Path(
        "src/mini_agent/runtime/support/session_persistence_loader.py"
    ),
    "mini_agent.runtime.support.session_persistence_metadata_registry": Path(
        "src/mini_agent/runtime/support/session_persistence_metadata_registry.py"
    ),
    "mini_agent.runtime.support.session_snapshot": Path(
        "src/mini_agent/runtime/support/session_snapshot.py"
    ),
    "mini_agent.runtime.support.session_diagnostics_service": Path(
        "src/mini_agent/runtime/support/session_diagnostics_service.py"
    ),
    "mini_agent.runtime.support.session_command_coordinator": Path(
        "src/mini_agent/runtime/support/session_command_coordinator.py"
    ),
    "mini_agent.runtime.support.session_control_error_service": Path(
        "src/mini_agent/runtime/support/session_control_error_service.py"
    ),
    "mini_agent.runtime.support.session_control_models": Path(
        "src/mini_agent/runtime/support/session_control_models.py"
    ),
    "mini_agent.runtime.support.session_local_agent_runtime_handler": Path(
        "src/mini_agent/runtime/support/session_local_agent_runtime_handler.py"
    ),
    "mini_agent.runtime.support.session_local_mcp_runtime_service": Path(
        "src/mini_agent/runtime/support/session_local_mcp_runtime_service.py"
    ),
    "mini_agent.runtime.support.session_agent_support": Path(
        "src/mini_agent/runtime/support/session_agent_support.py"
    ),
    "mini_agent.runtime.support.main_agent_runtime_policy_loader": Path(
        "src/mini_agent/runtime/support/main_agent_runtime_policy_loader.py"
    ),
    "mini_agent.runtime.support.runtime_policy_service": Path(
        "src/mini_agent/runtime/support/runtime_policy_service.py"
    ),
    "mini_agent.runtime.support.turn_context_provider_builder": Path(
        "src/mini_agent/runtime/support/turn_context_provider_builder.py"
    ),
    "mini_agent.runtime.support.session_persistence_record_builder": Path(
        "src/mini_agent/runtime/support/session_persistence_record_builder.py"
    ),
    "mini_agent.runtime.support.session_runtime_persistence": Path(
        "src/mini_agent/runtime/support/session_runtime_persistence.py"
    ),
    "mini_agent.runtime.support.session_shared_transcript_store": Path(
        "src/mini_agent/runtime/support/session_shared_transcript_store.py"
    ),
}


def test_deleted_runtime_support_owner_paths_are_absent() -> None:
    missing = [
        str(path)
        for path in DELETED_RUNTIME_SUPPORT_OWNERS.values()
        if (REPO_ROOT / path).exists()
    ]
    assert missing == [], (
        "Deleted runtime support owners must stay absent after the v11.1 hard cut:\n"
        + "\n".join(sorted(missing))
    )


@pytest.mark.parametrize("module_name", sorted(DELETED_RUNTIME_SUPPORT_OWNERS))
def test_deleted_runtime_support_owner_modules_are_not_importable(module_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_active_source_tree_does_not_import_deleted_runtime_support_owners() -> None:
    violations: list[str] = []
    deleted_modules = set(DELETED_RUNTIME_SUPPORT_OWNERS)
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
        "Active source files must not depend on deleted runtime support owners:\n"
        + "\n".join(sorted(violations))
    )
