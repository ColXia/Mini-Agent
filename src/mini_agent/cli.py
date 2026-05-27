"""Mini-Agent CLI - Unified entry point.

Usage:
    mini-agent                            # Unified terminal entry (auto mode)
    mini                                  # Unified terminal entry shortcut
    mini-agent --mode tui                 # Force full-screen TUI
    mini-agent --mode cli                 # Force line-based CLI
    mini-agent --prompt "hello"           # Headless single prompt
    mini-agent desktop                    # Start DesktopUI and attach/spawn local gateway
    mini-agent serve --port 8080          # Gateway API host mode (explicit)
    mini-agent stack up                   # Start gateway + active remote adapter stack and attach TUI
    mini qq                               # Shortcut: start gateway + QQ remote adapter + TUI
    mini qq status                        # Shortcut: check QQ runtime stack status
    mini qq down                          # Shortcut: stop QQ runtime stack

Subcommands:
    mini-agent serve              # Start gateway API host explicitly
    mini-agent desktop            # Start DesktopUI shell
    mini-agent stack up           # Start runtime stack (gateway + optional QQ remote adapter + TUI)
    mini-agent qq                 # Shortcut to boot gateway + QQ remote adapter + TUI
    mini-agent qq status          # Shortcut to inspect QQ runtime stack
    mini-agent qq down            # Shortcut to stop QQ runtime stack
    mini-agent stack down         # Stop runtime stack
    mini-agent stack status       # Check runtime stack status
    mini-agent stack logs         # Show runtime stack logs
    mini-agent list subprograms   # List available subprograms
    mini-agent list channels      # List available channels
"""

import argparse
import asyncio
from datetime import datetime, timezone
import json
import os
import sys
from pathlib import Path
from typing import Any

from .config_bootstrap import (
    load_entry_config,
    load_local_env_files,
    load_noninteractive_config,
)
from .utils.terminal_utils import supports_unicode_box_art


