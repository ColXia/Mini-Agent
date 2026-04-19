"""Assembly helpers for Stage 3 explicit user-service wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, cast

from mini_agent.application.ports.agent_runtime_port import AgentRuntimePort
from mini_agent.application.ports.model_runtime_port import ModelRuntimePort
from mini_agent.application.ports.run_runtime_port import RunRuntimePort
from mini_agent.application.ports.session_agent_runtime_port import SessionAgentRuntimePort
from mini_agent.application.ports.session_task_port import SessionTaskPort
from mini_agent.application.ports.session_task_runtime_port import SessionTaskRuntimePort
from mini_agent.application.ports.workspace_runtime_port import WorkspaceRuntimePort
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.application.use_cases.session_task_service import SessionTaskService

from .agent_user_service import AgentUserService
from .command_user_service import CommandUserService
from .model_user_service import ModelUserService
from .workspace_user_service import WorkspaceUserService


class RuntimeBackedUserServiceSupport(
    SessionTaskRuntimePort,
    RunRuntimePort,
    SessionAgentRuntimePort,
    Protocol,
):
    """Narrow structural support contract for resolving runtime-backed typed ports."""

    async def resolve_run_id_for_session(self, session_id: str) -> str | None: ...


def _require_session_task_runtime(runtime: SessionTaskRuntimePort | None) -> SessionTaskRuntimePort:
    if runtime is None:
        raise RuntimeError("Session task runtime is not configured.")
    return runtime


def _require_session_task_port(port: SessionTaskPort | None) -> SessionTaskPort:
    if port is None:
        raise RuntimeError("Session task port is not configured.")
    return port


def _require_session_agent_runtime(runtime: SessionAgentRuntimePort | None) -> SessionAgentRuntimePort:
    if runtime is None:
        raise RuntimeError("Session agent runtime is not configured.")
    return runtime


def _require_run_runtime(runtime: RunRuntimePort | None) -> RunRuntimePort:
    if runtime is None:
        raise RuntimeError("Run runtime is not configured.")
    return runtime


def _supports_session_task_port(candidate: object) -> bool:
    return hasattr(candidate, "resolve_run_id_for_session")


def _supports_run_runtime(candidate: object) -> bool:
    return all(
        hasattr(candidate, attr)
        for attr in (
            "get_run",
            "interrupt_run",
            "resume_run",
            "cancel_run",
            "resolve_approval_wait",
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
    run_runtime: RunRuntimePort
    agent_runtime: AgentRuntimePort | None = None
    model_runtime: ModelRuntimePort | None = None
    workspace_runtime: WorkspaceRuntimePort | None = None
    command_runtime: Any = None


def resolve_runtime_backed_user_service_ports(
    *,
    runtime_manager: RuntimeBackedUserServiceSupport,
    session_task_runtime: SessionTaskRuntimePort | None = None,
    session_task_port: SessionTaskPort | None = None,
    session_agent_runtime: SessionAgentRuntimePort | None = None,
    agent_runtime: AgentRuntimePort | None = None,
    run_runtime: RunRuntimePort | None = None,
    model_runtime: ModelRuntimePort | None = None,
    workspace_runtime: WorkspaceRuntimePort | None = None,
    command_runtime: Any = None,
) -> RuntimeBackedUserServicePorts:
    """Resolve direct runtime-backed typed ports from the active runtime owner."""

    return RuntimeBackedUserServicePorts(
        session_task_runtime=session_task_runtime or cast(SessionTaskRuntimePort, runtime_manager),
        session_task_port=session_task_port
        or (
            cast(SessionTaskPort, runtime_manager)
            if _supports_session_task_port(runtime_manager)
            else (_raise_missing_session_task_port())
        ),
        session_agent_runtime=session_agent_runtime or cast(SessionAgentRuntimePort, runtime_manager),
        run_runtime=run_runtime
        or (
            cast(RunRuntimePort, runtime_manager)
            if _supports_run_runtime(runtime_manager)
            else (_raise_missing_run_runtime())
        ),
        agent_runtime=agent_runtime,
        model_runtime=model_runtime,
        workspace_runtime=workspace_runtime,
        command_runtime=command_runtime,
    )


def _raise_missing_session_task_port() -> SessionTaskPort:
    raise RuntimeError(
        "Runtime-backed user-service assembly requires direct session-to-run lookup support; "
        "session compatibility adapters are no longer an active path."
    )


def _raise_missing_run_runtime() -> RunRuntimePort:
    raise RuntimeError(
        "Runtime-backed user-service assembly requires direct run-runtime methods; "
        "session-derived run compatibility is no longer an active path."
    )


def assemble_typed_user_services(
    *,
    session_task_runtime: SessionTaskRuntimePort | None = None,
    session_task_port: SessionTaskPort | None = None,
    session_agent_runtime: SessionAgentRuntimePort | None = None,
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
    """Assemble explicit user services from typed ports only."""

    resolved_session_task_service = session_task_service or SessionTaskService(
        runtime_manager=_require_session_task_runtime(session_task_runtime),
        session_agent_runtime=_require_session_agent_runtime(session_agent_runtime),
    )
    resolved_run_control_service = run_control_service or RunControlApplicationService(
        run_runtime=_require_run_runtime(run_runtime),
        session_run_lookup=_require_session_task_port(session_task_port),
    )
    resolved_agent_service = agent_service or AgentUserService(
        agent_runtime=agent_runtime,
        run_control=resolved_run_control_service,
    )
    resolved_model_service = model_service or ModelUserService(
        model_runtime=model_runtime,
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
    runtime_manager: RuntimeBackedUserServiceSupport,
    session_task_runtime: SessionTaskRuntimePort | None = None,
    session_task_port: SessionTaskPort | None = None,
    session_agent_runtime: SessionAgentRuntimePort | None = None,
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
        agent_runtime=agent_runtime,
        run_runtime=run_runtime,
        model_runtime=model_runtime,
        workspace_runtime=workspace_runtime,
        command_runtime=command_runtime,
    )
    resolved_session_task_service = session_task_service or SessionTaskService(
        runtime_manager=_require_session_task_runtime(resolved_ports.session_task_runtime),
        session_agent_runtime=_require_session_agent_runtime(resolved_ports.session_agent_runtime),
    )

    resolved_run_control_service = run_control_service or RunControlApplicationService(
        run_runtime=resolved_ports.run_runtime,
        session_run_lookup=_require_session_task_port(resolved_ports.session_task_port),
    )

    resolved_agent_service = agent_service or AgentUserService(
        agent_runtime=resolved_ports.agent_runtime,
        run_control=resolved_run_control_service,
    )

    resolved_model_service = model_service or ModelUserService(
        model_runtime=resolved_ports.model_runtime,
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
    "RuntimeBackedUserServiceSupport",
    "RuntimeBackedUserServicePorts",
    "UserServiceAssembly",
    "assemble_runtime_backed_user_services",
    "assemble_typed_user_services",
    "resolve_runtime_backed_user_service_ports",
]
