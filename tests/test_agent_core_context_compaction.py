"""Tests for P14 T2.5 context compression baseline."""

from __future__ import annotations

from mini_agent.agent_core.context.context_compaction import LayeredContextCompactor
from mini_agent.schema.schema import Message


def test_snip_compaction_keeps_tail_lines_for_old_tool_output():
    tool_old = "\n".join([f"old-line-{index}" for index in range(1, 11)])
    tool_recent = "\n".join([f"recent-line-{index}" for index in range(1, 6)])
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="task"),
        Message(role="tool", content=tool_old, tool_call_id="t-1", name="bash"),
        Message(role="tool", content=tool_recent, tool_call_id="t-2", name="bash"),
    ]

    compactor = LayeredContextCompactor(
        token_budget=5000,
        keep_recent_tool_messages=1,
        snip_tail_lines=3,
    )
    result = compactor.compact(messages, enable_masking=False)

    tool_contents = [msg.content for msg in result.messages if msg.role == "tool"]
    assert any(isinstance(content, str) and "kept last 3 lines of 10" in content for content in tool_contents)
    assert any(isinstance(content, str) and "old-line-10" in content for content in tool_contents)
    assert result.stats.snipped_messages == 1


def test_masking_marks_irrelevant_old_tool_output():
    long_irrelevant = ("build log " * 60).strip()
    relevant = ("database migration complete " * 20).strip()
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="check database migration"),
        Message(role="tool", content=long_irrelevant, tool_call_id="t-1", name="bash"),
        Message(role="tool", content=relevant, tool_call_id="t-2", name="bash"),
    ]

    compactor = LayeredContextCompactor(token_budget=5000, keep_recent_tool_messages=1)
    result = compactor.compact(messages, query="database migration", enable_masking=True)

    masked_tool_messages = [
        msg
        for msg in result.messages
        if msg.role == "tool" and isinstance(msg.content, str) and msg.content.startswith("[Tool output masked:")
    ]
    assert len(masked_tool_messages) == 1
    assert "irrelevant_to_query" in masked_tool_messages[0].content
    assert result.stats.masked_messages == 1


def test_reverse_budget_keeps_user_messages():
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="first request"),
        Message(role="assistant", content="A" * 500),
        Message(role="tool", content="T" * 500, tool_call_id="x1", name="bash"),
        Message(role="user", content="second request"),
        Message(role="assistant", content="B" * 500),
        Message(role="tool", content="U" * 500, tool_call_id="x2", name="bash"),
    ]

    compactor = LayeredContextCompactor(token_budget=380, keep_recent_tool_messages=1)
    result = compactor.compact(messages, query="second request")

    users = [msg.content for msg in result.messages if msg.role == "user"]
    assert "first request" in users
    assert "second request" in users
    assert result.stats.compressed_messages <= result.stats.original_messages


def test_microcompact_merges_adjacent_assistant_messages():
    messages = [
        Message(role="system", content="sys"),
        Message(role="user", content="task"),
        Message(role="assistant", content="part 1"),
        Message(role="assistant", content="part 2"),
        Message(role="assistant", content="part 3"),
    ]

    compactor = LayeredContextCompactor(token_budget=5000)
    result = compactor.compact(messages, enable_masking=False)

    assistant_messages = [msg for msg in result.messages if msg.role == "assistant"]
    assert len(assistant_messages) == 1
    assert "part 1" in assistant_messages[0].content
    assert "part 2" in assistant_messages[0].content
    assert "part 3" in assistant_messages[0].content
    assert result.stats.merged_messages == 2
