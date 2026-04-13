"""DesktopUI process bootstrap."""

from __future__ import annotations

import argparse
from pathlib import Path

from mini_agent.desktop.app import launch_desktop_ui


def run_desktop_from_cli(args: argparse.Namespace) -> int:
    """Bridge the shared CLI parser into the DesktopUI app bootstrap."""
    source_root = Path(__file__).resolve().parents[2]
    repo_root = source_root.parent
    workspace = Path(args.workspace).resolve() if getattr(args, "workspace", None) else repo_root
    return launch_desktop_ui(
        host=str(getattr(args, "host", "127.0.0.1")),
        port=int(getattr(args, "port", 8008)),
        workspace=workspace,
        approval_profile=getattr(args, "approval_profile", None),
        access_level=getattr(args, "access_level", None),
        startup_timeout=float(getattr(args, "startup_timeout", 20.0)),
        attach_only=bool(getattr(args, "attach_only", False)),
        source_root=source_root,
        repo_root=repo_root,
    )
