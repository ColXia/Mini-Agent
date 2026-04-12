"""CI guard: fail when deterministic gate artifact is missing or not PASS."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mini_agent.dev.deterministic_gate_artifact import (  # noqa: E402
    validate_deterministic_gate_artifact,
)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate deterministic gate artifact exists and is PASS.")
    parser.add_argument(
        "--artifact-pattern",
        default="workspace/release_gate/release_gate_deterministic_*.md",
        help="Glob pattern (relative to repo root) used to find deterministic gate artifacts.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    status = validate_deterministic_gate_artifact(
        repo_root=REPO_ROOT,
        pattern=args.artifact_pattern,
    )
    print(f"[artifact-check] pattern: {status.pattern}")
    print(f"[artifact-check] matched: {status.matched_count}")
    print(f"[artifact-check] latest: {status.latest_artifact or '-'}")
    print(f"[artifact-check] latest_pass: {status.latest_pass}")
    if status.ok:
        print("[artifact-check] result: PASS")
        return 0
    print("[artifact-check] result: FAIL")
    if status.matched_count == 0:
        print("[artifact-check] reason: deterministic gate artifact missing", file=sys.stderr)
    else:
        print("[artifact-check] reason: latest deterministic gate artifact is not PASS", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

