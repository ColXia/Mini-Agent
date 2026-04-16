"""Focused regression tests for the live session persistence owner."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mini_agent.session.persistence import SessionPersistence


def _messages(seed: str = "x") -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "system"},
        {"role": "user", "content": f"user:{seed}"},
        {"role": "assistant", "content": f"assistant:{seed}"},
    ]


def test_session_persistence_roundtrip_checkpoint_and_delete(tmp_path) -> None:
    persistence = SessionPersistence(tmp_path / "sessions")
    now_utc = datetime.now(timezone.utc).isoformat()

    persistence.save_session(
        session_id="sess_roundtrip_01",
        workspace_dir=str(tmp_path),
        created_at=now_utc,
        updated_at=now_utc,
        messages=_messages("roundtrip"),
        execution_policy={"max_steps": 7},
        configured_execution_policy={"max_steps": 7},
    )

    record = persistence.load_session("sess_roundtrip_01")
    assert record is not None
    assert record["session_id"] == "sess_roundtrip_01"
    assert record["workspace_dir"] == str(tmp_path)
    assert record["message_count"] == 3
    assert record["messages"][-1]["content"] == "assistant:roundtrip"
    assert record["execution_policy"]["max_steps"] == 7

    checkpoint = persistence.save_checkpoint(
        "sess_roundtrip_01",
        "before_reset",
        record["messages"],
    )
    assert checkpoint["checkpoint_name"] == "before_reset"
    assert checkpoint["message_count"] == 3

    checkpoints = persistence.list_checkpoints("sess_roundtrip_01")
    assert checkpoints
    assert checkpoints[0]["checkpoint_name"] == "before_reset"

    restored_checkpoint = persistence.load_checkpoint("sess_roundtrip_01", "before_reset")
    assert restored_checkpoint == record["messages"]

    assert persistence.delete_session("sess_roundtrip_01") is True
    assert persistence.load_session("sess_roundtrip_01") is None
    assert persistence.load_checkpoint("sess_roundtrip_01", "before_reset") is None


def test_session_persistence_cleanup_and_search_index(tmp_path) -> None:
    persistence = SessionPersistence(tmp_path / "sessions")
    now = datetime.now(timezone.utc)
    older = (now - timedelta(hours=2)).isoformat()
    newer = now.isoformat()

    persistence.save_session(
        session_id="sess_old_01",
        workspace_dir=str(tmp_path),
        created_at=older,
        updated_at=older,
        messages=_messages("legacy search marker"),
        execution_policy={"max_steps": 5},
        configured_execution_policy={"max_steps": 5},
    )
    persistence.save_session(
        session_id="sess_new_01",
        workspace_dir=str(tmp_path),
        created_at=newer,
        updated_at=newer,
        messages=_messages("fresh search marker"),
        execution_policy={"max_steps": 5},
        configured_execution_policy={"max_steps": 5},
    )

    search_hits = persistence.search_sessions(query="fresh search marker", limit=10)
    assert search_hits
    assert search_hits[0]["session_id"] == "sess_new_01"

    stats = persistence.session_search_stats()
    assert stats["backend"] in {"fts5", "like"}
    assert stats["indexed_sessions"] >= 2

    cleanup = persistence.cleanup(max_count=1, now=now)
    assert cleanup["deleted"] == 1
    assert cleanup["remaining"] == 1
    assert cleanup["deleted_session_ids"] == ["sess_old_01"]

    records = persistence.list_sessions()
    assert [item["session_id"] for item in records] == ["sess_new_01"]
