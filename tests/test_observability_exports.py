from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import mini_agent.cli as cli
from mini_agent.ops.observability_exports import prune_observability_export_jobs


def _write_export_job(
    log_dir: Path,
    *,
    job_id: str,
    status: str,
    completed_at: datetime | None,
    updated_at: datetime,
    artifact_rel_path: str | None = None,
) -> Path:
    jobs_dir = log_dir / "exports" / "jobs"
    jobs_dir.mkdir(parents=True, exist_ok=True)

    payload: dict[str, str] = {
        "job_id": job_id,
        "status": status,
        "updated_at": updated_at.isoformat(),
    }
    if completed_at is not None:
        payload["completed_at"] = completed_at.isoformat()
    if artifact_rel_path is not None:
        payload["artifact_file"] = artifact_rel_path

    metadata_file = jobs_dir / f"{job_id}.json"
    metadata_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return metadata_file


def test_prune_observability_export_jobs_prunes_expired_terminal_jobs(tmp_path: Path) -> None:
    log_dir = tmp_path / "log"
    now = datetime.now(timezone.utc)

    old_artifact_rel = "exports/artifacts/old.jsonl"
    old_artifact_file = log_dir / old_artifact_rel
    old_artifact_file.parent.mkdir(parents=True, exist_ok=True)
    old_artifact_file.write_text("old", encoding="utf-8")

    old_job = _write_export_job(
        log_dir,
        job_id="exp_old",
        status="completed",
        completed_at=now - timedelta(hours=2),
        updated_at=now - timedelta(hours=2),
        artifact_rel_path=old_artifact_rel,
    )
    recent_job = _write_export_job(
        log_dir,
        job_id="exp_recent",
        status="completed",
        completed_at=now - timedelta(minutes=10),
        updated_at=now - timedelta(minutes=10),
    )
    running_job = _write_export_job(
        log_dir,
        job_id="exp_running",
        status="running",
        completed_at=None,
        updated_at=now - timedelta(minutes=1),
    )

    summary = prune_observability_export_jobs(log_dir, ttl_seconds=1800, max_jobs=20)

    assert summary["removed_jobs"] == 1
    assert summary["removed_metadata_files"] == 1
    assert summary["removed_artifact_files"] == 1
    assert summary["remaining_jobs"] == 2
    assert not old_job.exists()
    assert not old_artifact_file.exists()
    assert recent_job.exists()
    assert running_job.exists()

    snapshot_file = log_dir / "exports" / "jobs" / "snapshot.json"
    snapshot = json.loads(snapshot_file.read_text(encoding="utf-8"))
    assert snapshot["job_count"] == 2
    assert set(snapshot["jobs"].keys()) == {"exp_recent", "exp_running"}


def test_prune_observability_export_jobs_enforces_max_jobs_with_terminal_priority(
    tmp_path: Path,
) -> None:
    log_dir = tmp_path / "log"
    now = datetime.now(timezone.utc)

    _write_export_job(
        log_dir,
        job_id="exp_running",
        status="running",
        completed_at=None,
        updated_at=now - timedelta(minutes=1),
    )
    _write_export_job(
        log_dir,
        job_id="exp_completed_1",
        status="completed",
        completed_at=now - timedelta(minutes=5),
        updated_at=now - timedelta(minutes=5),
    )
    _write_export_job(
        log_dir,
        job_id="exp_completed_2",
        status="completed",
        completed_at=now - timedelta(minutes=4),
        updated_at=now - timedelta(minutes=4),
    )
    _write_export_job(
        log_dir,
        job_id="exp_completed_3",
        status="completed",
        completed_at=now - timedelta(minutes=3),
        updated_at=now - timedelta(minutes=3),
    )

    summary = prune_observability_export_jobs(
        log_dir,
        ttl_seconds=60 * 60 * 24 * 365,
        max_jobs=2,
    )

    assert summary["removed_jobs"] == 2
    assert summary["removed_metadata_files"] == 2
    assert summary["remaining_jobs"] == 2

    remaining = sorted(path.stem for path in (log_dir / "exports" / "jobs").glob("exp_*.json"))
    assert remaining == ["exp_completed_3", "exp_running"]


def test_run_prune_export_jobs_command_uses_filesystem_pruner(tmp_path: Path, capsys) -> None:
    log_dir = tmp_path / "log"
    args = argparse.Namespace(path=str(log_dir), max_age_hours=1, max_jobs=5)
    cli.run_prune_export_jobs_command(args)
    output = capsys.readouterr().out
    assert "Export Job Prune Report" in output
    assert "removed_jobs:" in output
