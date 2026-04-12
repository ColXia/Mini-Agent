from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.agent import Agent, TurnStopReason
from mini_agent.logger import AgentLogger
from mini_agent.memory.automation import TurnMemoryAutomation
from mini_agent.schema import FunctionCall, LLMResponse, Message, ToolCall
from mini_agent.turn_context import RuntimeTurnContext


@pytest.fixture(autouse=True)
def _global_memory_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))


class _StaticLLM:
    def __init__(self, response: LLMResponse) -> None:
        self.response = response

    async def generate(self, messages, tools=None):  # noqa: ANN001,ARG002
        return self.response


def _tool_call(name: str) -> ToolCall:
    return ToolCall(
        id=f"{name}-1",
        type="function",
        function=FunctionCall(name=name, arguments={}),
    )


def test_turn_memory_automation_stores_profile_fact_and_daily_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    global_user_file = (tmp_path / "global" / "USER.md").resolve()
    automation = TurnMemoryAutomation(str(workspace), min_assistant_chars_for_daily=40)
    monkeypatch.setattr(
        automation,
        "_extract_profile_fact",
        lambda _message: "User prefers concise Chinese replies.",
    )

    result = automation.process_turn(
        stop_reason="end_turn",
        turn_messages=[
            Message(role="user", content="remember my reply preference"),
            Message(
                role="assistant",
                content="I will answer in Chinese and keep the structure concise for future turns.",
            ),
        ],
        turn_context={"metadata": {"surface": "tui"}},
        assistant_message="I will answer in Chinese and keep the structure concise for future turns.",
    )

    assert result.stored_profile_fact is True
    assert result.stored_daily_note is True
    assert result.stored_long_term_note is False
    assert result.explicit_profile_tool_used is False
    assert "User prefers concise Chinese replies." in global_user_file.read_text(encoding="utf-8")
    assert not (workspace / "USER.md").exists()
    daily_files = sorted((workspace / "memory").glob("*.md"))
    assert len(daily_files) == 1
    assert "user: remember my reply preference" in daily_files[0].read_text(encoding="utf-8")


