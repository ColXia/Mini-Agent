from __future__ import annotations

from pathlib import Path

import scripts.terminal_readiness_gate as gate


def _recorded_steps(monkeypatch, tmp_path: Path):
    calls: list[tuple[str, list[str]]] = []

    def _fake_run_step(*, name, cmd, env, fail_fast, capture_output=False):  # noqa: ANN001
        _ = env
        _ = fail_fast
        _ = capture_output
        calls.append((name, list(cmd)))
        parsed_output = None
        if name == "headless_live_smoke":
            parsed_output = {
                "ok": True,
                "type": "result",
                "model": "gpt-live",
                "output": "READY",
                "prepared_context": {
                    "item_count": 1,
                    "sources": ["knowledge_base"],
                },
                "prepared_context_diagnostics": {
                    "turn_count": 1,
                    "turns_with_context": 1,
                    "total_item_count": 1,
                    "source_turn_counts": {"knowledge_base": 1},
                    "source_item_counts": {"knowledge_base": 1},
                    "provider_status_totals": {"used": 1},
                },
            }
        return gate.StepResult(
            name=name,
            command=" ".join(cmd),
            ok=True,
            duration_seconds=0.1,
            note="passed",
            parsed_output=parsed_output,
        )

    monkeypatch.setattr(gate, "_run_step", _fake_run_step)
    monkeypatch.setattr(gate, "_write_report", lambda **kwargs: None)
    monkeypatch.setattr(gate, "_has_any_real_key", lambda: True)
    return calls, tmp_path / "report.md"


def test_live_headless_runs_before_targeted_and_baseline(monkeypatch, tmp_path: Path) -> None:
    calls, report_file = _recorded_steps(monkeypatch, tmp_path)

    result = gate.main(
        [
            "--run-live-headless",
            "--skip-tui-checklist",
            "--skip-tui-walkthrough",
            "--skip-shared-session-walkthrough",
            "--skip-channel-ingress-walkthrough",
            "--report-file",
            str(report_file),
        ]
    )

    assert result == 0
    assert [name for name, _cmd in calls] == [
        "cli_help",
        "cli_list_modules",
        "headless_live_smoke",
        "terminal_targeted_tests",
        "full_regression",
        "p23_runtime_baseline",
    ]


def test_live_headless_uses_lighter_default_baseline_runs(monkeypatch, tmp_path: Path) -> None:
    calls, report_file = _recorded_steps(monkeypatch, tmp_path)

    result = gate.main(
        [
            "--run-live-headless",
            "--skip-tui-checklist",
            "--skip-tui-walkthrough",
            "--skip-shared-session-walkthrough",
            "--skip-channel-ingress-walkthrough",
            "--report-file",
            str(report_file),
        ]
    )

    assert result == 0
    baseline_cmd = dict(calls)["p23_runtime_baseline"]
    assert baseline_cmd[-2:] == ["--runs", "20"]


def test_gate_can_skip_runtime_baseline(monkeypatch, tmp_path: Path) -> None:
    calls, report_file = _recorded_steps(monkeypatch, tmp_path)

    result = gate.main(
        [
            "--skip-baseline",
            "--skip-tui-checklist",
            "--skip-tui-walkthrough",
            "--skip-shared-session-walkthrough",
            "--skip-channel-ingress-walkthrough",
            "--report-file",
            str(report_file),
        ]
    )

    assert result == 0
    assert "p23_runtime_baseline" not in [name for name, _cmd in calls]


def test_gate_respects_explicit_baseline_runs_override(monkeypatch, tmp_path: Path) -> None:
    calls, report_file = _recorded_steps(monkeypatch, tmp_path)

    result = gate.main(
        [
            "--baseline-runs",
            "37",
            "--skip-tui-checklist",
            "--skip-tui-walkthrough",
            "--skip-shared-session-walkthrough",
            "--skip-channel-ingress-walkthrough",
            "--report-file",
            str(report_file),
        ]
    )

    assert result == 0
    baseline_cmd = dict(calls)["p23_runtime_baseline"]
    assert baseline_cmd[-2:] == ["--runs", "37"]


def test_gate_targeted_tests_follow_current_v11_1_boundaries(monkeypatch, tmp_path: Path) -> None:
    calls, report_file = _recorded_steps(monkeypatch, tmp_path)

    result = gate.main(
        [
            "--skip-full-tests",
            "--skip-baseline",
            "--skip-tui-checklist",
            "--skip-tui-walkthrough",
            "--skip-shared-session-walkthrough",
            "--skip-channel-ingress-walkthrough",
            "--report-file",
            str(report_file),
        ]
    )

    assert result == 0
    targeted_cmd = dict(calls)["terminal_targeted_tests"]
    assert "tests/test_main_agent_surface_service.py" not in targeted_cmd
    assert "tests/test_v11_1_stage_h4_application_hard_cut.py" in targeted_cmd
    assert "tests/test_script_surface_boundary_hygiene.py" in targeted_cmd


