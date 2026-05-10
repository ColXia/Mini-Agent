from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from mini_agent.dev.p19_rollout_reporting import (
    _build_kpi_sparkline,
    _build_kpi_sparkline_metadata,
    _build_kpi_sparklines,
    build_target_remediation_hints,
    build_weekly_rollout_payload,
    build_weekly_rollout_report,
    evaluate_target_bands,
    parse_promotion_advisory_status,
    parse_promotion_decision,
    parse_report_overall,
    parse_runtime_snapshot,
    summarize_weekly_rollout,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_runtime_snapshot(
    path: Path,
    *,
    captured_at: str,
    saturation: int,
    conflict: int,
    mode: str = "team",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "captured_at": captured_at,
        "runtime": {
            "mode": mode,
            "active_sessions": 1,
            "max_active_sessions": 4,
            "team_saturation_rejections": saturation,
            "team_workspace_conflict_rejections": conflict,
        },
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def test_parse_report_fields_and_runtime_snapshot(tmp_path: Path) -> None:
    now = "2026-04-07T05:56:38.000000+00:00"
    matrix = tmp_path / "tmp_matrix.md"
    matrix.write_text(
        "\n".join(
            [
                "# Matrix",
                "",
                "- Overall: PASS",
                f"- Started: {now}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert parse_report_overall(matrix) == "PASS"

    promotion = tmp_path / "tmp_promotion.md"
    promotion.write_text(
        "\n".join(
            [
                "# Promotion",
                "",
                "- Decision: READY",
                f"- Started: {now}",
                "",
                "### Remote no-dry-run gate",
                "- Role: ADVISORY",
                "- Status: SKIP",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert parse_promotion_decision(promotion) == "READY"
    assert parse_promotion_advisory_status(promotion) == "SKIP"

    runtime_json = tmp_path / "tmp_runtime.json"
    _write_runtime_snapshot(
        runtime_json,
        captured_at="2026-04-07T06:00:00+00:00",
        saturation=2,
        conflict=1,
    )
    runtime = parse_runtime_snapshot(runtime_json)
    assert runtime is not None
    assert runtime.team_saturation_rejections == 2
    assert runtime.team_workspace_conflict_rejections == 1


def test_summarize_weekly_rollout_ready_with_trend_and_delta(tmp_path: Path) -> None:
    now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)

    # Previous window artifacts (Apr 1 - Apr 7)
    _write(
        tmp_path / "workspace" / "p19_matrix" / "p19_runtime_matrix_20260407T100000Z.md",
        "\n".join(["# Matrix", "- Overall: PASS", "- Started: 2026-04-07T10:00:00+00:00"]) + "\n",
    )
    _write(
        tmp_path / "workspace" / "release_gate" / "release_gate_deterministic_20260407T101000Z.md",
        "\n".join(["# Gate", "- Overall: PASS", "- Started: 2026-04-07T10:10:00+00:00"]) + "\n",
    )
    _write(
        tmp_path / "workspace" / "release_promotion" / "release_promotion_20260407T102000Z.md",
        "\n".join(
            [
                "# Promotion",
                "- Decision: READY",
                "- Started: 2026-04-07T10:20:00+00:00",
                "",
                "### Remote no-dry-run gate",
                "- Role: ADVISORY",
                "- Status: SKIP",
            ]
        )
        + "\n",
    )
    _write_runtime_snapshot(
        tmp_path / "workspace" / "release_gate" / "studio_ops_runtime_20260407T101000Z.json",
        captured_at="2026-04-07T10:11:00+00:00",
        saturation=0,
        conflict=0,
    )

    # Current window artifacts (Apr 7 - Apr 14)
    _write(
        tmp_path / "workspace" / "p19_matrix" / "p19_runtime_matrix_20260414T100000Z.md",
        "\n".join(["# Matrix", "- Overall: PASS", "- Started: 2026-04-14T10:00:00+00:00"]) + "\n",
    )
    _write(
        tmp_path / "workspace" / "release_gate" / "release_gate_deterministic_20260414T101000Z.md",
        "\n".join(["# Gate", "- Overall: PASS", "- Started: 2026-04-14T10:10:00+00:00"]) + "\n",
    )
    _write(
        tmp_path / "workspace" / "release_promotion" / "release_promotion_20260414T102000Z.md",
        "\n".join(
            [
                "# Promotion",
                "- Decision: READY",
                "- Started: 2026-04-14T10:20:00+00:00",
                "",
                "### Remote no-dry-run gate",
                "- Role: ADVISORY",
                "- Status: WARN",
            ]
        )
        + "\n",
    )
    _write_runtime_snapshot(
        tmp_path / "workspace" / "release_gate" / "studio_ops_runtime_20260414T101000Z.json",
        captured_at="2026-04-14T10:11:00+00:00",
        saturation=1,
        conflict=0,
    )

    summary = summarize_weekly_rollout(repo_root=tmp_path, now=now, window_days=7)
    previous_summary = summarize_weekly_rollout(repo_root=tmp_path, now=summary.window_start, window_days=7)

    assert summary.overall == "READY"
    assert summary.matrix_pass_count == 1
    assert summary.deterministic_pass_count == 1
    assert summary.promotion_ready_count == 1
    assert summary.advisory_warn_fail_count == 1
    assert summary.saturation_last == 1
    assert summary.conflict_last == 0
    assert summary.saturation_trend == "n/a"

    target_eval = evaluate_target_bands(summary=summary, target_profile="stage")
    assert target_eval.pass_all is True

    report = build_weekly_rollout_report(summary=summary, target_profile="stage", previous_summary=previous_summary)
    assert "## KPI Dashboard" in report
    assert "## Runtime Counter Trends" in report
    assert "## Runtime Mode Split" in report
    assert "## Target Remediation Hints" in report
    assert "## Weekly Delta vs Previous Window" in report
    assert "Rollback Decision Log (Template)" in report
    payload = build_weekly_rollout_payload(summary=summary, target_profile="stage", previous_summary=previous_summary)
    assert payload["target_profile"] == "stage"
    assert payload["target_profile_status"] == "PASS"
    assert payload["counts"]["runtime_snapshots"] == 1
    assert payload["delta_vs_previous_window"]["advisory_skip_count"] == -1


def test_summarize_weekly_rollout_attention_when_matrix_missing(tmp_path: Path) -> None:
    now = datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)
    _write(
        tmp_path / "workspace" / "release_gate" / "release_gate_deterministic_20260407T101000Z.md",
        "- Overall: PASS\n- Started: 2026-04-07T10:10:00+00:00\n",
    )
    _write(
        tmp_path / "workspace" / "release_promotion" / "release_promotion_20260407T102000Z.md",
        "- Decision: READY\n- Started: 2026-04-07T10:20:00+00:00\n### Remote no-dry-run gate\n- Status: PASS\n",
    )

    summary = summarize_weekly_rollout(repo_root=tmp_path, now=now, window_days=7)
    assert summary.checklist.has_matrix_runs is False
    assert summary.overall == "ATTENTION"


def test_target_profile_prod_detects_runtime_pressure(tmp_path: Path) -> None:
    now = datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)

    _write(
        tmp_path / "workspace" / "p19_matrix" / "p19_runtime_matrix_20260407T100000Z.md",
        "- Overall: PASS\n- Started: 2026-04-07T10:00:00+00:00\n",
    )
    _write(
        tmp_path / "workspace" / "release_gate" / "release_gate_deterministic_20260407T101000Z.md",
        "- Overall: PASS\n- Started: 2026-04-07T10:10:00+00:00\n",
    )
    _write(
        tmp_path / "workspace" / "release_promotion" / "release_promotion_20260407T102000Z.md",
        "- Decision: READY\n- Started: 2026-04-07T10:20:00+00:00\n### Remote no-dry-run gate\n- Status: PASS\n",
    )
    _write_runtime_snapshot(
        tmp_path / "workspace" / "release_gate" / "studio_ops_runtime_20260407T101000Z.json",
        captured_at="2026-04-07T10:11:00+00:00",
        saturation=1,
        conflict=0,
    )

    summary = summarize_weekly_rollout(repo_root=tmp_path, now=now, window_days=7)
    target_eval = evaluate_target_bands(summary=summary, target_profile="prod")
    assert target_eval.pass_all is False
    assert any(row.kpi == "Saturation counter (last)" and row.status == "ATTENTION" for row in target_eval.rows)
    hints = build_target_remediation_hints(summary=summary, target_profile="prod")
    assert any("concurrency pressure" in hint for hint in hints)


class TestKpiSparklines:
    """Tests for KPI sparkline data generation."""

    def test_build_kpi_sparkline_empty(self) -> None:
        result = _build_kpi_sparkline([])
        assert result == []

    def test_build_kpi_sparkline_basic(self) -> None:
        values = [1.0, 0.0, 1.0, 0.5]
        result = _build_kpi_sparkline(values)
        assert result == [1.0, 0.0, 1.0, 0.5]

    def test_build_kpi_sparkline_with_none(self) -> None:
        values: list[float | None] = [1.0, None, 0.5, None]
        result = _build_kpi_sparkline(values)
        assert result == [1.0, -1, 0.5, -1]

    def test_build_kpi_sparkline_truncation(self) -> None:
        values = list(range(30))
        result = _build_kpi_sparkline(values, max_points=20)
        assert len(result) == 20
        assert result[0] == 10  # First value should be 10 (30 - 20)
        assert result[-1] == 29  # Last value should be 29

    def test_build_kpi_sparkline_metadata_empty(self, tmp_path: Path) -> None:
        now = datetime(2026, 4, 7, 12, 0, 0, tzinfo=timezone.utc)
        summary = summarize_weekly_rollout(repo_root=tmp_path, now=now, window_days=7)
        metadata = _build_kpi_sparkline_metadata(summary)
        assert metadata["matrix_pass_rate"]["count"] == 0
        assert metadata["saturation_counter"]["values"] == []

    def test_build_kpi_sparkline_metadata_with_data(self, tmp_path: Path) -> None:
        now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)

        # Create multiple reports for sparkline data
        for i, status in enumerate(["PASS", "FAIL", "PASS"]):
            _write(
                tmp_path / "workspace" / "p19_matrix" / f"p19_runtime_matrix_2026041{i}T100000Z.md",
                f"- Overall: {status}\n- Started: 2026-04-1{i}T10:00:00+00:00\n",
            )

        for i, status in enumerate(["PASS", "PASS"]):
            _write(
                tmp_path / "workspace" / "release_gate" / f"release_gate_deterministic_2026041{i}T101000Z.md",
                f"- Overall: {status}\n- Started: 2026-04-1{i}T10:10:00+00:00\n",
            )

        for i, saturation in enumerate([0, 1, 2]):
            _write_runtime_snapshot(
                tmp_path / "workspace" / "release_gate" / f"studio_ops_runtime_2026041{i}T101000Z.json",
                captured_at=f"2026-04-1{i}T10:11:00+00:00",
                saturation=saturation,
                conflict=0,
            )

        summary = summarize_weekly_rollout(repo_root=tmp_path, now=now, window_days=7)
        metadata = _build_kpi_sparkline_metadata(summary)

        # Matrix sparkline should have 3 values
        assert metadata["matrix_pass_rate"]["count"] == 3
        assert metadata["matrix_pass_rate"]["values"] == [1.0, 0.0, 1.0]
        assert metadata["matrix_pass_rate"]["last"] == 1.0

        # Deterministic sparkline should have 2 values
        assert metadata["deterministic_pass_rate"]["count"] == 2
        assert metadata["deterministic_pass_rate"]["values"] == [1.0, 1.0]

        # Saturation sparkline should have 3 values
        assert metadata["saturation_counter"]["count"] == 3
        assert metadata["saturation_counter"]["values"] == [0.0, 1.0, 2.0]
        assert metadata["saturation_counter"]["min"] == 0.0
        assert metadata["saturation_counter"]["max"] == 2.0

    def test_payload_includes_sparklines(self, tmp_path: Path) -> None:
        now = datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)

        _write(
            tmp_path / "workspace" / "p19_matrix" / "p19_runtime_matrix_20260414T100000Z.md",
            "- Overall: PASS\n- Started: 2026-04-14T10:00:00+00:00\n",
        )
        _write(
            tmp_path / "workspace" / "release_gate" / "release_gate_deterministic_20260414T101000Z.md",
            "- Overall: PASS\n- Started: 2026-04-14T10:10:00+00:00\n",
        )
        _write(
            tmp_path / "workspace" / "release_promotion" / "release_promotion_20260414T102000Z.md",
            "- Decision: READY\n- Started: 2026-04-14T10:20:00+00:00\n### Remote no-dry-run gate\n- Status: PASS\n",
        )
        _write_runtime_snapshot(
            tmp_path / "workspace" / "release_gate" / "studio_ops_runtime_20260414T101000Z.json",
            captured_at="2026-04-14T10:11:00+00:00",
            saturation=0,
            conflict=0,
        )

        summary = summarize_weekly_rollout(repo_root=tmp_path, now=now, window_days=7)
        payload = build_weekly_rollout_payload(summary=summary, target_profile="stage")

        assert "sparklines" in payload
        assert "matrix_pass_rate" in payload["sparklines"]
        assert "saturation_counter" in payload["sparklines"]
        assert "conflict_counter" in payload["sparklines"]
        assert "active_sessions" in payload["sparklines"]
