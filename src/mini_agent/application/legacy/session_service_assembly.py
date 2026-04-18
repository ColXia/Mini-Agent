"""Assembly helpers for runtime-backed legacy session application services."""

from __future__ import annotations

from typing import TYPE_CHECKING

from mini_agent.application.ports.agent_runtime_port import AgentRuntimePort
from mini_agent.application.ports.model_runtime_port import ModelRuntimePort
from mini_agent.application.ports.run_runtime_port import RunRuntimePort
from mini_agent.application.ports.session_runtime_port import SessionRuntimePort
from mini_agent.application.ports.session_task_port import SessionTaskPort
from mini_agent.application.ports.session_task_runtime_port import SessionTaskRuntimePort
from mini_agent.application.ports.workspace_runtime_port import WorkspaceRuntimePort
from mini_agent.application.user_service_assembly import (
    UserServiceAssembly as RuntimeBackedSessionApplicationAssembly,
    assemble_runtime_backed_user_services,
    assemble_typed_user_services,
)
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.application.use_cases.session_task_service import SessionTaskService
from mini_agent.application.user_services.agent_user_service import AgentUserService
from mini_agent.application.user_services.command_user_service import CommandUserService
from mini_agent.application.user_services.model_user_service import ModelUserService
from .session_agent_runtime_port import SessionAgentRuntimePort
from .session_model_selection_runtime_port import SessionModelSelectionRuntimePort
from ..user_services.workspace_user_service import WorkspaceUserService

if TYPE_CHECKING:
    from mini_agent.application.legacy import SessionApplicationService


def assemble_typed_session_application(
    *,
    session_task_runtime: SessionTaskRuntimePort | None = None,
    session_task_port: SessionTaskPort | None = None,
    session_agent_runtime: SessionAgentRuntimePort | None = None,
    session_model_runtime: SessionModelSelectionRuntimePort | None = None,
    agent_runtime: AgentRuntimePort | None = None,
    run_runtime: RunRuntimePort | None = None,
    model_runtime: ModelRuntimePort | None = None,
    workspace_runtime: WorkspaceRuntimePort | None = None,
    command_runtime: object = None,
    session_task_service: SessionTaskService | None = None,
    run_control_service: RunControlApplicationService | None = None,
    agent_service: AgentUserService | None = None,
    workspace_service: WorkspaceUserService | None = None,
    model_service: ModelUserService | None = None,
    command_service: CommandUserService | None = None,
) -> RuntimeBackedSessionApplicationAssembly:
    """Compatibility wrapper over Stage 3 typed user-service assembly."""

    return assemble_typed_user_services(
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


def assemble_runtime_backed_session_application(
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
    command_runtime: object = None,
    session_task_service: SessionTaskService | None = None,
    run_control_service: RunControlApplicationService | None = None,
    agent_service: AgentUserService | None = None,
    workspace_service: WorkspaceUserService | None = None,
    model_service: ModelUserService | None = None,
    command_service: CommandUserService | None = None,
) -> RuntimeBackedSessionApplicationAssembly:
    """Compatibility wrapper over Stage 3 runtime-backed user-service assembly."""

    return assemble_runtime_backed_user_services(
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


def build_runtime_backed_session_service(
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
    command_runtime: object = None,
    session_task_service: SessionTaskService | None = None,
    run_control_service: RunControlApplicationService | None = None,
    agent_service: AgentUserService | None = None,
    workspace_service: WorkspaceUserService | None = None,
    model_service: ModelUserService | None = None,
    command_service: CommandUserService | None = None,
) -> "SessionApplicationService":
    """Build the legacy facade through the runtime-compatibility classmethod."""

    from mini_agent.application.legacy import SessionApplicationService

    return SessionApplicationService.from_runtime_compatibility(
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


def build_typed_session_service(
    *,
    session_task_runtime: SessionTaskRuntimePort | None = None,
    session_task_port: SessionTaskPort | None = None,
    session_agent_runtime: SessionAgentRuntimePort | None = None,
    session_model_runtime: SessionModelSelectionRuntimePort | None = None,
    agent_runtime: AgentRuntimePort | None = None,
    run_runtime: RunRuntimePort | None = None,
    model_runtime: ModelRuntimePort | None = None,
    workspace_runtime: WorkspaceRuntimePort | None = None,
    command_runtime: object = None,
    session_task_service: SessionTaskService | None = None,
    run_control_service: RunControlApplicationService | None = None,
    agent_service: AgentUserService | None = None,
    workspace_service: WorkspaceUserService | None = None,
    model_service: ModelUserService | None = None,
    command_service: CommandUserService | None = None,
) -> "SessionApplicationService":
    """Build the legacy facade through the typed-compatibility classmethod."""

    from mini_agent.application.legacy import SessionApplicationService

    return SessionApplicationService.from_typed_compatibility(
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


__all__ = [
    "RuntimeBackedSessionApplicationAssembly",
    "assemble_runtime_backed_session_application",
    "assemble_typed_session_application",
    "build_runtime_backed_session_service",
    "build_typed_session_service",
]
