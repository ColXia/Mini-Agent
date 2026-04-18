"""Application-layer orchestration use cases."""

from __future__ import annotations

from importlib import import_module

from .facades.agent_delegation_execution_handler import AgentDelegationExecutionHandler
from .ports import (
    AgentRuntimePort,
    ModelRuntimePort,
    RunRuntimePort,
    SessionAgentRuntimePort,
    SessionModelSelectionRuntimePort,
    SessionTaskPort,
    SessionTaskRuntimePort,
    WorkspaceRuntimePort,
)
from .support import ApplicationInteractionBinding, ManagedSessionTurn
from .use_cases import (
    AgentApplicationService,
    AgentInteractionApplicationService,
    ChannelIngressUseCases,
    ChannelNovelActionHandler,
    CommandApplicationService,
    MemoryOperationsUseCases,
    ModelBindingApplicationService,
    OperationsPathPolicy,
    ProviderOperationsUseCases,
    RunControlApplicationService,
    SessionTaskService,
    WorkspaceApplicationService,
)
from .user_services import (
    AgentUserService,
    CommandUserService,
    ModelUserService,
    RuntimeBackedUserServicePorts,
    UserServiceAssembly,
    WorkspaceUserService,
    assemble_typed_user_services,
    resolve_runtime_backed_user_service_ports,
)

__all__ = [
    "AgentDelegationExecutionHandler",
    "AgentApplicationService",
    "AgentInteractionApplicationService",
    "AgentRuntimePort",
    "AgentUserService",
    "ApplicationInteractionBinding",
    "ChannelIngressUseCases",
    "ChannelNovelActionHandler",
    "CommandApplicationService",
    "CommandUserService",
    "ManagedSessionTurn",
    "MemoryOperationsUseCases",
    "ModelBindingApplicationService",
    "ModelRuntimePort",
    "OperationsPathPolicy",
    "ModelUserService",
    "ProviderOperationsUseCases",
    "RuntimeBackedUserServicePorts",
    "RunControlApplicationService",
    "RunRuntimePort",
    "SessionTaskService",
    "UserServiceAssembly",
    "assemble_typed_user_services",
    "resolve_runtime_backed_user_service_ports",
    "SessionAgentRuntimePort",
    "SessionModelSelectionRuntimePort",
    "SessionTaskRuntimePort",
    "SessionTaskPort",
    "WorkspaceApplicationService",
    "WorkspaceRuntimePort",
    "WorkspaceUserService",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "ManagedRuntimeSessionPort": (".session_runtime_port", "ManagedRuntimeSessionPort"),
    "MainAgentSurfaceService": (".main_agent_surface_service", "MainAgentSurfaceService"),
    "MainAgentSurfaceAssembly": (".surface_service_assembly", "MainAgentSurfaceAssembly"),
    "RuntimeBackedSessionApplicationAssembly": (
        ".session_service_assembly",
        "RuntimeBackedSessionApplicationAssembly",
    ),
    "SessionApplicationService": (".session_service", "SessionApplicationService"),
    "SessionRuntimePort": (".session_runtime_port", "SessionRuntimePort"),
    "SessionTurnScopePort": (".session_runtime_port", "SessionTurnScopePort"),
    "assemble_main_agent_surface_service": (".surface_service_assembly", "assemble_main_agent_surface_service"),
    "assemble_runtime_backed_session_application": (
        ".session_service_assembly",
        "assemble_runtime_backed_session_application",
    ),
    "assemble_runtime_backed_main_agent_surface_service": (
        ".surface_service_assembly",
        "assemble_runtime_backed_main_agent_surface_service",
    ),
    "assemble_typed_session_application": (
        ".session_service_assembly",
        "assemble_typed_session_application",
    ),
    "build_main_agent_surface_service": (".surface_service_assembly", "build_main_agent_surface_service"),
    "assemble_runtime_backed_user_services": (
        ".user_service_assembly",
        "assemble_runtime_backed_user_services",
    ),
    "build_runtime_backed_session_service": (
        ".session_service_assembly",
        "build_runtime_backed_session_service",
    ),
    "build_runtime_backed_main_agent_surface_service": (
        ".surface_service_assembly",
        "build_runtime_backed_main_agent_surface_service",
    ),
    "build_typed_session_service": (".session_service_assembly", "build_typed_session_service"),
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
