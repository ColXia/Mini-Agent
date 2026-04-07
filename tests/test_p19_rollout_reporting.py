from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from mini_agent.dev.p19_rollout_reporting import (
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
                "### OpenWebUI no-dry-run gate",
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
                "### OpenWebUI no-dry-run gate",
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
                "### OpenWebUI no-dry-run gate",
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
        "- Decision: READY\n- Started: 2026-04-07T10:20:00+00:00\n### OpenWebUI no-dry-run gate\n- Status: PASS\n",
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
        "- Decision: READY\n- Started: 2026-04-07T10:20:00+00:00\n### OpenWebUI no-dry-run gate\n- Status: PASS\n",
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