def test_gate_report_includes_live_headless_context_section(monkeypatch, tmp_path: Path) -> None:
    calls: list[tuple[str, list[str]]] = []
    report_file = tmp_path / "report.md"

    def _fake_run_step(*, name, cmd, env, fail_fast, capture_output=False):  # noqa: ANN001
        _ = env
        _ = fail_fast
        _ = capture_output
        calls.append((name, list(cmd)))
        parsed_output = None
        if name == "headless_live_smoke":
            parsed_output = {
                "ok": True,
                "type": "result",
                "model": "gpt-live",
                "output": "READY",
                "prepared_context": {
                    "item_count": 1,
                    "sources": ["knowledge_base"],
                    "raw_item_count": 2,
                    "dropped_duplicate_count": 1,
                },
                "prepared_context_diagnostics": {
                    "turn_count": 1,
                    "turns_with_context": 1,
                    "total_item_count": 1,
                    "curated_turn_count": 1,
                    "total_dropped_item_count": 1,
                    "source_turn_counts": {"knowledge_base": 1},
                    "source_item_counts": {"knowledge_base": 1},
                    "provider_status_totals": {"used": 1, "no_match": 1},
                },
            }
        return gate.StepResult(
            name=name,
            command=" ".join(cmd),
            ok=True,
            duration_seconds=0.1,
            note="passed",
            parsed_output=parsed_output,
        )

    monkeypatch.setattr(gate, "_run_step", _fake_run_step)
    monkeypatch.setattr(gate, "_has_any_real_key", lambda: True)

    result = gate.main(
        [
            "--run-live-headless",
            "--skip-tui-checklist",
            "--skip-tui-walkthrough",
            "--skip-shared-session-walkthrough",
            "--skip-channel-ingress-walkthrough",
            "--skip-full-tests",
            "--skip-baseline",
            "--report-file",
            str(report_file),
        ]
    )

    assert result == 0
    report = report_file.read_text(encoding="utf-8")
    assert "## Live Headless Context" in report
    assert "- Context contract: PASS" in report
    assert "- Diagnostics: 1 turn(s) | 1 with context | 1 item(s) | curated 1 | dropped 1" in report
    assert "- Last prepared context: 1 item(s) | from knowledge_base | raw 2 | dedupe-drop 1" in report
    assert "- Source coverage: knowledge_base 1 turn(s)/1 item(s)" in report
    assert "- Provider totals: no_match 1, used 1" in report
    assert [name for name, _cmd in calls] == [
        "cli_help",
        "cli_list_modules",
        "headless_live_smoke",
        "terminal_targeted_tests",
    ]


def test_live_headless_fails_when_context_contract_is_missing(monkeypatch, tmp_path: Path) -> None:
    report_file = tmp_path / "report.md"

    def _fake_run_step(*, name, cmd, env, fail_fast, capture_output=False):  # noqa: ANN001
        _ = cmd
        _ = env
        _ = fail_fast
        _ = capture_output
        parsed_output = {"ok": True, "type": "result", "model": "gpt-live", "output": "READY"}
        if name != "headless_live_smoke":
            parsed_output = None
        return gate.StepResult(
            name=name,
            command=name,
            ok=True,
            duration_seconds=0.1,
            note="passed",
            parsed_output=parsed_output,
        )

    monkeypatch.setattr(gate, "_run_step", _fake_run_step)
    monkeypatch.setattr(gate, "_has_any_real_key", lambda: True)

    result = gate.main(
        [
            "--run-live-headless",
            "--skip-tui-checklist",
            "--skip-tui-walkthrough",
            "--skip-shared-session-walkthrough",
            "--skip-channel-ingress-walkthrough",
            "--skip-full-tests",
            "--skip-baseline",
            "--report-file",
            str(report_file),
        ]
    )

    assert result == 1
    report = report_file.read_text(encoding="utf-8")
    assert "- Overall: FAIL" in report
    assert "- Context contract: FAIL" in report
    assert "- Contract note: prepared_context_diagnostics missing from live smoke output" in report


def test_gate_runs_scripted_tui_walkthroughs_by_default(monkeypatch, tmp_path: Path) -> None:
    calls, report_file = _recorded_steps(monkeypatch, tmp_path)

    result = gate.main(["--skip-full-tests", "--skip-baseline", "--report-file", str(report_file)])

    assert result == 0
    assert [name for name, _cmd in calls] == [
        "cli_help",
        "cli_list_modules",
        "tui_manual_checklist",
        "tui_interaction_walkthrough",
        "shared_session_gateway_walkthrough",
        "channel_ingress_gateway_walkthrough",
        "terminal_targeted_tests",
    ]


def test_gate_can_skip_scripted_tui_walkthroughs(monkeypatch, tmp_path: Path) -> None:
    calls, report_file = _recorded_steps(monkeypatch, tmp_path)

    result = gate.main(
        [
            "--skip-full-tests",
            "--skip-baseline",
            "--skip-tui-checklist",
            "--skip-tui-walkthrough",
            "--skip-shared-session-walkthrough",
            "--skip-channel-ingress-walkthrough",
            "--report-file",
            str(report_file),
        ]
    )

    assert result == 0
    assert [name for name, _cmd in calls] == [
        "cli_help",
        "cli_list_modules",
        "terminal_targeted_tests",
    ]
