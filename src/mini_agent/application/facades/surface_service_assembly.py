"""Assembly helpers for explicit main-agent surface wiring."""

from __future__ import annotations

from typing import Any

from dataclasses import dataclass

from mini_agent.application.ports.agent_runtime_port import AgentRuntimePort
from mini_agent.application.ports.model_runtime_port import ModelRuntimePort
from mini_agent.application.ports.run_runtime_port import RunRuntimePort
from mini_agent.application.ports.session_agent_runtime_port import SessionAgentRuntimePort
from mini_agent.application.ports.session_model_selection_runtime_port import SessionModelSelectionRuntimePort
from mini_agent.application.ports.session_runtime_port import SessionRuntimePort
from mini_agent.application.ports.session_task_port import SessionTaskPort
from mini_agent.application.ports.session_task_runtime_port import SessionTaskRuntimePort
from mini_agent.application.ports.workspace_runtime_port import WorkspaceRuntimePort
from mini_agent.application.support import (
    FormatBootstrapErrorFn,
    ResolveWorkspaceDirFn,
    SseEventFn,
    ToUtcIsoFn,
)
from mini_agent.application.use_cases.agent_interaction_application_service import AgentInteractionApplicationService
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.application.use_cases.session_task_service import SessionTaskService
from mini_agent.application.user_service_assembly import (
    UserServiceAssembly,
    assemble_runtime_backed_user_services,
)
from mini_agent.application.user_services.agent_user_service import AgentUserService
from mini_agent.application.user_services.command_user_service import CommandUserService
from mini_agent.application.user_services.model_user_service import ModelUserService
from mini_agent.application.user_services.workspace_user_service import WorkspaceUserService

from .main_agent_surface_service import MainAgentSurfaceService
from .surface_dependency_resolution import (
    resolve_surface_agent_entry_service,
    resolve_surface_model_entry_service,
    resolve_surface_run_control_service,
    resolve_surface_session_task_service,
    resolve_surface_workspace_entry_service,
)


@dataclass(frozen=True, slots=True)
class MainAgentSurfaceAssembly:
    """Explicit surface assembly over user-service-owned dependencies."""

    surface_service: MainAgentSurfaceService
    user_service_assembly: UserServiceAssembly | None = None
    runtime_manager: Any = None
    legacy_session_service: object | None = None


def assemble_main_agent_surface_service(
    *,
    user_service_assembly: UserServiceAssembly | None = None,
    session_service: object | None = None,
    session_task_service: SessionTaskService | None = None,
    run_control_service: RunControlApplicationService | AgentUserService | None = None,
    agent_service: AgentUserService | None = None,
    workspace_service: WorkspaceUserService | None = None,
    model_service: ModelUserService | None = None,
    interaction_service: AgentInteractionApplicationService | None = None,
    resolve_workspace_dir: ResolveWorkspaceDirFn,
    to_utc_iso: ToUtcIsoFn,
    sse_event: SseEventFn,
    format_bootstrap_error: FormatBootstrapErrorFn,
    stream_chunk_size: int,
) -> MainAgentSurfaceAssembly:
    """Assemble the main-agent surface from explicit user-service owners."""

    resolved_session_task_service = session_task_service
    resolved_run_control_service = run_control_service
    resolved_agent_service = agent_service
    resolved_model_service = model_service
    resolved_workspace_service = workspace_service
    if user_service_assembly is not None:
        resolved_session_task_service = resolved_session_task_service or user_service_assembly.session_task_service
        resolved_agent_service = resolved_agent_service or user_service_assembly.agent_service
        resolved_model_service = resolved_model_service or user_service_assembly.model_service
        resolved_workspace_service = resolved_workspace_service or user_service_assembly.workspace_service
        if resolved_run_control_service is None and resolved_agent_service is None:
            resolved_run_control_service = user_service_assembly.run_control_service

    if session_service is not None:
        resolved_session_task_service = resolve_surface_session_task_service(
            session_service,
            resolved_session_task_service,
        )
        resolved_agent_service = resolve_surface_agent_entry_service(
            session_service,
            resolved_agent_service,
        )
        resolved_model_service = resolve_surface_model_entry_service(
            session_service,
            resolved_model_service,
        )
        resolved_workspace_service = resolve_surface_workspace_entry_service(
            session_service,
            resolved_workspace_service,
        )
        resolved_run_control_service = resolve_surface_run_control_service(
            session_service,
            resolved_run_control_service,
            resolved_agent_service,
        )
    elif resolved_run_control_service is None and resolved_agent_service is not None and all(
        hasattr(resolved_agent_service, attr)
        for attr in ("cancel_session_run", "approve_session_wait", "deny_session_wait")
    ):
        resolved_run_control_service = resolved_agent_service

    surface_service = MainAgentSurfaceService(
        session_task_service=resolved_session_task_service,
        run_control_service=resolved_run_control_service,
        agent_service=resolved_agent_service,
        model_service=resolved_model_service,
        workspace_service=resolved_workspace_service,
        interaction_service=interaction_service,
        resolve_workspace_dir=resolve_workspace_dir,
        to_utc_iso=to_utc_iso,
        sse_event=sse_event,
        format_bootstrap_error=format_bootstrap_error,
        stream_chunk_size=stream_chunk_size,
    )
    return MainAgentSurfaceAssembly(
        surface_service=surface_service,
        user_service_assembly=user_service_assembly,
        runtime_manager=None,
        legacy_session_service=session_service,
    )


