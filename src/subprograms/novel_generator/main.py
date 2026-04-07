"""Deprecated standalone entry point for novel-generator subprogram."""

from __future__ import annotations

import sys


def main() -> None:
    print(
        "Standalone novel-generator host is removed in hard-refactor mode.\n"
        "Run the unified backend host instead:\n"
        "  python -m uvicorn apps.agent_studio_gateway.main:app --host 127.0.0.1 --port 8008",
        file=sys.stderr,
    )
    raise SystemExit(2)


if __name__ == "__main__":
    main()
