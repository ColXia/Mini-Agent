#!/usr/bin/env python3
"""Run the stable local test subset used by refactor P2 baseline."""

from __future__ import annotations

from pathlib import Path
import subprocess
import sys


def main() -> int:
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        str(repo_root / "tests"),
        "-k",
        "not integration and not llm and not llm_clients",
    ]
    return subprocess.call(cmd, cwd=repo_root)


if __name__ == "__main__":
    raise SystemExit(main())
