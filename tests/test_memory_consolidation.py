"""Two-phase memory consolidation baseline tests."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from mini_agent.memory.consolidation import MemoryConsolidationPipeline
from mini_agent.memory.consolidation_scheduler import ConsolidationScheduler
from mini_agent.session.persistence import SessionPersistence


def _utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _messages(seed: str) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": "system"},
        {"role": "user", "content": f"user note {seed} keep deterministic transitions"},
        {"role": "assistant", "content": f"assistant summary {seed} with observability drift context"},
    ]


def test_consolidation_scheduler_phase1_and_phase2(tmp_path):
    store_dir = tmp_path / "sessions"
    memory_file = tmp_path / "MEMORY.md"

    persistence = SessionPersistence(store_dir)
    persistence.save_session(
        session_id="sess_cons_01",
        workspace_dir=str(tmp_path),
        created_at=_utc_iso(),
        updated_at=_utc_iso(),
        messages=_messages("alpha"),
        execution_policy={"max_steps": 5},
        configured_execution_policy={"max_steps": 5},
    )

    scheduler = ConsolidationScheduler(
        session_persistence=persistence,
        base_dir=store_dir,
        memory_file=memory_file,
    )

    phase1 = scheduler.run_phase1(max_jobs=8)
    assert phase1.leased == 1
    assert phase1.processed == 1
    assert phase1.failed == 0
    assert len(phase1.artifact_ids) == 1
    assert scheduler.job_store.stats()["done"] == 1

    artifacts = scheduler.phase1_store.list_artifacts()
    assert len(artifacts) == 1
    assert len(artifacts[0].raw_memory) >= 1

    phase2 = scheduler.run_phase2(top_n=20)
    assert phase2.processed_artifacts == 1
    assert len(phase2.output_items) >= 1
    assert memory_file.exists()
    text = memory_file.read_text(encoding="utf-8")
    assert "MINI_AGENT_CONSOLIDATED_MEMORY_BEGIN" in text
    assert "deterministic transitions" in text

    # Running phase2 again without new artifacts should keep existing output.
    phase2_again = scheduler.run_phase2(top_n=20)
    assert phase2_again.processed_artifacts == 0
    assert phase2_again.removed == []
    assert phase2_again.output_items == phase2.output_items


def test_memory_consolidation_pipeline_end_to_end(tmp_path):
    store_dir = tmp_path / "sessions"
    memory_file = tmp_path / "MEMORY.md"
    persistence = SessionPersistence(store_dir)

    for idx in range(2):
        persistence.save_session(
            session_id=f"sess_cons_{idx}",
            workspace_dir=str(tmp_path),
            created_at=_utc_iso(),
            updated_at=_utc_iso(),
            messages=_messages(f"beta-{idx}"),
            execution_policy={"max_steps": 5},
            configured_execution_policy={"max_steps": 5},
        )

    pipeline = MemoryConsolidationPipeline(
        session_store_dir=store_dir,
        memory_file=memory_file,
    )
    summary = pipeline.run(phase="all", max_jobs=8, top_n=30)

    assert summary["phase"] == "all"
    assert summary["phase1"]["processed"] >= 1
    assert summary["phase2"]["processed_artifacts"] >= 1
    assert summary["job_stats"]["done"] >= 1
    assert memory_file.exists()
    assert "Consolidated Memory" in memory_file.read_text(encoding="utf-8")


def test_consolidation_job_lease_retry_backoff(tmp_path):
    store_dir = tmp_path / "sessions"
    memory_file = tmp_path / "MEMORY.md"
    persistence = SessionPersistence(store_dir)
    scheduler = ConsolidationScheduler(
        session_persistence=persistence,
        base_dir=store_dir,
        memory_file=memory_file,
    )

    now = datetime.now(timezone.utc)
    scheduler.job_store.upsert_session_jobs(
        [
            {
                "session_id": "sess_job_01",
                "updated_at": now.isoformat(),
            }
        ]
    )

    leased = scheduler.job_store.lease_jobs(max_jobs=1, lease_seconds=120, now_utc=now)
    assert len(leased) == 1
    assert leased[0]["session_id"] == "sess_job_01"

    scheduler.job_store.mark_failure(
        "sess_job_01",
        error="transient failure",
        retry_seconds=600,
        now_utc=now,
    )
    leased_during_backoff = scheduler.job_store.lease_jobs(max_jobs=1, now_utc=now + timedelta(seconds=300))
    assert leased_during_backoff == []

    leased_after_backoff = scheduler.job_store.lease_jobs(max_jobs=1, now_utc=now + timedelta(seconds=601))
    assert len(leased_after_backoff) == 1
