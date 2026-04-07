"""Tests for consolidated-memory relevance retrieval baseline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mini_agent.memory.relevance import ConsolidatedMemoryRelevanceRetriever
from mini_agent.session.persistence import SessionPersistence


def _write_consolidated_memory(path, *, items: list[str], last_updated_utc: str) -> None:
    section_lines = [
        "<!-- MINI_AGENT_CONSOLIDATED_MEMORY_BEGIN -->",
        "## Consolidated Memory",
    ]
    section_lines.extend(f"- {item}" for item in items)
    section_lines.append(f"last_updated_utc: {last_updated_utc}")
    section_lines.append("<!-- MINI_AGENT_CONSOLIDATED_MEMORY_END -->")
    path.write_text(
        "# Long-Term Memory\n\n" + "\n".join(section_lines) + "\n",
        encoding="utf-8",
    )


def test_relevance_retriever_returns_ranked_top_hits(tmp_path):
    memory_file = tmp_path / "MEMORY.md"
    now = datetime.now(timezone.utc)
    _write_consolidated_memory(
        memory_file,
        items=[
            "deterministic planner transitions for rollout stability",
            "observability export queue backpressure policy",
            "session drift diagnostics summary in health endpoint",
        ],
        last_updated_utc=now.isoformat(),
    )

    retriever = ConsolidatedMemoryRelevanceRetriever(memory_file)
    payload = retriever.search(
        query="planner transitions",
        top_k=5,
        support_lookup=lambda _query, _limit: [{"updated_at": now.isoformat()}],
    )

    assert payload["returned"] >= 1
    assert payload["memory_last_updated_utc"] is not None
    assert payload["hits"][0]["content"] == "deterministic planner transitions for rollout stability"
    assert payload["hits"][0]["drift_status"] == "aligned"


def test_relevance_retriever_marks_possibly_stale_without_support_hits(tmp_path):
    memory_file = tmp_path / "MEMORY.md"
    stale_time = datetime.now(timezone.utc) - timedelta(days=90)
    _write_consolidated_memory(
        memory_file,
        items=["legacy deployment checklist for obsolete provider"],
        last_updated_utc=stale_time.isoformat(),
    )

    retriever = ConsolidatedMemoryRelevanceRetriever(memory_file)
    payload = retriever.search(
        query="obsolete provider checklist",
        top_k=5,
        stale_after_days=30,
        support_lookup=lambda _query, _limit: [],
    )

    assert payload["returned"] == 1
    assert payload["hits"][0]["drift_status"] == "possibly_stale"


def test_session_persistence_relevance_uses_side_query_support(tmp_path):
    store_dir = tmp_path / "sessions"
    memory_file = tmp_path / "MEMORY.md"
    persistence = SessionPersistence(store_dir)
    now_utc = datetime.now(timezone.utc).isoformat()

    persistence.save_session(
        session_id="sess_rel_01",
        workspace_dir=str(tmp_path),
        created_at=now_utc,
        updated_at=now_utc,
        messages=[
            {"role": "system", "content": "system"},
            {
                "role": "assistant",
                "content": "backpressure observability guardrails queue diagnostics",
            },
        ],
        execution_policy={"max_steps": 5},
        configured_execution_policy={"max_steps": 5},
    )

    _write_consolidated_memory(
        memory_file,
        items=[
            "backpressure observability guardrails queue diagnostics",
            "daily note about unrelated weather",
        ],
        last_updated_utc=now_utc,
    )

    payload = persistence.search_relevant_memory(
        query="queue guardrails",
        memory_file=memory_file,
        top_k=5,
        stale_after_days=30,
    )

    assert payload["returned"] >= 1
    assert payload["hits"][0]["content"] == "backpressure observability guardrails queue diagnostics"
    assert payload["hits"][0]["drift_status"] in {"aligned", "unverified"}
