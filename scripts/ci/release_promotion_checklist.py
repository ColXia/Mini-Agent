"""Release promotion checklist runner.

Policy enforcement:
- Deterministic release gate is mandatory.
- Remote no-dry-run gate is advisory.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mini_agent.dev.release_promotion_checklist import (  # noqa: E402
    PromotionChecklistItem,
    build_promotion_report,
    collect_advisories,
    is_promotion_ready,
)


@dataclass(frozen=True)
class GateExecutionResult:
    name: str
    command: str
    report_file: Path
    ok: bool
    duration_seconds: float
    note: str


def _first_token(raw: str) -> str:
    for item in raw.split(","):
        token = item.strip()
        if token:
            return token
    return ""


def _resolve_python(cli_value: str | None) -> str:
    if cli_value and cli_value.strip():
        return cli_value.strip()
    return sys.executable


def _build_env() -> dict[str, str]:
    env = dict(os.environ)
    src_path = str(SRC_ROOT)
    existing = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = src_path if not existing else f"{src_path}{os.pathsep}{existing}"
    return env


def _run_gate(*, name: str, cmd: list[str], report_file: Path) -> GateExecutionResult:
    start = time.perf_counter()
    print(f"[promotion] {name}")
    print(f"$ {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=REPO_ROOT, env=_build_env(), check=False)
    duration = time.perf_counter() - start
    if completed.returncode == 0:
        return GateExecutionResult(
            name=name,
            command=" ".join(cmd),
            report_file=report_file,
            ok=True,
            duration_seconds=duration,
            note="passed",
        )
    return GateExecutionResult(
        name=name,
        command=" ".join(cmd),
        report_file=report_file,
        ok=False,
        duration_seconds=duration,
        note=f"exit_code={completed.returncode}",
    )


def _default_report_path(*, folder: str, prefix: str, started_at: datetime) -> Path:
    return REPO_ROOT / "workspace" / folder / f"{prefix}_{started_at.strftime('%Y%m%dT%H%M%SZ')}.md"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run release promotion checklist with mandatory/advisory policy.")
    parser.add_argument("--python", default=None, help="Python interpreter path used for gate commands.")

    parser.add_argument("--studio-base-url", default="http://127.0.0.1:8008", help="Studio gateway base URL.")
    parser.add_argument("--studio-token", default=None, help="Studio token for ops smoke.")
    parser.add_argument("--studio-timeout", type=float, default=20.0, help="Studio smoke per-request timeout.")
    parser.add_argument(
        "--studio-workspace-root",
        default=str((REPO_ROOT / "src" / "workspace").resolve()),
        help="Workspace root for studio smoke temporary data.",
    )
    parser.add_argument(
        "--start-local-gateway",
        dest="start_local_gateway",
        action="store_true",
        default=True,
        help="Start temporary local gateway inside release_gate runs (default: enabled).",
    )
    parser.add_argument(
        "--no-start-local-gateway",
        dest="start_local_gateway",
        action="store_false",
        help="Do not start local gateway inside release_gate runs.",
    )

    parser.add_argument("--deterministic-report-file", default=None, help="Optional deterministic gate report path.")
    parser.add_argument(
        "--report-file",
        default=None,
        help="Optional promotion checklist report path; default: workspace/release_promotion/release_promotion_<utc>.md",
    )
    return parser.parse_args(argv)


def _base_gate_cmd(
    *,
    python_bin: str,
    report_file: Path,
    start_local_gateway: bool,
    studio_base_url: str,
    studio_token: str,
    studio_timeout: float,
    studio_workspace_root: str,
) -> list[str]:
    cmd: list[str] = [
        python_bin,
        "scripts/ci/release_gate.py",
        "--report-file",
        str(report_file),
        "--studio-base-url",
        studio_base_url,
        "--studio-timeout",
        str(studio_timeout),
        "--studio-workspace-root",
        studio_workspace_root,
    ]
    if start_local_gateway:
        cmd.append("--start-local-gateway")
    if studio_token:
        cmd.extend(["--studio-token", studio_token])
    return cmd


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    python_bin = _resolve_python(args.python)
    started_at = datetime.now(timezone.utc)

    deterministic_report = (
        Path(args.deterministic_report_file).expanduser().resolve()
        if args.deterministic_report_file
        else _default_report_path(folder="release_gate", prefix="release_gate_deterministic", started_at=started_at)
    )
    promotion_report = (
        Path(args.report_file).expanduser().resolve()
        if args.report_file
        else _default_report_path(folder="release_promotion", prefix="release_promotion", started_at=started_at)
    )

    studio_token = (args.studio_token or "").strip() or _first_token(os.getenv("MINI_AGENT_STUDIO_API_KEYS", ""))

    deterministic_cmd = _base_gate_cmd(
        python_bin=python_bin,
        report_file=deterministic_report,
        start_local_gateway=bool(args.start_local_gateway),
        studio_base_url=args.studio_base_url,
        studio_token=studio_token,
        studio_timeout=float(args.studio_timeout),
        studio_workspace_root=args.studio_workspace_root,
    )
    deterministic_result = _run_gate(
        name="deterministic_gate",
        cmd=deterministic_cmd,
        report_file=deterministic_report,
    )
    checklist_items: list[PromotionChecklistItem] = [
        PromotionChecklistItem(
            name="Deterministic release gate",
            mandatory=True,
            status="PASS" if deterministic_result.ok else "FAIL",
            note=deterministic_result.note,
            report_file=str(deterministic_result.report_file),
            command=deterministic_result.command,
            duration_seconds=deterministic_result.duration_seconds,
        )
    ]
    checklist_items.append(
        PromotionChecklistItem(
            name="Remote no-dry-run gate",
            mandatory=False,
            status="SKIP",
            note="No dedicated remote no-dry-run gate is configured in the current architecture.",
        )
    )

    ended_at = datetime.now(timezone.utc)
    promotion_report.parent.mkdir(parents=True, exist_ok=True)
    promotion_report.write_text(
        build_promotion_report(
            started_at=started_at,
            ended_at=ended_at,
            items=checklist_items,
        ),
        encoding="utf-8",
    )

    ready = is_promotion_ready(checklist_items)
    advisories = collect_advisories(checklist_items)
    print(f"[promotion] report: {promotion_report}")
    print(f"[promotion] decision: {'READY' if ready else 'BLOCKED'}")
    if advisories:
        print("[promotion] advisories:")
        for item in advisories:
            print(f"- {item}")
    return 0 if ready else 1


if __name__ == "__main__":
    raise SystemExit(main())

