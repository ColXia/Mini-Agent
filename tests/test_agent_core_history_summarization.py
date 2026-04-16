"""Tests for agent-core history compaction and summarization semantics."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.agent_core.engine import Agent
from mini_agent.agent_core.history.summarization import AgentHistoryCompactionService
from mini_agent.logger import AgentLogger
from mini_agent.schema import LLMCompletionResult, Message


class SummaryLLM:
    """Return pre-defined summary responses and capture calls."""

    def __init__(self, responses: list[LLMCompletionResult]) -> None:
        self._responses = responses
        self.calls = 0

    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        response_index = min(self.calls, len(self._responses) - 1) if self._responses else 0
        self.calls += 1
        if not self._responses:
            raise AssertionError("generate should not be called in this test")
        return self._responses[response_index]


@pytest.mark.asyncio
async def test_history_compaction_normalizes_legacy_summary_message_without_fake_user_turn() -> None:
    service = AgentHistoryCompactionService(llm_client=SummaryLLM([]))
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="ship feature"),
        Message(role="user", content="[Assistant Execution Summary]\n\nimplemented and verified"),
    ]

    result = await service.compact_history(
        messages=messages,
        token_limit=10_000,
        api_total_tokens=0,
        skip_next_token_check=False,
    )

    assert result.compacted is False
    assert [message.role for message in result.messages] == ["system", "user", "assistant"]
    assert AgentHistoryCompactionService.is_internal_summary_message(result.messages[-1]) is True
    assert "implemented and verified" in str(result.messages[-1].content)


@pytest.mark.asyncio
async def test_agent_summarize_messages_writes_internal_assistant_summary_and_preserves_user_query(
    tmp_path: Path,
) -> None:
    llm = SummaryLLM([LLMCompletionResult(content="condensed execution summary", finish_reason="stop")])
    agent = Agent(
        llm_client=llm,
        system_prompt="system",
        tools=[],
        token_limit=1,
        workspace_dir=str(tmp_path / "workspace"),
        logger=AgentLogger(log_dir=tmp_path / "logs"),
        console_output=False,
    )
    agent.history_compaction_service = AgentHistoryCompactionService(
        llm_client=llm,
        token_estimator=lambda messages: (
            lambda items: (len(items) * 100)
            + sum(len(str(item.content or "")) for item in items)
        )(list(messages)),
    )
    agent.messages = [
        Message(role="system", content="system"),
        Message(role="user", content="build the feature"),
        Message(role="assistant", content="working through the task"),
        Message(role="tool", content="ok", tool_call_id="tool-1", name="echo"),
    ]

    await agent._apply_history_compaction()  # noqa: SLF001

    assert llm.calls == 1
    assert len(agent.messages) == 3
    assert [message.role for message in agent.messages] == ["system", "user", "assistant"]
    assert AgentHistoryCompactionService.is_internal_summary_message(agent.messages[-1]) is True
    assert "condensed execution summary" in str(agent.messages[-1].content)
    assert agent._last_user_query() == "build the feature"  # noqa: SLF001
    assert agent._last_user_message_index() == 1  # noqa: SLF001
    assert agent._skip_next_token_check is True  # noqa: SLF001

    await agent._apply_history_compaction()  # noqa: SLF001

    assert llm.calls == 1
    assert agent._skip_next_token_check is False  # noqa: SLF001


@pytest.mark.asyncio
async def test_history_compaction_preserves_existing_internal_summary_without_resummarizing_round(
    tmp_path: Path,
) -> None:
    llm = SummaryLLM([LLMCompletionResult(content="second round summary", finish_reason="stop")])
    service = AgentHistoryCompactionService(llm_client=llm)
    existing_summary = AgentHistoryCompactionService.build_internal_summary_message("first round summary")
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="task one"),
        existing_summary,
        Message(role="user", content="task two"),
        Message(role="assistant", content="working on task two"),
        Message(role="tool", content="ok", tool_call_id="tool-2", name="echo"),
    ]

    result = await service.compact_history(
        messages=messages,
        token_limit=1,
        api_total_tokens=999,
        skip_next_token_check=False,
    )

    summary_messages = [
        message for message in result.messages if AgentHistoryCompactionService.is_internal_summary_message(message)
    ]

    assert llm.calls == 1
    assert result.compacted is True
    assert [message.role for message in result.messages] == ["system", "user", "assistant", "user", "assistant"]
    assert len(summary_messages) == 2
    assert "first round summary" in str(summary_messages[0].content)
    assert "second round summary" in str(summary_messages[1].content)


@pytest.mark.asyncio
async def test_history_compaction_only_skips_next_check_when_tokens_shrink() -> None:
    llm = SummaryLLM(
        [
            LLMCompletionResult(
                content=("verbose summary " * 80).strip(),
                finish_reason="stop",
            )
        ]
    )
    service = AgentHistoryCompactionService(
        llm_client=llm,
        token_estimator=lambda messages: sum(
            len(str(message.content or ""))
            for message in messages
        ),
    )
    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="task one"),
        Message(role="assistant", content="short reply"),
        Message(role="tool", content="tool ok", tool_call_id="tool-1", name="echo"),
    ]

    result = await service.compact_history(
        messages=messages,
        token_limit=1,
        api_total_tokens=999,
        skip_next_token_check=False,
    )

    assert llm.calls == 1
    assert result.compacted is False
    assert result.skip_next_token_check is False
    assert list(result.messages) == messages
    assert result.compacted_tokens is not None
    assert result.compacted_tokens >= result.estimated_tokens
