"""Agent user service for v11.3.

This module provides the AgentUserService that sits between
User Surfaces and the Business Logic Layer for agent-related operations.

Key responsibilities:
- Current agent running state
- Current agent model binding
- Current agent task entry
- interrupt / resume / cancel operations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from mini_agent.agent_core.contracts.agent_instance import (
    AgentInstance,
    AgentInstanceLifecycleState,
)
from mini_agent.agent_core.contracts.run import Run, RunStatus, RunPhase
from mini_agent.agent_core.contracts.agent_profile import AgentProfile
from mini_agent.utils.text import safe_text


def _safe_text(value: Any) -> str:
    return safe_text(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentStateKind(str, Enum):
    """Agent state kinds exposed to user surfaces."""

    IDLE = "idle"
    READY = "ready"
    RUNNING = "running"
    WAITING = "waiting"
    PAUSED = "paused"
    ERRORED = "errored"
    RETIRED = "retired"


class TaskSubmitResultKind(str, Enum):
    """Result kinds for task submission."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    QUEUED = "queued"


@dataclass(frozen=True, slots=True)
class AgentStateView:
    """View of agent state for user surfaces."""

    agent_id: str
    state_kind: AgentStateKind
    current_workspace_id: str | None = None
    current_session_id: str | None = None
    active_run_id: str | None = None
    model_id: str | None = None
    model_provider_id: str | None = None
    waiting_reason: str | None = None
    updated_at: datetime | None = None

    @property
    def is_idle(self) -> bool:
        return self.state_kind == AgentStateKind.IDLE

    @property
    def is_running(self) -> bool:
        return self.state_kind == AgentStateKind.RUNNING

    @property
    def is_waiting(self) -> bool:
        return self.state_kind == AgentStateKind.WAITING

    @property
    def can_submit(self) -> bool:
        return self.state_kind in {
            AgentStateKind.IDLE,
            AgentStateKind.READY,
            AgentStateKind.PAUSED,
        }


@dataclass(frozen=True, slots=True)
class TaskSubmitResult:
    """Result of task submission."""

    result_kind: TaskSubmitResultKind
    run_id: str | None = None
    session_id: str | None = None
    rejection_reason: str | None = None
    queued_position: int | None = None


@dataclass(frozen=True, slots=True)
class RunControlResult:
    """Result of run control operations."""

    success: bool
    run_id: str | None = None
    previous_status: RunStatus | None = None
    new_status: RunStatus | None = None
    error_reason: str | None = None


