from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mini_agent.memory.service import MemoryService
from mini_agent.session.persistence import SessionPersistence


def _write_consolidated_memory(memory_file: Path, *, items: list[str], last_updated_utc: str) -> None:
    memory_file.write_text(
        "\n".join(
            [
                "# Long-Term Memory",
                "",
                "<!-- MINI_AGENT_CONSOLIDATED_MEMORY_BEGIN -->",
                "## Consolidated Memory",
                *[f"- {item}" for item in items],
                f"last_updated_utc: {last_updated_utc}",
                "<!-- MINI_AGENT_CONSOLIDATED_MEMORY_END -->",
                "",
            ]
        ),
        encoding="utf-8",
    )


@pytest.fixture(autouse=True)
def _global_memory_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MINI_AGENT_GLOBAL_MEMORY_ROOT", str((tmp_path / "global").resolve()))


def test_memory_service_unifies_notes_profile_and_export(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    memory = MemoryService(workspace)
    now = datetime.now()

    memory.append_note(
        content="alpha launch decision",
        category="planning",
        scope="long_term",
        now=now,
    )
    memory.append_note(
        content="alpha rollout today",
        category="daily",
        scope="daily",
        now=now,
    )
    memory.add_profile_fact(fact="User prefers concise answers.")

    summary = memory.summary()
    assert summary.workspace_dir == str(workspace)
    assert summary.notes_count >= 2
    assert "planning" in summary.categories

    search = memory.search_notes(query="alpha", limit=10)
    assert len(search) >= 2
    assert any("alpha" in item.content for item in search)

    daily = memory.daily_snapshot(day=now.date().isoformat())
    assert daily.note_count >= 1
    assert "alpha rollout today" in daily.content

    exported = memory.export_notes(format="jsonl")
    assert exported["format"] == "jsonl"
    assert "alpha launch decision" in exported["content"]

    profile = memory.profile()
    assert profile["fact_count"] >= 1
    assert profile["scope"] == "global"
    assert Path(profile["user_file"]) == (tmp_path / "global" / "USER.md").resolve()
    assert not (workspace / "USER.md").exists()
    profile_hits = memory.search_profile(query="concise", limit=5)
    assert profile_hits
    assert "concise answers" in profile_hits[0]["fact"]


def test_memory_service_unifies_session_search_and_consolidated_retrieval(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    session_store_dir = (tmp_path / "sessions").resolve()
    memory_file = workspace / "MEMORY.md"
    _write_consolidated_memory(
        memory_file,
        items=[
            "restart recovery must preserve lost approval hints for the next turn",
            "models panel follows the active provider selection",
        ],
        last_updated_utc="2026-04-09T10:00:00+00:00",
    )

    persistence = SessionPersistence(session_store_dir)
    persistence.save_session(
        session_id="sess-memory-core",
        workspace_dir=str(workspace),
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        messages=[
            {"role": "user", "content": "check restart recovery"},
            {"role": "assistant", "content": "lost approval hints are preserved after restart"},
        ],
    )

    memory = MemoryService(workspace, session_store_dir=session_store_dir)
    hits = memory.search_sessions(query="approval", limit=10)
    assert hits
    assert hits[0]["session_id"] == "sess-memory-core"

    payload = memory.search_relevant_consolidated_memory(
        query="How are lost approvals preserved after restart?",
        top_k=3,
        stale_after_days=30,
    )
    assert payload["returned"] >= 1
    assert any("lost approval hints" in item["content"] for item in payload["hits"])


def test_memory_service_search_sessions_can_filter_by_workspace_anchor_and_exclude_current(tmp_path: Path) -> None:
    workspace_root = (tmp_path / "repo").resolve()
    nested_workspace = (workspace_root / "src" / "feature").resolve()
    nested_workspace.mkdir(parents=True, exist_ok=True)
    (workspace_root / "MEMORY.md").write_text("# Long-Term Memory\n", encoding="utf-8")

    other_workspace = (tmp_path / "other-repo").resolve()
    other_workspace.mkdir(parents=True, exist_ok=True)
    (other_workspace / "MEMORY.md").write_text("# Long-Term Memory\n", encoding="utf-8")

    session_store_dir = (tmp_path / "sessions").resolve()
    persistence = SessionPersistence(session_store_dir)
    persistence.save_session(
        session_id="sess-same-anchor",
        workspace_dir=str(nested_workspace),
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        messages=[
            {"role": "assistant", "content": "keep the opencode-style sidebar proportions"},
        ],
    )
    persistence.save_session(
        session_id="sess-other-anchor",
        workspace_dir=str(other_workspace),
        created_at=datetime.now(timezone.utc).isoformat(),
        updated_at=datetime.now(timezone.utc).isoformat(),
        messages=[
            {"role": "assistant", "content": "keep the opencode-style sidebar proportions"},
        ],
    )

    memory = MemoryService(nested_workspace, session_store_dir=session_store_dir)
    hits = memory.search_sessions(
        query="sidebar proportions",
        limit=10,
        workspace_anchor_dir=str(nested_workspace),
        exclude_session_id="sess-current",
    )
    assert len(hits) == 1
    assert hits[0]["session_id"] == "sess-same-anchor"
    assert hits[0]["workspace_anchor_dir"] == str(nested_workspace)


def test_memory_service_refreshes_consolidated_memory_when_workspace_history_is_newer(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    session_store_dir = (tmp_path / "sessions").resolve()

    persistence = SessionPersistence(session_store_dir)
    updated_at = datetime.now(timezone.utc).isoformat()
    persistence.save_session(
        session_id="sess-refresh-01",
        workspace_dir=str(workspace),
        created_at=updated_at,
        updated_at=updated_at,
        messages=[
            {"role": "user", "content": "keep gateway shared sessions restart-safe"},
            {"role": "assistant", "content": "gateway shared sessions stay restart-safe with persisted transcript state"},
        ],
    )

    memory = MemoryService(workspace, session_store_dir=session_store_dir)
    before = memory.consolidated_refresh_status()
    assert before["needs_refresh"] is True
    assert before["reason"] == "missing_consolidated_section"

    refreshed = memory.refresh_consolidated_memory()
    assert refreshed["refreshed"] is True
    assert refreshed["before"]["needs_refresh"] is True
    assert refreshed["after"]["needs_refresh"] is False

    snapshot = memory.consolidated_snapshot()
    assert any("restart-safe" in item for item in snapshot["items"])


def test_memory_service_refresh_status_is_noop_when_consolidated_memory_is_fresh(tmp_path: Path) -> None:
    workspace = (tmp_path / "workspace").resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    session_store_dir = (tmp_path / "sessions").resolve()
    updated_at = datetime.now(timezone.utc).isoformat()

    persistence = SessionPersistence(session_store_dir)
    persistence.save_session(
        session_id="sess-refresh-fresh",
        workspace_dir=str(workspace),
        created_at=updated_at,
        updated_at=updated_at,
        messages=[
            {"role": "assistant", "content": "models follow the active provider selection"},
        ],
    )

    _write_consolidated_memory(
        workspace / "MEMORY.md",
        items=["models follow the active provider selection"],
        last_updated_utc=(datetime.now(timezone.utc) + timedelta(seconds=1)).isoformat(),
    )

    memory = MemoryService(workspace, session_store_dir=session_store_dir)
    status = memory.consolidated_refresh_status()
    assert status["needs_refresh"] is False
    assert status["reason"] == "fresh"

    refreshed = memory.refresh_consolidated_memory()
    assert refreshed["refreshed"] is False
    assert refreshed["skipped"] is True
    assert refreshed["reason"] == "fresh"
