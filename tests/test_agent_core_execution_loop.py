"""Tests for P14 T2.1 agent-core execution loop baseline."""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from mini_agent.agent_core.engine import Agent, AgentExecutionPolicy, TurnExecutionResult, TurnStopReason
from mini_agent.agent_core.context.context_compaction import estimate_tokens
from mini_agent.agent_core.context.loop_context import AgentLoopContext
from mini_agent.agent_core.execution.agent_loop import AgentSubmissionLoop, InMemoryLoopMessageBus
from mini_agent.agent_core.execution.permissions.approval import ApprovalEngine
from mini_agent.agent_core.execution.permissions.policy import PermissionPolicy
from mini_agent.logger import AgentLogger
from mini_agent.schema.schema import FunctionCall, LLMCompletionResult, Message, ToolCall
from mini_agent.tools.base import Tool, ToolResult


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

    async def run_turn(self, *, cancel_event=None, hooks=None, turn_context=None, start_new_run=True):  # noqa: ANN001
        del hooks
        del turn_context
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


class _HookedFakeAgent(_FakeAgent):
    async def run_turn(self, *, cancel_event=None, hooks=None, turn_context=None, start_new_run=True):  # noqa: ANN001
        del turn_context
        self.run_turn_calls.append(
            {
                "max_steps": self.max_steps,
                "max_tool_calls_per_step": self.max_tool_calls_per_step,
                "start_new_run": bool(start_new_run),
                "cancel_event_supplied": cancel_event is not None,
            }
        )
        tool_call = SimpleNamespace(
            id="call-shell",
            function=SimpleNamespace(name="bash", arguments={"command": "pytest -q"}),
        )
        if hooks and hooks.on_step_plan:
            await hooks.on_step_plan(SimpleNamespace(step=1, planned_tool_calls=[tool_call]))
        if hooks and hooks.on_tool_call_start:
            await hooks.on_tool_call_start(1, tool_call)
        if hooks and hooks.on_tool_call_result:
            await hooks.on_tool_call_result(
                1,
                tool_call,
                SimpleNamespace(success=True, stdout="32 passed", stderr="", content="32 passed"),
            )
        return TurnExecutionResult(
            stop_reason=TurnStopReason.END_TURN,
            message="hooked-ok",
        )


class _ObservedPolicyAgent(_FakeAgent):
    def __init__(self) -> None:
        super().__init__()
        self.execution_policy = AgentExecutionPolicy(
            max_steps=self.max_steps,
            max_tool_calls_per_step=self.max_tool_calls_per_step,
        )
        self.policy_types_during_run: list[str] = []
        self.policy_values_during_run: list[tuple[object, object]] = []

    @contextmanager
    def override_execution_policy(self, policy):  # noqa: ANN001
        previous_policy = self.execution_policy
        previous_max_steps = self.max_steps
        previous_max_tool_calls = self.max_tool_calls_per_step
        normalized_policy = AgentExecutionPolicy(
            max_steps=policy.max_steps,
            max_tool_calls_per_step=policy.max_tool_calls_per_step,
        )
        self.execution_policy = normalized_policy
        self.max_steps = normalized_policy.max_steps
        self.max_tool_calls_per_step = normalized_policy.max_tool_calls_per_step
        try:
            yield previous_policy
        finally:
            self.execution_policy = previous_policy
            self.max_steps = previous_max_steps
            self.max_tool_calls_per_step = previous_max_tool_calls

    async def run_turn(self, *, cancel_event=None, hooks=None, turn_context=None, start_new_run=True):  # noqa: ANN001
        del cancel_event
        del hooks
        del turn_context
        policy = self.execution_policy
        self.policy_types_during_run.append(type(policy).__name__)
        self.policy_values_during_run.append(
            (
                getattr(policy, "max_steps", None),
                getattr(policy, "max_tool_calls_per_step", None),
            )
        )
        self.run_turn_calls.append(
            {
                "max_steps": self.max_steps,
                "max_tool_calls_per_step": self.max_tool_calls_per_step,
                "start_new_run": bool(start_new_run),
                "cancel_event_supplied": False,
            }
        )
        return TurnExecutionResult(
            stop_reason=TurnStopReason.END_TURN,
            message="observed-ok",
        )


