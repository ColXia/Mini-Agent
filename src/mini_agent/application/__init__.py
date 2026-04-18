"""Application-layer orchestration use cases."""

from __future__ import annotations

from importlib import import_module

from .facades.agent_delegation_execution_handler import AgentDelegationExecutionHandler
from .legacy import (
    RuntimeBackedSessionApplicationAssembly,
    SessionApplicationService,
    assemble_runtime_backed_session_application,
    assemble_typed_session_application,
    build_runtime_backed_session_service,
    build_typed_session_service,
)
from .ports import (
    AgentRuntimePort,
    ModelRuntimePort,
    RunRuntimePort,
    SessionAgentRuntimePort,
    SessionModelSelectionRuntimePort,
    SessionTaskRuntimePort,
    SessionTaskPort,
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
    assemble_runtime_backed_user_services,
    assemble_typed_user_services,
    resolve_runtime_backed_user_service_ports,
)
from .ports import ManagedRuntimeSessionPort, SessionRuntimePort, SessionTurnScopePort

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
    "ManagedRuntimeSessionPort",
    "ManagedSessionTurn",
    "MemoryOperationsUseCases",
    "ModelBindingApplicationService",
    "ModelRuntimePort",
    "OperationsPathPolicy",
    "ModelUserService",
    "ProviderOperationsUseCases",
    "RuntimeBackedSessionApplicationAssembly",
    "RuntimeBackedUserServicePorts",
    "RunControlApplicationService",
    "SessionTaskService",
    "RunRuntimePort",
    "UserServiceAssembly",
    "build_typed_session_service",
    "build_runtime_backed_session_service",
    "assemble_typed_session_application",
    "assemble_runtime_backed_session_application",
    "assemble_typed_user_services",
    "assemble_runtime_backed_user_services",
    "resolve_runtime_backed_user_service_ports",
    "SessionAgentRuntimePort",
    "SessionModelSelectionRuntimePort",
    "SessionApplicationService",
    "SessionTaskRuntimePort",
    "SessionRuntimePort",
    "SessionTaskPort",
    "SessionTurnScopePort",
    "WorkspaceApplicationService",
    "WorkspaceRuntimePort",
    "WorkspaceUserService",
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
