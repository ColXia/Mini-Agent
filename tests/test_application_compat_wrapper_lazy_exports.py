from __future__ import annotations

import importlib


def _reset_lazy_export(module_name: str, attr_name: str):
    module = importlib.import_module(module_name)
    module.__dict__.pop(attr_name, None)
    return module


def test_application_main_agent_surface_wrapper_resolves_export_lazily() -> None:
    module = _reset_lazy_export("mini_agent.application.main_agent_surface_service", "MainAgentSurfaceService")

    assert "MainAgentSurfaceService" not in module.__dict__

    resolved = getattr(module, "MainAgentSurfaceService")

    assert resolved is not None
    assert module.__dict__["MainAgentSurfaceService"] is resolved


def test_application_session_service_wrapper_resolves_export_lazily() -> None:
    module = _reset_lazy_export("mini_agent.application.session_service", "SessionApplicationService")

    assert "SessionApplicationService" not in module.__dict__

    resolved = getattr(module, "SessionApplicationService")

    assert resolved is not None
    assert module.__dict__["SessionApplicationService"] is resolved


def test_facade_surface_assembly_wrapper_resolves_exports_lazily() -> None:
    module = _reset_lazy_export(
        "mini_agent.application.facades.surface_service_assembly",
        "build_main_agent_surface_service",
    )

    assert "build_main_agent_surface_service" not in module.__dict__

    resolved = getattr(module, "build_main_agent_surface_service")

    assert resolved is not None
    assert module.__dict__["build_main_agent_surface_service"] is resolved