def assemble_runtime_backed_main_agent_surface_service(
    *,
    runtime_manager: SessionRuntimePort,
    session_task_runtime: SessionTaskRuntimePort | None = None,
    session_task_port: SessionTaskPort | None = None,
    session_agent_runtime: SessionAgentRuntimePort | None = None,
    session_model_runtime: SessionModelSelectionRuntimePort | None = None,
    agent_runtime: AgentRuntimePort | None = None,
    run_runtime: RunRuntimePort | None = None,
    model_runtime: ModelRuntimePort | None = None,
    workspace_runtime: WorkspaceRuntimePort | None = None,
    command_runtime: Any = None,
    session_task_service: SessionTaskService | None = None,
    run_control_service: RunControlApplicationService | AgentUserService | None = None,
    agent_service: AgentUserService | None = None,
    workspace_service: WorkspaceUserService | None = None,
    model_service: ModelUserService | None = None,
    command_service: CommandUserService | None = None,
    interaction_service: AgentInteractionApplicationService | None = None,
    resolve_workspace_dir: ResolveWorkspaceDirFn,
    to_utc_iso: ToUtcIsoFn,
    sse_event: SseEventFn,
    format_bootstrap_error: FormatBootstrapErrorFn,
    stream_chunk_size: int,
) -> MainAgentSurfaceAssembly:
    """Assemble a surface directly from a runtime-backed user-service graph."""

    user_service_assembly = assemble_runtime_backed_user_services(
        runtime_manager=runtime_manager,
        session_task_runtime=session_task_runtime,
        session_task_port=session_task_port,
        session_agent_runtime=session_agent_runtime,
        session_model_runtime=session_model_runtime,
        agent_runtime=agent_runtime,
        run_runtime=run_runtime,
        model_runtime=model_runtime,
        workspace_runtime=workspace_runtime,
        command_runtime=command_runtime,
        session_task_service=session_task_service,
        run_control_service=run_control_service,
        agent_service=agent_service,
        workspace_service=workspace_service,
        model_service=model_service,
        command_service=command_service,
    )
    assembly = assemble_main_agent_surface_service(
        user_service_assembly=user_service_assembly,
        interaction_service=interaction_service,
        resolve_workspace_dir=resolve_workspace_dir,
        to_utc_iso=to_utc_iso,
        sse_event=sse_event,
        format_bootstrap_error=format_bootstrap_error,
        stream_chunk_size=stream_chunk_size,
    )
    return MainAgentSurfaceAssembly(
        surface_service=assembly.surface_service,
        user_service_assembly=user_service_assembly,
        runtime_manager=runtime_manager,
        legacy_session_service=None,
    )


