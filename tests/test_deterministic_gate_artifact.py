from __future__ import annotations

from pathlib import Path

from mini_agent.dev.deterministic_gate_artifact import (
    list_gate_artifacts,
    report_has_pass_status,
    validate_deterministic_gate_artifact,
)


def test_validate_deterministic_gate_artifact_missing(tmp_path: Path) -> None:
    status = validate_deterministic_gate_artifact(
        repo_root=tmp_path,
        pattern="workspace/release_gate/release_gate_deterministic_*.md",
    )
    assert status.matched_count == 0
    assert status.latest_artifact is None
    assert status.latest_pass is False
    assert status.ok is False


def test_validate_deterministic_gate_artifact_uses_latest_file(tmp_path: Path) -> None:
    folder = tmp_path / "workspace" / "release_gate"
    folder.mkdir(parents=True, exist_ok=True)
    older = folder / "release_gate_deterministic_20260407T010000Z.md"
    newer = folder / "release_gate_deterministic_20260407T020000Z.md"
    older.write_text("# Release Gate Report\n- Overall: FAIL\n", encoding="utf-8")
    newer.write_text("# Release Gate Report\n- Overall: PASS\n", encoding="utf-8")

    artifacts = list_gate_artifacts(
        repo_root=tmp_path,
        pattern="workspace/release_gate/release_gate_deterministic_*.md",
    )
    assert artifacts[-1].name == newer.name

    status = validate_deterministic_gate_artifact(
        repo_root=tmp_path,
        pattern="workspace/release_gate/release_gate_deterministic_*.md",
    )
    assert status.matched_count == 2
    assert status.latest_artifact is not None
    assert Path(status.latest_artifact).name == newer.name
    assert status.latest_pass is True
    assert status.ok is True


def test_report_has_pass_status_negative_case(tmp_path: Path) -> None:
    path = tmp_path / "report.md"
    path.write_text("# Release Gate Report\n- Overall: FAIL\n", encoding="utf-8")
    assert report_has_pass_status(path) is False

