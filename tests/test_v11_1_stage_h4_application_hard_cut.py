from __future__ import annotations

import importlib
from pathlib import Path

import pytest

import mini_agent.application as application_module
import mini_agent.application.facades as application_facades_module


REPO_ROOT = Path(__file__).resolve().parents[1]
DELETED_PATHS = (
    Path("src/mini_agent/application/main_agent_surface_service.py"),
    Path("src/mini_agent/application/surface_service_assembly.py"),
    Path("src/mini_agent/application/session_service.py"),
    Path("src/mini_agent/application/session_service_assembly.py"),
    Path("src/mini_agent/application/session_runtime_compat.py"),
    Path("src/mini_agent/application/facades/main_agent_surface_service.py"),
    Path("src/mini_agent/application/facades/surface_service_assembly.py"),
    Path("src/mini_agent/application/facades/surface_dependency_resolution.py"),
)
DELETED_MODULES = (
    "mini_agent.application.main_agent_surface_service",
    "mini_agent.application.surface_service_assembly",
    "mini_agent.application.session_service",
    "mini_agent.application.session_service_assembly",
    "mini_agent.application.session_runtime_compat",
    "mini_agent.application.facades.main_agent_surface_service",
    "mini_agent.application.facades.surface_service_assembly",
    "mini_agent.application.facades.surface_dependency_resolution",
    "mini_agent.application.legacy",
)
REMOVED_APPLICATION_EXPORTS = (
    "MainAgentSurfaceService",
    "MainAgentSurfaceAssembly",
    "SessionApplicationService",
    "assemble_main_agent_surface_service",
    "assemble_runtime_backed_main_agent_surface_service",
    "assemble_runtime_backed_session_application",
    "assemble_typed_session_application",
    "build_main_agent_surface_service",
    "build_runtime_backed_main_agent_surface_service",
    "build_runtime_backed_session_service",
    "build_typed_session_service",
)
REMOVED_FACADE_EXPORTS = (
    "MainAgentSurfaceService",
    "MainAgentSurfaceAssembly",
    "assemble_main_agent_surface_service",
    "assemble_runtime_backed_main_agent_surface_service",
    "build_main_agent_surface_service",
    "build_runtime_backed_main_agent_surface_service",
)


def test_stage_h4_removed_application_paths_do_not_exist() -> None:
    for relative_path in DELETED_PATHS:
        assert not (REPO_ROOT / relative_path).exists(), f"{relative_path} should be removed by the H4 hard cut"


def test_stage_h4_application_namespace_drops_legacy_exports() -> None:
    for name in REMOVED_APPLICATION_EXPORTS:
        assert not hasattr(application_module, name), f"{name} should not remain in mini_agent.application"

    for name in REMOVED_FACADE_EXPORTS:
        assert not hasattr(application_facades_module, name), f"{name} should not remain in mini_agent.application.facades"


@pytest.mark.parametrize("module_name", DELETED_MODULES)
def test_stage_h4_removed_modules_are_not_importable(module_name: str) -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)
