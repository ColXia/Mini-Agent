from __future__ import annotations

import importlib


def _reset_lazy_export(module_name: str, attr_name: str):
    module = importlib.import_module(module_name)
    module.__dict__.pop(attr_name, None)
    return module


def test_runtime_session_access_wrapper_resolves_exports_lazily() -> None:
    module = _reset_lazy_export(
        "mini_agent.runtime.session_access_handler",
        "RuntimeSessionAccessHandler",
    )

    assert "RuntimeSessionAccessHandler" not in module.__dict__

    resolved = getattr(module, "RuntimeSessionAccessHandler")

    assert resolved is not None
    assert module.__dict__["RuntimeSessionAccessHandler"] is resolved


def test_runtime_session_control_models_wrapper_resolves_exports_lazily() -> None:
    module = _reset_lazy_export(
        "mini_agent.runtime.session_control_models",
        "RuntimeSessionControlCommand",
    )

    assert "RuntimeSessionControlCommand" not in module.__dict__

    resolved = getattr(module, "RuntimeSessionControlCommand")

    assert resolved is not None
    assert module.__dict__["RuntimeSessionControlCommand"] is resolved


def test_runtime_session_read_model_wrapper_resolves_exports_lazily() -> None:
    module = _reset_lazy_export(
        "mini_agent.runtime.session_read_model_builder",
        "RuntimeSessionReadModelBuilder",
    )

    assert "RuntimeSessionReadModelBuilder" not in module.__dict__

    resolved = getattr(module, "RuntimeSessionReadModelBuilder")

    assert resolved is not None
    assert module.__dict__["RuntimeSessionReadModelBuilder"] is resolved


def test_runtime_session_snapshot_handler_wrapper_resolves_exports_lazily() -> None:
    module = _reset_lazy_export(
        "mini_agent.runtime.session_snapshot_handler",
        "RuntimeSessionSnapshotImportCommand",
    )

    assert "RuntimeSessionSnapshotImportCommand" not in module.__dict__

    resolved = getattr(module, "RuntimeSessionSnapshotImportCommand")

    assert resolved is not None
    assert module.__dict__["RuntimeSessionSnapshotImportCommand"] is resolved


def test_runtime_session_restore_wrapper_resolves_exports_lazily() -> None:
    module = _reset_lazy_export(
        "mini_agent.runtime.session_restore_handler",
        "RuntimeSessionRestoreHandler",
    )

    assert "RuntimeSessionRestoreHandler" not in module.__dict__

    resolved = getattr(module, "RuntimeSessionRestoreHandler")

    assert resolved is not None
    assert module.__dict__["RuntimeSessionRestoreHandler"] is resolved


def test_runtime_session_cancel_service_wrapper_resolves_exports_lazily() -> None:
    module = _reset_lazy_export(
        "mini_agent.runtime.session_cancel_service",
        "SessionCancelService",
    )

    assert "SessionCancelService" not in module.__dict__

    resolved = getattr(module, "SessionCancelService")

    assert resolved is not None
    assert module.__dict__["SessionCancelService"] is resolved


def test_runtime_session_pending_approval_service_wrapper_resolves_exports_lazily() -> None:
    module = _reset_lazy_export(
        "mini_agent.runtime.session_pending_approval_service",
        "SessionPendingApprovalService",
    )

    assert "SessionPendingApprovalService" not in module.__dict__

    resolved = getattr(module, "SessionPendingApprovalService")

    assert resolved is not None
    assert module.__dict__["SessionPendingApprovalService"] is resolved


def test_runtime_session_lifecycle_wrapper_resolves_exports_lazily() -> None:
    module = _reset_lazy_export(
        "mini_agent.runtime.session_lifecycle",
        "resolve_session_lifecycle_policy",
    )

    assert "resolve_session_lifecycle_policy" not in module.__dict__

    resolved = getattr(module, "resolve_session_lifecycle_policy")

    assert resolved is not None
    assert module.__dict__["resolve_session_lifecycle_policy"] is resolved


def test_runtime_workspace_path_utils_wrapper_resolves_exports_lazily() -> None:
    module = _reset_lazy_export(
        "mini_agent.runtime.workspace_path_utils",
        "workspace_path_key",
    )

    assert "workspace_path_key" not in module.__dict__

    resolved = getattr(module, "workspace_path_key")

    assert resolved is not None
    assert module.__dict__["workspace_path_key"] is resolved


def test_runtime_policy_loader_wrapper_resolves_exports_lazily() -> None:
    module = _reset_lazy_export(
        "mini_agent.runtime.main_agent_runtime_policy_loader",
        "load_main_agent_runtime_policy",
    )

    assert "load_main_agent_runtime_policy" not in module.__dict__

    resolved = getattr(module, "load_main_agent_runtime_policy")

    assert resolved is not None
    assert module.__dict__["load_main_agent_runtime_policy"] is resolved
