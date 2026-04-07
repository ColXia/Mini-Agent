"""Tests for run-log retention and rotation behavior."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from mini_agent.logger import AgentLogger, EventLogRetentionPolicy


def _write_run_pair(log_dir: Path, run_suffix: str, *, size: int, age_days: int) -> None:
    run_name = f"agent_run_{run_suffix}"
    text = "x" * size
    log_file = log_dir / f"{run_name}.log"
    event_file = log_dir / f"{run_name}.events.jsonl"
    log_file.write_text(text, encoding="utf-8")
    event_file.write_text(text, encoding="utf-8")

    target_ts = (datetime.now(timezone.utc) - timedelta(days=age_days)).timestamp()
    for path in (log_file, event_file):
        Path(path).touch()
        # Set same access and modified time for deterministic ordering.
        import os

        os.utime(path, (target_ts, target_ts))


def test_retention_by_max_runs(tmp_path: Path):
    _write_run_pair(tmp_path, "20260101_000000_001", size=32, age_days=6)
    _write_run_pair(tmp_path, "20260102_000000_001", size=32, age_days=5)
    _write_run_pair(tmp_path, "20260103_000000_001", size=32, age_days=4)
    _write_run_pair(tmp_path, "20260104_000000_001", size=32, age_days=3)

    logger = AgentLogger(
        log_dir=tmp_path,
        retention_policy=EventLogRetentionPolicy(
            enabled=True,
            prune_on_start=False,
            max_runs=2,
            max_age_days=365,
            max_total_size_mb=64,
        ),
    )
    summary = logger.prune_logs()

    assert summary["removed_runs"] == 2
    assert summary["remaining_runs"] == 2
    remaining_names = sorted(path.name for path in tmp_path.glob("agent_run_*.log"))
    assert remaining_names == [
        "agent_run_20260103_000000_001.log",
        "agent_run_20260104_000000_001.log",
    ]


def test_retention_by_age(tmp_path: Path):
    _write_run_pair(tmp_path, "20260105_000000_001", size=16, age_days=10)
    _write_run_pair(tmp_path, "20260106_000000_001", size=16, age_days=1)

    logger = AgentLogger(
        log_dir=tmp_path,
        retention_policy=EventLogRetentionPolicy(
            enabled=True,
            prune_on_start=False,
            max_runs=20,
            max_age_days=2,
            max_total_size_mb=64,
        ),
    )
    summary = logger.prune_logs()

    assert summary["removed_runs"] == 1
    remaining_names = sorted(path.name for path in tmp_path.glob("agent_run_*.log"))
    assert remaining_names == ["agent_run_20260106_000000_001.log"]


def test_retention_by_total_size(tmp_path: Path):
    _write_run_pair(tmp_path, "20260107_000000_001", size=800, age_days=3)
    _write_run_pair(tmp_path, "20260108_000000_001", size=800, age_days=2)
    _write_run_pair(tmp_path, "20260109_000000_001", size=800, age_days=1)

    logger = AgentLogger(
        log_dir=tmp_path,
        retention_policy=EventLogRetentionPolicy(
            enabled=True,
            prune_on_start=False,
            max_runs=20,
            max_age_days=365,
            max_total_size_mb=0.002,  # ~2KB for both file types together
        ),
    )
    summary = logger.prune_logs()

    assert summary["removed_runs"] >= 1
    assert summary["remaining_bytes"] <= int(0.002 * 1024 * 1024)
