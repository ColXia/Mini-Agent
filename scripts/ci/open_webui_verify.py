"""Verification entrypoint for OpenWebUI adapter positioning and compatibility."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]


def _run(cmd: list[str]) -> None:
    print(f"$ {' '.join(cmd)}")
    env = dict(os.environ)
    src_path = str(REPO_ROOT / "src")
    pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = src_path if not pythonpath else f"{src_path}{os.pathsep}{pythonpath}"
    subprocess.run(cmd, cwd=REPO_ROOT, env=env, check=True)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify OpenWebUI adapter compatibility and integration boundaries.")
    parser.add_argument(
        "--skip-unit",
        action="store_true",
        help="Skip unit tests and only run live smoke checks.",
    )
    parser.add_argument(
        "--run-smoke",
        action="store_true",
        help="Run scripts/ci/open_webui_smoke.py after unit tests.",
    )
    parser.add_argument(
        "--adapter-base-url",
        default="http://127.0.0.1:8010",
        help="Adapter base URL for smoke checks.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Adapter token for smoke checks.",
    )
    parser.add_argument(
        "--model",
        default=None,
        help="Optional model id for smoke checks.",
    )
    parser.add_argument(
        "--no-dry-run",
        action="store_true",
        help="Pass through to smoke script and disable metadata.dry_run.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=20.0,
        help="Per-request timeout for smoke checks.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])

    if not args.skip_unit:
        _run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_open_webui_adapter.py",
                "tests/test_open_webui_main.py",
                "tests/test_open_webui_positioning.py",
                "tests/test_agent_studio_frontend_contract_client.py",
            ]
        )

    if args.run_smoke:
        cmd = [
            sys.executable,
            "scripts/ci/open_webui_smoke.py",
            "--adapter-base-url",
            args.adapter_base_url,
            "--timeout",
            str(args.timeout),
        ]
        if args.api_key:
            cmd.extend(["--api-key", args.api_key])
        if args.model:
            cmd.extend(["--model", args.model])
        if args.no_dry_run:
            cmd.append("--no-dry-run")
        _run(cmd)

    print("OpenWebUI verification passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
