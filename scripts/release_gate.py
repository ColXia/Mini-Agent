"""Unified pre-release gate runner.

Runs a bounded verification chain for release readiness:
1) OpenWebUI adapter verification
2) Studio Ops token-enabled smoke
3) Stable regression set
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
from typing import Any
from urllib.parse import urlparse

import requests


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class StepResult:
    name: str
    command: str
    ok: bool
    duration_seconds: float
    note: str = ""


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


def _build_env(overrides: dict[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ)
    src_path = str(REPO_ROOT / "src")
    existing = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = src_path if not existing else f"{src_path}{os.pathsep}{existing}"
    if overrides:
        env.update(overrides)
    return env


def _run_step(
    *,
    name: str,
    cmd: list[str],
    env: dict[str, str],
    fail_fast: bool,
) -> StepResult:
    start = time.perf_counter()
    print(f"[gate] {name}")
    print(f"$ {' '.join(cmd)}")
    completed = subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=False)
    duration = time.perf_counter() - start
    if completed.returncode == 0:
        return StepResult(
            name=name,
            command=" ".join(cmd),
            ok=True,
            duration_seconds=duration,
            note="passed",
        )

    result = StepResult(
        name=name,
        command=" ".join(cmd),
        ok=False,
        duration_seconds=duration,
        note=f"exit_code={completed.returncode}",
    )
    if fail_fast:
        raise RuntimeError(f"{name} failed ({result.note})")
    return result


def _wait_http_ok(url: str, timeout_seconds: int = 90) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=5)
            if 200 <= response.status_code < 500:
                return
        except Exception:
            pass
        time.sleep(0.7)
    raise RuntimeError(f"timed out waiting for service: {url}")


def _start_local_gateway(
    *,
    python_bin: str,
    base_url: str,
    studio_token: str | None,
) -> subprocess.Popen[str]:
    parsed = urlparse(base_url)
    host = (parsed.hostname or "").strip() or "127.0.0.1"
    port = int(parsed.port or 8008)
    if host not in {"127.0.0.1", "localhost"}:
        raise RuntimeError("--start-local-gateway only supports local base URLs (127.0.0.1/localhost).")

    env_overrides: dict[str, str] = {}
    if studio_token:
        env_overrides["MINI_AGENT_STUDIO_API_KEYS"] = studio_token

    proc = subprocess.Popen(
        [
            python_bin,
            "-m",
            "uvicorn",
            "apps.agent_studio_gateway.main:app",
            "--host",
            host,
            "--port",
            str(port),
        ],
        cwd=REPO_ROOT,
        env=_build_env(env_overrides),
        text=True,
    )
    health_url = f"{parsed.scheme or 'http'}://{host}:{port}/api/v1/system/health"
    _wait_http_ok(health_url)
    return proc


def _stop_process(proc: subprocess.Popen[str] | None) -> None:
    if not proc or proc.poll() is not None:
        return
    proc.kill()
    try:
        proc.wait(timeout=10)
    except Exception:
        pass


def _write_report(
    *,
    report_file: Path,
    args: argparse.Namespace,
    studio_runtime_report_file: Path | None,
    results: list[StepResult],
    started_at: datetime,
    ended_at: datetime,
    overall_ok: bool,
) -> None:
    report_file.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = [
        f"# Release Gate Report - {started_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        f"- Overall: {'PASS' if overall_ok else 'FAIL'}",
        f"- Started: {started_at.isoformat()}",
        f"- Ended: {ended_at.isoformat()}",
        f"- Duration: {(ended_at - started_at).total_seconds():.1f}s",
        "",
        "## Config",
        "",
        f"- openwebui_verify: {'skip' if args.skip_openwebui_verify else 'run'}",
        f"- studio_ops_smoke: {'skip' if args.skip_studio_ops_smoke else 'run'}",
        f"- stable_tests: {'skip' if args.skip_stable_tests else 'run'}",
        f"- studio_base_url: {args.studio_base_url}",
        f"- start_local_gateway: {bool(args.start_local_gateway)}",
        f"- studio_runtime_snapshot: {studio_runtime_report_file if studio_runtime_report_file else '-'}",
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
    report_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run unified pre-release verification gates.")
    parser.add_argument("--python", default=None, help="Python interpreter path used for child commands.")

    parser.add_argument("--skip-openwebui-verify", action="store_true", help="Skip open_webui_verify step.")
    parser.add_argument("--skip-studio-ops-smoke", action="store_true", help="Skip studio_ops_smoke step.")
    parser.add_argument("--skip-stable-tests", action="store_true", help="Skip scripts/test_stable.py step.")
    parser.add_argument("--no-fail-fast", action="store_true", help="Keep running remaining steps after a failure.")

    parser.add_argument("--openwebui-run-smoke", action="store_true", help="Enable open_webui_verify --run-smoke.")
    parser.add_argument("--openwebui-adapter-base-url", default="http://127.0.0.1:8010", help="OpenWebUI adapter base URL.")
    parser.add_argument("--openwebui-api-key", default=None, help="OpenWebUI adapter token.")
    parser.add_argument("--openwebui-model", default=None, help="Optional OpenWebUI model id.")
    parser.add_argument("--openwebui-no-dry-run", action="store_true", help="Pass --no-dry-run to open_webui_verify.")
    parser.add_argument("--openwebui-timeout", type=float, default=20.0, help="OpenWebUI smoke per-request timeout.")

    parser.add_argument("--studio-base-url", default="http://127.0.0.1:8008", help="Studio gateway base URL.")
    parser.add_argument("--studio-token", default=None, help="Studio token. Defaults to first MINI_AGENT_STUDIO_API_KEYS.")
    parser.add_argument("--studio-expect-auth", dest="studio_expect_auth", action="store_true", default=None)
    parser.add_argument("--studio-no-expect-auth", dest="studio_expect_auth", action="store_false")
    parser.add_argument("--studio-timeout", type=float, default=20.0, help="Studio smoke per-request timeout.")
    parser.add_argument(
        "--studio-workspace-root",
        default=str((REPO_ROOT / "src" / "workspace").resolve()),
        help="Workspace root for studio_ops_smoke temporary data.",
    )
    parser.add_argument(
        "--studio-runtime-report-file",
        default=None,
        help="Optional Studio Ops runtime snapshot artifact path.",
    )
    parser.add_argument(
        "--start-local-gateway",
        action="store_true",
        help="Start a temporary local gateway before studio_ops_smoke and stop it after run.",
    )

    parser.add_argument(
        "--report-file",
        default=None,
        help="Optional report file path; default: workspace/release_gate/release_gate_<utc>.md",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    python_bin = _resolve_python(args.python)
    fail_fast = not args.no_fail_fast
    results: list[StepResult] = []
    started_at = datetime.now(timezone.utc)
    default_studio_runtime_report_file = (
        REPO_ROOT / "workspace" / "release_gate" / f"studio_ops_runtime_{started_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    )
    studio_runtime_report_file = (
        Path(args.studio_runtime_report_file).expanduser().resolve()
        if args.studio_runtime_report_file
        else default_studio_runtime_report_file
    )

    studio_token = (args.studio_token or "").strip() or _first_token(os.getenv("MINI_AGENT_STUDIO_API_KEYS", ""))
    if args.start_local_gateway and not studio_token and args.studio_expect_auth is not False:
        # Keep local auth boundary deterministic for smoke check.
        studio_token = "studio-release-gate-token"

    gateway_proc: subprocess.Popen[str] | None = None
    try:
        if args.start_local_gateway and not args.skip_studio_ops_smoke:
            print("[gate] starting local gateway for studio smoke")
            gateway_proc = _start_local_gateway(
                python_bin=python_bin,
                base_url=args.studio_base_url,
                studio_token=studio_token,
            )

        if not args.skip_openwebui_verify:
            cmd = [python_bin, "scripts/open_webui_verify.py"]
            if args.openwebui_run_smoke:
                cmd.extend(["--run-smoke", "--adapter-base-url", args.openwebui_adapter_base_url, "--timeout", str(args.openwebui_timeout)])
                if args.openwebui_api_key:
                    cmd.extend(["--api-key", args.openwebui_api_key.strip()])
                if args.openwebui_model:
                    cmd.extend(["--model", args.openwebui_model.strip()])
                if args.openwebui_no_dry_run:
                    cmd.append("--no-dry-run")
            results.append(_run_step(name="open_webui_verify", cmd=cmd, env=_build_env(), fail_fast=fail_fast))

        if not args.skip_studio_ops_smoke:
            cmd = [
                python_bin,
                "scripts/studio_ops_smoke.py",
                "--base-url",
                args.studio_base_url,
                "--workspace-root",
                args.studio_workspace_root,
                "--timeout",
                str(args.studio_timeout),
                "--runtime-report-file",
                str(studio_runtime_report_file),
            ]
            if studio_token:
                cmd.extend(["--token", studio_token])
            expect_auth = bool(studio_token) if args.studio_expect_auth is None else bool(args.studio_expect_auth)
            cmd.append("--expect-auth" if expect_auth else "--no-expect-auth")
            results.append(_run_step(name="studio_ops_smoke", cmd=cmd, env=_build_env(), fail_fast=fail_fast))
            if gateway_proc and not args.skip_stable_tests:
                # Stable tests use TestClient startup and should not conflict with a live bound gateway port.
                print("[gate] stopping local gateway before stable tests")
                _stop_process(gateway_proc)
                gateway_proc = None

        if not args.skip_stable_tests:
            cmd = [python_bin, "scripts/test_stable.py"]
            results.append(_run_step(name="stable_tests", cmd=cmd, env=_build_env(), fail_fast=fail_fast))
    except Exception as exc:  # noqa: BLE001
        if fail_fast:
            print(f"[gate] failed: {exc}", file=sys.stderr)
            # Add a synthetic summary step for fail-fast exceptions that happened before
            # one specific command could be captured by _run_step.
            if not results or results[-1].ok:
                results.append(
                    StepResult(
                        name="gate_runtime",
                        command="internal",
                        ok=False,
                        duration_seconds=0.0,
                        note=str(exc),
                    )
                )
        else:
            print(f"[gate] warning: {exc}", file=sys.stderr)
    finally:
        _stop_process(gateway_proc)

    ended_at = datetime.now(timezone.utc)
    overall_ok = all(item.ok for item in results)
    report_file = Path(args.report_file).expanduser().resolve() if args.report_file else (
        REPO_ROOT
        / "workspace"
        / "release_gate"
        / f"release_gate_{started_at.strftime('%Y%m%dT%H%M%SZ')}.md"
    )
    _write_report(
        report_file=report_file,
        args=args,
        studio_runtime_report_file=studio_runtime_report_file if not args.skip_studio_ops_smoke else None,
        results=results,
        started_at=started_at,
        ended_at=ended_at,
        overall_ok=overall_ok,
    )
    print(f"[gate] report: {report_file}")
    print(f"[gate] overall: {'PASS' if overall_ok else 'FAIL'}")
    return 0 if overall_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
