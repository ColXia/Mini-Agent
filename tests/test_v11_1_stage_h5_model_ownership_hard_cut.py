from __future__ import annotations

import ast
import importlib
from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.agent_studio_gateway.main_agent_router import create_main_agent_router
from mini_agent.application.use_cases.session_task_service import SessionTaskService
from mini_agent.application.user_services.model_user_service import ModelUserService


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
DELETED_PATHS = (
    Path("src/mini_agent/model_manager/session_selection_service.py"),
    Path("src/mini_agent/application/ports/session_model_selection_runtime_port.py"),
)
DELETED_MODULES = (
    "mini_agent.model_manager.session_selection_service",
    "mini_agent.application.ports.session_model_selection_runtime_port",
)
FORBIDDEN_PATTERNS = (
    "update_session_model_selection",
    "session_model_runtime",
)


def test_stage_h5_deleted_model_selection_files_are_absent() -> None:
    for relative_path in DELETED_PATHS:
        assert not (REPO_ROOT / relative_path).exists(), f"{relative_path} should be removed by the H5 hard cut"


@pytest.mark.parametrize("module_name", DELETED_MODULES)
def test_stage_h5_deleted_model_selection_modules_are_not_importable(module_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_stage_h5_active_services_drop_session_model_entrypoints() -> None:
    assert not hasattr(SessionTaskService, "update_session_model_selection")
    assert not hasattr(ModelUserService, "update_session_model_selection")


def test_stage_h5_gateway_router_drops_session_model_route() -> None:
    router = create_main_agent_router(
        deps=SimpleNamespace(
            build_health_response=lambda: None,
            get_runtime_diagnostics=lambda: None,
            get_routing_diagnostics=lambda: None,
            run_main_agent_chat=lambda request: None,
            stream_main_agent_chat=lambda **kwargs: iter(()),
            resolve_workspace_dir=lambda workspace_dir=None: Path("."),
            get_session_task_service=lambda: None,
            get_run_control_service=lambda: None,
            get_workspace_service=lambda: None,
            get_model_service=lambda: None,
            get_channel_ingress_use_cases=lambda: None,
            list_models=lambda: {"items": []},
            require_ops_auth=lambda: None,
        )
    )
    routes = {route.path for route in router.routes}
    assert "/api/v1/agent/sessions/{session_id}/model" not in routes


def test_stage_h5_active_source_tree_no_longer_mentions_deleted_session_model_entrypoints() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        relative = path.relative_to(REPO_ROOT)
        try:
            source = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(relative))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if any(pattern == node.value for pattern in FORBIDDEN_PATTERNS):
                    violations.append(f"{relative}:{node.lineno}: lingering deleted model-selection symbol {node.value!r}")

    assert violations == [], "Active source should not keep deleted session-model entrypoint symbols:\n" + "\n".join(violations)
