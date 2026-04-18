"""Legacy/transitional application entrypoints."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "AgentModelRuntimeAdapter",
    "RuntimeBackedSessionApplicationAssembly",
    "SessionBackedRunRuntimeAdapter",
    "SessionAgentRuntimePort",
    "SessionAgentCompatibilityAdapter",
    "SessionApplicationService",
    "SessionModelSelectionRuntimePort",
    "SessionModelSelectionCompatibilityAdapter",
    "SessionTaskCompatibilityAdapter",
    "UnavailableRunRuntimeAdapter",
    "assemble_runtime_backed_session_application",
    "assemble_typed_session_application",
    "build_runtime_backed_session_service",
    "build_typed_session_service",
]

_EXPORTS: dict[str, tuple[str, str]] = {
    "AgentModelRuntimeAdapter": (".session_runtime_compat", "AgentModelRuntimeAdapter"),
    "RuntimeBackedSessionApplicationAssembly": (".session_service_assembly", "RuntimeBackedSessionApplicationAssembly"),
    "SessionBackedRunRuntimeAdapter": (".session_runtime_compat", "SessionBackedRunRuntimeAdapter"),
    "SessionAgentRuntimePort": (".session_agent_runtime_port", "SessionAgentRuntimePort"),
    "SessionAgentCompatibilityAdapter": (".session_runtime_compat", "SessionAgentCompatibilityAdapter"),
    "SessionApplicationService": (".session_service", "SessionApplicationService"),
    "SessionModelSelectionRuntimePort": (".session_model_selection_runtime_port", "SessionModelSelectionRuntimePort"),
    "SessionModelSelectionCompatibilityAdapter": (
        ".session_runtime_compat",
        "SessionModelSelectionCompatibilityAdapter",
    ),
    "SessionTaskCompatibilityAdapter": (".session_runtime_compat", "SessionTaskCompatibilityAdapter"),
    "UnavailableRunRuntimeAdapter": (".session_runtime_compat", "UnavailableRunRuntimeAdapter"),
    "assemble_runtime_backed_session_application": (
        ".session_service_assembly",
        "assemble_runtime_backed_session_application",
    ),
    "assemble_typed_session_application": (".session_service_assembly", "assemble_typed_session_application"),
    "build_runtime_backed_session_service": (".session_service_assembly", "build_runtime_backed_session_service"),
    "build_typed_session_service": (".session_service_assembly", "build_typed_session_service"),
}


def __getattr__(name: str):
    export = _EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = export
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
