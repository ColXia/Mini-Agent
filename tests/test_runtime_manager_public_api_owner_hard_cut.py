from __future__ import annotations

import ast
from pathlib import Path

from mini_agent.runtime.handlers.main_agent_runtime_public_api_mixin import (
    MainAgentRuntimePublicApiMixin,
)
from mini_agent.runtime.main_agent_runtime_manager import MainAgentRuntimeManager


REPO_ROOT = Path(__file__).resolve().parents[1]
MANAGER_PATH = REPO_ROOT / "src/mini_agent/runtime/main_agent_runtime_manager.py"
MIXIN_PATH = REPO_ROOT / "src/mini_agent/runtime/handlers/main_agent_runtime_public_api_mixin.py"
EXTRACTED_PUBLIC_API_METHODS = {
    "clear",
    "build_ephemeral_agent",
    "turn_scope_handler",
    "validate_workspace",
    "get_or_create_session",
    "ensure_session_runtime_policy_ready_for_turn",
    "ensure_agent_model_binding_for_turn",
    "ensure_default_session",
    "create_session",
    "create_derived_session",
    "import_session_snapshot",
    "export_session_snapshot",
    "get_runtime_diagnostics",
    "list_sessions",
    "rename_session",
    "set_session_shared",
    "get_session_detail",
    "get_recent_messages",
    "resolve_run_id_for_session",
    "get_run",
    "interrupt_run",
    "resume_run",
    "cancel_run",
    "resolve_approval_wait",
    "delete_session",
    "reset_session",
    "cancel_session_turn",
    "set_active_surface",
    "control_session_context",
    "update_session_context_policy",
    "manage_session_memory",
    "manage_session_skills",
    "update_session_runtime_policy",
    "queue_workspace_skill_reload",
    "apply_pending_session_skill_reload",
    "mark_turn_started",
    "mark_turn_finished",
    "bind_session_surface",
    "record_message",
    "record_activity",
    "record_pending_approval",
    "clear_pending_approval",
    "resolve_pending_approval",
    "build_recovery_turn_context",
    "clear_recovery_context",
}


def _class_method_names(path: Path, class_name: str) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            names: set[str] = set()
            for body_item in node.body:
                if isinstance(body_item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(body_item.name)
            return names
    raise AssertionError(f"class {class_name} not found in {path}")


def test_runtime_manager_public_api_owner_is_extracted_to_handler_module() -> None:
    assert MainAgentRuntimePublicApiMixin.__module__ == (
        "mini_agent.runtime.handlers.main_agent_runtime_public_api_mixin"
    )
    assert MainAgentRuntimeManager.__mro__[1] is MainAgentRuntimePublicApiMixin


def test_runtime_manager_root_shell_no_longer_physically_owns_extracted_public_api_methods() -> None:
    manager_methods = _class_method_names(MANAGER_PATH, "MainAgentRuntimeManager")
    leaked = sorted(EXTRACTED_PUBLIC_API_METHODS & manager_methods)
    assert leaked == [], (
        "Runtime manager root shell must not re-own extracted public API methods:\n"
        + "\n".join(leaked)
    )


def test_runtime_manager_public_api_mixin_owns_extracted_method_surface() -> None:
    mixin_methods = _class_method_names(MIXIN_PATH, "MainAgentRuntimePublicApiMixin")
    missing = sorted(EXTRACTED_PUBLIC_API_METHODS - mixin_methods)
    assert missing == [], (
        "Runtime public API mixin must own the extracted method surface:\n"
        + "\n".join(missing)
    )
