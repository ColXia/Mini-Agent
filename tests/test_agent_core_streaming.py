from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_agent.agent_core.context.loop_context import AgentLoopContext
from mini_agent.agent_core.engine import Agent, PlannerExecutorHooks, TurnStopReason
from mini_agent.agent_core.execution.agent_loop import (
    AgentSubmissionLoop,
    InMemoryLoopMessageBus,
    wait_for_submission_completion,
)
from mini_agent.schema.schema import LLMStreamEvent, LLMStreamEventType


class _StreamingLLM:
    async def stream_generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        _ = messages
        yield LLMStreamEvent(type=LLMStreamEventType.MESSAGE_START, metadata={"protocol": "test"})
        yield LLMStreamEvent(type=LLMStreamEventType.THINKING_DELTA, delta="plan ")
        yield LLMStreamEvent(type=LLMStreamEventType.TEXT_DELTA, delta="hello ")
        yield LLMStreamEvent(type=LLMStreamEventType.TEXT_DELTA, delta="world")
        yield LLMStreamEvent(type=LLMStreamEventType.MESSAGE_STOP, finish_reason="stop")


@pytest.mark.asyncio
async def test_agent_run_turn_aggregates_native_stream_events(tmp_path: Path) -> None:
    agent = Agent(
        llm_client=_StreamingLLM(),
        system_prompt="You are a test agent.",
        tools=[],
        workspace_dir=str(tmp_path),
        console_output=False,
    )
    agent.add_user_message("say hello")

    seen_events: list[tuple[int, str, str | None]] = []

    async def _on_llm_event(step: int, event: LLMStreamEvent) -> None:
        seen_events.append((step, event.type.value, event.delta))

    result = await agent.run_turn(
        hooks=PlannerExecutorHooks(on_llm_event=_on_llm_event),
        turn_context={"session_id": "sess-stream", "submission_id": "sub-stream", "user_input": "say hello"},
    )

    assert result.stop_reason == TurnStopReason.END_TURN
    assert result.message == "hello world"
    assert seen_events == [
        (1, "message_start", None),
        (1, "thinking_delta", "plan "),
        (1, "text_delta", "hello "),
        (1, "text_delta", "world"),
        (1, "message_stop", None),
    ]
    assert agent.messages[-1].role == "assistant"
    assert agent.messages[-1].content == "hello world"
    assert agent.messages[-1].thinking == "plan "


@pytest.mark.asyncio
async def test_submission_loop_publishes_llm_stream_events(tmp_path: Path) -> None:
    agent = Agent(
        llm_client=_StreamingLLM(),
        system_prompt="You are a test agent.",
        tools=[],
        workspace_dir=str(tmp_path),
        console_output=False,
    )
    bus = InMemoryLoopMessageBus()
    loop = AgentSubmissionLoop(
        context=AgentLoopContext(
            config=SimpleNamespace(agent=SimpleNamespace(max_steps=4, max_tool_calls_per_step=None)),
            message_bus=bus,
            session_id="sess-loop-stream",
        ),
        agent_factory=lambda _context: agent,
    )

    await loop.start()
    try:
        submission_id = await loop.submit_user_input("stream via loop")
        payload = await wait_for_submission_completion(bus=bus, submission_id=submission_id)

        llm_events = [item["payload"] for item in bus.events if item["event_type"] == "loop.llm_event"]
        assert payload["state"] == "completed"
        assert payload["message"] == "hello world"
        assert [item["llm_event_type"] for item in llm_events] == [
            "message_start",
            "thinking_delta",
            "text_delta",
            "text_delta",
            "message_stop",
        ]
        assert llm_events[2]["delta"] == "hello "
        assert llm_events[3]["delta"] == "world"
    finally:
        await loop.stop()
