"""Run deterministic runtime-mode regression matrix for P19 rollout."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
import os
from pathlib import Path
import subprocess
import sys
import time


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class MatrixResult:
    profile: str
    command: str
    ok: bool
    duration_seconds: float
    note: str = ""


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


def _run_profile(name: str, cmd: list[str], env: dict[str, str]) -> MatrixResult:
    start = time.perf_counter()
    print(f"[matrix] {name}")
    print(f"$ {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=False)
    duration = time.perf_counter() - start
    if completed.returncode == 0:
        return MatrixResult(
            profile=name,
            command=" ".join(cmd),
            ok=True,
            duration_seconds=duration,
            note="passed",
        )
    return MatrixResult(
        profile=name,
        command=" ".join(cmd),
        ok=False,
        duration_seconds=duration,
        note=f"exit_code={completed.returncode}",
    )


def _write_report(
    *,
    report_file: Path,
    results: list[MatrixResult],
    started_at: datetime,
    ended_at: datetime,
) -> None:
    overall_ok = all(item.ok for item in results)
    report_file.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        f"# P19 Runtime Matrix Report - {started_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        f"- Overall: {'PASS' if overall_ok else 'FAIL'}",
        f"- Started: {started_at.isoformat()}",
        f"- Ended: {ended_at.isoformat()}",
        f"- Duration: {(ended_at - started_at).total_seconds():.1f}s",
        "",
        "## Profiles",
        "",
    ]
    for item in results:
        lines.append(f"### {item.profile}")
        lines.append(f"- Status: {'PASS' if item.ok else 'FAIL'}")
        lines.append(f"- Duration: {item.duration_seconds:.1f}s")
        lines.append(f"- Note: {item.note}")
        lines.append(f"- Command: `{item.command}`")
        lines.append("")
    report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run deterministic single_main/team regression matrix.")
    parser.add_argument("--python", default=None, help="Python interpreter used for child commands.")
    parser.add_argument(
        "--report-file",
        default=None,
        help="Optional report path; default: workspace/p19_matrix/p19_runtime_matrix_<utc>.md",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    python_bin = _resolve_python(args.python)
    env = _build_env()
    started_at = datetime.now(timezone.utc)

    results: list[MatrixResult] = []
    results.append(
        _run_profile(
            "single_main_profile",
            [
                python_bin,
                "-m",
                "pytest",
                "-q",
                "tests/test_p19_runtime_matrix.py::test_single_main_profile_contract",
            ],
            env,
        )
    )
    results.append(
        _run_profile(
            "team_profile",
            [
                python_bin,
                "-m",
                "pytest",
                "-q",
                "tests/test_p19_runtime_matrix.py::test_team_profile_contract",
            ],
            env,
        )
    )

    ended_at = datetime.now(timezone.utc)
    report_file = Path(args.report_file).expanduser().resolve() if args.report_file else (
        REPO_ROOT
        / "workspace"
        / "p19_matrix"
        / f"p19_runtime_matrix_{started_at.strftime('%Y%m%dT%H%M%SZ')}.md"
    )
    _write_report(
        report_file=report_file,
        results=results,
        started_at=started_at,
        ended_at=ended_at,
    )
    overall_ok = all(item.ok for item in results)
    print(f"[matrix] report: {report_file}")
    print(f"[matrix] overall: {'PASS' if overall_ok else 'FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
