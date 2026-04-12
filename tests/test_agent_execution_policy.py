"""Unit tests for Agent execution policy and tool-call budgeting."""

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

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
from mini_agent.code_agent import ApprovalEngine, PermissionPolicy
from mini_agent.logger import AgentLogger
from mini_agent.security.policy import RuntimePolicy, RuntimePolicyEngine
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


class OverflowThenSuccessLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        _ = messages
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError(
                "This model's maximum context length is 128000 tokens. "
                "However, your messages resulted in 140253 tokens."
            )
        return LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")


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


class BashEchoTool(Tool):
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return "Shell helper tool."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "run_in_background": {"type": "boolean"},
            },
            "required": ["command"],
        }

    async def execute(
        self,
        command: str,
        run_in_background: bool = False,
        _mini_agent_host_access_approved: bool = False,
    ) -> ToolResult:
        _ = _mini_agent_host_access_approved
        self.calls.append((command, run_in_background))
        return ToolResult(success=True, content=f"bash:{command}")


class HostAccessAwareBashTool(Tool):
    def __init__(self) -> None:
        self.calls: list[tuple[str, bool]] = []

    @property
    def name(self) -> str:
        return "bash"

    @property
    def description(self) -> str:
        return "Shell helper tool with host-access marker."

    @property
    def parameters(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "command": {"type": "string"},
                "run_in_background": {"type": "boolean"},
            },
            "required": ["command"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        command: str,
        run_in_background: bool = False,
        _mini_agent_host_access_approved: bool = False,
    ) -> ToolResult:
        self.calls.append((command, _mini_agent_host_access_approved))
        return ToolResult(success=True, content=f"bash:{command}:{run_in_background}")


class BlockingCancelableTool(Tool):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.cancel_requested = asyncio.Event()

    @property
    def name(self) -> str:
        return "block"

    @property
    def description(self) -> str:
        return "Block until cancellation."

    @property
    def parameters(self) -> dict:
        return {"type": "object", "properties": {"text": {"type": "string"}}}

    async def execute(self, text: str) -> ToolResult:  # noqa: ARG002
        self.started.set()
        await self.release.wait()
        return ToolResult(success=True, content="released")

    async def cancel_running(self, *, reason: str | None = None) -> bool:
        _ = reason
        self.cancel_requested.set()
        self.release.set()
        return True


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
async def test_planner_recovers_once_from_context_overflow_and_records_limit(tmp_path: Path) -> None:
    catalog_path = tmp_path / ".mini-agent" / "providers.json"
    catalog_path.parent.mkdir(parents=True, exist_ok=True)
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v1",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    logger = AgentLogger(log_dir=tmp_path / "logs")
    llm = OverflowThenSuccessLLM()
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[EchoTool()],
        max_steps=2,
        token_limit=200_000,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
    )
    agent.runtime_route = SimpleNamespace(
        provider_id="maas",
        model="astron-code-latest",
        catalog_path=str(catalog_path),
    )
    agent.add_user_message("please continue")

    plan = await agent._plan_step(step=1, run_start_time=0.0)  # noqa: SLF001

    assert isinstance(plan, StepPlan)
    assert plan.response_content == "done"
    assert llm.calls == 2
    assert agent.token_limit == 128_000

    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    provider = catalog["providers"][0]
    assert provider["model_learned_token_limits"]["astron-code-latest"] == 128_000


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


@pytest.mark.asyncio
async def test_run_turn_cancels_running_tool_with_best_effort_interrupt(tmp_path: Path):
    responses = [
        LLMResponse(
            content="call block tool",
            thinking=None,
            tool_calls=[
                ToolCall(
                    id="tool-block-1",
                    type="function",
                    function=FunctionCall(name="block", arguments={"text": "x"}),
                )
            ],
            finish_reason="tool_calls",
        ),
        LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop"),
    ]
    llm = SequenceLLM(responses)
    block_tool = BlockingCancelableTool()
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[block_tool],
        max_steps=3,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
        console_output=False,
    )
    agent.add_user_message("run")

    cancel_event = asyncio.Event()
    turn_task = asyncio.create_task(agent.run_turn(cancel_event=cancel_event))
    await block_tool.started.wait()
    cancel_event.set()
    result = await asyncio.wait_for(turn_task, timeout=3)

    assert result.stop_reason == TurnStopReason.CANCELLED
    assert block_tool.cancel_requested.is_set() is True