class _ApprovalBindingRefusingAgent:
    __slots__ = ("messages",)

    def __init__(self) -> None:
        self.messages: list[str] = []

    def add_user_message(self, content: str) -> None:
        self.messages.append(content)

    async def run_turn(self, *, cancel_event=None, hooks=None, turn_context=None, start_new_run=True):  # noqa: ANN001
        _ = (cancel_event, hooks, turn_context, start_new_run)
        raise AssertionError("run_turn should not execute when approval binding fails")


def _find_event(bus: InMemoryLoopMessageBus, event_type: str) -> dict[str, object]:
    for item in bus.events:
        if item["event_type"] == event_type:
            return item["payload"]
    raise AssertionError(f"Expected event {event_type} was not published.")


class _SequenceLLM:
    def __init__(self, responses: list[LLMCompletionResult]):
        self._responses = responses
        self.calls = 0

    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        response_index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[response_index]


class _EchoTool(Tool):
    def __init__(self) -> None:
        self.calls: list[str] = []

    @property
    def name(self) -> str:
        return "echo"

    @property
    def description(self) -> str:
        return "Echo helper tool."

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, text: str) -> ToolResult:
        self.calls.append(text)
        return ToolResult(success=True, content=f"echo:{text}")


class _StaticTurnContextProvider:
    name = "static_context"

    async def prepare(self, *, turn_context, agent):  # noqa: ANN001
        _ = agent
        return {
            "title": "Injected context",
            "content": f"query={turn_context.user_input}",
        }


class _UnusedLLM:
    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        raise AssertionError("LLM should not be called during explicit context mutation tests.")


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
async def test_submission_loop_preserves_execution_policy_shape_during_turn_override():
    bus = InMemoryLoopMessageBus()
    config = _Config(agent=_AgentConfig(max_steps=20, max_tool_calls_per_step=3))
    context = AgentLoopContext(config=config, message_bus=bus, session_id="session-policy")
    agent = _ObservedPolicyAgent()
    loop = AgentSubmissionLoop(context=context, agent_factory=lambda _ctx: agent)

    await loop.start()
    await loop.submit_user_input(
        "observe-policy",
        policy_overrides={"max_steps": 5, "max_tool_calls_per_step": 2},
    )
    await loop.join()
    await loop.stop()

    assert agent.policy_types_during_run == ["AgentExecutionPolicy"]
    assert agent.policy_values_during_run == [(5, 2)]
    assert isinstance(agent.execution_policy, AgentExecutionPolicy)
    assert agent.execution_policy.max_steps == 99
    assert agent.execution_policy.max_tool_calls_per_step == 9


@pytest.mark.asyncio
async def test_submission_loop_fallback_override_keeps_legacy_execution_policy_shape():
    bus = InMemoryLoopMessageBus()
    config = _Config(agent=_AgentConfig(max_steps=20, max_tool_calls_per_step=3))
    context = AgentLoopContext(config=config, message_bus=bus, session_id="session-policy-fallback")
    agent = _FakeAgent()
    loop = AgentSubmissionLoop(context=context, agent_factory=lambda _ctx: agent)

    await loop.start()
    await loop.submit_user_input(
        "observe-policy-fallback",
        policy_overrides={"max_steps": 5, "max_tool_calls_per_step": 2},
    )
    await loop.join()
    await loop.stop()

    assert agent.run_turn_calls[0]["max_steps"] == 5
    assert agent.run_turn_calls[0]["max_tool_calls_per_step"] == 2
    assert isinstance(agent.execution_policy, dict)
    assert agent.execution_policy["max_steps"] == 99
    assert agent.execution_policy["max_tool_calls_per_step"] == 9


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


