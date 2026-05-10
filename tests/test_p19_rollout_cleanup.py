"""Tests for P19 rollout artifact cleanup helpers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

# Add src to path for imports
import sys
REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from scripts.ci.p19_rollout_cleanup import (
    _parse_artifact_timestamp,
    cleanup_all_rollout_artifacts,
    cleanup_old_artifacts,
    list_rollout_artifacts,
)


def _write_artifact(path: Path, content: str = "") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content or "test", encoding="utf-8")


class TestParseArtifactTimestamp:
    """Tests for artifact timestamp parsing."""

    def test_parse_weekly_rollout_timestamp(self) -> None:
        result = _parse_artifact_timestamp("p19_weekly_rollout_20260510T101248Z.md")
        assert result is not None
        assert result.year == 2026
        assert result.month == 5
        assert result.day == 10
        assert result.hour == 10
        assert result.minute == 12
        assert result.second == 48

    def test_parse_release_gate_timestamp(self) -> None:
        result = _parse_artifact_timestamp("release_gate_deterministic_20260407T101000Z.md")
        assert result is not None
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 7

    def test_parse_runtime_snapshot_timestamp(self) -> None:
        result = _parse_artifact_timestamp("studio_ops_runtime_20260414T101000Z.json")
        assert result is not None
        assert result.year == 2026
        assert result.month == 4
        assert result.day == 14

    def test_parse_invalid_timestamp(self) -> None:
        result = _parse_artifact_timestamp("invalid_file.md")
        assert result is None

    def test_parse_no_timestamp(self) -> None:
        result = _parse_artifact_timestamp("report.md")
        assert result is None


class TestListRolloutArtifacts:
    """Tests for listing rollout artifacts."""

    def test_list_empty(self, tmp_path: Path) -> None:
        artifacts = list_rollout_artifacts(repo_root=tmp_path)
        assert artifacts == []

    def test_list_with_artifacts(self, tmp_path: Path) -> None:
        _write_artifact(tmp_path / "workspace" / "p19_rollout" / "p19_weekly_rollout_20260510T100000Z.md")

        artifacts = list_rollout_artifacts(repo_root=tmp_path)
        assert len(artifacts) == 1

    def test_list_with_multiple_patterns(self, tmp_path: Path) -> None:
        from scripts.ci.p19_rollout_cleanup import list_rollout_artifacts_multi

        _write_artifact(tmp_path / "workspace" / "p19_rollout" / "p19_weekly_rollout_20260510T100000Z.md")
        _write_artifact(tmp_path / "workspace" / "p19_rollout" / "p19_weekly_rollout_20260510T100000Z.json")

        artifacts = list_rollout_artifacts_multi(
            repo_root=tmp_path,
            patterns=[
                "workspace/p19_rollout/p19_weekly_rollout_*.md",
                "workspace/p19_rollout/p19_weekly_rollout_*.json",
            ],
        )
        assert len(artifacts) == 2


class TestCleanupOldArtifacts:
    """Tests for artifact cleanup."""

    def test_cleanup_by_age(self, tmp_path: Path) -> None:
        # Create old artifact (40 days ago)
        old_date = datetime.now(timezone.utc) - timedelta(days=40)
        old_name = f"p19_weekly_rollout_{old_date.strftime('%Y%m%dT%H%M%SZ')}.md"
        _write_artifact(tmp_path / "workspace" / "p19_rollout" / old_name, "old content")

        # Create new artifact
        new_date = datetime.now(timezone.utc) - timedelta(days=5)
        new_name = f"p19_weekly_rollout_{new_date.strftime('%Y%m%dT%H%M%SZ')}.md"
        _write_artifact(tmp_path / "workspace" / "p19_rollout" / new_name, "new content")

        result = cleanup_old_artifacts(
            repo_root=tmp_path,
            max_age_days=30,
            max_count=100,
            dry_run=False,
        )

        assert result["deleted_count"] == 1
        assert result["kept_count"] == 1

    def test_cleanup_by_count(self, tmp_path: Path) -> None:
        # Create 15 artifacts
        for i in range(15):
            date = datetime.now(timezone.utc) - timedelta(days=i)
            name = f"p19_weekly_rollout_{date.strftime('%Y%m%dT%H%M%SZ')}.md"
            _write_artifact(tmp_path / "workspace" / "p19_rollout" / name, f"content {i}")

        result = cleanup_old_artifacts(
            repo_root=tmp_path,
            max_age_days=365,  # Don't delete by age
            max_count=10,
            dry_run=False,
        )

        assert result["deleted_count"] == 5  # 15 - 10 = 5 deleted
        assert result["kept_count"] == 10

    def test_cleanup_dry_run(self, tmp_path: Path) -> None:
        # Create old artifact
        old_date = datetime.now(timezone.utc) - timedelta(days=40)
        old_name = f"p19_weekly_rollout_{old_date.strftime('%Y%m%dT%H%M%SZ')}.md"
        old_path = tmp_path / "workspace" / "p19_rollout" / old_name
        _write_artifact(old_path, "old content")

        result = cleanup_old_artifacts(
            repo_root=tmp_path,
            max_age_days=30,
            max_count=100,
            dry_run=True,
        )

        assert result["deleted_count"] == 1
        assert result["dry_run"] is True
        # File should still exist after dry run
        assert old_path.exists()


class TestCleanupAllRolloutArtifacts:
    """Tests for cleaning up all artifact categories."""

    def test_cleanup_all_categories(self, tmp_path: Path) -> None:
        # Create artifacts in different categories
        old_date = datetime.now(timezone.utc) - timedelta(days=40)

        # Rollout reports
        _write_artifact(
            tmp_path / "workspace" / "p19_rollout" / f"p19_weekly_rollout_{old_date.strftime('%Y%m%dT%H%M%SZ')}.md"
        )

        # Matrix reports
        _write_artifact(
            tmp_path / "workspace" / "p19_matrix" / f"p19_runtime_matrix_{old_date.strftime('%Y%m%dT%H%M%SZ')}.md"
        )

        # Release gates
        _write_artifact(
            tmp_path / "workspace" / "release_gate" / f"release_gate_deterministic_{old_date.strftime('%Y%m%dT%H%M%SZ')}.md"
        )

        result = cleanup_all_rollout_artifacts(
            repo_root=tmp_path,
            max_age_days=30,
            max_count=100,
            dry_run=False,
        )

        assert result["total_deleted"] == 3
        assert "categories" in result
        assert result["categories"]["rollout_reports"]["deleted_count"] == 1
        assert result["categories"]["matrix_reports"]["deleted_count"] == 1
        assert result["categories"]["deterministic_gates"]["deleted_count"] == 1
