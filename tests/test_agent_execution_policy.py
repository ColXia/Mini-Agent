"""Unit tests for Agent execution policy and tool-call budgeting."""

from pathlib import Path

import pytest

from mini_agent.acp import MiniMaxACPAgent
from mini_agent.agent import (
    Agent,
    PlannerExecutorHooks,
    StepExecutionState,
    StepFailureEnvelope,
    StepOutcome,
    StepPlan,
    StepTransition,
    TurnStopReason,
)
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from mini_agent.logger import AgentLogger
from mini_agent.schema import FunctionCall, LLMResponse, ToolCall
from mini_agent.tools.base import Tool, ToolResult


def _tool_call(index: int) -> ToolCall:
    return ToolCall(
        id=f"tool-{index}",
        type="function",
        function=FunctionCall(name="echo", arguments={"text": f"msg-{index}"}),
    )


class SequenceLLM:
    """Return pre-defined LLM responses in sequence."""

    def __init__(self, responses: list[LLMResponse]):
        self._responses = responses
        self.calls = 0

    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        response_index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[response_index]


class FailingLLM:
    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        raise RuntimeError("llm boom")


class EchoTool(Tool):
    def __init__(self):
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


class DummyConn:
    def __init__(self):
        self.updates: list[tuple[str, object]] = []

    async def session_update(self, session_id, update):  # noqa: ANN001
        self.updates.append((session_id, update))


@pytest.mark.asyncio
async def test_agent_truncates_tool_calls_per_step(tmp_path: Path):
    responses = [
        LLMResponse(
            content="calling tools",
            thinking=None,
            tool_calls=[_tool_call(1), _tool_call(2), _tool_call(3)],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop"),
    ]
    llm = SequenceLLM(responses)
    echo_tool = EchoTool()
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[echo_tool],
        max_steps=4,
        max_tool_calls_per_step=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
    )
    agent.add_user_message("run")

    result = await agent.run()
    assert result == "done"
    assert echo_tool.calls == ["msg-1", "msg-2"]

    event_file = logger.get_event_file_path()
    assert event_file is not None
    events = AgentLogger.read_events(event_file)
    truncated_events = [event for event in events if event["type"] == "step.tool_calls_truncated"]
    assert len(truncated_events) == 1
    payload = truncated_events[0]["payload"]
    assert payload["requested_tool_calls"] == 3
    assert payload["executed_tool_calls"] == 2
    assert payload["truncated_tool_calls"] == 1


@pytest.mark.asyncio
async def test_agent_without_budget_executes_all_tool_calls(tmp_path: Path):
    responses = [
        LLMResponse(
            content="calling tools",
            thinking=None,
            tool_calls=[_tool_call(1), _tool_call(2), _tool_call(3)],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop"),
    ]
    llm = SequenceLLM(responses)
    echo_tool = EchoTool()
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[echo_tool],
        max_steps=4,
        max_tool_calls_per_step=None,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
    )
    agent.add_user_message("run")

    result = await agent.run()
    assert result == "done"
    assert echo_tool.calls == ["msg-1", "msg-2", "msg-3"]

    event_file = logger.get_event_file_path()
    assert event_file is not None
    events = AgentLogger.read_events(event_file)
    assert all(event["type"] != "step.tool_calls_truncated" for event in events)


@pytest.mark.asyncio
async def test_acp_prompt_respects_tool_call_budget(tmp_path: Path):
    responses = [
        LLMResponse(
            content="",
            thinking="plan tools",
            tool_calls=[_tool_call(1), _tool_call(2), _tool_call(3)],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop"),
    ]
    llm = SequenceLLM(responses)
    echo_tool = EchoTool()
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(
            max_steps=3,
            max_tool_calls_per_step=1,
            workspace_dir=str(tmp_path),
        ),
        tools=ToolsConfig(),
    )
    acp_agent = MiniMaxACPAgent(
        config=config,
        llm=llm,
        base_tools=[echo_tool],
        system_prompt="system",
    )
    conn = DummyConn()
    acp_agent.on_connect(conn)

    session = await acp_agent.new_session(cwd=None)
    response = await acp_agent.prompt(prompt=[{"text": "hello"}], session_id=session.session_id)
    assert response.stopReason == "end_turn"
    assert echo_tool.calls == ["msg-1"]


