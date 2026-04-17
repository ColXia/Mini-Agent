"""Assembly helpers for runtime-backed session application services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mini_agent.application.ports.session_runtime_port import SessionRuntimePort
from mini_agent.application.ports.session_task_port import SessionTaskPort
from mini_agent.application.ports.session_task_runtime_port import SessionTaskRuntimePort
from mini_agent.application.use_cases.run_control_application_service import RunControlApplicationService
from mini_agent.application.use_cases.session_task_service import SessionTaskService
from mini_agent.application.user_services.agent_user_service import AgentUserService
from mini_agent.application.user_services.model_user_service import ModelUserService

from .session_runtime_compat import (
    SessionAgentCompatibilityAdapter,
    SessionModelSelectionCompatibilityAdapter,
    SessionTaskCompatibilityAdapter,
    UnavailableRunRuntimeAdapter,
)
from .session_agent_runtime_port import SessionAgentRuntimePort
from .session_model_selection_runtime_port import SessionModelSelectionRuntimePort

if TYPE_CHECKING:
    from mini_agent.application.legacy import SessionApplicationService


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


@dataclass(frozen=True, slots=True)
class RuntimeBackedSessionApplicationAssembly:
    """Explicitly assembled runtime-backed session application dependencies."""

    session_task_service: SessionTaskService
    run_control_service: RunControlApplicationService
    agent_service: AgentUserService
    model_service: ModelUserService


def assemble_typed_session_application(
    *,
    session_task_runtime: SessionTaskRuntimePort | None = None,
    session_task_port: SessionTaskPort | None = None,
    session_agent_runtime: SessionAgentRuntimePort | None = None,
    session_model_runtime: SessionModelSelectionRuntimePort | None = None,
    session_task_service: SessionTaskService | None = None,
    run_control_service: RunControlApplicationService | None = None,
    agent_service: AgentUserService | None = None,
    model_service: ModelUserService | None = None,
) -> RuntimeBackedSessionApplicationAssembly:
    """Assemble explicit session application dependencies from typed seams only."""

    resolved_session_task_service = session_task_service or SessionTaskService(
        runtime_manager=_require_session_task_runtime(session_task_runtime)
    )
    resolved_run_control_service = run_control_service or RunControlApplicationService(
        run_runtime=UnavailableRunRuntimeAdapter(),
        session_tasks=_require_session_task_port(session_task_port),
    )
    resolved_agent_service = agent_service or AgentUserService(
        run_control=resolved_run_control_service,
        session_agent_runtime=_require_session_agent_runtime(session_agent_runtime),
    )
    resolved_model_service = model_service or ModelUserService(
        session_model_runtime=_require_session_model_runtime(session_model_runtime),
    )
    return RuntimeBackedSessionApplicationAssembly(
        session_task_service=resolved_session_task_service,
        run_control_service=resolved_run_control_service,
        agent_service=resolved_agent_service,
        model_service=resolved_model_service,
    )


def assemble_runtime_backed_session_application(
    *,
    runtime_manager: SessionRuntimePort,
    session_task_runtime: SessionTaskRuntimePort | None = None,
    session_task_port: SessionTaskPort | None = None,
    session_agent_runtime: SessionAgentRuntimePort | None = None,
    session_model_runtime: SessionModelSelectionRuntimePort | None = None,
    session_task_service: SessionTaskService | None = None,
    run_control_service: RunControlApplicationService | None = None,
    agent_service: AgentUserService | None = None,
    model_service: ModelUserService | None = None,
) -> RuntimeBackedSessionApplicationAssembly:
    """Assemble explicit session application dependencies from a broad runtime seam."""

    resolved_session_task_runtime = session_task_runtime or runtime_manager
    resolved_session_task_service = session_task_service or SessionTaskService(
        runtime_manager=_require_session_task_runtime(resolved_session_task_runtime)
    )

    resolved_session_task_port = session_task_port or SessionTaskCompatibilityAdapter(runtime_manager)
    resolved_run_control_service = run_control_service or RunControlApplicationService(
        run_runtime=UnavailableRunRuntimeAdapter(),
        session_tasks=_require_session_task_port(resolved_session_task_port),
    )

    resolved_session_agent_runtime = session_agent_runtime or SessionAgentCompatibilityAdapter(runtime_manager)
    resolved_agent_service = agent_service or AgentUserService(
        run_control=resolved_run_control_service,
        session_agent_runtime=_require_session_agent_runtime(resolved_session_agent_runtime),
    )

    resolved_session_model_runtime = session_model_runtime or SessionModelSelectionCompatibilityAdapter(runtime_manager)
    resolved_model_service = model_service or ModelUserService(
        session_model_runtime=_require_session_model_runtime(resolved_session_model_runtime),
    )

    return RuntimeBackedSessionApplicationAssembly(
        session_task_service=resolved_session_task_service,
        run_control_service=resolved_run_control_service,
        agent_service=resolved_agent_service,
        model_service=resolved_model_service,
    )


def build_runtime_backed_session_service(
    *,
    runtime_manager: SessionRuntimePort,
    session_task_runtime: SessionTaskRuntimePort | None = None,
    session_task_port: SessionTaskPort | None = None,
    session_agent_runtime: SessionAgentRuntimePort | None = None,
    session_model_runtime: SessionModelSelectionRuntimePort | None = None,
    session_task_service: SessionTaskService | None = None,
    run_control_service: RunControlApplicationService | None = None,
    agent_service: AgentUserService | None = None,
    model_service: ModelUserService | None = None,
) -> "SessionApplicationService":
    """Build the legacy session facade from explicit assembly rather than constructor fallback."""

    from mini_agent.application.legacy import SessionApplicationService

    assembly = assemble_runtime_backed_session_application(
        runtime_manager=runtime_manager,
        session_task_runtime=session_task_runtime,
        session_task_port=session_task_port,
        session_agent_runtime=session_agent_runtime,
        session_model_runtime=session_model_runtime,
        session_task_service=session_task_service,
        run_control_service=run_control_service,
        agent_service=agent_service,
        model_service=model_service,
    )
    return SessionApplicationService(
        session_task_service=assembly.session_task_service,
        run_control_service=assembly.run_control_service,
        agent_service=assembly.agent_service,
        model_service=assembly.model_service,
    )


def build_typed_session_service(
    *,
    session_task_runtime: SessionTaskRuntimePort | None = None,
    session_task_port: SessionTaskPort | None = None,
    session_agent_runtime: SessionAgentRuntimePort | None = None,
    session_model_runtime: SessionModelSelectionRuntimePort | None = None,
    session_task_service: SessionTaskService | None = None,
    run_control_service: RunControlApplicationService | None = None,
    agent_service: AgentUserService | None = None,
    model_service: ModelUserService | None = None,
) -> "SessionApplicationService":
    """Build the legacy session facade from typed seams without constructor fallback."""

    from mini_agent.application.legacy import SessionApplicationService

    assembly = assemble_typed_session_application(
        session_task_runtime=session_task_runtime,
        session_task_port=session_task_port,
        session_agent_runtime=session_agent_runtime,
        session_model_runtime=session_model_runtime,
        session_task_service=session_task_service,
        run_control_service=run_control_service,
        agent_service=agent_service,
        model_service=model_service,
    )
    return SessionApplicationService(
        session_task_service=assembly.session_task_service,
        run_control_service=assembly.run_control_service,
        agent_service=assembly.agent_service,
        model_service=assembly.model_service,
    )


__all__ = [
    "RuntimeBackedSessionApplicationAssembly",
    "assemble_runtime_backed_session_application",
    "assemble_typed_session_application",
    "build_runtime_backed_session_service",
    "build_typed_session_service",
]
