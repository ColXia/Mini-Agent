"""Generate weekly P19 rollout KPI dashboard and checklist report."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mini_agent.dev.p19_rollout_reporting import (  # noqa: E402
    build_weekly_rollout_payload,
    build_weekly_rollout_report,
    evaluate_target_bands,
    get_target_bands,
    list_target_profiles,
    summarize_weekly_rollout,
)


# Environment variables that can indicate deployment stage
_CI_ENV_VARS = [
    "DEPLOYMENT_STAGE",
    "ENVIRONMENT",
    "ENV",
    "STAGE",
    "CI_ENV",
    "GITHUB_ENV",
]


def _detect_target_profile_from_env() -> str:
    """Detect target profile from CI environment variables.

    Returns:
        Detected profile name, or 'stage' as default fallback
    """
    for env_var in _CI_ENV_VARS:
        value = os.environ.get(env_var, "").strip().lower()
        if not value:
            continue
        # Normalize common environment names to profile names
        if value in ("dev", "development"):
            return "dev"
        if value in ("stage", "staging", "stg"):
            return "stage"
        if value in ("prod", "production"):
            return "prod"
        # Direct match with profile names
        if value in list_target_profiles():
            return value
    return "stage"


def _resolve_target_profile(profile_arg: str) -> str:
    """Resolve target profile from argument or environment.

    Args:
        profile_arg: The --target-profile argument value

    Returns:
        Resolved profile name
    """
    if profile_arg == "auto":
        return _detect_target_profile_from_env()
    return profile_arg


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate weekly Stage-C rollout KPI review report.")
    parser.add_argument(
        "--window-days",
        type=int,
        default=7,
        help="How many recent days to include in the weekly review window.",
    )
    parser.add_argument(
        "--min-matrix-runs",
        type=int,
        default=1,
        help="Minimum matrix runs required in the review window.",
    )
    parser.add_argument(
        "--min-deterministic-runs",
        type=int,
        default=1,
        help="Minimum deterministic gate runs required in the review window.",
    )
    parser.add_argument(
        "--matrix-pattern",
        default="workspace/p19_matrix/p19_runtime_matrix_*.md",
        help="Glob pattern for P19 runtime matrix reports.",
    )
    parser.add_argument(
        "--deterministic-pattern",
        default="workspace/release_gate/release_gate_deterministic_*.md",
        help="Glob pattern for deterministic release gate reports.",
    )
    parser.add_argument(
        "--promotion-pattern",
        default="workspace/release_promotion/release_promotion_*.md",
        help="Glob pattern for promotion checklist reports.",
    )
    parser.add_argument(
        "--runtime-snapshot-pattern",
        default="workspace/release_gate/studio_ops_runtime_*.json",
        help="Glob pattern for Studio Ops runtime snapshot artifacts.",
    )
    parser.add_argument(
        "--target-profile",
        default="stage",
        help="Target KPI profile (environment band). Use 'auto' to detect from CI environment variables.",
    )
    parser.add_argument(
        "--report-file",
        default=None,
        help="Optional output path. Default: workspace/p19_rollout/p19_weekly_rollout_<utc>.md",
    )
    parser.add_argument(
        "--json-report-file",
        default=None,
        help="Optional JSON output path. Default: workspace/p19_rollout/p19_weekly_rollout_<utc>.json",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero when overall weekly status is ATTENTION.",
    )
    parser.add_argument(
        "--strict-targets",
        action="store_true",
        help="Also fail when target profile evaluation is ATTENTION.",
    )
    return parser.parse_args(argv)


def _default_report_file(*, now: datetime) -> Path:
    return REPO_ROOT / "workspace" / "p19_rollout" / f"p19_weekly_rollout_{now.strftime('%Y%m%dT%H%M%SZ')}.md"


def _default_json_report_file(*, now: datetime) -> Path:
    return REPO_ROOT / "workspace" / "p19_rollout" / f"p19_weekly_rollout_{now.strftime('%Y%m%dT%H%M%SZ')}.json"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    resolved_profile = _resolve_target_profile(args.target_profile)
    # Validate resolved profile
    if resolved_profile not in list_target_profiles():
        print(f"[p19-weekly] invalid target profile: {resolved_profile}", file=sys.stderr)
        return 1

    now = datetime.now(timezone.utc)
    summary = summarize_weekly_rollout(
        repo_root=REPO_ROOT,
        now=now,
        window_days=max(1, int(args.window_days)),
        min_matrix_runs=max(1, int(args.min_matrix_runs)),
        min_deterministic_runs=max(1, int(args.min_deterministic_runs)),
        matrix_pattern=args.matrix_pattern,
        deterministic_pattern=args.deterministic_pattern,
        promotion_pattern=args.promotion_pattern,
        runtime_snapshot_pattern=args.runtime_snapshot_pattern,
    )
    previous_summary = summarize_weekly_rollout(
        repo_root=REPO_ROOT,
        now=summary.window_start,
        window_days=max(1, int(args.window_days)),
        min_matrix_runs=max(1, int(args.min_matrix_runs)),
        min_deterministic_runs=max(1, int(args.min_deterministic_runs)),
        matrix_pattern=args.matrix_pattern,
        deterministic_pattern=args.deterministic_pattern,
        promotion_pattern=args.promotion_pattern,
        runtime_snapshot_pattern=args.runtime_snapshot_pattern,
    )
    target_eval = evaluate_target_bands(summary=summary, target_profile=resolved_profile)

    report_file = Path(args.report_file).expanduser().resolve() if args.report_file else _default_report_file(now=now)
    json_report_file = (
        Path(args.json_report_file).expanduser().resolve()
        if args.json_report_file
        else _default_json_report_file(now=now)
    )
    report_file.parent.mkdir(parents=True, exist_ok=True)
    json_report_file.parent.mkdir(parents=True, exist_ok=True)
    report_file.write_text(
        build_weekly_rollout_report(
            summary=summary,
            target_profile=resolved_profile,
            previous_summary=previous_summary,
        ),
        encoding="utf-8",
    )
    json_report_file.write_text(
        json.dumps(
            build_weekly_rollout_payload(
                summary=summary,
                target_profile=resolved_profile,
                previous_summary=previous_summary,
            ),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    print(f"[p19-weekly] report: {report_file}")
    print(f"[p19-weekly] json_report: {json_report_file}")
    print(f"[p19-weekly] overall: {summary.overall}")
    if args.target_profile == "auto":
        print(f"[p19-weekly] target_profile=auto -> {resolved_profile}")
    else:
        print(f"[p19-weekly] target_profile={resolved_profile}")
    print(
        f"[p19-weekly] target_status={'PASS' if target_eval.pass_all else 'ATTENTION'}"
    )
    print(
        "[p19-weekly] window counts: "
        f"matrix={len(summary.matrix_reports)}, "
        f"deterministic={len(summary.deterministic_reports)}, "
        f"promotion={len(summary.promotion_reports)}, "
        f"runtime={len(summary.runtime_snapshots)}"
    )
    if args.strict and summary.overall != "READY":
        print("[p19-weekly] strict mode: ATTENTION -> FAIL", file=sys.stderr)
        return 1
    if args.strict_targets and not target_eval.pass_all:
        print("[p19-weekly] strict-targets mode: target profile ATTENTION -> FAIL", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
