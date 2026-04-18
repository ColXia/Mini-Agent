"""Lazy runtime package exports.

Avoid eager imports here so submodule imports like ``mini_agent.runtime.tooling``
do not pull in the full runtime manager graph during package initialization.
That keeps CLI/skill support import paths free from circular import failures.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

__all__ = [
    "MainAgentRuntimeManager",
    "MainAgentRuntimeDiagnostics",
    "MainAgentRuntimeMode",
    "MainAgentRuntimePolicy",
    "MainAgentSessionState",
    "SessionLifecycleDecision",
    "SurfaceSessionLifecycleRuntime",
    "build_surface_session_key",
    "resolve_session_lifecycle_policy",
    "add_workspace_tools",
    "initialize_agent_tools",
    "initialize_shared_tools",
    "MainAgentWorkspaceRuntimeAdapter",
]

_RUNTIME_EXPORTS = {
    "MainAgentRuntimeManager",
}
_RUNTIME_CONTRACT_EXPORTS = {
    "MainAgentRuntimeDiagnostics",
    "MainAgentRuntimeMode",
    "MainAgentRuntimePolicy",
}
_RUNTIME_STATE_EXPORTS = {
    "MainAgentSessionState",
}
_SESSION_EXPORTS = {
    "SessionLifecycleDecision",
    "SurfaceSessionLifecycleRuntime",
    "build_surface_session_key",
    "resolve_session_lifecycle_policy",
}
_TOOLING_EXPORTS = {
    "add_workspace_tools",
    "initialize_agent_tools",
    "initialize_shared_tools",
}
_WORKSPACE_RUNTIME_EXPORTS = {
    "MainAgentWorkspaceRuntimeAdapter",
}


def __getattr__(name: str) -> Any:
    if name in _RUNTIME_EXPORTS:
        module = import_module(".main_agent_runtime_manager", __name__)
        return getattr(module, name)
    if name in _RUNTIME_CONTRACT_EXPORTS:
        module = import_module(".main_agent_runtime_contracts", __name__)
        return getattr(module, name)
    if name in _RUNTIME_STATE_EXPORTS:
        module = import_module(".session_state", __name__)
        return getattr(module, name)
    if name in _SESSION_EXPORTS:
        module = import_module(".support.session_lifecycle", __name__)
        return getattr(module, name)
    if name in _TOOLING_EXPORTS:
        module = import_module(".support.tooling", __name__)
        return getattr(module, name)
    if name in _WORKSPACE_RUNTIME_EXPORTS:
        module = import_module(".workspace_runtime_adapter", __name__)
        return getattr(module, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