# ANSI color codes
class Colors:
    """Terminal color definitions."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"


def print_banner():
    """Print the Mini-Agent banner."""
    if supports_unicode_box_art():
        banner = f"""
{Colors.BRIGHT_CYAN}╔══════════════════════════════════════════════════════════╗
║  {Colors.BOLD}Mini-Agent{Colors.RESET}{Colors.BRIGHT_CYAN} - Intelligent Agent Platform              ║
║  Powered by MiniMax M2.5                                ║
╚══════════════════════════════════════════════════════════╝{Colors.RESET}
"""
        print(banner)
        return
    print("=" * 60)
    print("  Mini-Agent - Intelligent Agent Platform")
    print("  Powered by MiniMax M2.5")
    print("=" * 60)


def print_safe_text(text: str) -> None:
    """Print text with terminal-encoding fallback to avoid UnicodeEncodeError."""
    if text is None:
        print("")
        return
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    safe = str(text).encode(encoding, errors="replace").decode(encoding, errors="replace")
    print(safe)


def create_main_parser() -> argparse.ArgumentParser:
    """Create the main argument parser.

    Returns:
        ArgumentParser instance
    """
    parser = argparse.ArgumentParser(
        prog="mini-agent",
        description="Mini-Agent - Intelligent Agent Platform",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  mini-agent                        Start unified terminal mode (TTY -> TUI)
  mini                              Start unified terminal mode shortcut
  mini-agent --mode tui             Force full-screen TUI
  mini-agent --mode cli             Force line-based CLI
  mini-agent --prompt "hello"       Run one prompt in headless mode
  mini-agent --prompt "hello" --output-format json
                                    Run headless and emit JSON
  mini-agent desktop                Start DesktopUI shell
  mini-agent serve --port 8080      Start gateway API host on port 8080
  mini-agent stack up               Start gateway + active remote adapter and attach TUI
  mini qq                           Shortcut: start gateway + QQ remote adapter + TUI
  mini qq status                    Shortcut: check QQ runtime stack status
  mini qq down                      Shortcut: stop QQ runtime stack
  mini-agent cli --task "hello"     Execute one task via CLI mode
  mini-agent list subprograms       List available subprograms
        """,
    )

    # Global options
    parser.add_argument(
        "--version",
        "-v",
        action="version",
        version="mini-agent 0.2.0",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8008,
        help="Gateway API port (used by `mini-agent serve`, default: 8008)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Gateway API host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for gateway API host (used by `mini-agent serve`)",
    )
    parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory",
    )
    parser.add_argument(
        "--agent-mode",
        dest="approval_profile",
        type=str,
        choices=["plan", "build"],
        default=None,
        help="Execution mode override",
    )
    parser.add_argument(
        "--access-level",
        type=str,
        choices=["default", "full-access"],
        default=None,
        help="Access level override",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["auto", "tui", "cli", "headless"],
        default="auto",
        help="Unified terminal mode (default: auto)",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        type=str,
        default=None,
        help="Single-prompt input for headless mode",
    )
    parser.add_argument(
        "--output-format",
        type=str,
        choices=["text", "json", "stream-json"],
        default="text",
        help="Headless output format (default: text)",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Serve subcommand (explicit gateway API host entry)
    serve_parser = subparsers.add_parser(
        "serve",
        help="Start gateway API host (single backend)",
    )
    serve_parser.add_argument(
        "--port",
        type=int,
        default=8008,
        help="Gateway API port (default: 8008)",
    )
    serve_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Gateway API host (default: 127.0.0.1)",
    )
    serve_parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    serve_parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory",
    )
    serve_parser.add_argument(
        "--agent-mode",
        dest="approval_profile",
        type=str,
        choices=["plan", "build"],
        default=None,
        help="Execution mode override",
    )
    serve_parser.add_argument(
        "--access-level",
        type=str,
        choices=["default", "full-access"],
        default=None,
        help="Access level override",
    )

    # CLI subcommand
    cli_parser = subparsers.add_parser(
        "cli",
        help="Start in CLI mode (interactive terminal)",
    )
    cli_parser.add_argument(
        "--task",
        "-t",
        type=str,
        default=None,
        help="Execute a single task and exit",
    )
    cli_parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory",
    )
    cli_parser.add_argument(
        "--agent-mode",
        dest="approval_profile",
        type=str,
        choices=["plan", "build"],
        default=None,
        help="Execution mode override",
    )
    cli_parser.add_argument(
        "--access-level",
        type=str,
        choices=["default", "full-access"],
        default=None,
        help="Access level override",
    )

    # TUI subcommand
    tui_parser = subparsers.add_parser(
        "tui",
        help="Start in TUI mode (full-screen terminal UI)",
    )
    tui_parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory",
    )
    tui_parser.add_argument(
        "--agent-mode",
        dest="approval_profile",
        type=str,
        choices=["plan", "build"],
        default=None,
        help="Execution mode override",
    )
    tui_parser.add_argument(
        "--access-level",
        type=str,
        choices=["default", "full-access"],
        default=None,
        help="Access level override",
    )
    tui_parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Optional initial prompt text",
    )

    desktop_parser = subparsers.add_parser(
        "desktop",
        help="Start DesktopUI shell",
    )
    desktop_parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory",
    )
    desktop_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Gateway host to attach/start (default: 127.0.0.1)",
    )
    desktop_parser.add_argument(
        "--port",
        type=int,
        default=8008,
        help="Gateway port to attach/start (default: 8008)",
    )
    desktop_parser.add_argument(
        "--agent-mode",
        dest="approval_profile",
        type=str,
        choices=["plan", "build"],
        default=None,
        help="Execution mode override for a newly started local gateway",
    )
    desktop_parser.add_argument(
        "--access-level",
        type=str,
        choices=["default", "full-access"],
        default=None,
        help="Access level override for a newly started local gateway",
    )
    desktop_parser.add_argument(
        "--startup-timeout",
        type=float,
        default=20.0,
        help="Seconds to wait for a newly started local gateway (default: 20)",
    )
    desktop_parser.add_argument(
        "--attach-only",
        action="store_true",
        help="Only attach to an existing gateway; do not start one if absent",
    )

    # List subcommand
    list_parser = subparsers.add_parser(
        "list",
        help="List available modules",
    )
    list_parser.add_argument(
        "type",
        nargs="?",
        default="all",
        choices=["all", "subprograms", "channels"],
        help="What to list: all, subprograms, or channels",
    )

    audit_parser = subparsers.add_parser(
        "security-audit",
        help="Run runtime security risk audit",
    )
    audit_parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory for audit context",
    )
    audit_parser.add_argument(
        "--agent-mode",
        dest="approval_profile",
        type=str,
        choices=["plan", "build"],
        default=None,
        help="Execution mode override for audit evaluation",
    )
    audit_parser.add_argument(
        "--access-level",
        type=str,
        choices=["default", "full-access"],
        default=None,
        help="Access level override for audit evaluation",
    )

    doctor_parser = subparsers.add_parser(
        "doctor",
        help="Run environment, workspace, and MCP diagnostics",
    )
    doctor_parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory for diagnostics",
    )
    doctor_parser.add_argument(
        "--mcp-handshake",
        action="store_true",
        help="Run optional deep MCP handshake probes for discovered servers",
    )

    replay_parser = subparsers.add_parser(
        "replay-log",
        help="Replay structured run events from an .events.jsonl file",
    )
    replay_parser.add_argument(
        "--file",
        "-f",
        type=str,
        required=True,
        help="Path to event log file (*.events.jsonl)",
    )
    replay_parser.add_argument(
        "--payload",
        action="store_true",
        help="Include event payload when replaying",
    )
    replay_parser.add_argument(
        "--expected-schema-version",
        type=str,
        default=None,
        help="Optional expected event schema version (MAJOR.MINOR.PATCH)",
    )

    prune_parser = subparsers.add_parser(
        "prune-logs",
        help="Prune run logs using retention policy",
    )
    prune_parser.add_argument(
        "--max-runs",
        type=int,
        default=None,
        help="Override max runs to keep",
    )
    prune_parser.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        help="Override max age in days",
    )
    prune_parser.add_argument(
        "--max-total-mb",
        type=float,
        default=None,
        help="Override max total log size in MB",
    )

    migrate_parser = subparsers.add_parser(
        "migrate-event-logs",
        help="Backfill missing schema_version in legacy event logs",
    )
    migrate_parser.add_argument(
        "--path",
        type=str,
        default="~/.mini-agent/log",
        help="Event log root path (directory or file)",
    )
    migrate_parser.add_argument(
        "--no-recursive",
        action="store_true",
        help="Disable recursive scan when --path is a directory",
    )
    migrate_parser.add_argument(
        "--target-schema-version",
        type=str,
        default=None,
        help="Target schema version for missing fields (default: current logger schema version)",
    )
    migrate_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only scan and report; do not modify files",
    )
    migrate_parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Do not keep *.bak backup files when rewriting logs",
    )

    prune_export_parser = subparsers.add_parser(
        "prune-export-jobs",
        help="Prune persisted observability export jobs/artifacts",
    )
    prune_export_parser.add_argument(
        "--path",
        type=str,
        default=None,
        help="Observability log dir path (defaults to config observability.log_dir)",
    )
    prune_export_parser.add_argument(
        "--max-age-hours",
        type=int,
        default=None,
        help="Override export job retention age in hours (applies to completed/failed jobs)",
    )
    prune_export_parser.add_argument(
        "--max-jobs",
        type=int,
        default=None,
        help="Override max retained export jobs (completed/failed jobs)",
    )

    provider_parser = subparsers.add_parser(
        "provider",
        help="Manage LLM providers",
    )
    provider_parser.add_argument(
        "action",
        choices=[
            "list",
            "limits",
            "clear-limit",
            "probe",
            "add",
            "remove",
            "enable",
            "disable",
            "show",
            "set-role",
            "bindings",
            "bind-feature",
            "clear-binding",
        ],
        help="Provider action",
    )
    provider_parser.add_argument(
        "--id",
        type=str,
        default=None,
        help="Provider ID",
    )
    provider_parser.add_argument(
        "--name",
        type=str,
        default=None,
        help="Provider name",
    )
    provider_parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="API base URL",
    )
    provider_parser.add_argument(
        "--key",
        type=str,
        default=None,
        help="API key",
    )
    provider_parser.add_argument(
        "--type",
        type=str,
        choices=["openai", "anthropic"],
        default="openai",
        help="API protocol family",
    )
    provider_parser.add_argument(
        "--models",
        type=str,
        default=None,
        help="Comma-separated list of supported models",
    )
    provider_parser.add_argument(
        "--model-id",
        type=str,
        default=None,
        help="Default model id for this provider",
    )
    provider_parser.add_argument(
        "--model-name",
        type=str,
        default=None,
        help="Display name for --model-id",
    )
    provider_parser.add_argument(
        "--model-role",
        type=str,
        choices=["chat", "embedding", "ocr", "unclassified"],
        default=None,
        help="Logical role for --model-id / selected model",
    )
    provider_parser.add_argument(
        "--context-window",
        type=int,
        default=None,
        help="Context window for --model-id / selected model",
    )
    provider_parser.add_argument(
        "--learned-token-limit",
        type=int,
        default=None,
        help="Learned or known token limit for --model-id / selected model",
    )
    provider_parser.add_argument(
        "--supports-tools",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Record tool-calling support for --model-id / selected model",
    )
    provider_parser.add_argument(
        "--supports-thinking",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Record thinking/reasoning support for --model-id / selected model",
    )
    provider_parser.add_argument(
        "--auto-discover-models",
        action="store_true",
        help="Discover available models when model is not provided",
    )
    provider_parser.add_argument(
        "--selected-model-id",
        type=str,
        default=None,
        help="Model id selected from discovered models",
    )
    provider_parser.add_argument(
        "--priority",
        type=int,
        default=0,
        help="Provider priority (higher = preferred)",
    )
    provider_parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Provider request timeout in seconds",
    )
    provider_parser.add_argument(
        "--header",
        action="append",
        default=None,
        help="Custom request header in KEY=VALUE form; repeat to set multiple headers",
    )
    provider_parser.add_argument(
        "--catalog",
        type=str,
        default=None,
        help="Provider catalog JSON file path (default: ~/.mini-agent/providers.json)",
    )
    provider_parser.add_argument(
        "--source",
        type=str,
        choices=["custom", "preset"],
        default=None,
        help="Provider source for learned-limit actions",
    )
    provider_parser.add_argument(
        "--feature-role",
        type=str,
        choices=["embedding", "ocr"],
        default=None,
        help="Feature-model binding role for binding actions",
    )

    models_parser = subparsers.add_parser(
        "models",
        help="Discover available models from providers",
    )
    models_parser.add_argument(
        "provider",
        type=str,
        nargs="?",
        default=None,
        help="Provider name (openai, anthropic, minimax)",
    )
    models_parser.add_argument(
        "--api-key",
        type=str,
        default=None,
        help="API key (will use environment variable if not provided)",
    )
    models_parser.add_argument(
        "--api-base",
        type=str,
        default=None,
        help="Custom API base URL",
    )
    models_parser.add_argument(
        "--all",
        action="store_true",
        help="Show all models including deprecated and fine-tuned",
    )
    models_parser.add_argument(
        "--latest",
        action="store_true",
        help="Only show the latest base model ID",
    )
    models_parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List all preset providers and their status",
    )

    consolidate_parser = subparsers.add_parser(
        "consolidate-memory",
        help="Run bounded two-phase memory consolidation pipeline",
    )
    consolidate_parser.add_argument(
        "--session-store-dir",
        type=str,
        default=None,
        help="Session store directory (defaults to runtime session store path)",
    )
    consolidate_parser.add_argument(
        "--memory-file",
        type=str,
        default=None,
        help="Target MEMORY.md file path (defaults to discovered anchor)",
    )
    consolidate_parser.add_argument(
        "--phase",
        type=str,
        choices=["phase1", "phase2", "all"],
        default="all",
        help="Which phase to run",
    )
    consolidate_parser.add_argument(
        "--max-jobs",
        type=int,
        default=8,
        help="Max phase1 leased jobs per run",
    )
    consolidate_parser.add_argument(
        "--lease-seconds",
        type=int,
        default=3600,
        help="Phase1 lease duration in seconds",
    )
    consolidate_parser.add_argument(
        "--retry-seconds",
        type=int,
        default=3600,
        help="Phase1 failure backoff in seconds",
    )
    consolidate_parser.add_argument(
        "--top-n",
        type=int,
        default=40,
        help="Max consolidated memory items for phase2",
    )

    stack_parser = subparsers.add_parser(
        "stack",
        help="Manage runtime stack for TUI + Remote Interaction (QQ) workflows",
    )
    stack_parser.add_argument(
        "action",
        choices=["up", "down", "status", "logs"],
        help="Runtime stack action",
    )
    stack_parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory (default: repo root)",
    )
    stack_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Gateway host (default: 127.0.0.1)",
    )
    stack_parser.add_argument(
        "--port",
        type=int,
        default=8008,
        help="Gateway port (default: 8008)",
    )
    stack_parser.add_argument(
        "--qqbot",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable QQ bot startup (default: auto-enable when qqbot .env exists)",
    )
    stack_parser.add_argument(
        "--tui",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Attach TUI in the current terminal after background services start",
    )
    stack_parser.add_argument(
        "--tui-prompt",
        type=str,
        default=None,
        help="Optional initial TUI prompt for `stack up`",
    )
    stack_parser.add_argument(
        "--startup-timeout",
        type=float,
        default=20.0,
        help="Startup timeout in seconds for gateway readiness (default: 20)",
    )
    stack_parser.add_argument(
        "--agent-mode",
        dest="approval_profile",
        type=str,
        choices=["plan", "build"],
        default=None,
        help="Execution mode override",
    )
    stack_parser.add_argument(
        "--access-level",
        type=str,
        choices=["default", "full-access"],
        default=None,
        help="Access level override",
    )
    stack_parser.add_argument(
        "--force",
        action="store_true",
        help="Force terminate lingering processes on `stack down`",
    )
    stack_parser.add_argument(
        "--target",
        type=str,
        choices=["all", "gateway", "qqbot"],
        default="all",
        help="Log target for `stack logs`",
    )
    stack_parser.add_argument(
        "--lines",
        type=int,
        default=120,
        help="Tail lines for `stack logs` (default: 120)",
    )

    qq_parser = subparsers.add_parser(
        "qq",
        help="Shortcut: start gateway + QQ remote adapter + TUI",
    )
    qq_parser.add_argument(
        "action",
        nargs="?",
        choices=["up", "down", "status", "logs"],
        default="up",
        help="QQ remote runtime shortcut action (default: up)",
    )
    qq_parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory (default: repo root)",
    )
    qq_parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Gateway host (default: 127.0.0.1)",
    )
    qq_parser.add_argument(
        "--port",
        type=int,
        default=8008,
        help="Gateway port (default: 8008)",
    )
    qq_parser.add_argument(
        "--startup-timeout",
        type=float,
        default=20.0,
        help="Startup timeout in seconds for gateway readiness (default: 20)",
    )
    qq_parser.add_argument(
        "--agent-mode",
        dest="approval_profile",
        type=str,
        choices=["plan", "build"],
        default=None,
        help="Execution mode override",
    )
    qq_parser.add_argument(
        "--access-level",
        type=str,
        choices=["default", "full-access"],
        default=None,
        help="Access level override",
    )
    qq_parser.add_argument(
        "--tui",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Attach TUI for `qq up` (default: enabled)",
    )
    qq_parser.add_argument(
        "--prompt",
        type=str,
        default=None,
        help="Optional initial TUI prompt",
    )
    qq_parser.add_argument(
        "--force",
        action="store_true",
        help="Force terminate lingering processes on `qq down`",
    )
    qq_parser.add_argument(
        "--target",
        type=str,
        choices=["all", "gateway", "qqbot"],
        default="all",
        help="Log target for `qq logs`",
    )
    qq_parser.add_argument(
        "--lines",
        type=int,
        default=120,
        help="Tail lines for `qq logs` (default: 120)",
    )

    return parser


