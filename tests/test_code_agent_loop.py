"""Tests for P14 T2.1 code-agent submission loop baseline."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pytest

from mini_agent.agent import TurnExecutionResult, TurnStopReason
from mini_agent.code_agent import AgentLoopContext, AgentSubmissionLoop, InMemoryLoopMessageBus


@dataclass
class _AgentConfig:
    max_steps: int = 50
    max_tool_calls_per_step: int | None = None


@dataclass
class _Config:
    agent: _AgentConfig


class _FakeAgent:
    def __init__(self, *, delay_seconds: float = 0.0):
        self.max_steps = 99
        self.max_tool_calls_per_step = 9
        self.execution_policy = {
            "max_steps": self.max_steps,
            "max_tool_calls_per_step": self.max_tool_calls_per_step,
        }
        self.delay_seconds = max(0.0, float(delay_seconds))
        self.messages: list[str] = []
        self.run_turn_calls: list[dict[str, object]] = []

    def add_user_message(self, content: str) -> None:
        self.messages.append(content)

    async def run_turn(self, *, cancel_event=None, hooks=None, start_new_run=True):  # noqa: ANN001
        del hooks
        call_record = {
            "max_steps": self.max_steps,
            "max_tool_calls_per_step": self.max_tool_calls_per_step,
            "start_new_run": bool(start_new_run),
            "cancel_event_supplied": cancel_event is not None,
        }
        self.run_turn_calls.append(call_record)

        if self.delay_seconds > 0:
            elapsed = 0.0
            while elapsed < self.delay_seconds:
                await asyncio.sleep(0.01)
                elapsed += 0.01
                if cancel_event is not None and cancel_event.is_set():
                    return TurnExecutionResult(
                        stop_reason=TurnStopReason.CANCELLED,
                        message="cancelled",
                    )

        if cancel_event is not None and cancel_event.is_set():
            return TurnExecutionResult(
                stop_reason=TurnStopReason.CANCELLED,
                message="cancelled",
            )

        return TurnExecutionResult(
            stop_reason=TurnStopReason.END_TURN,
            message="ok",
        )


def _find_event(bus: InMemoryLoopMessageBus, event_type: str) -> dict[str, object]:
    for item in bus.events:
        if item["event_type"] == event_type:
            return item["payload"]
    raise AssertionError(f"Expected event {event_type} was not published.")


@pytest.mark.asyncio
async def test_submission_loop_processes_user_input_with_turn_snapshot():
    bus = InMemoryLoopMessageBus()
    config = _Config(agent=_AgentConfig(max_steps=20, max_tool_calls_per_step=3))
    context = AgentLoopContext(config=config, message_bus=bus, session_id="session-a")
    agent = _FakeAgent()
    loop = AgentSubmissionLoop(context=context, agent_factory=lambda _ctx: agent)

    await loop.start()
    submission_id = await loop.submit_user_input(
        "hello",
        policy_overrides={"max_steps": 5, "max_tool_calls_per_step": 2},
        metadata={"trace_id": "trace-1"},
        start_new_run=False,
    )
    await loop.join()
    await loop.stop()

    assert submission_id
    assert agent.messages == ["hello"]
    assert len(agent.run_turn_calls) == 1
    assert agent.run_turn_calls[0]["max_steps"] == 5
    assert agent.run_turn_calls[0]["max_tool_calls_per_step"] == 2
    assert agent.run_turn_calls[0]["start_new_run"] is False
    assert agent.max_steps == 99
    assert agent.max_tool_calls_per_step == 9

    scheduled = _find_event(bus, "loop.turn.scheduled")
    assert scheduled["submission_id"] == submission_id
    assert scheduled["session_id"] == "session-a"
    assert scheduled["policy"]["max_steps"] == 5
    assert scheduled["policy"]["max_tool_calls_per_step"] == 2
    assert scheduled["metadata"]["trace_id"] == "trace-1"

    completed = _find_event(bus, "loop.turn.completed")
    assert completed["submission_id"] == submission_id
    assert completed["state"] == "completed"
    assert completed["stop_reason"] == "end_turn"


@pytest.mark.asyncio
async def test_submission_loop_turn_snapshot_isolated_from_late_config_change():
    bus = InMemoryLoopMessageBus()
    config = _Config(agent=_AgentConfig(max_steps=12, max_tool_calls_per_step=None))
    context = AgentLoopContext(config=config, message_bus=bus, session_id="session-b")
    agent = _FakeAgent()
    loop = AgentSubmissionLoop(context=context, agent_factory=lambda _ctx: agent)

    await loop.submit_user_input("snapshot-test")
    config.agent.max_steps = 77

    await loop.start()
    await loop.join()
    await loop.stop()

    assert len(agent.run_turn_calls) == 1
    assert agent.run_turn_calls[0]["max_steps"] == 12


@pytest.mark.asyncio
async def test_submission_loop_interrupt_cancels_running_turn():
    bus = InMemoryLoopMessageBus()
    config = _Config(agent=_AgentConfig(max_steps=30, max_tool_calls_per_step=4))
    context = AgentLoopContext(config=config, message_bus=bus, session_id="session-c")
    agent = _FakeAgent(delay_seconds=0.8)
    loop = AgentSubmissionLoop(context=context, agent_factory=lambda _ctx: agent)

    await loop.start()
    await loop.submit_user_input("long-running")

    # Wait until one submission is active.
    for _ in range(60):
        if loop.current_submission_id is not None:
            break
        await asyncio.sleep(0.01)
    assert loop.current_submission_id is not None

    await loop.submit_interrupt(reason="user_cancel")
    await loop.join()
    await loop.stop()

    completed = _find_event(bus, "loop.turn.completed")
    assert completed["state"] == "interrupted"
    assert completed["stop_reason"] == "cancelled"

    interrupt = _find_event(bus, "loop.interrupt")
    assert interrupt["dispatched"] is True

