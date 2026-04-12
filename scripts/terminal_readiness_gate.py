"""Terminal-first readiness gate for real usage validation.

Scope:
- TUI/CLI-first core checks
- scripted TUI operator walkthroughs
- scripted gateway/shared-session walkthroughs
- scripted channel-ingress/gateway walkthroughs
- Regression tests and runtime baseline
- Optional live headless smoke (requires real API key)
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import locale
import os
from pathlib import Path
import subprocess
import sys
import time

from dotenv import dotenv_values


REPO_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_PRESET_ENV_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "MINIMAX_API_KEY",
)
PLACEHOLDER_KEYS = {
    "YOUR_API_KEY_HERE",
    "YOUR_OPENAI_API_KEY_HERE",
    "YOUR_ANTHROPIC_API_KEY_HERE",
    "YOUR_GEMINI_API_KEY_HERE",
    "YOUR_MINIMAX_API_KEY_HERE",
    "your_api_key",
    "your-api-key",
    "sk-cp-xxxxx",
    "sk-...",
    "sk-ant-...",
}


@dataclass(frozen=True)
class StepResult:
    name: str
    command: str
    ok: bool
    duration_seconds: float
    note: str = ""
    stdout: str = ""
    stderr: str = ""
    parsed_output: dict[str, object] | None = None


def _resolve_python(cli_value: str | None) -> str:
    if cli_value and cli_value.strip():
        return cli_value.strip()
    return sys.executable


def _build_env() -> dict[str, str]:
    env = dict(os.environ)
    src_path = str(REPO_ROOT / "src")
    existing = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = src_path if not existing else f"{src_path}{os.pathsep}{existing}"
    return env


def _is_valid_key(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text in PLACEHOLDER_KEYS:
        return False
    if text.endswith("..."):
        return False
    if (text.startswith("${") and text.endswith("}")) or (text.startswith("$") and len(text) > 1):
        return False
    return True


def _has_any_real_key() -> bool:
    for env_key in OFFICIAL_PRESET_ENV_KEYS:
        if _is_valid_key(os.getenv(env_key)):
            return True

    env_local = REPO_ROOT / ".env.local"
    if env_local.exists():
        values = dotenv_values(env_local)
        for env_key in OFFICIAL_PRESET_ENV_KEYS:
            if _is_valid_key(values.get(env_key)):
                return True
    return False


def _run_step(
    *,
    name: str,
    cmd: list[str],
    env: dict[str, str],
    fail_fast: bool,
    capture_output: bool = False,
) -> StepResult:
    start = time.perf_counter()
    print(f"[terminal-gate] {name}")
    print(f"$ {' '.join(cmd)}")
    completed = subprocess.run(
        cmd,
        cwd=REPO_ROOT,
        env=env,
        check=False,
        stdout=subprocess.PIPE if capture_output else None,
        stderr=subprocess.PIPE if capture_output else None,
    )
    duration = time.perf_counter() - start
    stdout = ""
    stderr = ""
    parsed_output: dict[str, object] | None = None
    if capture_output:
        stdout = _decode_subprocess_output(completed.stdout)
        stderr = _decode_subprocess_output(completed.stderr)
        parsed_output = _parse_last_json_object(stdout)
        if completed.returncode != 0:
            if stdout.strip():
                print(stdout.rstrip())
            if stderr.strip():
                print(stderr.rstrip(), file=sys.stderr)
    if completed.returncode == 0:
        return StepResult(
            name=name,
            command=" ".join(cmd),
            ok=True,
            duration_seconds=duration,
            note="passed",
            stdout=stdout,
            stderr=stderr,
            parsed_output=parsed_output,
        )

    result = StepResult(
        name=name,
        command=" ".join(cmd),
        ok=False,
        duration_seconds=duration,
        note=f"exit_code={completed.returncode}",
        stdout=stdout,
        stderr=stderr,
        parsed_output=parsed_output,
    )
    if fail_fast:
        raise RuntimeError(f"{name} failed ({result.note})")
    return result


def _decode_subprocess_output(data: bytes | None) -> str:
    if not data:
        return ""
    candidate_encodings = [
        locale.getpreferredencoding(False) or "",
        "utf-8",
        "gb18030",
        "cp936",
    ]
    seen: set[str] = set()
    for encoding in candidate_encodings:
        normalized = str(encoding or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def _parse_last_json_object(text: str) -> dict[str, object] | None:
    stripped = str(text or "").strip()
    if not stripped:
        return None

    candidates = [line.strip() for line in stripped.splitlines() if line.strip()]
    if stripped not in candidates:
        candidates.append(stripped)

    for candidate in reversed(candidates):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            return payload
    return None


def _prepared_context_diagnostics_summary(value: object) -> str:
    diagnostics = value if isinstance(value, dict) else {}
    turn_count = int(diagnostics.get("turn_count") or 0)
    if turn_count <= 0:
        return ""

    parts = [
        f"{turn_count} turn(s)",
        f"{int(diagnostics.get('turns_with_context') or 0)} with context",
        f"{int(diagnostics.get('total_item_count') or 0)} item(s)",
    ]
    curated_turn_count = int(diagnostics.get("curated_turn_count") or 0)
    if curated_turn_count > 0:
        parts.append(f"curated {curated_turn_count}")
    dropped = int(diagnostics.get("total_dropped_item_count") or 0)
    if dropped > 0:
        parts.append(f"dropped {dropped}")
    return " | ".join(parts)


def _prepared_context_last_turn_summary(value: object) -> str:
    prepared_context = value if isinstance(value, dict) else {}
    item_count = int(prepared_context.get("item_count") or 0)
    raw_item_count = int(prepared_context.get("raw_item_count") or 0)
    dropped_duplicate_count = int(prepared_context.get("dropped_duplicate_count") or 0)
    dropped_budget_count = int(prepared_context.get("dropped_budget_count") or 0)
    sources = [str(item).strip() for item in list(prepared_context.get("sources") or []) if str(item or "").strip()]

    parts = [f"{item_count} item(s)"]
    if sources:
        parts.append(f"from {', '.join(sources)}")
    if raw_item_count > item_count:
        parts.append(f"raw {raw_item_count}")
    if dropped_duplicate_count > 0:
        parts.append(f"dedupe-drop {dropped_duplicate_count}")
    if dropped_budget_count > 0:
        parts.append(f"budget-drop {dropped_budget_count}")
    return " | ".join(parts)


def _headless_context_contract_status(results: list[StepResult]) -> tuple[bool, str]:
    live_result = next((item for item in results if item.name == "headless_live_smoke"), None)
    if live_result is None:
        return True, "not_run"

    payload = live_result.parsed_output if isinstance(live_result.parsed_output, dict) else {}
    if not payload:
        return False, "live headless output was not valid JSON"

    diagnostics = payload.get("prepared_context_diagnostics")
    if not isinstance(diagnostics, dict):
        return False, "prepared_context_diagnostics missing from live smoke output"
    if int(diagnostics.get("turn_count") or 0) <= 0:
        return False, "prepared_context_diagnostics recorded no turns"
    return True, "prepared_context_diagnostics active"


def _build_live_headless_context_section(results: list[StepResult]) -> list[str]:
    live_result = next((item for item in results if item.name == "headless_live_smoke"), None)
    if live_result is None:
        return []

    lines = [
        "## Live Headless Context",
        "",
    ]
    contract_ok, contract_note = _headless_context_contract_status(results)
    payload = live_result.parsed_output if isinstance(live_result.parsed_output, dict) else {}
    diagnostics = payload.get("prepared_context_diagnostics") if isinstance(payload, dict) else {}
    prepared_context = payload.get("prepared_context") if isinstance(payload, dict) else {}

    lines.append(f"- Context contract: {'PASS' if contract_ok else 'FAIL'}")
    lines.append(f"- Contract note: {contract_note}")
    model = str(payload.get('model') or "").strip() if isinstance(payload, dict) else ""
    if model:
        lines.append(f"- Model: {model}")

    diagnostics_summary = _prepared_context_diagnostics_summary(diagnostics)
    lines.append(f"- Diagnostics: {diagnostics_summary or 'none reported'}")

    turns_with_context = 0
    if isinstance(diagnostics, dict):
        turns_with_context = int(diagnostics.get("turns_with_context") or 0)
    if turns_with_context > 0:
        lines.append("- Context matched this smoke: yes")
    else:
        lines.append("- Context matched this smoke: no")

    prepared_summary = _prepared_context_last_turn_summary(prepared_context)
    lines.append(f"- Last prepared context: {prepared_summary or 'none'}")

    if isinstance(diagnostics, dict):
        source_turn_counts = dict(diagnostics.get("source_turn_counts") or {})
        source_item_counts = dict(diagnostics.get("source_item_counts") or {})
        if source_turn_counts or source_item_counts:
            source_parts: list[str] = []
            ordered_sources = sorted(
                set(source_turn_counts) | set(source_item_counts),
                key=lambda source: (
                    -int(source_item_counts.get(source) or 0),
                    -int(source_turn_counts.get(source) or 0),
                    source,
                ),
            )
            for source in ordered_sources[:5]:
                source_parts.append(
                    f"{source} {int(source_turn_counts.get(source) or 0)} turn(s)/"
                    f"{int(source_item_counts.get(source) or 0)} item(s)"
                )
            lines.append(f"- Source coverage: {'; '.join(source_parts)}")

        provider_status_totals = dict(diagnostics.get("provider_status_totals") or {})
        if provider_status_totals:
            ordered_statuses = sorted(
                provider_status_totals.items(),
                key=lambda item: (-int(item[1]), item[0]),
            )
            parts = [f"{status} {count}" for status, count in ordered_statuses]
            lines.append(f"- Provider totals: {', '.join(parts)}")

    if not contract_ok and live_result.stdout.strip():
        preview = live_result.stdout.strip().splitlines()[-1]
        lines.append(f"- Raw output tail: `{preview}`")

    lines.append("")
    return lines


def _write_report(
    *,
    report_file: Path,
    args: argparse.Namespace,
    results: list[StepResult],
    started_at: datetime,
    ended_at: datetime,
    overall_ok: bool,
) -> None:
    report_file.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        f"# Terminal Readiness Gate Report - {started_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        f"- Overall: {'PASS' if overall_ok else 'FAIL'}",
        f"- Started: {started_at.isoformat()}",
        f"- Ended: {ended_at.isoformat()}",
        f"- Duration: {(ended_at - started_at).total_seconds():.1f}s",
        f"- Full tests: {'run' if not args.skip_full_tests else 'skip'}",
        f"- Live headless smoke: {'run' if args.run_live_headless else 'skip'}",
        f"- TUI manual checklist: {'run' if not args.skip_tui_checklist else 'skip'}",
        f"- TUI interaction walkthrough: {'run' if not args.skip_tui_walkthrough else 'skip'}",
        f"- Shared-session gateway walkthrough: {'run' if not args.skip_shared_session_walkthrough else 'skip'}",
        f"- Channel-ingress gateway walkthrough: {'run' if not args.skip_channel_ingress_walkthrough else 'skip'}",
        f"- Runtime baseline: {'run' if not args.skip_baseline else 'skip'}",
        f"- Baseline runs: {args.baseline_runs if args.baseline_runs is not None else ('20 (live-default)' if args.run_live_headless else '50 (default)')}",
        "",
        "## Steps",
        "",
    ]
    for item in results:
        lines.append(f"### {item.name}")
        lines.append(f"- Status: {'PASS' if item.ok else 'FAIL'}")
        lines.append(f"- Duration: {item.duration_seconds:.1f}s")
        lines.append(f"- Note: {item.note}")
        lines.append(f"- Command: `{item.command}`")
        lines.append("")
    lines.extend(_build_live_headless_context_section(results))
    report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run terminal-first readiness gate (TUI/CLI).",
    )
    parser.add_argument("--python", default=None, help="Python interpreter path used for child commands.")
    parser.add_argument("--skip-full-tests", action="store_true", help="Skip `pytest -q` full regression.")
    parser.add_argument("--skip-tui-checklist", action="store_true", help="Skip `scripts/tui_manual_checklist.py`.")
    parser.add_argument(
        "--skip-tui-walkthrough",
        action="store_true",
        help="Skip `scripts/tui_interaction_walkthrough.py`.",
    )
    parser.add_argument(
        "--skip-shared-session-walkthrough",
        action="store_true",
        help="Skip `scripts/shared_session_gateway_walkthrough.py`.",
    )
    parser.add_argument(
        "--skip-channel-ingress-walkthrough",
        action="store_true",
        help="Skip `scripts/channel_ingress_gateway_walkthrough.py`.",
    )
    parser.add_argument("--skip-baseline", action="store_true", help="Skip `scripts/p23_runtime_baseline.py`.")
    parser.add_argument("--run-live-headless", action="store_true", help="Run real headless CLI smoke with provider key.")
    parser.add_argument(
        "--headless-prompt",
        default="Reply with exactly: READY",
        help="Prompt used for live headless smoke.",
    )
    parser.add_argument(
        "--workspace",
        default=str((REPO_ROOT / "workspace").resolve()),
        help="Workspace for live headless smoke.",
    )
    parser.add_argument(
        "--baseline-runs",
        type=int,
        default=None,
        help="Optional run count override for `scripts/p23_runtime_baseline.py`.",
    )
    parser.add_argument("--no-fail-fast", action="store_true", help="Continue running remaining steps after failure.")
    parser.add_argument(
        "--report-file",
        default=None,
        help="Optional report path. Defaults to workspace/readiness/terminal_readiness_<utc>.md",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    python_bin = _resolve_python(args.python)
    fail_fast = not args.no_fail_fast
    env = _build_env()
    results: list[StepResult] = []
    baseline_runs = int(args.baseline_runs) if args.baseline_runs is not None else (20 if args.run_live_headless else 50)
    baseline_runs = max(10, baseline_runs)

    started_at = datetime.now(timezone.utc)
    default_report_file = (
        REPO_ROOT / "workspace" / "readiness" / f"terminal_readiness_{started_at.strftime('%Y%m%dT%H%M%SZ')}.md"
    )
    report_file = Path(args.report_file).expanduser().resolve() if args.report_file else default_report_file

    try:
        results.append(
            _run_step(
                name="cli_help",
                cmd=[python_bin, "-m", "mini_agent.cli", "--help"],
                env=env,
                fail_fast=fail_fast,
            )
        )
        results.append(
            _run_step(
                name="cli_list_modules",
                cmd=[python_bin, "-m", "mini_agent.cli", "list", "all"],
                env=env,
                fail_fast=fail_fast,
            )
        )
        if args.run_live_headless:
            if not _has_any_real_key():
                raise RuntimeError(
                    "Live headless smoke requested but no valid provider key found "
                    "(env: OPENAI/ANTHROPIC/GEMINI/MINIMAX or .env.local)."
                )
            results.append(
                _run_step(
                    name="headless_live_smoke",
                    cmd=[
                        python_bin,
                        "-m",
                        "mini_agent.cli",
                        "--mode",
                        "headless",
                        "--prompt",
                        str(args.headless_prompt),
                        "--output-format",
                        "json",
                        "--workspace",
                        str(Path(args.workspace).expanduser().resolve()),
                    ],
                    env=env,
                    fail_fast=fail_fast,
                    capture_output=True,
                )
            )
        if not args.skip_tui_checklist:
            results.append(
                _run_step(
                    name="tui_manual_checklist",
                    cmd=[python_bin, "scripts/tui_manual_checklist.py"],
                    env=env,
                    fail_fast=fail_fast,
                )
            )
        if not args.skip_tui_walkthrough:
            results.append(
                _run_step(
                    name="tui_interaction_walkthrough",
                    cmd=[python_bin, "scripts/tui_interaction_walkthrough.py"],
                    env=env,
                    fail_fast=fail_fast,
                )
            )
        if not args.skip_shared_session_walkthrough:
            results.append(
                _run_step(
                    name="shared_session_gateway_walkthrough",
                    cmd=[python_bin, "scripts/shared_session_gateway_walkthrough.py"],
                    env=env,
                    fail_fast=fail_fast,
                )
            )
        if not args.skip_channel_ingress_walkthrough:
            results.append(
                _run_step(
                    name="channel_ingress_gateway_walkthrough",
                    cmd=[python_bin, "scripts/channel_ingress_gateway_walkthrough.py"],
                    env=env,
                    fail_fast=fail_fast,
                )
            )
        results.append(
            _run_step(
                name="terminal_targeted_tests",
                cmd=[
                    python_bin,
                    "-m",
                    "pytest",
                    "tests/test_agent_core_kernel.py",
                    "tests/test_code_agent_minimal_workflow.py",
                    "tests/test_cli_unified_mode.py",
                    "tests/test_cli_submission_loop.py",
                    "tests/test_channel_ingress_gateway_walkthrough.py",
                    "tests/test_shared_session_gateway_walkthrough.py",
                    "tests/test_terminal_readiness_gate.py",
                    "tests/test_tui_readiness_walkthroughs.py",
                    "tests/test_tui_app.py",
                    "tests/test_main_agent_gateway_use_cases.py",
                    "-q",
                ],
                env=env,
                fail_fast=fail_fast,
            )
        )
        if not args.skip_full_tests:
            results.append(
                _run_step(
                    name="full_regression",
                    cmd=[python_bin, "-m", "pytest", "-q"],
                    env=env,
                    fail_fast=fail_fast,
                )
            )
        if not args.skip_baseline:
            results.append(
                _run_step(
                    name="p23_runtime_baseline",
                    cmd=[
                        python_bin,
                        "scripts/p23_runtime_baseline.py",
                        "--runs",
                        str(baseline_runs),
                    ],
                    env=env,
                    fail_fast=fail_fast,
                )
            )
    except Exception as exc:
        print(f"[terminal-gate] error: {exc}")
        if fail_fast and not any(not item.ok for item in results):
            # Keep a fail marker when exception occurs before first explicit failed step.
            results.append(
                StepResult(
                    name="terminal_gate",
                    command="internal",
                    ok=False,
                    duration_seconds=0.0,
                    note=str(exc),
                )
            )

    headless_context_ok, _headless_context_note = _headless_context_contract_status(results)
    overall_ok = bool(results) and all(item.ok for item in results) and headless_context_ok
    ended_at = datetime.now(timezone.utc)
    _write_report(
        report_file=report_file,
        args=args,
        results=results,
        started_at=started_at,
        ended_at=ended_at,
        overall_ok=overall_ok,
    )

    print(f"[terminal-gate] report: {report_file}")
    print(f"[terminal-gate] overall: {'PASS' if overall_ok else 'FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