def _apply_runtime_policy_overrides(args: argparse.Namespace) -> None:
    approval_profile = getattr(args, "approval_profile", None)
    access_level = getattr(args, "access_level", None)
    if approval_profile:
        os.environ["MINI_AGENT_APPROVAL_PROFILE"] = approval_profile
        os.environ["MINI_AGENT_AGENT_MODE"] = approval_profile
    if access_level:
        os.environ["MINI_AGENT_ACCESS_LEVEL"] = access_level


def run_gateway_mode(args: argparse.Namespace) -> None:
    """Run in Studio API mode (single backend host)."""
    import atexit

    import uvicorn

    from .ops.doctor import format_doctor_report, run_startup_self_check
    from .utils.single_instance import SingleInstanceManager

    _apply_runtime_policy_overrides(args)

    # Enforce single backend-host instance.
    instance_manager = SingleInstanceManager()
    is_first, existing_pid = instance_manager.check_and_lock()
    if not is_first:
        print(
            f"{Colors.RED}Error: Another Mini-Agent instance is already running{Colors.RESET}"
        )
        print(f"  PID: {existing_pid}")
        print(f"  Lock file: {instance_manager.pid_file}")
        sys.exit(1)
    atexit.register(instance_manager.release_lock)

    config = _load_cli_entry_config_or_report()
    if config is None:
        return

    workspace = (
        Path(args.workspace).resolve()
        if args.workspace
        else Path(config.agent.workspace_dir).resolve()
    )
    is_ready, findings = run_startup_self_check(config=config, workspace=workspace)
    print(format_doctor_report(findings, title="Startup Self-Check"))
    if not is_ready:
        print(
            f"{Colors.RED}[X] Startup self-check failed. Fix blocking issues before launching Studio API host.{Colors.RESET}"
        )
        return

    os.environ["MINI_AGENT_STUDIO_HOST"] = args.host
    os.environ["MINI_AGENT_STUDIO_PORT"] = str(args.port)
    os.environ["MINI_AGENT_STUDIO_ENABLE_INSTANCE_LOCK"] = "1"
    os.environ["MINI_AGENT_RUNTIME_MODE"] = "single_main"
    os.environ["MINI_AGENT_MAIN_WORKSPACE"] = str(workspace)

    print_banner()
    print(f"{Colors.CYAN}Starting Studio API host...{Colors.RESET}")
    print(f"  host: {args.host}")
    print(f"  port: {args.port}")
    print(f"  workspace: {workspace}")
    print("  runtime_mode: single_main")
    if args.reload:
        print(f"  reload: {Colors.YELLOW}enabled{Colors.RESET}")

    try:
        uvicorn.run(
            "apps.agent_studio_gateway.main:app",
            host=args.host,
            port=args.port,
            reload=bool(args.reload),
        )
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}Received interrupt signal...{Colors.RESET}")


def run_cli_mode(args: argparse.Namespace) -> None:
    """Run in CLI mode.

    Args:
        args: Parsed arguments
    """
    from .cli_interactive import run_interactive_session

    _apply_runtime_policy_overrides(args)
    print_banner()

    # Determine workspace
    workspace = Path(args.workspace) if args.workspace else Path.cwd()
    workspace.mkdir(parents=True, exist_ok=True)

    # Run interactive or single task
    task = getattr(args, "task", None)
    asyncio.run(
        run_interactive_session(
            workspace=workspace,
            task=task,
            approval_profile=getattr(args, "approval_profile", None),
        )
    )


def run_tui_mode(args: argparse.Namespace) -> None:
    """Run in full-screen TUI mode."""
    from .tui.app import run_tui

    _apply_runtime_policy_overrides(args)
    workspace = Path(args.workspace) if args.workspace else Path.cwd()
    workspace.mkdir(parents=True, exist_ok=True)

    asyncio.run(
        run_tui(
            workspace=workspace,
            approval_profile=getattr(args, "approval_profile", None),
            access_level=getattr(args, "access_level", None),
            initial_prompt=getattr(args, "prompt", None),
            config_loader=load_noninteractive_config,
        )
    )


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _read_non_tty_prompt() -> str | None:
    if sys.stdin.isatty():
        return None
    data = sys.stdin.read()
    text = str(data or "").strip()
    return text or None


def _load_cli_entry_config_or_report(*, report_errors: bool = True) -> Any | None:
    """Load config for CLI-owned command surfaces without moving ownership below the entry."""

    try:
        return load_entry_config()
    except Exception as exc:
        if report_errors:
            print(f"{Colors.RED}[X] Failed to load configuration: {exc}{Colors.RESET}")
        return None


async def _run_headless_prompt_async(
    *,
    workspace: Path,
    prompt: str,
    approval_profile: str | None,
    config,
) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    from .agent_core.engine import TurnStopReason
    from .cli_interactive import (
        build_agent,
        create_submission_loop_for_agent,
        run_prompt_via_submission_loop,
    )
    from .tools.mcp_loader import cleanup_mcp_connections

    agent = await build_agent(
        workspace,
        approval_profile=approval_profile,
        config=config,
    )
    agent.console_output = False
    submission_loop = None
    loop_bus = None
    try:
        submission_loop, loop_bus = await create_submission_loop_for_agent(
            agent=agent,
            session_id="headless-session",
        )
        payload = await run_prompt_via_submission_loop(
            loop=submission_loop,
            bus=loop_bus,
            agent=agent,
            prompt=prompt,
            metadata={"surface": "headless", "mode": "single_prompt"},
            start_new_run=True,
            approval_resolver=lambda _payload: False,
        )
        state = str(payload.get("state", "") or "").strip().lower()
        stop_reason = str(payload.get("stop_reason", "") or "").strip().lower()
        message = str(payload.get("message", "") or "").strip()
        error = str(payload.get("error", "") or "").strip()

        if not (state == "completed" and stop_reason in {"end_turn", ""}):
            if state == "interrupted" or stop_reason == TurnStopReason.CANCELLED.value:
                raise RuntimeError(message or "Task cancelled by user.")
            if stop_reason == TurnStopReason.MAX_TURN_REQUESTS.value:
                raise RuntimeError(message or "Turn reached max request limit.")
            raise RuntimeError(message or error or "Turn failed.")

        model_id = ""
        llm_client = getattr(agent, "llm_client", None)
        if llm_client is not None:
            model_id = str(getattr(llm_client, "model", "") or "")
        if not model_id:
            llm_obj = getattr(agent, "llm", None)
            model_id = str(getattr(llm_obj, "model", "") or "")
        model_id = model_id or "unknown"
        prepared_context = payload.get("prepared_context")
        if not isinstance(prepared_context, dict):
            prepared_context = {}
        prepared_context_diagnostics = payload.get("prepared_context_diagnostics")
        if not isinstance(prepared_context_diagnostics, dict):
            prepared_context_diagnostics = {}
        return message, model_id, prepared_context, prepared_context_diagnostics
    finally:
        if submission_loop is not None:
            await submission_loop.stop()
        await cleanup_mcp_connections()