@pytest.mark.asyncio
async def test_submission_loop_exec_approval_resumes_waiting_tool_execution(tmp_path):
    bus = InMemoryLoopMessageBus()
    context = AgentLoopContext(message_bus=bus, session_id="session-approval")
    echo_tool = _EchoTool()
    agent = Agent(
        llm_client=_SequenceLLM(
            [
                LLMCompletionResult(
                    content="calling tool",
                    thinking=None,
                    tool_calls=[
                        ToolCall(
                            id="tool-1",
                            type="function",
                            function=FunctionCall(name="echo", arguments={"text": "hello"}),
                        )
                    ],
                    finish_reason="tool_calls",
                ),
                LLMCompletionResult(content="done", thinking=None, tool_calls=None, finish_reason="stop"),
            ]
        ),
        system_prompt="system",
        tools=[echo_tool],
        max_steps=3,
        workspace_dir=str(tmp_path / "workspace"),
        logger=AgentLogger(log_dir=tmp_path / "logs"),
        console_output=False,
        approval_engine=ApprovalEngine(PermissionPolicy.strict_policy()),
    )
    loop = AgentSubmissionLoop(context=context, agent_factory=lambda _ctx: agent)

    await loop.start()
    submission_id = await loop.submit_user_input("run approval test")

    approval_payload = None
    for _ in range(100):
        for event in bus.events:
            if event.get("event_type") == "loop.approval.requested":
                payload = event.get("payload")
                if isinstance(payload, dict) and payload.get("submission_id") == submission_id:
                    approval_payload = payload
                    break
        if approval_payload is not None:
            break
        await asyncio.sleep(0.02)

    assert approval_payload is not None
    assert echo_tool.calls == []

    await loop.submit_exec_approval(
        approved=True,
        token=str(approval_payload.get("token")),
    )
    await loop.join()
    await loop.stop()

    assert echo_tool.calls == ["hello"]
    completed = _find_event(bus, "loop.turn.completed")
    assert completed["submission_id"] == submission_id
    assert completed["state"] == "completed"


@pytest.mark.asyncio
async def test_submission_loop_surfaces_agent_bootstrap_failure_when_approval_binding_fails():
    bus = InMemoryLoopMessageBus()
    context = AgentLoopContext(message_bus=bus, session_id="session-bootstrap-failure")
    agent = _ApprovalBindingRefusingAgent()
    loop = AgentSubmissionLoop(context=context, agent_factory=lambda _ctx: agent)

    await loop.start()
    submission_id = await loop.submit_user_input("should fail before execution")
    await loop.join()
    await loop.stop()

    completed = _find_event(bus, "loop.turn.completed")
    assert completed["submission_id"] == submission_id
    assert completed["state"] == "errored"
    assert completed["error"] == "agent_bootstrap_failed"
    assert "tool approval handler" in completed["message"]

    errored = _find_event(bus, "loop.turn.errored")
    assert errored["submission_id"] == submission_id
    assert errored["error"] == "agent_bootstrap_failed"


@pytest.mark.asyncio
async def test_submission_loop_completed_payload_includes_activity_report():
    bus = InMemoryLoopMessageBus()
    context = AgentLoopContext(message_bus=bus, session_id="session-activity")
    agent = _HookedFakeAgent()
    loop = AgentSubmissionLoop(context=context, agent_factory=lambda _ctx: agent)

    await loop.start()
    submission_id = await loop.submit_user_input("show activity")
    await loop.join()
    await loop.stop()

    activity_events = [item["payload"] for item in bus.events if item["event_type"] == "loop.activity"]
    assert activity_events
    assert any(item["label"] == "thinking" for item in activity_events)
    assert any(item["label"] == "shell" and item["state"] == "ok" for item in activity_events)

    completed = _find_event(bus, "loop.turn.completed")
    assert completed["submission_id"] == submission_id
    assert completed["state"] == "completed"
    assert completed["running_state"] == "step 1: shell ok"
    assert completed["last_activity_summary"] == "shell | ok | pytest -q | 32 passed"
    shell_item = next(item for item in completed["activity_items"] if item["label"] == "shell")
    assert shell_item["preview"] == "pytest -q"
    assert shell_item["output_summary"] == "32 passed"
    assert shell_item["state"] == "ok"


