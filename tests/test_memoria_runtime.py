from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime
from mini_agent.memory.runtime_task_memory import TurnRuntimeTaskMemory
from mini_agent.agent_core.context.turn_context import RuntimeTaskMemoryTurnContextProvider, RuntimeTurnContext


def test_workspace_memoria_runtime_persists_namespaced_memory_across_restart(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_root = (tmp_path / "state").resolve()

    runtime = WorkspaceMemoriaRuntime(workspace, state_root=state_root)
    runtime.save_session_memory(
        "sess-a",
        content="remote recovery remains visible in TUI threads after restart",
        metadata={"kind": "turn_summary"},
    )
    runtime.save_session_memory(
        "sess-b",
        content="workspace B keeps unrelated deployment notes",
        metadata={"kind": "turn_summary"},
    )
    runtime.save_workspace_shared_memory(
        content="workspace prefers TUI/CLI-first operating flow",
        metadata={"kind": "shared_fact"},
    )

    restored = WorkspaceMemoriaRuntime(workspace, state_root=state_root)
    payload = restored.retrieve_for_turn(
        session_id="sess-a",
        query="How should restart recovery show up in TUI threads?",
    )

    session_hits = payload["session_hits"]
    shared_hits = payload["shared_hits"]
    assert any("remote recovery remains visible" in item["content"] for item in session_hits)
    assert all("workspace B keeps unrelated deployment notes" not in item["content"] for item in session_hits)
    assert any("TUI/CLI-first operating flow" in item["content"] for item in shared_hits)


def test_workspace_memoria_runtime_can_clear_one_session_namespace_without_touching_others(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_root = (tmp_path / "state").resolve()

    runtime = WorkspaceMemoriaRuntime(workspace, state_root=state_root)
    runtime.save_session_memory(
        "sess-clear-a",
        content="session A runtime state should be removed on reset",
    )
    runtime.save_session_memory(
        "sess-clear-b",
        content="session B runtime state should remain available",
    )
    runtime.save_workspace_shared_memory(
        content="shared runtime facts stay outside session reset scope",
    )

    cleared = runtime.clear_session_namespace("sess-clear-a")

    assert cleared is True
    stats = runtime.stats()
    assert "session:sess-clear-a" not in stats["namespaces"]
    assert "session:sess-clear-b" in stats["namespaces"]
    assert "workspace:shared" in stats["namespaces"]


def test_workspace_memoria_runtime_can_snapshot_and_restore_session_namespace_payload(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_root = (tmp_path / "state").resolve()

    source = WorkspaceMemoriaRuntime(workspace, state_root=state_root)
    source.save_session_memory(
        "sess-source",
        content="share and unshare should preserve session-scoped runtime task memory",
    )
    payload = source.snapshot_session_namespace_payload("sess-source")

    assert payload["entry_count"] >= 1

    restored = WorkspaceMemoriaRuntime(workspace, state_root=state_root)
    result = restored.restore_session_namespace_payload("sess-dest", payload)
    assert result["restored"] is True

    turn_payload = restored.retrieve_for_turn(
        session_id="sess-dest",
        query="How should share and unshare preserve runtime task memory?",
    )
    assert any("share and unshare should preserve" in item["content"] for item in turn_payload["session_hits"])


def test_workspace_memoria_runtime_can_snapshot_and_merge_workspace_shared_namespace_payload(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    source_state_root = (tmp_path / "source-state").resolve()
    target_state_root = (tmp_path / "target-state").resolve()

    source = WorkspaceMemoriaRuntime(workspace, state_root=source_state_root)
    source.save_workspace_shared_memory(
        content="workspace-shared runtime memory should migrate without overwriting existing shared facts",
    )
    payload = source.snapshot_workspace_shared_namespace_payload()

    target = WorkspaceMemoriaRuntime(workspace, state_root=target_state_root)
    target.save_workspace_shared_memory(
        content="existing shared runtime facts must remain intact during merge restore",
    )

    result = target.restore_workspace_shared_namespace_payload(payload)

    assert result["restored"] is True
    assert result["merged"] is True
    assert result["added_count"] >= 1
    turn_payload = target.retrieve_for_turn(
        session_id="sess-any",
        query="How should workspace-shared runtime memory behave during migration restore?",
    )
    shared_hits = turn_payload["shared_hits"]
    assert any("migrate without overwriting existing shared facts" in item["content"] for item in shared_hits)
    assert any("existing shared runtime facts must remain intact" in item["content"] for item in shared_hits)


@pytest.mark.asyncio
async def test_runtime_task_memory_turn_context_provider_returns_session_and_shared_hits(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_root = (tmp_path / "state").resolve()

    runtime = WorkspaceMemoriaRuntime(workspace, state_root=state_root)
    runtime.save_session_memory(
        "sess-provider",
        content="gateway cancel must route through the shared session endpoint",
    )
    runtime.save_workspace_shared_memory(
        content="workspace keeps shared-session recovery visible in status views",
    )

    provider = RuntimeTaskMemoryTurnContextProvider(workspace, state_root=state_root)
    item = await provider.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-provider",
            submission_id="sub-provider",
            user_input="How does cancel work for shared sessions?",
        ),
        agent=SimpleNamespace(messages=[]),
    )

    assert item is not None
    assert item.source == "runtime_task_memory"
    assert "gateway cancel must route through the shared session endpoint" in item.content
    assert "shared-session recovery visible in status views" in item.content
    assert item.metadata["session_returned"] >= 1
    assert item.metadata["shared_returned"] >= 1


@pytest.mark.asyncio
async def test_runtime_task_memory_turn_context_provider_suppresses_shared_hits_when_session_hits_are_enough(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_root = (tmp_path / "state").resolve()

    runtime = WorkspaceMemoriaRuntime(workspace, state_root=state_root)
    runtime.save_session_memory(
        "sess-suppress",
        content="current task keeps the latest debug findings visible for this session",
    )
    runtime.save_workspace_shared_memory(
        content="workspace shared sessions should route reply targets through the active surface",
    )

    provider = RuntimeTaskMemoryTurnContextProvider(
        workspace,
        state_root=state_root,
        session_top_k=1,
        shared_top_k=1,
    )
    item = await provider.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-suppress",
            submission_id="sub-suppress",
            user_input="How do I keep the latest debug findings visible for this task?",
        ),
        agent=SimpleNamespace(messages=[]),
    )

    assert item is not None
    assert "latest debug findings visible for this session" in item.content
    assert "route reply targets through the active surface" not in item.content
    assert item.metadata["shared_returned"] == 0
    assert item.metadata["workspace_shared_reason"] == "suppressed_by_session_hits"


@pytest.mark.asyncio
async def test_runtime_task_memory_turn_context_provider_uses_shared_hits_as_fallback(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_root = (tmp_path / "state").resolve()

    runtime = WorkspaceMemoriaRuntime(workspace, state_root=state_root)
    runtime.save_session_memory(
        "sess-fallback",
        content="session-local scratch note for an unrelated debugging task",
    )
    runtime.save_workspace_shared_memory(
        content="gateway shared sessions should route reply targets through the active surface",
    )

    provider = RuntimeTaskMemoryTurnContextProvider(
        workspace,
        state_root=state_root,
        session_top_k=2,
        shared_top_k=1,
    )
    item = await provider.prepare(
        turn_context=RuntimeTurnContext(
            session_id="sess-fallback",
            submission_id="sub-fallback",
            user_input="How should reply targets be routed through the active surface?",
        ),
        agent=SimpleNamespace(messages=[]),
    )

    assert item is not None
    assert "route reply targets through the active surface" in item.content
    assert item.metadata["shared_returned"] >= 1
    assert item.metadata["workspace_shared_reason"] == "session_fallback"


def test_turn_runtime_task_memory_persists_turn_summary(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_root = (tmp_path / "state").resolve()
    writer = TurnRuntimeTaskMemory(str(workspace), state_root=str(state_root))

    result = writer.process_turn(
        stop_reason="end_turn",
        turn_context=SimpleNamespace(session_id="sess-write"),
        assistant_message="Gateway restart recovery now keeps the last tool state visible.",
        turn_messages=[
            SimpleNamespace(role="user", content="Keep gateway restart recovery visible"),
            SimpleNamespace(role="assistant", content="Gateway restart recovery now keeps the last tool state visible."),
        ],
    )

    assert result.stored is True
    runtime = WorkspaceMemoriaRuntime(workspace, state_root=state_root)
    payload = runtime.retrieve_for_turn(
        session_id="sess-write",
        query="How is gateway restart recovery kept visible?",
    )
    assert any("Gateway restart recovery now keeps the last tool state visible." in item["content"] for item in payload["session_hits"])


def test_turn_runtime_task_memory_records_knowledge_base_grounding_metadata(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_root = (tmp_path / "state").resolve()
    writer = TurnRuntimeTaskMemory(str(workspace), state_root=str(state_root))

    result = writer.process_turn(
        stop_reason="end_turn",
        turn_context=SimpleNamespace(session_id="sess-kb"),
        assistant_message="The workspace keeps gateway reply routing bound to the active surface.",
        turn_messages=[
            SimpleNamespace(role="user", content="How does reply routing work?"),
            SimpleNamespace(
                role="tool",
                name="knowledge_base_query",
                content=(
                    "Knowledge base results:\n"
                    "- knowledge_base_id: default\n"
                    "- query: reply routing active surface\n"
                    "- store_path: D:/file/Mini-Agent/.kb.json\n"
                    "- hits: 1\n"
                    "1. [routing.md] Gateway routes reply targets through the active surface.\n"
                    "   citation: docs/routing.md | score=0.9321 | bm25=0.5000 | vector=0.4321"
                ),
            ),
            SimpleNamespace(
                role="assistant",
                content="The workspace keeps gateway reply routing bound to the active surface.",
            ),
        ],
    )

    assert result.stored is True
    assert result.knowledge_base_grounded is True
    assert result.knowledge_base_id == "default"
    assert result.knowledge_base_hits == 1
    assert "docs/routing.md" in result.knowledge_base_refs

    runtime = WorkspaceMemoriaRuntime(workspace, state_root=state_root)
    entry = runtime.get_namespace_entry(
        runtime.session_namespace("sess-kb"),
        engram_id=str(result.engram_id),
    )
    assert entry is not None
    metadata = dict(entry.get("metadata") or {})
    assert metadata["knowledge_base_grounded"] is True
    assert metadata["knowledge_base_query"] == "reply routing active surface"


def test_turn_runtime_task_memory_marks_workspace_shared_candidate_and_can_promote_it(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_root = (tmp_path / "state").resolve()
    writer = TurnRuntimeTaskMemory(str(workspace), state_root=str(state_root))

    result = writer.process_turn(
        stop_reason="end_turn",
        turn_context=SimpleNamespace(session_id="sess-shared"),
        assistant_message="Gateway shared sessions should route reply targets through the active surface.",
        turn_messages=[
            SimpleNamespace(role="user", content="How should shared-session replies work?"),
            SimpleNamespace(
                role="assistant",
                content="Gateway shared sessions should route reply targets through the active surface.",
            ),
        ],
    )

    assert result.stored is True
    assert result.workspace_shared_candidate is True
    runtime = WorkspaceMemoriaRuntime(workspace, state_root=state_root)
    promoted = runtime.promote_session_memory_to_workspace_shared(
        session_id="sess-shared",
        engram_id=str(result.engram_id),
    )
    assert promoted["promoted"] is True
    payload = runtime.retrieve_for_turn(
        session_id="sess-shared",
        query="How should gateway shared sessions route reply targets?",
    )
    assert any("route reply targets through the active surface" in item["content"] for item in payload["shared_hits"])


def test_turn_runtime_task_memory_skips_low_signal_control_turn(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    state_root = (tmp_path / "state").resolve()
    writer = TurnRuntimeTaskMemory(str(workspace), state_root=str(state_root))

    result = writer.process_turn(
        stop_reason="end_turn",
        turn_context=SimpleNamespace(session_id="sess-skip"),
        assistant_message="好的。",
        turn_messages=[
            SimpleNamespace(role="user", content="1"),
            SimpleNamespace(role="assistant", content="好的。"),
        ],
    )

    assert result.stored is False
    assert result.skipped_reason == "low_signal_control_turn"
    runtime = WorkspaceMemoriaRuntime(workspace, state_root=state_root)
    assert "session:sess-skip" not in runtime.stats()["namespaces"]


def test_workspace_memoria_runtime_can_promote_session_memory_to_workspace_note(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    runtime = WorkspaceMemoriaRuntime(workspace, state_root=(tmp_path / "state").resolve())
    saved = runtime.save_session_memory(
        "sess-promote",
        content="Workspace keeps QQ and TUI over one shared session contract.",
    )

    promoted = runtime.promote_session_memory_to_workspace_note(
        session_id="sess-promote",
        engram_id=str(saved["engram_id"]),
    )

    assert promoted["promoted"] is True
    memory_file = workspace / "MEMORY.md"
    assert memory_file.exists()
    assert "QQ and TUI over one shared session contract" in memory_file.read_text(encoding="utf-8")


def test_workspace_memoria_runtime_promote_note_uses_kb_confirmed_for_grounded_runtime_memory(
    tmp_path: Path,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    runtime = WorkspaceMemoriaRuntime(workspace, state_root=(tmp_path / "state").resolve())
    saved = runtime.save_session_memory(
        "sess-kb-note",
        content="Workspace reply routing stays bound to the active surface.",
        metadata={
            "knowledge_base_grounded": True,
            "knowledge_base_query": "reply routing active surface",
            "knowledge_base_id": "default",
            "knowledge_base_hits": 1,
            "knowledge_base_refs": ["docs/routing.md"],
        },
    )

    promoted = runtime.promote_session_memory_to_workspace_note(
        session_id="sess-kb-note",
        engram_id=str(saved["engram_id"]),
    )

    assert promoted["promoted"] is True
    assert promoted["category"] == "kb_confirmed"
    assert promoted["knowledge_base_grounding"]["grounded"] is True
    assert promoted["knowledge_base_grounding"]["refs"] == ["docs/routing.md"]


def test_workspace_memoria_runtime_can_promote_session_memory_to_global_profile(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    global_root = (tmp_path / "global").resolve()
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str(global_root))

    runtime = WorkspaceMemoriaRuntime(workspace, state_root=(tmp_path / "state").resolve())
    saved = runtime.save_session_memory(
        "sess-profile",
        content="User prefers concise Chinese replies across workspaces.",
    )

    promoted = runtime.promote_session_memory_to_global_profile(
        session_id="sess-profile",
        engram_id=str(saved["engram_id"]),
    )

    assert promoted["promoted"] is True
    user_file = global_root / "USER.md"
    assert user_file.exists()
    assert "concise Chinese replies across workspaces" in user_file.read_text(encoding="utf-8")