def run_headless_mode(args: argparse.Namespace) -> None:
    """Run one-shot headless prompt mode (for scripts/CI)."""

    _apply_runtime_policy_overrides(args)
    prompt = str(getattr(args, "prompt", "") or "").strip()
    if not prompt:
        print(f"{Colors.RED}Error: --prompt is required in headless mode.{Colors.RESET}")
        raise SystemExit(1)

    workspace = Path(args.workspace) if args.workspace else Path.cwd()
    workspace.mkdir(parents=True, exist_ok=True)

    try:
        config = load_entry_config()
        reply, model_id, prepared_context, prepared_context_diagnostics = asyncio.run(
            _run_headless_prompt_async(
                workspace=workspace,
                prompt=prompt,
                approval_profile=getattr(args, "approval_profile", None),
                config=config,
            )
        )
    except Exception as exc:
        output_format = getattr(args, "output_format", "text")
        if output_format == "json":
            print_safe_text(
                json.dumps(
                    {
                        "ok": False,
                        "type": "error",
                        "error": str(exc),
                        "timestamp": _utc_now_iso(),
                    },
                    ensure_ascii=False,
                )
            )
        elif output_format == "stream-json":
            print_safe_text(
                json.dumps(
                    {
                        "type": "error",
                        "ok": False,
                        "error": str(exc),
                        "timestamp": _utc_now_iso(),
                    },
                    ensure_ascii=False,
                )
            )
        else:
            print(f"{Colors.RED}Error: {exc}{Colors.RESET}")
        raise SystemExit(1) from exc

    output_format = getattr(args, "output_format", "text")
    if output_format == "json":
        print_safe_text(
            json.dumps(
                {
                    "ok": True,
                    "type": "result",
                    "model": model_id,
                    "output": reply,
                    "prepared_context": prepared_context,
                    "prepared_context_diagnostics": prepared_context_diagnostics,
                    "timestamp": _utc_now_iso(),
                },
                ensure_ascii=False,
            )
        )
        return

    if output_format == "stream-json":
        print_safe_text(
            json.dumps(
                {"type": "start", "ok": True, "timestamp": _utc_now_iso()},
                ensure_ascii=False,
            )
        )
        print_safe_text(
            json.dumps(
                {
                    "type": "assistant",
                    "ok": True,
                    "model": model_id,
                    "content": reply,
                    "prepared_context": prepared_context,
                    "prepared_context_diagnostics": prepared_context_diagnostics,
                    "timestamp": _utc_now_iso(),
                },
                ensure_ascii=False,
            )
        )
        print_safe_text(
            json.dumps(
                {"type": "end", "ok": True, "timestamp": _utc_now_iso()},
                ensure_ascii=False,
            )
        )
        return

    print_safe_text(reply)


def run_unified_terminal_mode(args: argparse.Namespace) -> None:
    """Single entry mode inspired by opencode/codex/gemini-cli."""
    mode = str(getattr(args, "mode", "auto") or "auto").strip().lower()
    prompt = str(getattr(args, "prompt", "") or "").strip()

    if mode == "tui":
        run_tui_mode(args)
        return

    if mode == "cli":
        cli_args = argparse.Namespace(**vars(args))
        if not getattr(cli_args, "task", None) and prompt:
            cli_args.task = prompt
        run_cli_mode(cli_args)
        return

    if mode == "headless":
        run_headless_mode(args)
        return

    # auto mode:
    if prompt:
        print(f"{Colors.DIM}[Info] Running in headless mode with your prompt...{Colors.RESET}")
        run_headless_mode(args)
        return

    piped_prompt = _read_non_tty_prompt()
    if piped_prompt:
        print(f"{Colors.DIM}[Info] Running in headless mode (piped input)...{Colors.RESET}")
        auto_args = argparse.Namespace(**vars(args))
        auto_args.prompt = piped_prompt
        run_headless_mode(auto_args)
        return

    if sys.stdin.isatty() and sys.stdout.isatty():
        print(f"{Colors.DIM}[Info] Starting TUI (full-screen terminal). Press Ctrl+C to exit.{Colors.RESET}")
        run_tui_mode(args)
        return

    print(
        f"{Colors.RED}Error: no interactive TTY detected. Use --prompt for headless mode.{Colors.RESET}"
    )
    raise SystemExit(1)


def _is_serve_intent(args: argparse.Namespace) -> bool:
    if getattr(args, "command", None) == "serve":
        return True
    return bool(args.reload) or str(args.host) != "127.0.0.1" or int(args.port) != 8008


def run_security_audit_command(args: argparse.Namespace) -> None:
    """Run security audit command."""
    from .security.audit import format_security_audit_report, run_security_audit

    config = _load_cli_entry_config_or_report()
    if config is None:
        return

    if args.approval_profile:
        config.security.approval_profile = args.approval_profile
    if getattr(args, "access_level", None):
        config.security.access_level = args.access_level

    workspace = (
        Path(args.workspace).resolve()
        if args.workspace
        else Path(config.agent.workspace_dir).resolve()
    )
    findings = run_security_audit(config, workspace=workspace)
    report = format_security_audit_report(findings)
    print(report)


def run_doctor_command(args: argparse.Namespace) -> None:
    """Run operational diagnostics command."""
    from .ops.doctor import format_doctor_report, run_doctor

    config = _load_cli_entry_config_or_report()
    if config is None:
        return

    workspace = (
        Path(args.workspace).resolve()
        if args.workspace
        else Path(config.agent.workspace_dir).resolve()
    )
    findings = run_doctor(
        config=config, workspace=workspace, deep_mcp_probe=bool(args.mcp_handshake)
    )
    print(format_doctor_report(findings))


def run_replay_log_command(args: argparse.Namespace) -> None:
    """Replay structured run event logs."""
    from .logger import AgentLogger

    try:
        events = AgentLogger.read_events(args.file)
    except Exception as exc:
        print(f"{Colors.RED}[X] Failed to load event log: {exc}{Colors.RESET}")
        return
    try:
        schema = AgentLogger.check_event_schema_compatibility(
            events,
            expected_version=args.expected_schema_version,
        )
    except ValueError as exc:
        print(f"{Colors.RED}[X] {exc}{Colors.RESET}")
        return
    if args.expected_schema_version and not schema.get("compatible", False):
        print(f"{Colors.RED}[X] Schema compatibility check failed.{Colors.RESET}")
        print(schema.get("reason"))
        return
    print(AgentLogger.format_replay(events, include_payload=args.payload))


def run_prune_logs_command(args: argparse.Namespace) -> None:
    """Prune run logs with configured or override retention policy."""
    from .logger import AgentLogger, EventLogRetentionPolicy

    config = _load_cli_entry_config_or_report()
    if config is None:
        return

    base = config.observability
    policy = EventLogRetentionPolicy(
        enabled=True,
        prune_on_start=True,
        max_runs=args.max_runs
        if args.max_runs is not None
        else base.event_log_max_runs,
        max_age_days=args.max_age_days
        if args.max_age_days is not None
        else base.event_log_max_age_days,
        max_total_size_mb=args.max_total_mb
        if args.max_total_mb is not None
        else base.event_log_max_total_mb,
    ).normalized()
    logger = AgentLogger(
        log_dir=Path(base.log_dir).expanduser(), retention_policy=policy
    )
    summary = logger.prune_logs()

    print("Run Log Prune Report")
    print("====================")
    print(f"removed_runs: {summary['removed_runs']}")
    print(f"removed_files: {summary['removed_files']}")
    print(f"freed_bytes: {summary['freed_bytes']}")
    print(f"remaining_runs: {summary['remaining_runs']}")
    print(f"remaining_bytes: {summary['remaining_bytes']}")