@pytest.mark.asyncio
async def test_executor_waits_for_manual_approval_before_running_tool(tmp_path: Path):
    echo_tool = EchoTool()
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=SequenceLLM([LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")]),
        system_prompt="system",
        tools=[echo_tool],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
        console_output=False,
        approval_engine=ApprovalEngine(PermissionPolicy.strict_policy()),
    )

    approval_future: asyncio.Future[bool | None] = asyncio.get_running_loop().create_future()
    approval_requests: list[object] = []

    async def _approval_handler(request) -> bool | None:  # noqa: ANN001
        approval_requests.append(request)
        return await approval_future

    agent.tool_approval_handler = _approval_handler

    execution_task = asyncio.create_task(
        agent._execute_tool_calls(  # noqa: SLF001
            step=1,
            tool_calls=[_tool_call(1)],
            step_state=StepExecutionState(step=1),
            run_start_time=0.0,
        )
    )

    for _ in range(50):
        if approval_requests:
            break
        await asyncio.sleep(0.01)

    assert approval_requests
    assert echo_tool.calls == []

    approval_future.set_result(True)
    outcome = await asyncio.wait_for(execution_task, timeout=2)

    assert outcome.transition == StepTransition.CONTINUE
    assert echo_tool.calls == ["msg-1"]


@pytest.mark.asyncio
async def test_executor_elevated_bash_requires_runtime_policy_approval_before_running_tool(tmp_path: Path):
    bash_tool = BashEchoTool()
    logger = AgentLogger(log_dir=tmp_path / "logs")
    policy_engine = RuntimePolicyEngine(
        RuntimePolicy(
            approval_profile="build",
            access_level="default",
            sandbox_mode="workspace",
            elevated_exec="require_approval",
            tool_allow=set(),
            tool_exclude=set(),
        )
    )
    agent = Agent(
        llm_client=SequenceLLM([LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")]),
        system_prompt="system",
        tools=[bash_tool],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
        console_output=False,
        approval_engine=ApprovalEngine(PermissionPolicy.full_auto_policy()),
        runtime_policy_engine=policy_engine,
    )

    approval_future: asyncio.Future[bool | None] = asyncio.get_running_loop().create_future()
    approval_requests: list[object] = []

    async def _approval_handler(request) -> bool | None:  # noqa: ANN001
        approval_requests.append(request)
        return await approval_future

    agent.tool_approval_handler = _approval_handler
    bash_call = ToolCall(
        id="tool-bash-1",
        type="function",
        function=FunctionCall(name="bash", arguments={"command": "sudo ls"}),
    )

    execution_task = asyncio.create_task(
        agent._execute_tool_calls(  # noqa: SLF001
            step=1,
            tool_calls=[bash_call],
            step_state=StepExecutionState(step=1),
            run_start_time=0.0,
        )
    )

    for _ in range(50):
        if approval_requests:
            break
        await asyncio.sleep(0.01)

    assert approval_requests
    assert "approval" in str(getattr(approval_requests[0], "reason", "")).lower()
    assert bash_tool.calls == []

    approval_future.set_result(True)
    outcome = await asyncio.wait_for(execution_task, timeout=2)

    assert outcome.transition == StepTransition.CONTINUE
    assert bash_tool.calls == [("sudo ls", False)]


@pytest.mark.asyncio
async def test_executor_marks_bash_invocation_with_host_access_after_runtime_approval(tmp_path: Path):
    bash_tool = HostAccessAwareBashTool()
    logger = AgentLogger(log_dir=tmp_path / "logs")
    policy_engine = RuntimePolicyEngine(
        RuntimePolicy(
            approval_profile="build",
            access_level="default",
            sandbox_mode="workspace",
            elevated_exec="require_approval",
            tool_allow=set(),
            tool_exclude=set(),
        )
    )
    agent = Agent(
        llm_client=SequenceLLM([LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")]),
        system_prompt="system",
        tools=[bash_tool],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
        console_output=False,
        approval_engine=ApprovalEngine(PermissionPolicy.full_auto_policy()),
        runtime_policy_engine=policy_engine,
    )

    approval_requests: list[object] = []

    async def _approval_handler(request) -> bool | None:  # noqa: ANN001
        approval_requests.append(request)
        return True

    agent.tool_approval_handler = _approval_handler
    bash_call = ToolCall(
        id="tool-bash-host-access",
        type="function",
        function=FunctionCall(name="bash", arguments={"command": r"Remove-Item ..\outside\victim.txt -Force"}),
    )

    outcome = await agent._execute_tool_calls(  # noqa: SLF001
        step=1,
        tool_calls=[bash_call],
        step_state=StepExecutionState(step=1),
        run_start_time=0.0,
    )

    assert outcome.transition == StepTransition.CONTINUE
    assert approval_requests
    assert "full-access approval" in str(getattr(approval_requests[0], "reason", "")).lower()
    assert bash_tool.calls == [(r"Remove-Item ..\outside\victim.txt -Force", True)]


@pytest.mark.asyncio
async def test_executor_denied_approval_returns_tool_error_without_executing(tmp_path: Path):
    echo_tool = EchoTool()
    logger = AgentLogger(log_dir=tmp_path / "logs")
    agent = Agent(
        llm_client=SequenceLLM([LLMResponse(content="done", thinking=None, tool_calls=None, finish_reason="stop")]),
        system_prompt="system",
        tools=[echo_tool],
        max_steps=2,
        workspace_dir=str(tmp_path / "workspace"),
        logger=logger,
        console_output=False,
        approval_engine=ApprovalEngine(PermissionPolicy.strict_policy()),
        tool_approval_handler=lambda _request: False,
    )
    step_state = StepExecutionState(step=1)

    outcome = await agent._execute_tool_calls(  # noqa: SLF001
        step=1,
        tool_calls=[_tool_call(1)],
        step_state=step_state,
        run_start_time=0.0,
    )

    assert outcome.transition == StepTransition.CONTINUE
    assert echo_tool.calls == []
    assert step_state.executed_tool_calls == 1
    assert agent.messages[-1].role == "tool"
    assert "denied by user approval" in str(agent.messages[-1].content).lower()
