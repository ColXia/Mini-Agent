"""Tests for FTS5-backed session transcript search index."""

from __future__ import annotations

from mini_agent.memory.session_search import SessionSearchIndex


def test_session_search_index_upsert_search_and_delete(tmp_path):
    index = SessionSearchIndex(tmp_path / "sessions")

    index.upsert_session(
        session_id="sess_a",
        workspace_dir=str(tmp_path),
        updated_at="2026-04-05T09:00:00+00:00",
        messages=[
            {"role": "user", "content": "please use deterministic planner transitions"},
            {"role": "assistant", "content": "ack deterministic planner transitions"},
        ],
    )
    index.upsert_session(
        session_id="sess_b",
        workspace_dir=str(tmp_path),
        updated_at="2026-04-05T09:10:00+00:00",
        messages=[
            {"role": "user", "content": "check observability drift counters"},
        ],
    )

    hits = index.search(query="deterministic planner", limit=10)
    assert len(hits) >= 1
    assert hits[0]["session_id"] == "sess_a"
    assert "deterministic" in hits[0]["content"].lower()

    stats = index.stats()
    assert stats["backend"] in {"fts5", "like"}
    assert stats["indexed_sessions"] == 2
    assert stats["indexed_messages"] == 3

    index.delete_session("sess_a")
    hits_after_delete = index.search(query="deterministic planner", limit=10)
    assert hits_after_delete == []