def run_migrate_event_logs_command(args: argparse.Namespace) -> None:
    """Migrate legacy event logs by backfilling missing schema_version fields."""
    from .logger import AgentLogger, EVENT_SCHEMA_VERSION

    target_version = args.target_schema_version or EVENT_SCHEMA_VERSION
    files = AgentLogger.list_event_log_files(args.path, recursive=not args.no_recursive)
    if not files:
        print("No event log files found for migration.")
        return

    migrated_files = 0
    changed_files = 0
    total_events = 0
    migrated_events = 0
    failures: list[str] = []

    for file_path in files:
        try:
            result = AgentLogger.migrate_event_schema_file(
                file_path,
                target_version=target_version,
                backup=not args.no_backup,
                dry_run=bool(args.dry_run),
            )
        except Exception as exc:
            failures.append(f"{file_path}: {exc}")
            continue

        migrated_files += 1
        total_events += int(result["total_events"])
        migrated_events += int(result["migrated_events"])
        if result.get("changed"):
            changed_files += 1

    mode = "DRY-RUN" if args.dry_run else "APPLY"
    print("Event Schema Migration Report")
    print("============================")
    print(f"mode: {mode}")
    print(f"path: {args.path}")
    print(f"target_schema_version: {target_version}")
    print(f"files_found: {len(files)}")
    print(f"files_processed: {migrated_files}")
    print(f"files_changed: {changed_files}")
    print(f"total_events: {total_events}")
    print(f"migrated_events: {migrated_events}")
    if failures:
        print(f"failures: {len(failures)}")
        for failure in failures:
            print(f" - {failure}")
    else:
        print("failures: 0")


def run_prune_export_jobs_command(args: argparse.Namespace) -> None:
    """Prune persisted observability export jobs and artifacts."""
    from .ops.observability_exports import prune_observability_export_jobs

    log_dir = args.path
    if not log_dir:
        config = _load_cli_entry_config_or_report(report_errors=False)
        if config is not None:
            log_dir = config.observability.log_dir
        else:
            log_dir = "~/.mini-agent/log"

    ttl_seconds = None
    if args.max_age_hours is not None:
        ttl_seconds = max(0, int(args.max_age_hours)) * 3600
    max_jobs = max(0, int(args.max_jobs)) if args.max_jobs is not None else None

    summary = prune_observability_export_jobs(
        log_dir=log_dir,
        ttl_seconds=ttl_seconds,
        max_jobs=max_jobs,
    )

    print("Export Job Prune Report")
    print("=======================")
    print(f"log_dir: {Path(log_dir).expanduser().resolve()}")
    print(f"removed_jobs: {summary.get('removed_jobs', 0)}")
    print(f"removed_metadata_files: {summary.get('removed_metadata_files', 0)}")
    print(f"removed_artifact_files: {summary.get('removed_artifact_files', 0)}")
    print(f"remaining_jobs: {summary.get('remaining_jobs', 0)}")


def run_consolidate_memory_command(args: argparse.Namespace) -> None:
    """Run two-phase memory consolidation pipeline."""
    from mini_agent.memory.consolidation import MemoryConsolidationPipeline

    pipeline = MemoryConsolidationPipeline(
        session_store_dir=args.session_store_dir,
        memory_file=args.memory_file,
    )
    summary = pipeline.run(
        phase=args.phase,
        max_jobs=max(1, int(args.max_jobs)),
        lease_seconds=max(1, int(args.lease_seconds)),
        retry_seconds=max(1, int(args.retry_seconds)),
        top_n=max(1, int(args.top_n)),
    )

    print("Memory Consolidation Report")
    print("===========================")
    print(f"phase: {summary.get('phase')}")
    print(f"session_store_dir: {summary.get('base_dir')}")
    print(f"memory_file: {summary.get('memory_file')}")

    phase1 = summary.get("phase1")
    if isinstance(phase1, dict):
        print("phase1:")
        print(f"  leased: {phase1.get('leased', 0)}")
        print(f"  processed: {phase1.get('processed', 0)}")
        print(f"  failed: {phase1.get('failed', 0)}")
        print(f"  artifact_ids: {len(phase1.get('artifact_ids', []))}")
        errors = phase1.get("errors", [])
        if isinstance(errors, list) and errors:
            print(f"  errors: {len(errors)}")
            for item in errors[:5]:
                print(f"    - {item}")

    phase2 = summary.get("phase2")
    if isinstance(phase2, dict):
        print("phase2:")
        print(f"  processed_artifacts: {phase2.get('processed_artifacts', 0)}")
        print(f"  added: {len(phase2.get('added', []))}")
        print(f"  retained: {len(phase2.get('retained', []))}")
        print(f"  removed: {len(phase2.get('removed', []))}")
        print(f"  output_items: {len(phase2.get('output_items', []))}")
        print(f"  watermark_size: {phase2.get('watermark_size', 0)}")

    job_stats = summary.get("job_stats")
    if isinstance(job_stats, dict):
        print("job_stats:")
        for key in ("pending", "leased", "retry", "done"):
            print(f"  {key}: {job_stats.get(key, 0)}")


def run_models_command(args: argparse.Namespace) -> None:
    """Discover available models from providers."""
    import asyncio
    import os

    load_local_env_files()

    from mini_agent.model_manager.preset_providers import (
        PresetProvider,
        get_preset_provider_config,
        list_preset_providers,
    )
    from mini_agent.model_manager.model_discovery import (
        list_available_models,
        get_latest_model_id,
    )

    # List preset providers
    if args.list_presets:
        print(f"{Colors.CYAN}Preset Providers:{Colors.RESET}\n")
        presets = list_preset_providers()

        for preset in presets:
            status = (
                f"{Colors.GREEN}[configured]{Colors.RESET}"
                if preset["is_configured"]
                else f"{Colors.DIM}[not configured]{Colors.RESET}"
            )
            print(
                f"  {Colors.BOLD}{preset['name']}{Colors.RESET} ({preset['provider']}) {status}"
            )
            print(f"    Environment: {preset['env_key']}")
            print(f"    API Base: {preset['api_base']}")
            print(f"    Default Model: {preset['default_model']}")
            print(f"    Description: {preset['description']}")
            print()

        return

    # Require provider argument
    if not args.provider:
        print(f"{Colors.RED}Error: provider argument is required{Colors.RESET}")
        print("Usage: mini-agent models <provider>")
        print("Providers: openai, anthropic, minimax, ollama")
        print("\nTo list preset providers: mini-agent models --list-presets")
        return

    provider = args.provider.lower()
    active_provider_names = {"openai", "anthropic", "minimax", "ollama"}
    ollama_enabled = (
        str(os.getenv("MINI_AGENT_OLLAMA_ENABLED") or os.getenv("MINI_AGENT_ENABLE_OLLAMA") or "")
        .strip()
        .lower()
        in {"1", "true", "yes", "on"}
    )
    ollama_host = (
        str(os.getenv("OLLAMA_HOST") or os.getenv("MINI_AGENT_OLLAMA_BASE_URL") or "").strip()
        or "http://localhost:11434"
    )

    # Validate provider
    if provider not in active_provider_names:
        print(f"{Colors.RED}Unknown provider: {provider}{Colors.RESET}")
        print(f"Supported providers: {', '.join(sorted(active_provider_names))}")
        return

    # Get API key
    api_key = args.api_key
    if not api_key:
        # Try environment variables
        env_key_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "minimax": "MINIMAX_API_KEY",
        }
        env_key = env_key_map.get(provider)
        if env_key:
            api_key = os.getenv(env_key)
        elif provider == "ollama":
            preset = get_preset_provider_config(
                PresetProvider.OLLAMA,
                use_latest_model=False,
            )
            if preset:
                api_key = str(preset["api_key"])
                if not args.api_base:
                    args.api_base = str(preset["api_base"])

        if not api_key:
            print(f"{Colors.RED}Error: No API key provided.{Colors.RESET}")
            if provider == "ollama":
                if ollama_enabled:
                    print(
                        "Ollama is enabled, but the local daemon is not reachable "
                        f"or no models were discovered at {ollama_host}"
                    )
                else:
                    print("Enable local Ollama with MINI_AGENT_OLLAMA_ENABLED=1")
                print("Optional host override: OLLAMA_HOST=http://localhost:11434")
            else:
                print(f"Set {env_key} environment variable or use --api-key")
            return

    try:
        if args.latest:
            # Only show latest model ID
            model_id = asyncio.run(
                get_latest_model_id(provider, api_key, args.api_base)
            )
            if model_id:
                print(model_id)
            else:
                print(f"{Colors.RED}No models found for {provider}{Colors.RESET}")
        else:
            # List all models
            asyncio.run(
                list_available_models(
                    provider, api_key, args.api_base, show_all=args.all
                )
            )
    except Exception as e:
        print(f"{Colors.RED}Error: {e}{Colors.RESET}")


