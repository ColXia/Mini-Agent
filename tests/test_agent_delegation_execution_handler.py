from __future__ import annotations

import asyncio
from pathlib import Path

from mini_agent.agent_core.engine import TurnExecutionResult, TurnStopReason
from mini_agent.application.facades.agent_delegation_execution_handler import AgentDelegationExecutionHandler


class _FakeTurn:
    def __init__(
        self,
        *,
        session_id: str,
        workspace_dir: Path | None = None,
        active_surface: str = "tui",
        origin_surface: str = "tui",
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        recovery_context: dict[str, object] | None = None,
    ) -> None:
        self.session_id = session_id
        self.workspace_dir = workspace_dir or Path(".").resolve()
        self.active_surface = active_surface
        self.origin_surface = origin_surface
        self.channel_type = channel_type
        self.conversation_id = conversation_id
        self.sender_id = sender_id
        self.recovery_context = dict(recovery_context) if recovery_context is not None else None
        self.recorded_messages: list[dict[str, object]] = []
        self.touched = 0
        self.captured = 0
        self.cleared = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    def capture_prepared_context_state(self) -> None:
        self.captured += 1

    def clear_recovery_context(self) -> None:
        self.cleared += 1
        self.recovery_context = None

    def record_message(self, **kwargs) -> None:  # noqa: ANN003
        self.recorded_messages.append(dict(kwargs))

    def touch(self) -> None:
        self.touched += 1


class _FakeSessionService:
    def __init__(self, child_turn: _FakeTurn) -> None:
        self.child_turn = child_turn
        self.calls: list[dict[str, object]] = []

    async def prepare_derived_chat_turn(self, **kwargs):  # noqa: ANN003, ANN201
        self.calls.append(dict(kwargs))
        return self.child_turn


class _FakeAgentExecution:
    def __init__(self, *, child_should_fail: bool = False) -> None:
        self.child_should_fail = child_should_fail
        self.calls: list[tuple[str, str]] = []

    async def run_agent_once(self, turn, request):  # noqa: ANN001, ANN201
        self.calls.append((str(turn.session_id), str(request.message)))
        if str(turn.session_id).startswith("child"):
            if self.child_should_fail:
                raise RuntimeError("delegated-failure")
            return TurnExecutionResult(
                stop_reason=TurnStopReason.END_TURN,
                message=f"delegated:{request.message}",
            )
        return TurnExecutionResult(
            stop_reason=TurnStopReason.END_TURN,
            message=f"parent:{request.message}",
        )


def test_agent_delegation_execution_handler_success_creates_child_turn() -> None:
    async def _run() -> None:
        parent_turn = _FakeTurn(session_id="parent-1")
        child_turn = _FakeTurn(session_id="child-1", recovery_context={"from": "parent"})
        session_service = _FakeSessionService(child_turn)
        agent_execution = _FakeAgentExecution()
        handler = AgentDelegationExecutionHandler(
            session_service=session_service,
            agent_execution=agent_execution,
            delegation_owner="sub-agent",
            fallback_worker_id="main-agent",
        )

        result = await handler.execute(turn=parent_turn, delegate_prompt="ship p23.3")

        assert result.reply == "delegated:ship p23.3"
        assert result.success is True
        assert result.fallback_used is False
        assert result.worker_id == "sub-agent"
        assert result.child_session_id == "child-1"
        assert [item["event_type"] for item in result.events] == [
            "delegation.started",
            "delegation.completed",
        ]
        assert session_service.calls[0]["title"] == "Task: ship p23.3"
        assert agent_execution.calls == [("child-1", "ship p23.3")]
        assert child_turn.captured == 1
        assert child_turn.cleared == 1
        assert child_turn.touched == 1
        assert child_turn.recorded_messages[-1]["content"] == "delegated:ship p23.3"
        assert parent_turn.touched == 1

    asyncio.run(_run())


def test_agent_delegation_execution_handler_failure_falls_back_to_parent() -> None:
    async def _run() -> None:
        parent_turn = _FakeTurn(session_id="parent-2")
        child_turn = _FakeTurn(session_id="child-2")
        session_service = _FakeSessionService(child_turn)
        agent_execution = _FakeAgentExecution(child_should_fail=True)
        handler = AgentDelegationExecutionHandler(
            session_service=session_service,
            agent_execution=agent_execution,
            delegation_owner="sub-agent",
            fallback_worker_id="main-agent",
        )

        result = await handler.execute(turn=parent_turn, delegate_prompt="recover task")

        assert result.reply == "parent:recover task"
        assert result.success is False
        assert result.fallback_used is True
        assert result.worker_id == "main-agent"
        assert result.child_session_id == "child-2"
        assert result.error == "delegated-failure"
        assert [item["event_type"] for item in result.events] == [
            "delegation.started",
            "delegation.failed",
            "delegation.completed",
        ]
        assert agent_execution.calls == [
            ("child-2", "recover task"),
            ("parent-2", "recover task"),
        ]
        assert child_turn.captured == 0
        assert child_turn.cleared == 0
        assert child_turn.touched == 1
        assert child_turn.recorded_messages[-1]["metadata"] == {"kind": "delegation_error"}
        assert "delegated-failure" in str(child_turn.recorded_messages[-1]["content"])

    asyncio.run(_run())
