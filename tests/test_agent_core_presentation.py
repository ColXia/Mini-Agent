"""Tests for agent-core presentation boundaries and headless execution."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.agent_core.engine import Agent, TurnStopReason
from mini_agent.agent_core.history.summarization import AgentHistoryCompactionService
from mini_agent.agent_core.presentation import AgentRuntimePresenter
from mini_agent.logger import AgentLogger
from mini_agent.schema import FunctionCall, LLMCompletionResult, Message, ToolCall
from mini_agent.tools.base import Tool, ToolResult


def _tool_call(index: int) -> ToolCall:
    return ToolCall(
        id=f"tool-{index}",
        type="function",
        function=FunctionCall(name="echo", arguments={"text": f"msg-{index}"}),
    )


class SequenceLLM:
    def __init__(self, responses: list[LLMCompletionResult]) -> None:
        self._responses = responses
        self.calls = 0

    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        response_index = min(self.calls, len(self._responses) - 1)
        self.calls += 1
        return self._responses[response_index]


class EchoTool(Tool):
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


class RecordingPresenter(AgentRuntimePresenter):
    def __init__(self) -> None:
        self.events: list[tuple[str, object]] = []

    def step_header(self, *, step: int, max_steps: int) -> None:
        self.events.append(("step_header", (step, max_steps)))

    def assistant_response(self, *, content: str) -> None:
        self.events.append(("assistant_response", content))

    def tool_call(self, *, function_name: str, arguments: dict[str, object]) -> None:
        self.events.append(("tool_call", (function_name, dict(arguments))))

    def tool_result(self, *, result: ToolResult) -> None:
        self.events.append(("tool_result", (result.success, result.content, result.error)))

    def history_summary_triggered(
        self,
        *,
        estimated_tokens: int,
        api_total_tokens: int,
        token_limit: int,
    ) -> None:
        self.events.append(("history_summary_triggered", (estimated_tokens, api_total_tokens, token_limit)))

    def history_summary_generated(self, *, round_num: int) -> None:
        self.events.append(("history_summary_generated", round_num))

    def history_summary_completed(
        self,
        *,
        estimated_tokens: int,
        compacted_tokens: int,
        user_message_count: int,
        summary_message_count: int,
    ) -> None:
        self.events.append(
            (
                "history_summary_completed",
                (estimated_tokens, compacted_tokens, user_message_count, summary_message_count),
            )
        )


@pytest.mark.asyncio
async def test_agent_headless_default_presenter_does_not_print_during_turn_execution(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    llm = SequenceLLM(
        [
            LLMCompletionResult(
                content="call tool",
                thinking=None,
                tool_calls=[_tool_call(1)],
                finish_reason="tool_calls",
            ),
            LLMCompletionResult(content="done", thinking=None, tool_calls=None, finish_reason="stop"),
        ]
    )
    echo_tool = EchoTool()
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[echo_tool],
        max_steps=3,
        workspace_dir=str(tmp_path / "workspace"),
        logger=AgentLogger(log_dir=tmp_path / "logs"),
        console_output=False,
    )
    agent.add_user_message("run")

    def _unexpected_print(*args, **kwargs):  # noqa: ANN001,ARG001
        raise AssertionError("headless agent execution should not call print() directly")

    monkeypatch.setattr("builtins.print", _unexpected_print)

    result = await agent.run_turn()

    assert result.stop_reason == TurnStopReason.END_TURN
    assert result.message == "done"
    assert echo_tool.calls == ["msg-1"]


@pytest.mark.asyncio
async def test_agent_routes_tool_and_history_feedback_through_presenter(tmp_path: Path) -> None:
    presenter = RecordingPresenter()
    llm = SequenceLLM(
        [
            LLMCompletionResult(
                content="call tool",
                thinking=None,
                tool_calls=[_tool_call(1)],
                finish_reason="tool_calls",
            ),
            LLMCompletionResult(content="done", thinking=None, tool_calls=None, finish_reason="stop"),
            LLMCompletionResult(content="summary text", thinking=None, tool_calls=None, finish_reason="stop"),
        ]
    )
    echo_tool = EchoTool()
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[echo_tool],
        max_steps=3,
        token_limit=10_000,
        workspace_dir=str(tmp_path / "workspace"),
        logger=AgentLogger(log_dir=tmp_path / "logs"),
        console_output=False,
        presenter=presenter,
    )
    agent.add_user_message("run")

    turn_result = await agent.run_turn()

    assert turn_result.stop_reason == TurnStopReason.END_TURN
    assert ("step_header", (1, 3)) in presenter.events
    assert ("tool_call", ("echo", {"text": "msg-1"})) in presenter.events
    assert ("tool_result", (True, "echo:msg-1", None)) in presenter.events
    assert ("assistant_response", "call tool") in presenter.events
    assert ("assistant_response", "done") in presenter.events

    agent.messages = [
        Message(role="system", content="system"),
        Message(role="user", content="previous task"),
        Message(role="assistant", content="working"),
        Message(role="tool", content="ok", tool_call_id="tool-x", name="echo"),
    ]
    agent.api_total_tokens = 999
    agent.token_limit = 1
    agent._skip_next_token_check = False  # noqa: SLF001
    agent.history_compaction_service = AgentHistoryCompactionService(
        llm_client=llm,
        presenter=presenter,
        token_estimator=lambda messages: (
            lambda items: (len(items) * 100)
            + sum(len(str(item.content or "")) for item in items)
        )(list(messages)),
    )

    await agent._apply_history_compaction()  # noqa: SLF001

    event_names = [name for name, _payload in presenter.events]
    assert "history_summary_triggered" in event_names
    assert "history_summary_generated" in event_names
    assert "history_summary_completed" in event_names
    assert AgentHistoryCompactionService.is_internal_summary_message(agent.messages[-1]) is True