def run_provider_command(args: argparse.Namespace) -> None:
    """Manage LLM providers."""
    import json
    from pathlib import Path
    from fastapi import HTTPException
    from mini_agent.application.use_cases.operations_provider_use_cases import ProviderOperationsUseCases
    from mini_agent.interfaces.ops import (
        StudioModelCapabilityProbeRequest,
        StudioProviderModelDiscoveryRequest,
        StudioProviderUpsertRequest,
    )
    from mini_agent.model_manager.provider import normalize_provider_catalog
    from mini_agent.model_manager.model_registry_service import ModelRegistryService

    def _resolve_provider_source(
        service: ModelRegistryService,
        *,
        provider_id: str | None,
        model_id: str | None = None,
        explicit_source: str | None = None,
    ) -> str | None:
        if explicit_source:
            return explicit_source
        if not provider_id:
            return None
        registry_matches = [
            item
            for item in service.list_registry()
            if str(item.get("provider_id") or "") == str(provider_id)
        ]
        if model_id:
            registry_matches = [
                item
                for item in registry_matches
                if any(
                    str(model.get("model_id") or "") == str(model_id)
                    for model in item.get("models", [])
                    if isinstance(model, dict)
                )
            ]
        unique_sources = sorted(
            {
                str(item.get("source") or "")
                for item in registry_matches
                if item.get("source")
            }
        )
        return unique_sources[0] if len(unique_sources) == 1 else None

    catalog_path = None
    if args.catalog:
        catalog_path = Path(args.catalog).expanduser().resolve()
    else:
        catalog_path = Path.home() / ".mini-agent" / "providers.json"

    if args.action == "list":
        if not catalog_path.exists():
            print(
                f"{Colors.YELLOW}No provider catalog found at {catalog_path}{Colors.RESET}"
            )
            print("Use 'mini-agent provider add' to add a provider.")
            return

        try:
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
            catalog = normalize_provider_catalog(payload)
        except Exception as e:
            print(f"{Colors.RED}Failed to load provider catalog: {e}{Colors.RESET}")
            return

        if not catalog.providers:
            print(f"{Colors.DIM}No providers configured.{Colors.RESET}")
            return

        print(f"{Colors.CYAN}Configured Providers:{Colors.RESET}\n")
        for provider in catalog.providers:
            status = (
                f"{Colors.GREEN}[enabled]{Colors.RESET}"
                if provider.enabled
                else f"{Colors.DIM}[disabled]{Colors.RESET}"
            )
            print(f"  {Colors.BOLD}{provider.name}{Colors.RESET} ({provider.id})")
            print(f"    type: {provider.api_type.value}")
            print(f"    url: {provider.api_base}")
            print(f"    models: {', '.join(provider.models)}")
            print(f"    priority: {provider.priority}")
            print(f"    status: {status}")
            print()

    elif args.action == "limits":
        service = ModelRegistryService(catalog_path=catalog_path)
        rows = service.list_learned_token_limits(
            source=args.source,
            provider_id=args.id,
            model_id=args.model_id,
        )
        if not rows:
            print(f"{Colors.DIM}No learned token limits found.{Colors.RESET}")
            return

        print(f"{Colors.CYAN}Learned Token Limits:{Colors.RESET}\n")
        for row in rows:
            learned = int(row.get("learned_token_limit") or 0)
            context_window = row.get("context_window")
            default_suffix = " | default" if row.get("is_default") else ""
            print(
                f"  [{row['source']}] {row['provider_id']}/{row['model_id']}{default_suffix}"
            )
            print(f"    learned: {learned:,}")
            print(
                f"    context: {int(context_window):,}"
                if isinstance(context_window, int) and context_window > 0
                else "    context: --"
            )
            print(f"    display: {row.get('display_name') or row['model_id']}")
            print()

    elif args.action == "clear-limit":
        if not args.id:
            print(
                f"{Colors.RED}Error: --id is required for clear-limit action.{Colors.RESET}"
            )
            return

        service = ModelRegistryService(catalog_path=catalog_path)
        source = args.source
        if not source:
            matches = service.list_learned_token_limits(
                provider_id=args.id,
                model_id=args.model_id,
            )
            unique_sources = sorted({str(item.get("source") or "") for item in matches if item.get("source")})
            if len(unique_sources) == 1:
                source = unique_sources[0]
            elif len(unique_sources) > 1:
                joined = ", ".join(unique_sources)
                print(
                    f"{Colors.RED}Error: multiple sources match {args.id}. Use --source <custom|preset>. "
                    f"Matches: {joined}{Colors.RESET}"
                )
                return
            else:
                registry_matches = [
                    item
                    for item in service.list_registry()
                    if str(item.get("provider_id") or "") == str(args.id)
                ]
                unique_sources = sorted({str(item.get("source") or "") for item in registry_matches if item.get("source")})
                if len(unique_sources) == 1:
                    source = unique_sources[0]
                elif len(unique_sources) > 1:
                    joined = ", ".join(unique_sources)
                    print(
                        f"{Colors.RED}Error: multiple providers match {args.id}. Use --source <custom|preset>. "
                        f"Matches: {joined}{Colors.RESET}"
                    )
                    return

        if not source:
            print(
                f"{Colors.RED}Error: provider source could not be resolved. Use --source <custom|preset>.{Colors.RESET}"
            )
            return

        try:
            result = service.clear_learned_token_limit(
                source=source,
                provider_id=args.id,
                model_id=args.model_id,
            )
        except Exception as e:
            print(f"{Colors.RED}Failed to clear learned token limit: {e}{Colors.RESET}")
            return

        removed_models = list(result.get("removed_models") or [])
        removed_count = int(result.get("removed_count") or 0)
        if args.model_id:
            if removed_count > 0:
                print(
                    f"{Colors.GREEN}Cleared learned token limit for {args.id}/{args.model_id}.{Colors.RESET}"
                )
            else:
                print(
                    f"{Colors.YELLOW}No learned token limit was set for {args.id}/{args.model_id}.{Colors.RESET}"
                )
        else:
            if removed_count > 0:
                print(
                    f"{Colors.GREEN}Cleared {removed_count} learned token limit(s) for provider '{args.id}'.{Colors.RESET}"
                )
                print(f"  models: {', '.join(removed_models)}")
            else:
                print(
                    f"{Colors.YELLOW}Provider '{args.id}' has no learned token limits to clear.{Colors.RESET}"
                )

    elif args.action == "probe":
        if not args.id or not args.model_id:
            print(
                f"{Colors.RED}Error: --id and --model-id are required for probe action.{Colors.RESET}"
            )
            return
        service = ModelRegistryService(catalog_path=catalog_path)
        source = _resolve_provider_source(
            service,
            provider_id=args.id,
            model_id=args.model_id,
            explicit_source=args.source,
        )
        if not source:
            print(
                f"{Colors.RED}Error: provider source could not be resolved. Use --source <custom|preset>.{Colors.RESET}"
            )
            return
        use_cases = ProviderOperationsUseCases(
            repo_root=Path.cwd().resolve(),
            workspace_root=catalog_path.parent.resolve(),
        )
        try:
            result = use_cases.probe_model_capabilities(
                payload=StudioModelCapabilityProbeRequest(
                    source=source,
                    provider_id=args.id,
                    model_id=args.model_id,
                ),
                catalog_path=str(catalog_path),
            )
        except HTTPException as exc:
            print(f"{Colors.RED}Failed to probe model capabilities: {exc.detail}{Colors.RESET}")
            return
        except Exception as exc:
            print(f"{Colors.RED}Failed to probe model capabilities: {exc}{Colors.RESET}")
            return

        print(f"{Colors.CYAN}Model Capability Probe:{Colors.RESET}\n")
        print(f"  source: {result.source}")
        print(f"  provider: {result.provider_id}")
        print(f"  model: {result.model.model_id}")
        print(f"  context_window: {result.model.context_window or '--'}")
        print(
            "  supports_tools: "
            f"{result.model.supports_tools_truth or '--'}"
            f" ({result.model.supports_tools_confidence or '--'}, {result.model.supports_tools_source or '--'})"
        )
        print(
            "  supports_thinking: "
            f"{result.model.supports_thinking_truth or '--'}"
            f" ({result.model.supports_thinking_confidence or '--'}, {result.model.supports_thinking_source or '--'})"
        )
        if result.updated_fields:
            print(f"  updated_fields: {', '.join(result.updated_fields)}")
        else:
            print("  updated_fields: none")
        if result.notes:
            print("  notes:")
            for note in result.notes:
                print(f"    - {note}")

    elif args.action == "set-role":
        if not args.id or not args.model_id or not args.model_role:
            print(
                f"{Colors.RED}Error: --id, --model-id, and --model-role are required for set-role action.{Colors.RESET}"
            )
            return
        service = ModelRegistryService(catalog_path=catalog_path)
        source = _resolve_provider_source(
            service,
            provider_id=args.id,
            model_id=args.model_id,
            explicit_source=args.source,
        )
        if not source:
            print(
                f"{Colors.RED}Error: provider source could not be resolved. Use --source <custom|preset>.{Colors.RESET}"
            )
            return
        try:
            result = service.set_model_role(
                source=source,
                provider_id=args.id,
                model_id=args.model_id,
                model_role=args.model_role,
            )
        except Exception as exc:
            print(f"{Colors.RED}Failed to set model role: {exc}{Colors.RESET}")
            return
        print(
            f"{Colors.GREEN}Updated model role:{Colors.RESET} "
            f"[{source}] {args.id}/{args.model_id} -> {args.model_role}"
        )
        default_model_id = str(result.get("default_model_id") or "").strip()
        if default_model_id:
            print(f"  default_model: {default_model_id}")

    elif args.action == "bindings":
        service = ModelRegistryService(catalog_path=catalog_path)
        items = service.list_feature_bindings()
        if not items:
            print(f"{Colors.DIM}No feature-model bindings configured.{Colors.RESET}")
            return
        print(f"{Colors.CYAN}Feature Model Bindings:{Colors.RESET}\n")
        for item in items:
            status = "resolved" if item.get("resolved") else "stale"
            print(f"  {item.get('feature_role')} [{status}]")
            print(
                f"    source: {item.get('source') or '--'} | "
                f"provider: {item.get('provider_id') or '--'} | "
                f"model: {item.get('model_id') or '--'}"
            )
            if item.get("display_name"):
                print(f"    display: {item.get('display_name')}")
            if item.get("provider_name"):
                print(f"    provider_name: {item.get('provider_name')}")
            if item.get("updated_at"):
                print(f"    updated_at: {item.get('updated_at')}")
            print()

    elif args.action == "bind-feature":
        if not args.feature_role or not args.id or not args.model_id:
            print(
                f"{Colors.RED}Error: --feature-role, --id, and --model-id are required for bind-feature action.{Colors.RESET}"
            )
            return
        service = ModelRegistryService(catalog_path=catalog_path)
        source = _resolve_provider_source(
            service,
            provider_id=args.id,
            model_id=args.model_id,
            explicit_source=args.source,
        )
        if not source:
            print(
                f"{Colors.RED}Error: provider source could not be resolved. Use --source <custom|preset>.{Colors.RESET}"
            )
            return
        try:
            result = service.bind_feature_model(
                feature_role=args.feature_role,
                source=source,
                provider_id=args.id,
                model_id=args.model_id,
            )
        except Exception as exc:
            print(f"{Colors.RED}Failed to bind feature model: {exc}{Colors.RESET}")
            return
        print(
            f"{Colors.GREEN}Feature model bound:{Colors.RESET} "
            f"{result.get('feature_role')} -> [{result.get('source')}] "
            f"{result.get('provider_id')}/{result.get('model_id')}"
        )

    elif args.action == "clear-binding":
        if not args.feature_role:
            print(
                f"{Colors.RED}Error: --feature-role is required for clear-binding action.{Colors.RESET}"
            )
            return
        service = ModelRegistryService(catalog_path=catalog_path)
        try:
            result = service.clear_feature_model_binding(feature_role=args.feature_role)
        except Exception as exc:
            print(f"{Colors.RED}Failed to clear feature model binding: {exc}{Colors.RESET}")
            return
        status = str(result.get("status") or "cleared")
        if status == "not_found":
            print(
                f"{Colors.YELLOW}No feature-model binding existed for {args.feature_role}.{Colors.RESET}"
            )
        else:
            print(
                f"{Colors.GREEN}Cleared feature-model binding for {args.feature_role}.{Colors.RESET}"
            )

    elif args.action == "add":
        if not args.name or not args.url or not args.key:
            print(
                f"{Colors.RED}Error: --name, --url, and --key are required for add action.{Colors.RESET}"
            )
            return

        models: list[str] = []
        if args.models:
            models = [m.strip() for m in args.models.split(",") if m.strip()]
        auto_discover = bool(args.auto_discover_models)
        if not models and not auto_discover and sys.stdin.isatty():
            confirm = (
                input("No model configured. Auto-discover available models now? [y/N]: ")
                .strip()
                .lower()
            )
            auto_discover = confirm in {"y", "yes"}

        selected_model_id = str(args.selected_model_id).strip() if args.selected_model_id else ""
        if auto_discover and not selected_model_id and sys.stdin.isatty():
            try:
                use_cases = ProviderOperationsUseCases(
                    repo_root=Path.cwd().resolve(),
                    workspace_root=catalog_path.parent.resolve(),
                )
                discovery = use_cases.discover_provider_models(
                    payload=StudioProviderModelDiscoveryRequest(
                        api_type=args.type,
                        api_base=args.url,
                        api_key=args.key,
                    )
                )
            except Exception:
                discovery = None
            if discovery is not None and discovery.models:
                print("\nDiscovered models:")
                for idx, item in enumerate(discovery.models, start=1):
                    print(f"  {idx}. {item.model_id}")
                raw_choice = input("Select one model by number (blank to skip): ").strip()
                if raw_choice.isdigit():
                    selected_index = int(raw_choice)
                    if 1 <= selected_index <= len(discovery.models):
                        selected_model_id = discovery.models[selected_index - 1].model_id

        headers: dict[str, str] = {}
        for raw_header in args.header or []:
            if "=" not in str(raw_header):
                print(
                    f"{Colors.RED}Error: --header must use KEY=VALUE form. Invalid: {raw_header}{Colors.RESET}"
                )
                return
            key, value = str(raw_header).split("=", 1)
            normalized_key = key.strip()
            normalized_value = value.strip()
            if not normalized_key or not normalized_value:
                print(
                    f"{Colors.RED}Error: --header must use non-empty KEY=VALUE form. Invalid: {raw_header}{Colors.RESET}"
                )
                return
            headers[normalized_key] = normalized_value

        use_cases = ProviderOperationsUseCases(
            repo_root=Path.cwd().resolve(),
            workspace_root=catalog_path.parent.resolve(),
        )
        try:
            created = use_cases.create_provider(
                payload=StudioProviderUpsertRequest(
                    id=args.id,
                    name=args.name,
                    api_type=args.type,
                    api_base=args.url,
                    api_key=args.key,
                    models=models,
                    model_id=args.model_id,
                    model_display_name=args.model_name,
                    model_role=args.model_role,
                    model_context_window=args.context_window,
                    model_learned_token_limit=args.learned_token_limit,
                    supports_tools=args.supports_tools,
                    supports_thinking=args.supports_thinking,
                    auto_discover_models=auto_discover,
                    selected_model_id=selected_model_id or None,
                    enabled=True,
                    priority=args.priority,
                    timeout=args.timeout,
                    headers=headers,
                ),
                catalog_path=str(catalog_path),
            )
        except HTTPException as exc:
            print(f"{Colors.RED}Provider not created: {exc.detail}{Colors.RESET}")
            return
        except Exception as exc:
            print(f"{Colors.RED}Provider not created: {exc}{Colors.RESET}")
            return

        print(f"{Colors.GREEN}Provider added successfully:{Colors.RESET}")
        print(f"  id: {created.id}")
        print(f"  name: {created.name}")
        print(f"  catalog: {created.catalog_path}")
        print(f"  models: {', '.join(created.models)}")

    elif args.action == "remove":
        if not args.id:
            print(
                f"{Colors.RED}Error: --id is required for remove action.{Colors.RESET}"
            )
            return

        if not catalog_path.exists():
            print(f"{Colors.RED}No provider catalog found.{Colors.RESET}")
            return

        try:
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
            catalog = normalize_provider_catalog(payload)
        except Exception as e:
            print(f"{Colors.RED}Failed to load provider catalog: {e}{Colors.RESET}")
            return

        remaining = [p.model_dump() for p in catalog.providers if p.id != args.id]

        if len(remaining) == len(catalog.providers):
            print(f"{Colors.YELLOW}Provider '{args.id}' not found.{Colors.RESET}")
            return

        catalog_path.write_text(
            json.dumps({"providers": remaining}, indent=2), encoding="utf-8"
        )
        print(f"{Colors.GREEN}Provider '{args.id}' removed.{Colors.RESET}")

    elif args.action in ["enable", "disable"]:
        if not args.id:
            print(
                f"{Colors.RED}Error: --id is required for {args.action} action.{Colors.RESET}"
            )
            return

        if not catalog_path.exists():
            print(f"{Colors.RED}No provider catalog found.{Colors.RESET}")
            return

        try:
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
            catalog = normalize_provider_catalog(payload)
        except Exception as e:
            print(f"{Colors.RED}Failed to load provider catalog: {e}{Colors.RESET}")
            return

        found = False
        updated = []
        for p in catalog.providers:
            data = p.model_dump()
            if p.id == args.id:
                data["enabled"] = args.action == "enable"
                found = True
            updated.append(data)

        if not found:
            print(f"{Colors.YELLOW}Provider '{args.id}' not found.{Colors.RESET}")
            return

        catalog_path.write_text(
            json.dumps({"providers": updated}, indent=2), encoding="utf-8"
        )
        status = "enabled" if args.action == "enable" else "disabled"
        print(f"{Colors.GREEN}Provider '{args.id}' {status}.{Colors.RESET}")

    elif args.action == "show":
        if not args.id:
            print(f"{Colors.RED}Error: --id is required for show action.{Colors.RESET}")
            return

        if not catalog_path.exists():
            print(f"{Colors.RED}No provider catalog found.{Colors.RESET}")
            return

        try:
            payload = json.loads(catalog_path.read_text(encoding="utf-8"))
            catalog = normalize_provider_catalog(payload)
        except Exception as e:
            print(f"{Colors.RED}Failed to load provider catalog: {e}{Colors.RESET}")
            return

        provider = catalog.find(args.id)
        if not provider:
            print(f"{Colors.YELLOW}Provider '{args.id}' not found.{Colors.RESET}")
            return

        print(f"{Colors.CYAN}Provider: {provider.name}{Colors.RESET}\n")
        print(json.dumps(provider.redacted(), indent=2))


