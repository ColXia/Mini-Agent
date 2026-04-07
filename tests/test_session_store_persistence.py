"""SessionStore persistence and retention tests (P3)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mini_agent.core.session import SessionState, SessionStore


@dataclass
class _DummyAgent:
    messages: list
    max_steps: int = 50
    max_tool_calls_per_step: int | None = None
    execution_policy: object | None = None


@dataclass
class _Policy:
    max_steps: int
    max_tool_calls_per_step: int | None = None


def _messages(seed: str = "x") -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "system"},
        {"role": "user", "content": f"user:{seed}"},
        {"role": "assistant", "content": f"assistant:{seed}"},
    ]


async def _build_agent(_workspace_dir: Path) -> _DummyAgent:
    return _DummyAgent(messages=[{"role": "system", "content": "system"}])


@pytest.mark.asyncio
async def test_store_restore_and_history_checkpoint(tmp_path: Path):
    store = SessionStore(storage_dir=tmp_path / "sessions")

    session = SessionState(
        session_id="sess_restore_01",
        workspace_dir=tmp_path,
        agent=_DummyAgent(messages=_messages("a")),
    )
    await store.set(session)
    await store.clear()

    restored = await store.restore("sess_restore_01", _build_agent)
    assert restored is not None
    assert len(restored.agent.messages) == 3
    assert restored.agent.messages[-1].content == "assistant:a"
    assert restored.agent.max_steps == 50
    assert restored.agent.max_tool_calls_per_step is None

    checkpoint = await store.save_checkpoint("sess_restore_01", "before_reset")
    assert checkpoint is not None
    assert checkpoint["message_count"] == 3

    checkpoint_history = await store.get_history(
        "sess_restore_01",
        checkpoint_name="before_reset",
    )
    assert checkpoint_history is not None
    assert len(checkpoint_history) == 3

    records = await store.list_records(include_inactive=True)
    assert records[0]["max_steps"] == 50
    assert records[0]["max_tool_calls_per_step"] is None
    assert records[0]["configured_max_steps"] == 50
    assert records[0]["configured_max_tool_calls_per_step"] is None
    assert records[0]["policy_drift"] is False
    assert records[0]["policy_drift_fields"] == []


@pytest.mark.asyncio
async def test_store_retention_max_count(tmp_path: Path):
    store = SessionStore(storage_dir=tmp_path / "sessions")
    await store.configure_retention(max_age_seconds=None, max_count=1)

    older = SessionState(
        session_id="sess_old_01",
        workspace_dir=tmp_path,
        agent=_DummyAgent(messages=_messages("old")),
        created_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        updated_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    newer = SessionState(
        session_id="sess_new_01",
        workspace_dir=tmp_path,
        agent=_DummyAgent(messages=_messages("new")),
    )

    await store.set(older)
    await store.set(newer)

    records = await store.list_records(include_inactive=True)
    assert len(records) == 1
    assert records[0]["session_id"] == "sess_new_01"


@pytest.mark.asyncio
async def test_store_set_storage_dir_migrates_active_sessions(tmp_path: Path):
    old_dir = tmp_path / "old-store"
    new_dir = tmp_path / "new-store"
    store = SessionStore(storage_dir=old_dir)

    await store.set(
        SessionState(
            session_id="sess_migrate_01",
            workspace_dir=tmp_path,
            agent=_DummyAgent(messages=_messages("migrate")),
        )
    )

    await store.set_storage_dir(new_dir, migrate_existing=True)
    await store.clear()

    restored = await store.restore("sess_migrate_01", _build_agent)
    assert restored is not None
    assert restored.workspace_dir == tmp_path.resolve()


@pytest.mark.asyncio
async def test_store_policy_drift_diagnostics_for_active_and_inactive_records(tmp_path: Path):
    store = SessionStore(storage_dir=tmp_path / "sessions")
    session = SessionState(
        session_id="sess_drift_01",
        workspace_dir=tmp_path,
        agent=_DummyAgent(
            messages=_messages("drift"),
            max_steps=7,
            max_tool_calls_per_step=3,
            execution_policy=_Policy(max_steps=10, max_tool_calls_per_step=5),
        ),
    )
    await store.set(session)

    active_record = await store.get_record("sess_drift_01", include_inactive=True)
    assert active_record is not None
    assert active_record["configured_max_steps"] == 10
    assert active_record["configured_max_tool_calls_per_step"] == 5
    assert active_record["max_steps"] == 7
    assert active_record["max_tool_calls_per_step"] == 3
    assert active_record["policy_drift"] is True
    assert sorted(active_record["policy_drift_fields"]) == [
        "max_steps",
        "max_tool_calls_per_step",
    ]

    await store.clear()

    inactive_record = await store.get_record("sess_drift_01", include_inactive=True)
    assert inactive_record is not None
    assert inactive_record["configured_max_steps"] == 10
    assert inactive_record["configured_max_tool_calls_per_step"] == 5
    assert inactive_record["max_steps"] == 7
    assert inactive_record["max_tool_calls_per_step"] == 3
    assert inactive_record["policy_drift"] is True
    assert sorted(inactive_record["policy_drift_fields"]) == [
        "max_steps",
        "max_tool_calls_per_step",
    ]


@pytest.mark.asyncio
async def test_store_rejects_invalid_session_id(tmp_path: Path):
    store = SessionStore(storage_dir=tmp_path / "sessions")

    with pytest.raises(ValueError):
        await store.get("bad!session")

    with pytest.raises(ValueError):
        await store.set(
            SessionState(
                session_id="bad!session",
                workspace_dir=tmp_path,
                agent=_DummyAgent(messages=_messages("bad")),
            )
        )


@pytest.mark.asyncio
async def test_store_session_search_active_vs_inactive(tmp_path: Path):
    store = SessionStore(storage_dir=tmp_path / "sessions")
    await store.set(
        SessionState(
            session_id="sess_search_01",
            workspace_dir=tmp_path,
            agent=_DummyAgent(messages=_messages("search-keyword")),
        )
    )

    active_payload = await store.search_sessions(
        query="search-keyword",
        include_inactive=False,
        limit=10,
    )
    assert active_payload["returned"] >= 1
    assert active_payload["hits"][0]["session_id"] == "sess_search_01"

    await store.clear()

    active_only_after_clear = await store.search_sessions(
        query="search-keyword",
        include_inactive=False,
        limit=10,
    )
    assert active_only_after_clear["returned"] == 0

    include_inactive_payload = await store.search_sessions(
        query="search-keyword",
        include_inactive=True,
        limit=10,
    )
    assert include_inactive_payload["returned"] >= 1
    assert include_inactive_payload["hits"][0]["session_id"] == "sess_search_01"

    stats = await store.session_search_stats()
    assert stats["backend"] in {"fts5", "like"}
    assert stats["indexed_sessions"] >= 1


@pytest.mark.asyncio
async def test_store_search_relevant_memory_uses_session_workspace(tmp_path: Path):
    store = SessionStore(storage_dir=tmp_path / "sessions")
    now_utc = datetime.now(timezone.utc).isoformat()
    await store.set(
        SessionState(
            session_id="sess_rel_store_01",
            workspace_dir=tmp_path,
            agent=_DummyAgent(
                messages=[
                    {"role": "system", "content": "system"},
                    {"role": "assistant", "content": "deterministic planner transitions for rollout stability"},
                ]
            ),
        )
    )

    memory_file = tmp_path / "MEMORY.md"
    memory_file.write_text(
        "\n".join(
            [
                "# Long-Term Memory",
                "",
                "<!-- MINI_AGENT_CONSOLIDATED_MEMORY_BEGIN -->",
                "## Consolidated Memory",
                "- deterministic planner transitions for rollout stability",
                f"last_updated_utc: {now_utc}",
                "<!-- MINI_AGENT_CONSOLIDATED_MEMORY_END -->",
                "",
            ]
        ),
        encoding="utf-8",
    )

    payload = await store.search_relevant_memory(
        query="planner transitions",
        session_id="sess_rel_store_01",
        top_k=5,
    )

    assert payload["returned"] >= 1
    assert payload["memory_file"] == str(memory_file.resolve())
    assert payload["hits"][0]["content"] == "deterministic planner transitions for rollout stability"
