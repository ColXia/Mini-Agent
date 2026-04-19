from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_agent.memory.automation import TurnMemoryAutomation
from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime
from mini_agent.memory.operator_actions import save_operator_workspace_note
from mini_agent.memory.runtime_task_memory import TurnRuntimeTaskMemory
from mini_agent.memory.service import MemoryService
from mini_agent.schema.schema import FunctionCall, Message, ToolCall
from mini_agent.session.persistence import SessionPersistence
from mini_agent.agent_core.context.turn_context import (
    RuntimeTaskMemoryTurnContextProvider,
    RuntimeTurnContext,
    SessionSearchTurnContextProvider,
)


@pytest.fixture(autouse=True)
def _global_memory_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))


def _tool_call(name: str) -> ToolCall:
    return ToolCall(
        id=f"{name}-1",
        type="function",
        function=FunctionCall(name=name, arguments={}),
    )


@pytest.mark.asyncio
async def test_personal_real_use_flow_keeps_boundaries_and_requires_explicit_kb_confirmation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace_a = (tmp_path / "workspace-a").resolve()
    workspace_b = (tmp_path / "workspace-b").resolve()
    workspace_a.mkdir(parents=True, exist_ok=True)
    workspace_b.mkdir(parents=True, exist_ok=True)
    state_root = (tmp_path / "state").resolve()
    session_store_dir = (tmp_path / "sessions").resolve()
    persistence = SessionPersistence(session_store_dir)

    timestamp = datetime(2026, 4, 10, tzinfo=timezone.utc).isoformat()
    persistence.save_session(
        session_id="sess-a-history",
        workspace_dir=str(workspace_a),
        created_at=timestamp,
        updated_at=timestamp,
        messages=[
            {"role": "user", "content": "Keep TUI and CLI as the main workflow."},
            {"role": "assistant", "content": "Confirmed. TUI/CLI stays the default workflow."},
        ],
    )
    persistence.save_session(
        session_id="sess-b-history",
        workspace_dir=str(workspace_b),
        created_at=timestamp,
        updated_at=timestamp,
        messages=[
            {"role": "user", "content": "Use a separate deployment runbook for cloud hosting."},
            {"role": "assistant", "content": "Confirmed. Deployment runbook stays separate here."},
        ],
    )

    automation = TurnMemoryAutomation(
        str(workspace_a),
        session_store_dir=str(session_store_dir),
        min_assistant_chars_for_daily=10,
    )
    monkeypatch.setattr(
        automation,
        "_extract_project_decision",
        lambda _message: "TUI/CLI-first workflow remains the default for this workspace.",
    )
    decision_result = automation.process_turn(
        stop_reason="end_turn",
        turn_messages=[
            Message(role="user", content="Keep TUI and CLI as the main workflow."),
            Message(role="assistant", content="Confirmed. I will keep TUI and CLI as the main workflow."),
        ],
        assistant_message="Confirmed. I will keep TUI and CLI as the main workflow.",
    )
    assert decision_result.stored_long_term_note is True

    kb_result = automation.process_turn(
        stop_reason="end_turn",
        turn_messages=[
            Message(role="user", content="Summarize the KB finding about reply routing."),
            Message(
                role="assistant",
                content="I will inspect the KB result first.",
                tool_calls=[_tool_call("knowledge_base_query")],
            ),
            Message(
                role="tool",
                name="knowledge_base_query",
                content=(
                    "Knowledge base results:\n"
                    "- knowledge_base_id: default\n"
                    "- query: gateway reply routing active surface\n"
                    "- store_path: D:/file/Mini-Agent/.kb.json\n"
                    "- hits: 1\n"
                    "1. [routing.md] Gateway routes reply targets through the active surface.\n"
                    "   citation: docs/routing.md | score=0.9321 | bm25=0.5000 | vector=0.4321"
                ),
            ),
            Message(
                role="assistant",
                content="The KB says gateway reply routing follows the active surface.",
            ),
        ],
        assistant_message="The KB says gateway reply routing follows the active surface.",
    )
    assert kb_result.skipped_reason == "knowledge_base_grounded_turn_requires_explicit_confirmation"

    confirmed = save_operator_workspace_note(
        workspace_dir=workspace_a,
        content="Confirmed from KB: gateway reply routing follows the active surface.",
        prepared_context_sources=["knowledge_base"],
        prepared_context={
            "sources": ["knowledge_base"],
            "items": [
                {
                    "source": "knowledge_base",
                    "metadata": {
                        "knowledge_base_id": "default",
                        "citations": [{"source_path": "docs/routing.md"}],
                    },
                }
            ],
        },
    )
    assert confirmed["category"] == "kb_confirmed"

    writer = TurnRuntimeTaskMemory(str(workspace_a), state_root=str(state_root))
    runtime_result = writer.process_turn(
        stop_reason="end_turn",
        turn_context=SimpleNamespace(session_id="sess-a-runtime"),
        assistant_message="Gateway shared sessions should route reply targets through the active surface.",
        turn_messages=[
            SimpleNamespace(role="user", content="How should shared-session replies work?"),
            SimpleNamespace(
                role="assistant",
                content="Gateway shared sessions should route reply targets through the active surface.",
            ),
        ],
    )
    assert runtime_result.stored is True

    runtime = WorkspaceMemoriaRuntime(workspace_a, state_root=state_root)
    promoted = runtime.promote_session_memory_to_workspace_shared(
        session_id="sess-a-runtime",
        engram_id=str(runtime_result.engram_id),
    )
    assert promoted["promoted"] is True

    runtime_provider = RuntimeTaskMemoryTurnContextProvider(
        workspace_a,
        state_root=state_root,
        session_top_k=2,
        shared_top_k=1,
    )
    runtime_item = await runtime_provider.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-a-next",
            submission_id="sub-a-next",
            user_input="How should gateway shared sessions route reply targets?",
        ),
        agent=SimpleNamespace(messages=[]),
    )
    assert runtime_item is not None
    assert "route reply targets through the active surface" in runtime_item.content

    session_provider_a = SessionSearchTurnContextProvider(
        workspace_a,
        session_store_dir=session_store_dir,
        top_k=3,
    )
    session_item_a = await session_provider_a.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-a-next",
            submission_id="sub-a-history",
            user_input="What workflow did we keep as the default?",
        ),
        agent=SimpleNamespace(messages=[]),
    )
    assert session_item_a is not None
    assert "TUI/CLI stays the default workflow" in session_item_a.content

    session_provider_b = SessionSearchTurnContextProvider(
        workspace_b,
        session_store_dir=session_store_dir,
        top_k=3,
    )
    session_item_b = await session_provider_b.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-b-next",
            submission_id="sub-b-history",
            user_input="What workflow did we keep as the default?",
        ),
        agent=SimpleNamespace(messages=[]),
    )
    assert session_item_b is None or "TUI/CLI stays the default workflow" not in session_item_b.content

    memory_a = MemoryService(workspace_a)
    memory_text = memory_a.long_term_file.read_text(encoding="utf-8")
    assert "TUI/CLI-first workflow remains the default for this workspace." in memory_text
    assert "kb_confirmed" in memory_text
    assert "gateway reply routing follows the active surface" in memory_text

