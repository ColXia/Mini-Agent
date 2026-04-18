"""Facade exports for cross-surface application entrypoints."""

from __future__ import annotations

from importlib import import_module

from .agent_delegation_execution_handler import (
    AgentDelegationExecutionHandler,
    AgentDelegationExecutionResult,
)
from .agent_route_execution_handler import AgentRouteExecutionHandler
from .agent_turn_execution_handler import (
    AgentTurnExecutionHandler,
    SurfaceActivityEmitter,
    SurfaceAgentExecutionRequest,
)
from .surface_chat_flow_handler import (
    ExecuteSurfaceChatTurnFn,
    SurfaceChatExecutionRequest,
    SurfaceChatExecutionResult,
    SurfaceChatFlowHandler,
    SurfaceChatStreamEvent,
)

__all__ = [
    "AgentDelegationExecutionHandler",
    "AgentDelegationExecutionResult",
    "AgentRouteExecutionHandler",
    "AgentTurnExecutionHandler",
    "ExecuteSurfaceChatTurnFn",
    "SurfaceActivityEmitter",
    "SurfaceAgentExecutionRequest",
    "SurfaceChatExecutionRequest",
    "SurfaceChatExecutionResult",
    "SurfaceChatFlowHandler",
    "SurfaceChatStreamEvent",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "MainAgentSurfaceService": (".main_agent_surface_service", "MainAgentSurfaceService"),
    "MainAgentSurfaceAssembly": (".surface_service_assembly", "MainAgentSurfaceAssembly"),
    "assemble_main_agent_surface_service": (".surface_service_assembly", "assemble_main_agent_surface_service"),
    "assemble_runtime_backed_main_agent_surface_service": (
        ".surface_service_assembly",
        "assemble_runtime_backed_main_agent_surface_service",
    ),
    "build_main_agent_surface_service": (".surface_service_assembly", "build_main_agent_surface_service"),
    "build_runtime_backed_main_agent_surface_service": (
        ".surface_service_assembly",
        "build_runtime_backed_main_agent_surface_service",
    ),
}


def __getattr__(name: str):
    export = _COMPAT_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = export
    module = import_module(module_name, __name__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value