def test_turn_memory_automation_stores_long_term_decision_and_daily_note(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    workspace = tmp_path / "workspace"
    automation = TurnMemoryAutomation(str(workspace), min_assistant_chars_for_daily=40)
    monkeypatch.setattr(
        automation,
        "_extract_project_decision",
        lambda _message: "WebUI is paused for now; TUI/CLI remains the main workflow.",
    )

    result = automation.process_turn(
        stop_reason="end_turn",
        turn_messages=[
            Message(role="user", content="use tui and cli as the main workflow"),
            Message(
                role="assistant",
                content="Confirmed. I will keep future implementation focused on TUI and CLI.",
            ),
        ],
        assistant_message="Confirmed. I will keep future implementation focused on TUI and CLI.",
    )

    assert result.stored_long_term_note is True
    assert result.stored_daily_note is True
    assert result.stored_profile_fact is False
    assert "WebUI is paused for now; TUI/CLI remains the main workflow." in (
        workspace / "MEMORY.md"
    ).read_text(encoding="utf-8")


def test_turn_memory_automation_skips_workflow_turn(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    global_user_file = (tmp_path / "global" / "USER.md").resolve()
    automation = TurnMemoryAutomation(str(workspace))

    result = automation.process_turn(
        stop_reason="end_turn",
        turn_messages=[
            Message(role="user", content="reply in Chinese"),
            Message(role="assistant", content="Okay."),
        ],
        turn_context={"metadata": {"mode": "workflow"}},
        assistant_message="Okay.",
    )

    assert result.skipped_reason == "workflow_turn"
    assert not global_user_file.exists()
    assert not (workspace / "MEMORY.md").exists()
    assert not (workspace / "memory").exists()


def test_turn_memory_automation_suppresses_duplicate_writeback_after_successful_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    global_user_file = (tmp_path / "global" / "USER.md").resolve()
    automation = TurnMemoryAutomation(str(workspace), min_assistant_chars_for_daily=10)
    monkeypatch.setattr(
        automation,
        "_extract_profile_fact",
        lambda _message: "User prefers concise Chinese replies.",
    )
    monkeypatch.setattr(
        automation,
        "_extract_project_decision",
        lambda _message: "WebUI is paused for now; TUI/CLI remains the main workflow.",
    )

    result = automation.process_turn(
        stop_reason="end_turn",
        turn_messages=[
            Message(role="user", content="store the memory explicitly"),
            Message(
                role="assistant",
                content="I will store both the user preference and the project decision.",
                tool_calls=[_tool_call("user_modeling"), _tool_call("record_note")],
            ),
            Message(role="tool", name="user_modeling", content="Profile conclude status=added"),
            Message(role="tool", name="record_note", content="Recorded note in both"),
            Message(role="assistant", content="Stored successfully."),
        ],
        assistant_message="Stored successfully.",
    )

    assert result.skipped_reason == "no_candidate_memory"
    assert result.explicit_profile_tool_used is True
    assert result.explicit_note_tool_used is True
    assert result.explicit_profile_tool_succeeded is True
    assert result.explicit_note_tool_succeeded is True
    assert result.action_count == 0
    assert not global_user_file.exists()
    assert not (workspace / "MEMORY.md").exists()


def test_turn_memory_automation_backfills_after_failed_memory_tools(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    global_user_file = (tmp_path / "global" / "USER.md").resolve()
    automation = TurnMemoryAutomation(str(workspace), min_assistant_chars_for_daily=10)
    monkeypatch.setattr(
        automation,
        "_extract_profile_fact",
        lambda _message: "User prefers concise Chinese replies.",
    )
    monkeypatch.setattr(
        automation,
        "_extract_project_decision",
        lambda _message: "WebUI is paused for now; TUI/CLI remains the main workflow.",
    )

    result = automation.process_turn(
        stop_reason="end_turn",
        turn_messages=[
            Message(role="user", content="store the memory explicitly"),
            Message(
                role="assistant",
                content="I will try the tools first.",
                tool_calls=[_tool_call("user_modeling"), _tool_call("record_note")],
            ),
            Message(role="tool", name="user_modeling", content="Error: profile store unavailable"),
            Message(role="tool", name="record_note", content="Error: note store unavailable"),
            Message(
                role="assistant",
                content="The tools failed, but I still finished extracting the stable conclusion.",
            ),
        ],
        assistant_message="The tools failed, but I still finished extracting the stable conclusion.",
    )

    assert result.explicit_profile_tool_used is True
    assert result.explicit_note_tool_used is True
    assert result.explicit_profile_tool_succeeded is False
    assert result.explicit_note_tool_succeeded is False
    assert result.stored_profile_fact is True
    assert result.stored_long_term_note is True
    assert result.stored_daily_note is True
    assert "User prefers concise Chinese replies." in global_user_file.read_text(encoding="utf-8")
    assert not (workspace / "USER.md").exists()
    assert "WebUI is paused for now; TUI/CLI remains the main workflow." in (
        workspace / "MEMORY.md"
    ).read_text(encoding="utf-8")


def test_turn_memory_automation_requires_explicit_confirmation_for_kb_grounded_turn(
    tmp_path: Path,
) -> None:
    workspace = tmp_path / "workspace"
    automation = TurnMemoryAutomation(str(workspace), min_assistant_chars_for_daily=10)

    result = automation.process_turn(
        stop_reason="end_turn",
        turn_messages=[
            Message(role="user", content="summarize the KB result"),
            Message(
                role="assistant",
                content="I will confirm the KB result after retrieval.",
                tool_calls=[_tool_call("knowledge_base_query")],
            ),
            Message(
                role="tool",
                name="knowledge_base_query",
                content=(
                    "Knowledge base results:\n"
                    "- knowledge_base_id: default\n"
                    "- query: gateway reply routing\n"
                    "- store_path: D:/file/Mini-Agent/.kb.json\n"
                    "- hits: 1\n"
                    "1. [routing.md] Gateway routes reply targets through the active surface.\n"
                    "   citation: docs/routing.md | score=0.9321 | bm25=0.5000 | vector=0.4321"
                ),
            ),
            Message(
                role="assistant",
                content="The KB says reply routing follows the active surface.",
            ),
        ],
        assistant_message="The KB says reply routing follows the active surface.",
    )

    assert result.knowledge_base_grounded is True
    assert result.skipped_reason == "knowledge_base_grounded_turn_requires_explicit_confirmation"
    assert result.action_count == 0
    assert not (workspace / "MEMORY.md").exists()
    assert not (workspace / "memory").exists()


def test_turn_memory_automation_skips_low_signal_control_turn(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    automation = TurnMemoryAutomation(str(workspace), min_assistant_chars_for_daily=10)

    result = automation.process_turn(
        stop_reason="end_turn",
        turn_messages=[
            Message(role="user", content="继续"),
            Message(role="assistant", content="好的，我继续。"),
        ],
        assistant_message="好的，我继续。",
    )

    assert result.skipped_reason == "low_signal_control_turn"
    assert result.action_count == 0
    assert not (workspace / "MEMORY.md").exists()
    assert not (workspace / "memory").exists()


@pytest.mark.asyncio
async def test_agent_run_turn_triggers_memory_automation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = tmp_path / "workspace"
    logger = AgentLogger(log_dir=tmp_path / "logs")
    automation = TurnMemoryAutomation(str(workspace), min_assistant_chars_for_daily=20)
    monkeypatch.setattr(
        automation,
        "_extract_project_decision",
        lambda _message: "WebUI is paused for now; TUI/CLI remains the main workflow.",
    )
    agent = Agent(
        llm_client=_StaticLLM(
            LLMResponse(
                content="Confirmed. I will keep implementation focused on TUI and CLI.",
                thinking=None,
                tool_calls=None,
                finish_reason="stop",
            )
        ),
        system_prompt="system",
        tools=[],
        max_steps=2,
        workspace_dir=str(workspace),
        logger=logger,
        console_output=False,
        turn_memory_automation=automation,
    )
    agent.add_user_message("keep tui and cli as the main workflow")

    result = await agent.run_turn(
        turn_context=RuntimeTurnContext(
            session_id="sess-memory-auto",
            submission_id="sub-memory-auto",
            user_input="keep tui and cli as the main workflow",
            metadata={"surface": "cli"},
        )
    )

    assert result.stop_reason == TurnStopReason.END_TURN
    assert agent.last_memory_automation["stored_long_term_note"] is True
    assert agent.last_memory_automation["stored_daily_note"] is True
    assert "WebUI is paused for now; TUI/CLI remains the main workflow." in (
        workspace / "MEMORY.md"
    ).read_text(encoding="utf-8")