@pytest.mark.asyncio
async def test_submission_loop_completed_payload_includes_prepared_turn_context(tmp_path):
    bus = InMemoryLoopMessageBus()
    context = AgentLoopContext(message_bus=bus, session_id="session-context")
    agent = Agent(
        llm_client=_SequenceLLM([LLMCompletionResult(content="done", thinking=None, tool_calls=None, finish_reason="stop")]),
        system_prompt="system",
        tools=[],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=AgentLogger(log_dir=tmp_path / "logs"),
        console_output=False,
        turn_context_providers=[_StaticTurnContextProvider()],
    )
    loop = AgentSubmissionLoop(context=context, agent_factory=lambda _ctx: agent)

    await loop.start()
    submission_id = await loop.submit_user_input("show injected context")
    await loop.join()
    await loop.stop()

    completed = _find_event(bus, "loop.turn.completed")
    assert completed["submission_id"] == submission_id
    prepared = completed["prepared_context"]
    assert prepared["item_count"] == 1
    assert prepared["sources"] == ["static_context"]
    assert prepared["items"][0]["title"] == "Injected context"
    assert prepared["items"][0]["preview"] == "query=show injected context"
    diagnostics = completed["prepared_context_diagnostics"]
    assert diagnostics["turn_count"] == 1
    assert diagnostics["turns_with_context"] == 1
    assert diagnostics["source_turn_counts"]["static_context"] == 1


@pytest.mark.asyncio
async def test_submission_loop_compact_mutates_agent_history(tmp_path):
    bus = InMemoryLoopMessageBus()
    context = AgentLoopContext(message_bus=bus, session_id="session-compact")
    agent = Agent(
        llm_client=_UnusedLLM(),
        system_prompt="system",
        tools=[],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=AgentLogger(log_dir=tmp_path / "logs"),
        console_output=False,
    )
    agent.add_user_message("first request")
    agent.messages.append(Message(role="assistant", content="A" * 900))
    agent.messages.append(Message(role="tool", content=("tool-output-a\n" * 80).strip(), tool_call_id="t-1", name="bash"))
    agent.add_user_message("second request")
    agent.messages.append(Message(role="assistant", content="B" * 900))
    agent.messages.append(Message(role="tool", content=("tool-output-b\n" * 80).strip(), tool_call_id="t-2", name="bash"))

    before_tokens = estimate_tokens(agent.messages)
    before_messages = len(agent.messages)

    loop = AgentSubmissionLoop(context=context, agent_factory=lambda _ctx: agent)
    await loop.start()
    await loop.submit_compact(reason="keep recent task context")
    await loop.join()
    await loop.stop()

    payload = _find_event(bus, "loop.compact")
    assert payload["applied"] is True
    assert payload["token_count_before"] == before_tokens
    assert payload["token_count_after"] < before_tokens
    assert len(agent.messages) <= before_messages
    assert payload["stats"]["compressed_tokens"] == payload["token_count_after"]


@pytest.mark.asyncio
async def test_submission_loop_drop_memories_prunes_to_latest_turn(tmp_path):
    bus = InMemoryLoopMessageBus()
    context = AgentLoopContext(message_bus=bus, session_id="session-drop")
    agent = Agent(
        llm_client=_UnusedLLM(),
        system_prompt="system",
        tools=[],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=AgentLogger(log_dir=tmp_path / "logs"),
        console_output=False,
    )
    agent.add_user_message("old request")
    agent.messages.append(Message(role="assistant", content="old answer " * 80))
    agent.messages.append(Message(role="tool", content=("old-tool\n" * 60).strip(), tool_call_id="old-tool", name="bash"))
    agent.add_user_message("latest request")
    agent.messages.append(Message(role="assistant", content="latest answer " * 60))
    agent.messages.append(
        Message(role="tool", content=("latest-tool\n" * 60).strip(), tool_call_id="latest-tool", name="bash")
    )

    before_tokens = estimate_tokens(agent.messages)

    loop = AgentSubmissionLoop(context=context, agent_factory=lambda _ctx: agent)
    await loop.start()
    await loop.submit_drop_memories(reason="clear older memory")
    await loop.join()
    await loop.stop()

    payload = _find_event(bus, "loop.drop_memories")
    user_contents = [msg.content for msg in agent.messages if msg.role == "user"]

    assert payload["applied"] is True
    assert payload["token_count_after"] < before_tokens
    assert "latest request" in user_contents
    assert "old request" not in user_contents