@dataclass(slots=True)
class AgentUserService:
    """User service for agent-related operations.

    This service provides a stable interface for TUI / Desktop / Remote
    to interact with the agent without directly accessing the kernel.

    The service aggregates:
    - AgentInstance state
    - Run control
    - Model binding queries
    - Session/task coordination
    """

    agent_id: str = "main-agent"
    _agent_instance: AgentInstance | None = None
    _agent_profile: AgentProfile | None = None
    _active_run: Run | None = None
    _model_binding_getter: Callable[[], dict[str, Any]] | None = None
    _run_submitter: Callable[[str, str | None], TaskSubmitResult] | None = None
    _run_interrupter: Callable[[], RunControlResult] | None = None
    _run_resumer: Callable[[], RunControlResult] | None = None
    _run_canceller: Callable[[], RunControlResult] | None = None

    def get_agent_state(self) -> AgentStateView:
        """Get the current agent state view.

        Returns:
            An AgentStateView with the current agent state
        """
        instance = self._agent_instance
        profile = self._agent_profile

        state_kind = self._map_lifecycle_to_state_kind(
            instance.lifecycle_state if instance else AgentInstanceLifecycleState.COLD
        )

        model_binding = self._get_model_binding()

        return AgentStateView(
            agent_id=self.agent_id,
            state_kind=state_kind,
            current_workspace_id=instance.current_workspace_id if instance else None,
            current_session_id=instance.current_session_id if instance else None,
            active_run_id=instance.active_run_id if instance else None,
            model_id=model_binding.get("model_id"),
            model_provider_id=model_binding.get("provider_id"),
            waiting_reason=str(instance.pending_wait_kind.value) if instance and instance.pending_wait_kind.value != "none" else None,
            updated_at=instance.updated_at if instance else None,
        )

    def get_model_binding(self) -> dict[str, Any]:
        """Get the current model binding.

        Returns:
            A dict with model binding information
        """
        return self._get_model_binding()

    def submit_task(
        self,
        task_content: str,
        *,
        session_id: str | None = None,
    ) -> TaskSubmitResult:
        """Submit a task for execution.

        Args:
            task_content: The task content to submit
            session_id: Optional session ID to use

        Returns:
            A TaskSubmitResult indicating the outcome
        """
        if not self._run_submitter:
            return TaskSubmitResult(
                result_kind=TaskSubmitResultKind.REJECTED,
                rejection_reason="No task submission handler configured",
            )

        normalized_content = _safe_text(task_content)
        if not normalized_content:
            return TaskSubmitResult(
                result_kind=TaskSubmitResultKind.REJECTED,
                rejection_reason="Task content is required",
            )

        state = self.get_agent_state()
        if not state.can_submit:
            return TaskSubmitResult(
                result_kind=TaskSubmitResultKind.REJECTED,
                rejection_reason=f"Agent is in {state.state_kind.value} state, cannot submit",
            )

        return self._run_submitter(normalized_content, session_id)

    def interrupt_run(self) -> RunControlResult:
        """Interrupt the current run.

        Returns:
            A RunControlResult indicating the outcome
        """
        if not self._run_interrupter:
            return RunControlResult(
                success=False,
                error_reason="No interrupt handler configured",
            )

        state = self.get_agent_state()
        if not state.is_running and state.state_kind != AgentStateKind.WAITING:
            return RunControlResult(
                success=False,
                error_reason=f"Agent is in {state.state_kind.value} state, cannot interrupt",
            )

        return self._run_interrupter()

    def resume_run(self) -> RunControlResult:
        """Resume a paused run.

        Returns:
            A RunControlResult indicating the outcome
        """
        if not self._run_resumer:
            return RunControlResult(
                success=False,
                error_reason="No resume handler configured",
            )

        state = self.get_agent_state()
        if state.state_kind != AgentStateKind.PAUSED:
            return RunControlResult(
                success=False,
                error_reason=f"Agent is in {state.state_kind.value} state, cannot resume",
            )

        return self._run_resumer()

    def cancel_run(self) -> RunControlResult:
        """Cancel the current run.

        Returns:
            A RunControlResult indicating the outcome
        """
        if not self._run_canceller:
            return RunControlResult(
                success=False,
                error_reason="No cancel handler configured",
            )

        state = self.get_agent_state()
        if state.state_kind in {AgentStateKind.IDLE, AgentStateKind.READY, AgentStateKind.RETIRED}:
            return RunControlResult(
                success=False,
                error_reason=f"Agent is in {state.state_kind.value} state, no run to cancel",
            )

        return self._run_canceller()

    def set_agent_instance(self, instance: AgentInstance) -> None:
        """Set the agent instance reference."""
        self._agent_instance = instance

    def set_agent_profile(self, profile: AgentProfile) -> None:
        """Set the agent profile reference."""
        self._agent_profile = profile

    def set_active_run(self, run: Run | None) -> None:
        """Set the active run reference."""
        self._active_run = run

    def set_model_binding_getter(self, getter: Callable[[], dict[str, Any]]) -> None:
        """Set the model binding getter function."""
        self._model_binding_getter = getter

    def set_run_submitter(self, submitter: Callable[[str, str | None], TaskSubmitResult]) -> None:
        """Set the task submission handler."""
        self._run_submitter = submitter

    def set_run_interrupter(self, interrupter: Callable[[], RunControlResult]) -> None:
        """Set the run interrupt handler."""
        self._run_interrupter = interrupter

    def set_run_resumer(self, resumer: Callable[[], RunControlResult]) -> None:
        """Set the run resume handler."""
        self._run_resumer = resumer

    def set_run_canceller(self, canceller: Callable[[], RunControlResult]) -> None:
        """Set the run cancel handler."""
        self._run_canceller = canceller

    def _get_model_binding(self) -> dict[str, Any]:
        """Get model binding from the configured getter."""
        if self._model_binding_getter:
            try:
                return self._model_binding_getter()
            except Exception:
                pass
        return {}

    @staticmethod
    def _map_lifecycle_to_state_kind(lifecycle: AgentInstanceLifecycleState) -> AgentStateKind:
        """Map agent instance lifecycle state to user-facing state kind."""
        mapping = {
            AgentInstanceLifecycleState.COLD: AgentStateKind.IDLE,
            AgentInstanceLifecycleState.READY: AgentStateKind.READY,
            AgentInstanceLifecycleState.ATTACHED: AgentStateKind.READY,
            AgentInstanceLifecycleState.RUNNING: AgentStateKind.RUNNING,
            AgentInstanceLifecycleState.WAITING: AgentStateKind.WAITING,
            AgentInstanceLifecycleState.PAUSED: AgentStateKind.PAUSED,
            AgentInstanceLifecycleState.MIGRATING: AgentStateKind.IDLE,
            AgentInstanceLifecycleState.ERRORED: AgentStateKind.ERRORED,
            AgentInstanceLifecycleState.RETIRED: AgentStateKind.RETIRED,
        }
        return mapping.get(lifecycle, AgentStateKind.IDLE)


__all__ = [
    "AgentStateKind",
    "AgentStateView",
    "AgentUserService",
    "RunControlResult",
    "TaskSubmitResult",
    "TaskSubmitResultKind",
]