@pytest.mark.asyncio
async def test_planner_returns_failed_transition_on_llm_error(tmp_path: Path):
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=FailingLLM(),
        system_prompt="system",
        tools=[EchoTool()],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
    )
    agent.add_user_message("run")

    outcome = await agent._plan_step(step=1, run_start_time=0.0)  # noqa: SLF001
    assert isinstance(outcome, StepOutcome)
    assert outcome.transition == StepTransition.FAILED
    assert "LLM call failed" in outcome.message
    assert isinstance(outcome.failure, StepFailureEnvelope)
    assert outcome.failure is not None
    assert outcome.failure.phase == "planner"
    assert outcome.failure.error_type == "RuntimeError"
    assert outcome.failure.recoverable is False
    assert outcome.failure.retryable is False


@pytest.mark.asyncio
async def test_executor_returns_complete_transition_without_tools(tmp_path: Path):
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=SequenceLLM([LLMResponse(content="", finish_reason="stop")]),
        system_prompt="system",
        tools=[EchoTool()],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
    )
    step_state = StepExecutionState(step=1)

    outcome = await agent._execute_tool_calls(  # noqa: SLF001
        step=1,
        tool_calls=[],
        step_state=step_state,
        run_start_time=0.0,
    )
    assert outcome.transition == StepTransition.COMPLETE


@pytest.mark.asyncio
async def test_run_emits_step_failed_and_metrics_payload(tmp_path: Path):
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=FailingLLM(),
        system_prompt="system",
        tools=[EchoTool()],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
    )
    agent.add_user_message("run")

    result = await agent.run()
    assert "LLM call failed" in result

    event_file = logger.get_event_file_path()
    assert event_file is not None
    events = AgentLogger.read_events(event_file)

    step_failed_events = [event for event in events if event["type"] == "step.failed"]
    assert len(step_failed_events) == 1
    failure = step_failed_events[0]["payload"]["failure"]
    assert failure["phase"] == "planner"
    assert failure["error_type"] == "RuntimeError"
    assert failure["recoverable"] is False
    assert failure["retryable"] is False

    run_failed_events = [event for event in events if event["type"] == "run.failed"]
    assert len(run_failed_events) == 1
    metrics = run_failed_events[0]["payload"]["metrics"]
    assert metrics["steps_started"] == 1
    assert metrics["steps_failed"] == 1
    assert metrics["failures_by_type"]["RuntimeError"] == 1


@pytest.mark.asyncio
async def test_run_turn_uses_shared_planner_executor_hooks(tmp_path: Path):
    responses = [
        LLMResponse(
            content="call tool",
            thinking="planning",
            tool_calls=[_tool_call(1)],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop"),
    ]
    llm = SequenceLLM(responses)
    echo_tool = EchoTool()
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[echo_tool],
        max_steps=3,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
        console_output=False,
    )
    agent.add_user_message("run")

    planned_steps: list[StepPlan] = []
    started_calls: list[str] = []
    completed_calls: list[tuple[str, bool]] = []

    async def on_step_plan(plan: StepPlan) -> None:
        planned_steps.append(plan)

    async def on_tool_start(step: int, tool_call: ToolCall) -> None:  # noqa: ARG001
        started_calls.append(tool_call.id)

    async def on_tool_result(step: int, tool_call: ToolCall, result: ToolResult) -> None:  # noqa: ARG001
        completed_calls.append((tool_call.id, result.success))

    result = await agent.run_turn(
        hooks=PlannerExecutorHooks(
            on_step_plan=on_step_plan,
            on_tool_call_start=on_tool_start,
            on_tool_call_result=on_tool_result,
        ),
    )

    assert result.stop_reason == TurnStopReason.END_TURN
    assert result.message == "done"
    assert planned_steps[0].response_thinking == "planning"
    assert started_calls == ["tool-1"]
    assert completed_calls == [("tool-1", True)]


@pytest.mark.asyncio
async def test_run_turn_refusal_on_planner_error(tmp_path: Path):
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=FailingLLM(),
        system_prompt="system",
        tools=[EchoTool()],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
        console_output=False,
    )
    agent.add_user_message("run")

    result = await agent.run_turn()
    assert result.stop_reason == TurnStopReason.REFUSAL
    assert "LLM call failed" in result.message