def run_list_command(args: argparse.Namespace) -> None:
    """Run the list command.

    Args:
        args: Parsed arguments
    """
    from .ops.discovery import discover_all

    print_banner()

    if args.type in ["all", "subprograms"]:
        print(f"{Colors.CYAN}[Subprograms]{Colors.RESET}")
        subprograms, _ = discover_all()
        if subprograms.modules:
            for sp in subprograms.modules:
                status = (
                    f"{Colors.GREEN}[+]{Colors.RESET}"
                    if sp.enabled
                    else f"{Colors.DIM}[-]{Colors.RESET}"
                )
                print(f"  {status} {sp.name} v{sp.version}")
                if sp.description:
                    print(f"      {Colors.DIM}{sp.description}{Colors.RESET}")
        else:
            print(f"  {Colors.DIM}No subprograms found{Colors.RESET}")
        print()

    if args.type in ["all", "channels"]:
        print(f"{Colors.CYAN}[Channels]{Colors.RESET}")
        _, channels = discover_all()
        if channels.modules:
            for ch in channels.modules:
                status = (
                    f"{Colors.GREEN}[+]{Colors.RESET}"
                    if ch.enabled
                    else f"{Colors.DIM}[-]{Colors.RESET}"
                )
                print(f"  {status} {ch.name} v{ch.version}")
                if ch.description:
                    print(f"      {Colors.DIM}{ch.description}{Colors.RESET}")
        else:
            print(f"  {Colors.DIM}No channels found{Colors.RESET}")
        print()


