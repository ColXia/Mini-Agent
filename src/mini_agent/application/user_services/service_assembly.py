"""Assembly helpers for Stage 3 explicit user-service wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from mini_agent.application.ports.agent_runtime_port import AgentRuntimePort
from mini_agent.application.ports.model_runtime_port import ModelRuntimePort
from mini_agent.application.ports.run_runtime_port import RunRuntimePort
from mini_agent.application.ports.session_agent_runtime_port import SessionAgentRuntimePort
from mini_agent.application.ports.session_model_selection_runtime_port import SessionModelSelectionRuntimePort
from mini_agent.application.ports.session_runtime_port import SessionRuntimePort
from mini_agent.application.ports.session_task_port import SessionTaskPort
from mini_agent.application.ports.session_task_runtime_port import SessionTaskRuntimePort
from mini_agent.application.ports.workspace_runtime_port import WorkspaceRuntimePort
from mini_agent.application.session_runtime_compat import (
    SessionBackedRunRuntimeAdapter,
    SessionTaskCompatibilityAdapter,
    UnavailableRunRuntimeAdapter,
)
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.application.use_cases.session_task_service import SessionTaskService

from .agent_user_service import AgentUserService
from .command_user_service import CommandUserService
from .model_user_service import ModelUserService
from .workspace_user_service import WorkspaceUserService


def _require_session_task_runtime(runtime: SessionTaskRuntimePort | None) -> SessionTaskRuntimePort:
    if runtime is None:
        raise RuntimeError("Session task runtime is not configured.")
    return runtime


def _require_session_task_port(port: SessionTaskPort | None) -> SessionTaskPort:
    if port is None:
        raise RuntimeError("Session task compatibility port is not configured.")
    return port


def _require_session_agent_runtime(runtime: SessionAgentRuntimePort | None) -> SessionAgentRuntimePort:
    if runtime is None:
        raise RuntimeError("Session agent compatibility runtime is not configured.")
    return runtime


def _require_session_model_runtime(
    runtime: SessionModelSelectionRuntimePort | None,
) -> SessionModelSelectionRuntimePort:
    if runtime is None:
        raise RuntimeError("Session model compatibility runtime is not configured.")
    return runtime


def _supports_session_task_port(candidate: object) -> bool:
    return all(
        hasattr(candidate, attr)
        for attr in (
            "get_session_task",
            "resolve_run_id_for_session",
            "cancel_session_turn",
            "resolve_pending_approval",
        )
    )


def _resolve_workspace_service(
    workspace_service: WorkspaceUserService | None,
    workspace_runtime: WorkspaceRuntimePort | None,
) -> WorkspaceUserService | None:
    if workspace_service is not None:
        return workspace_service
    if workspace_runtime is None:
        return None
    return WorkspaceUserService(workspace_runtime=workspace_runtime)


def _resolve_command_service(
    command_service: CommandUserService | None,
    command_runtime: Any,
) -> CommandUserService | None:
    if command_service is not None:
        return command_service
    if command_runtime is None:
        return None
    return CommandUserService(command_runtime=command_runtime)


@dataclass(frozen=True, slots=True)
class UserServiceAssembly:
    """Explicit Stage 3 assembly of user services over typed seams."""

    session_task_service: SessionTaskService
    run_control_service: RunControlApplicationService
    agent_service: AgentUserService
    model_service: ModelUserService
    workspace_service: WorkspaceUserService | None = None
    command_service: CommandUserService | None = None


@dataclass(frozen=True, slots=True)
class RuntimeBackedUserServicePorts:
    """Resolved runtime-backed port bundle for Stage 5 migration."""

    session_task_runtime: SessionTaskRuntimePort
    session_task_port: SessionTaskPort
    session_agent_runtime: SessionAgentRuntimePort
    session_model_runtime: SessionModelSelectionRuntimePort
    run_runtime: RunRuntimePort
    agent_runtime: AgentRuntimePort | None = None
    model_runtime: ModelRuntimePort | None = None
    workspace_runtime: WorkspaceRuntimePort | None = None
    command_runtime: Any = None


def resolve_runtime_backed_user_service_ports(
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
) -> RuntimeBackedUserServicePorts:
    """Resolve direct runtime-backed typed ports while isolating remaining compatibility seams."""

    return RuntimeBackedUserServicePorts(
        session_task_runtime=session_task_runtime or cast(SessionTaskRuntimePort, runtime_manager),
        # Run attachment remains transitional, but a real runtime manager can now satisfy the
        # session-task compatibility contract directly without an extra adapter layer.
        session_task_port=(
            session_task_port
            or (
                cast(SessionTaskPort, runtime_manager)
                if _supports_session_task_port(runtime_manager)
                else SessionTaskCompatibilityAdapter(runtime_manager)
            )
        ),
        session_agent_runtime=session_agent_runtime or cast(SessionAgentRuntimePort, runtime_manager),
        session_model_runtime=session_model_runtime or cast(SessionModelSelectionRuntimePort, runtime_manager),
        run_runtime=run_runtime or SessionBackedRunRuntimeAdapter(runtime_manager),
        agent_runtime=agent_runtime,
        model_runtime=model_runtime,
        workspace_runtime=workspace_runtime,
        command_runtime=command_runtime,
    )


def assemble_typed_user_services(
    *,
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
    run_control_service: RunControlApplicationService | None = None,
    agent_service: AgentUserService | None = None,
    workspace_service: WorkspaceUserService | None = None,
    model_service: ModelUserService | None = None,
    command_service: CommandUserService | None = None,
) -> UserServiceAssembly:
    """Assemble explicit user services from typed ports without legacy constructor fallback."""

    resolved_session_task_service = session_task_service or SessionTaskService(
        runtime_manager=_require_session_task_runtime(session_task_runtime)
    )
    resolved_run_control_service = run_control_service or RunControlApplicationService(
        run_runtime=run_runtime or UnavailableRunRuntimeAdapter(),
        session_tasks=_require_session_task_port(session_task_port),
    )
    resolved_agent_service = agent_service or AgentUserService(
        agent_runtime=agent_runtime,
        run_control=resolved_run_control_service,
        session_agent_runtime=_require_session_agent_runtime(session_agent_runtime),
    )
    resolved_model_service = model_service or ModelUserService(
        model_runtime=model_runtime,
        session_model_runtime=_require_session_model_runtime(session_model_runtime),
    )
    resolved_workspace_service = _resolve_workspace_service(workspace_service, workspace_runtime)
    resolved_command_service = _resolve_command_service(command_service, command_runtime)
    return UserServiceAssembly(
        session_task_service=resolved_session_task_service,
        run_control_service=resolved_run_control_service,
        agent_service=resolved_agent_service,
        model_service=resolved_model_service,
        workspace_service=resolved_workspace_service,
        command_service=resolved_command_service,
    )


def assemble_runtime_backed_user_services(
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
    run_control_service: RunControlApplicationService | None = None,
    agent_service: AgentUserService | None = None,
    workspace_service: WorkspaceUserService | None = None,
    model_service: ModelUserService | None = None,
    command_service: CommandUserService | None = None,
) -> UserServiceAssembly:
    """Assemble explicit user services from a broad runtime seam plus optional typed ports."""

    resolved_ports = resolve_runtime_backed_user_service_ports(
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
    )
    resolved_session_task_service = session_task_service or SessionTaskService(
        runtime_manager=_require_session_task_runtime(resolved_ports.session_task_runtime)
    )

    resolved_run_control_service = run_control_service or RunControlApplicationService(
        run_runtime=resolved_ports.run_runtime,
        session_tasks=_require_session_task_port(resolved_ports.session_task_port),
    )

    resolved_agent_service = agent_service or AgentUserService(
        agent_runtime=resolved_ports.agent_runtime,
        run_control=resolved_run_control_service,
        session_agent_runtime=_require_session_agent_runtime(resolved_ports.session_agent_runtime),
    )

    resolved_model_service = model_service or ModelUserService(
        model_runtime=resolved_ports.model_runtime,
        session_model_runtime=_require_session_model_runtime(resolved_ports.session_model_runtime),
    )

    resolved_workspace_service = _resolve_workspace_service(workspace_service, resolved_ports.workspace_runtime)
    resolved_command_service = _resolve_command_service(command_service, resolved_ports.command_runtime)

    return UserServiceAssembly(
        session_task_service=resolved_session_task_service,
        run_control_service=resolved_run_control_service,
        agent_service=resolved_agent_service,
        model_service=resolved_model_service,
        workspace_service=resolved_workspace_service,
        command_service=resolved_command_service,
    )


__all__ = [
    "RuntimeBackedUserServicePorts",
    "UserServiceAssembly",
    "assemble_runtime_backed_user_services",
    "assemble_typed_user_services",
    "resolve_runtime_backed_user_service_ports",
]