def build_main_agent_surface_service(
    *,
    user_service_assembly: UserServiceAssembly | None = None,
    session_service: object | None = None,
    session_task_service: SessionTaskService | None = None,
    run_control_service: RunControlApplicationService | AgentUserService | None = None,
    agent_service: AgentUserService | None = None,
    workspace_service: WorkspaceUserService | None = None,
    model_service: ModelUserService | None = None,
    interaction_service: AgentInteractionApplicationService | None = None,
    resolve_workspace_dir: ResolveWorkspaceDirFn,
    to_utc_iso: ToUtcIsoFn,
    sse_event: SseEventFn,
    format_bootstrap_error: FormatBootstrapErrorFn,
    stream_chunk_size: int,
) -> MainAgentSurfaceService:
    """Build a main-agent surface while preferring explicit user-service assembly."""

    return assemble_main_agent_surface_service(
        user_service_assembly=user_service_assembly,
        session_service=session_service,
        session_task_service=session_task_service,
        run_control_service=run_control_service,
        agent_service=agent_service,
        workspace_service=workspace_service,
        model_service=model_service,
        interaction_service=interaction_service,
        resolve_workspace_dir=resolve_workspace_dir,
        to_utc_iso=to_utc_iso,
        sse_event=sse_event,
        format_bootstrap_error=format_bootstrap_error,
        stream_chunk_size=stream_chunk_size,
    ).surface_service


def build_runtime_backed_main_agent_surface_service(
    *,
    runtime_manager: SessionRuntimePort,
    session_task_runtime: SessionTaskRuntimePort | None = None,
    session_task_port: SessionTaskPort | None = None,
    session_agent_runtime: SessionAgentRuntimePort | None = None,
    session_model_runtime: SessionModelSelectionRuntimePort | None = None,
    agent_runtime: AgentRuntimePort | None = None,
    run_runtime: RunRuntimePort | None = None,
    model_runtime: ModelRuntimePort | None = None,
    workspace_runtime: WorkspaceRuntimePort | None = None,
    command_runtime: Any = None,
    session_task_service: SessionTaskService | None = None,
    run_control_service: RunControlApplicationService | AgentUserService | None = None,
    agent_service: AgentUserService | None = None,
    workspace_service: WorkspaceUserService | None = None,
    model_service: ModelUserService | None = None,
    command_service: CommandUserService | None = None,
    interaction_service: AgentInteractionApplicationService | None = None,
    resolve_workspace_dir: ResolveWorkspaceDirFn,
    to_utc_iso: ToUtcIsoFn,
    sse_event: SseEventFn,
    format_bootstrap_error: FormatBootstrapErrorFn,
    stream_chunk_size: int,
) -> MainAgentSurfaceService:
    """Build a main-agent surface directly from a runtime-backed user-service graph."""

    return assemble_runtime_backed_main_agent_surface_service(
        runtime_manager=runtime_manager,
        session_task_runtime=session_task_runtime,
        session_task_port=session_task_port,
        session_agent_runtime=session_agent_runtime,
        session_model_runtime=session_model_runtime,
        agent_runtime=agent_runtime,
        run_runtime=run_runtime,
        model_runtime=model_runtime,
        workspace_runtime=workspace_runtime,
        command_runtime=command_runtime,
        session_task_service=session_task_service,
        run_control_service=run_control_service,
        agent_service=agent_service,
        workspace_service=workspace_service,
        model_service=model_service,
        command_service=command_service,
        interaction_service=interaction_service,
        resolve_workspace_dir=resolve_workspace_dir,
        to_utc_iso=to_utc_iso,
        sse_event=sse_event,
        format_bootstrap_error=format_bootstrap_error,
        stream_chunk_size=stream_chunk_size,
    ).surface_service


__all__ = [
    "MainAgentSurfaceAssembly",
    "assemble_main_agent_surface_service",
    "assemble_runtime_backed_main_agent_surface_service",
    "build_main_agent_surface_service",
    "build_runtime_backed_main_agent_surface_service",
]