def run_stack_command(args: argparse.Namespace) -> None:
    """Run runtime stack manager command."""
    from .workspace_runtime.runtime_stack_manager import RuntimeStackManager

    source_root = Path(__file__).resolve().parents[1]
    repo_root = source_root.parent
    manager = RuntimeStackManager(source_root=source_root, repo_root=repo_root)
    action = args.action

    try:
        if action == "up":
            workspace = Path(args.workspace).resolve() if args.workspace else repo_root
            status = manager.up(
                host=args.host,
                gateway_port=int(args.port),
                workspace=workspace,
                qqbot=args.qqbot,
                approval_profile=getattr(args, "approval_profile", None),
                access_level=getattr(args, "access_level", None),
                startup_timeout=float(args.startup_timeout),
            )
            print(f"{Colors.GREEN}Runtime stack is running.{Colors.RESET}")
            print(
                f"  gateway: http://{status.host}:{status.gateway_port} (PID {status.gateway_pid})"
            )
            if status.qqbot_enabled and status.qqbot_pid:
                print(f"  qqbot:   running (PID {status.qqbot_pid})")
            elif status.qqbot_enabled:
                print("  qqbot:   enabled but not active")
            else:
                print("  qqbot:   skipped")
            print(f"  workspace: {status.workspace}")
            print(f"  state: {status.state_file}")
            print(f"  logs:  {status.gateway_log} | {status.qqbot_log}")
            if status.message:
                print(f"  note: {status.message}")
            if bool(args.tui):
                os.environ["MINI_AGENT_GATEWAY_BASE"] = f"http://{status.host}:{status.gateway_port}"
                print(f"{Colors.CYAN}Attaching TUI to runtime stack...{Colors.RESET}")
                run_tui_mode(
                    argparse.Namespace(
                        workspace=str(workspace),
                        approval_profile=getattr(args, "approval_profile", None),
                        access_level=getattr(args, "access_level", None),
                        prompt=getattr(args, "tui_prompt", None),
                    )
                )
            return

        if action == "down":
            status = manager.down(force=bool(args.force))
            print(f"{Colors.GREEN}Runtime stack stopped.{Colors.RESET}")
            print(f"  state: {status.state_file}")
            if status.message:
                print(f"  note: {status.message}")
            return

        if action == "status":
            status = manager.status()
            overall = (
                f"{Colors.GREEN}running{Colors.RESET}"
                if status.running
                else f"{Colors.YELLOW}stopped{Colors.RESET}"
            )
            gateway = (
                f"{Colors.GREEN}running{Colors.RESET} (PID {status.gateway_pid})"
                if status.gateway_running
                else f"{Colors.YELLOW}stopped{Colors.RESET}"
            )
            if status.qqbot_enabled:
                qqbot = (
                    f"{Colors.GREEN}running{Colors.RESET} (PID {status.qqbot_pid})"
                    if status.qqbot_running
                    else f"{Colors.YELLOW}stopped{Colors.RESET}"
                )
            else:
                qqbot = f"{Colors.DIM}disabled{Colors.RESET}"
            print(f"Runtime stack status: {overall}")
            print(f"  gateway:  {gateway} @ http://{status.host}:{status.gateway_port}")
            print(f"  qqbot:    {qqbot}")
            print(f"  workspace: {status.workspace}")
            print(f"  state: {status.state_file}")
            print(f"  logs:  {status.gateway_log} | {status.qqbot_log}")
            if not status.qqbot_configured:
                print("  qqbot_env: missing")
            if status.message:
                print(f"  note: {status.message}")
            return

        if action == "logs":
            payload = manager.read_logs(target=args.target, lines=max(1, int(args.lines)))
            if "gateway" in payload:
                print("===== gateway.log =====")
                print_safe_text(payload["gateway"] or "(empty)")
            if "qqbot" in payload:
                print("===== qqbot.log =====")
                print_safe_text(payload["qqbot"] or "(empty)")
            return

        raise RuntimeError(f"Unsupported stack action: {action}")
    except RuntimeError as exc:
        print(f"{Colors.RED}Error: {exc}{Colors.RESET}")
        raise SystemExit(1) from exc


def run_desktop_command(args: argparse.Namespace) -> None:
    """Run DesktopUI bootstrap command."""
    try:
        from apps.desktop_ui.main import run_desktop_from_cli

        exit_code = int(run_desktop_from_cli(args) or 0)
        if exit_code:
            raise SystemExit(exit_code)
    except RuntimeError as exc:
        print(f"{Colors.RED}Error: {exc}{Colors.RESET}")
        raise SystemExit(1) from exc


def run_qq_command(args: argparse.Namespace) -> None:
    """Shortcut command for gateway + the active QQ remote adapter + TUI startup."""
    action = getattr(args, "action", "up")
    run_stack_command(
        argparse.Namespace(
            action=action,
            workspace=getattr(args, "workspace", None),
            host=getattr(args, "host", "127.0.0.1"),
            port=int(getattr(args, "port", 8008)),
            qqbot=True if action == "up" else None,
            tui=bool(getattr(args, "tui", True)) if action == "up" else False,
            tui_prompt=getattr(args, "prompt", None) if action == "up" else None,
            startup_timeout=float(getattr(args, "startup_timeout", 20.0)),
            force=bool(getattr(args, "force", False)),
            target=getattr(args, "target", "all"),
            lines=int(getattr(args, "lines", 120)),
            approval_profile=getattr(args, "approval_profile", None),
            access_level=getattr(args, "access_level", None),
        )
    )


def main() -> None:
    """Main entry point for Mini-Agent CLI."""
    parser = create_main_parser()
    args = parser.parse_args()

    # Handle subcommands
    if args.command == "serve":
        run_gateway_mode(args)
    elif args.command == "cli":
        run_cli_mode(args)
    elif args.command == "tui":
        run_tui_mode(args)
    elif args.command == "desktop":
        run_desktop_command(args)
    elif args.command == "models":
        run_models_command(args)
    elif args.command == "list":
        run_list_command(args)
    elif args.command == "security-audit":
        run_security_audit_command(args)
    elif args.command == "doctor":
        run_doctor_command(args)
    elif args.command == "replay-log":
        run_replay_log_command(args)
    elif args.command == "prune-logs":
        run_prune_logs_command(args)
    elif args.command == "migrate-event-logs":
        run_migrate_event_logs_command(args)
    elif args.command == "prune-export-jobs":
        run_prune_export_jobs_command(args)
    elif args.command == "consolidate-memory":
        run_consolidate_memory_command(args)
    elif args.command == "stack":
        run_stack_command(args)
    elif args.command == "qq":
        run_qq_command(args)
    elif args.command == "provider":
        run_provider_command(args)
    else:
        # Default: unified terminal mode; retain serve-intent fallback for host/port/reload.
        if _is_serve_intent(args):
            run_gateway_mode(args)
            return
        run_unified_terminal_mode(args)

if __name__ == "__main__":
    main()
