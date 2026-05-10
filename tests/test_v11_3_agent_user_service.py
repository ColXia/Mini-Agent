"""Tests for v11.3 AgentUserService."""

from __future__ import annotations

import pytest
from datetime import datetime, timezone

from mini_agent.agent_core.contracts.agent_instance import (
    AgentInstance,
    AgentInstanceLifecycleState,
)
from mini_agent.agent_core.contracts.agent_profile import AgentProfile
from mini_agent.agent_core.contracts.run import Run, RunStatus, RunPhase
from mini_agent.user_services.agent_user_service import (
    AgentStateKind,
    AgentStateView,
    AgentUserService,
    RunControlResult,
    TaskSubmitResult,
    TaskSubmitResultKind,
)


class TestAgentStateView:
    """Tests for AgentStateView."""

    def test_state_view_creation(self) -> None:
        view = AgentStateView(
            agent_id="main-agent",
            state_kind=AgentStateKind.RUNNING,
            current_workspace_id="ws-001",
            current_session_id="sess-001",
            active_run_id="run-001",
            model_id="gpt-4",
            model_provider_id="openai",
        )
        assert view.agent_id == "main-agent"
        assert view.state_kind == AgentStateKind.RUNNING
        assert view.is_running is True
        assert view.is_idle is False
        assert view.is_waiting is False

    def test_state_view_can_submit(self) -> None:
        idle_view = AgentStateView(
            agent_id="main-agent",
            state_kind=AgentStateKind.IDLE,
        )
        assert idle_view.can_submit is True

        running_view = AgentStateView(
            agent_id="main-agent",
            state_kind=AgentStateKind.RUNNING,
        )
        assert running_view.can_submit is False

        paused_view = AgentStateView(
            agent_id="main-agent",
            state_kind=AgentStateKind.PAUSED,
        )
        assert paused_view.can_submit is True


class TestAgentUserService:
    """Tests for AgentUserService."""

    def test_service_creation(self) -> None:
        service = AgentUserService(agent_id="test-agent")
        assert service.agent_id == "test-agent"

    def test_get_agent_state_without_instance(self) -> None:
        service = AgentUserService()
        state = service.get_agent_state()
        assert state.agent_id == "main-agent"
        assert state.state_kind == AgentStateKind.IDLE
        assert state.current_workspace_id is None
        assert state.active_run_id is None

    def test_get_agent_state_with_instance(self) -> None:
        service = AgentUserService()
        instance = AgentInstance(
            agent_instance_id="inst-001",
            agent_profile_id="profile-001",
            lifecycle_state=AgentInstanceLifecycleState.RUNNING,
            current_workspace_id="ws-001",
            current_session_id="sess-001",
            active_run_id="run-001",
        )
        service.set_agent_instance(instance)

        state = service.get_agent_state()
        assert state.state_kind == AgentStateKind.RUNNING
        assert state.current_workspace_id == "ws-001"
        assert state.active_run_id == "run-001"

    def test_get_model_binding(self) -> None:
        service = AgentUserService()
        service.set_model_binding_getter(lambda: {
            "model_id": "gpt-4",
            "provider_id": "openai",
        })

        binding = service.get_model_binding()
        assert binding["model_id"] == "gpt-4"
        assert binding["provider_id"] == "openai"

    def test_submit_task_without_handler(self) -> None:
        service = AgentUserService()
        result = service.submit_task("test task")
        assert result.result_kind == TaskSubmitResultKind.REJECTED
        assert "No task submission handler" in result.rejection_reason

    def test_submit_task_with_handler(self) -> None:
        service = AgentUserService()

        def submit_handler(content: str, session_id: str | None) -> TaskSubmitResult:
            return TaskSubmitResult(
                result_kind=TaskSubmitResultKind.ACCEPTED,
                run_id="run-001",
                session_id=session_id or "sess-001",
            )

        service.set_run_submitter(submit_handler)
        result = service.submit_task("test task")
        assert result.result_kind == TaskSubmitResultKind.ACCEPTED
        assert result.run_id == "run-001"

    def test_submit_task_empty_content(self) -> None:
        service = AgentUserService()
        service.set_run_submitter(lambda c, s: TaskSubmitResult(result_kind=TaskSubmitResultKind.ACCEPTED))

        result = service.submit_task("")
        assert result.result_kind == TaskSubmitResultKind.REJECTED
        assert "Task content is required" in result.rejection_reason

    def test_submit_task_when_running(self) -> None:
        service = AgentUserService()
        instance = AgentInstance(
            agent_instance_id="inst-001",
            agent_profile_id="profile-001",
            lifecycle_state=AgentInstanceLifecycleState.RUNNING,
        )
        service.set_agent_instance(instance)
        service.set_run_submitter(lambda c, s: TaskSubmitResult(result_kind=TaskSubmitResultKind.ACCEPTED))

        result = service.submit_task("test task")
        assert result.result_kind == TaskSubmitResultKind.REJECTED
        assert "cannot submit" in result.rejection_reason

    def test_interrupt_run_without_handler(self) -> None:
        service = AgentUserService()
        result = service.interrupt_run()
        assert result.success is False
        assert "No interrupt handler" in result.error_reason

    def test_interrupt_run_when_running(self) -> None:
        service = AgentUserService()
        instance = AgentInstance(
            agent_instance_id="inst-001",
            agent_profile_id="profile-001",
            lifecycle_state=AgentInstanceLifecycleState.RUNNING,
        )
        service.set_agent_instance(instance)
        service.set_run_interrupter(lambda: RunControlResult(
            success=True,
            run_id="run-001",
            previous_status=RunStatus.RUNNING,
            new_status=RunStatus.PAUSED,
        ))

        result = service.interrupt_run()
        assert result.success is True
        assert result.previous_status == RunStatus.RUNNING
        assert result.new_status == RunStatus.PAUSED

    def test_resume_run_when_paused(self) -> None:
        service = AgentUserService()
        instance = AgentInstance(
            agent_instance_id="inst-001",
            agent_profile_id="profile-001",
            lifecycle_state=AgentInstanceLifecycleState.PAUSED,
        )
        service.set_agent_instance(instance)
        service.set_run_resumer(lambda: RunControlResult(
            success=True,
            run_id="run-001",
            previous_status=RunStatus.PAUSED,
            new_status=RunStatus.RUNNING,
        ))

        result = service.resume_run()
        assert result.success is True

    def test_cancel_run(self) -> None:
        service = AgentUserService()
        instance = AgentInstance(
            agent_instance_id="inst-001",
            agent_profile_id="profile-001",
            lifecycle_state=AgentInstanceLifecycleState.RUNNING,
        )
        service.set_agent_instance(instance)
        service.set_run_canceller(lambda: RunControlResult(
            success=True,
            run_id="run-001",
            previous_status=RunStatus.RUNNING,
            new_status=RunStatus.CANCELLED,
        ))

        result = service.cancel_run()
        assert result.success is True
        assert result.new_status == RunStatus.CANCELLED
