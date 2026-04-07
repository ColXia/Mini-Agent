"""Mini-Agent CLI - Unified entry point.

Usage:
    mini-agent                    # Studio API mode (default) - single backend host
    mini-agent cli                # CLI mode - interactive terminal session
    mini-agent cli --task "..."   # CLI mode - execute single task

Studio API Mode Options:
    mini-agent --port 8080        # Specify Studio API port
    mini-agent --reload           # Enable auto-reload

Subcommands:
    mini-agent dev up             # Start Studio backend + frontend dev stack
    mini-agent dev status         # Check Studio dev process status
    mini-agent dev down           # Stop Studio dev stack
    mini-agent dev logs           # Tail Studio dev logs
    mini-agent list subprograms   # List available subprograms
    mini-agent list channels      # List available channels
"""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Optional


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
    try:
        banner = f"""
{Colors.BRIGHT_CYAN}╔═══════════════════════════════════════════════════════════╗
║                                                           ║
║   {Colors.BOLD}Mini-Agent{Colors.RESET}{Colors.BRIGHT_CYAN} - Intelligent Agent Platform              ║
║                                                           ║
║   Powered by MiniMax M2.5                                 ║
║                                                           ║
╚═══════════════════════════════════════════════════════════╝{Colors.RESET}
"""
        print(banner)
    except UnicodeEncodeError:
        # Fallback for Windows terminals with limited encoding
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
  mini-agent                        Start Studio API host (single backend)
  mini-agent --port 8080            Start Studio API on port 8080
  mini-agent cli                    Interactive CLI session
  mini-agent cli --task "hello"     Execute single task
  mini-agent dev up                 Start Studio dev stack (backend + frontend)
  mini-agent dev status             Show Studio dev stack status
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
        "-p",
        type=int,
        default=8008,
        help="Studio API port (default: 8008)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Studio API host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="Enable auto-reload for development",
    )
    parser.add_argument(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace directory",
    )
    parser.add_argument(
        "--approval-profile",
        type=str,
        choices=["suggest", "auto-edit", "full-auto"],
        default=None,
        help="Runtime approval profile override",
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

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
        "--approval-profile",
        type=str,
        choices=["suggest", "auto-edit", "full-auto"],
        default=None,
        help="Runtime approval profile override",
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
        "--approval-profile",
        type=str,
        choices=["suggest", "auto-edit", "full-auto"],
        default=None,
        help="Approval profile override for audit evaluation",
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
        choices=["list", "add", "remove", "enable", "disable", "show"],
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
        choices=["openai", "anthropic", "gemini", "custom"],
        default="openai",
        help="API protocol type",
    )
    provider_parser.add_argument(
        "--models",
        type=str,
        default=None,
        help="Comma-separated list of supported models",
    )
    provider_parser.add_argument(
        "--priority",
        type=int,
        default=0,
        help="Provider priority (higher = preferred)",
    )
    provider_parser.add_argument(
        "--catalog",
        type=str,
        default=None,
        help="Provider catalog JSON file path (default: ~/.mini-agent/providers.json)",
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
        help="Provider name (openai, anthropic, gemini, minimax)",
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

    dev_parser = subparsers.add_parser(
        "dev",
        help="Manage Studio dev processes (one backend + one frontend)",
    )
    dev_parser.add_argument(
        "action",
        choices=["up", "down", "status", "logs", "profile"],
        help="Dev manager action",
    )
    dev_parser.add_argument(
        "--profile",
        type=str,
        default="single-main",
        help="Startup profile name (default: single-main)",
    )
    dev_parser.add_argument(
        "--init-profile",
        action="store_true",
        help="Create profile template file when missing (`dev profile` action)",
    )
    dev_parser.add_argument(
        "--show-json",
        action="store_true",
        help="Print resolved profile as JSON (`dev profile` action)",
    )
    dev_parser.add_argument(
        "--host",
        type=str,
        default=None,
        help="Optional host override for selected profile",
    )
    dev_parser.add_argument(
        "--gateway-port",
        type=int,
        default=None,
        help="Optional gateway port override for selected profile",
    )
    dev_parser.add_argument(
        "--frontend-port",
        type=int,
        default=None,
        help="Optional frontend port override for selected profile",
    )
    dev_parser.add_argument(
        "--startup-timeout",
        type=float,
        default=None,
        help="Optional startup timeout override for `dev up`",
    )
    dev_parser.add_argument(
        "--backend-reload",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Enable/disable backend uvicorn --reload for `dev up`",
    )
    dev_parser.add_argument(
        "--frontend-install",
        action="store_true",
        help="Run `npm install` in frontend dir when node_modules is missing",
    )
    dev_parser.add_argument(
        "--force",
        action="store_true",
        help="Force terminate lingering processes on `dev down`",
    )
    dev_parser.add_argument(
        "--target",
        choices=["all", "backend", "frontend"],
        default="all",
        help="Log target for `dev logs`",
    )
    dev_parser.add_argument(
        "--lines",
        type=int,
        default=120,
        help="Tail lines for `dev logs` (default: 120)",
    )
    dev_parser.add_argument(
        "--follow",
        action="store_true",
        help="Follow logs continuously for `dev logs`",
    )

    return parser


def run_gateway_mode(args: argparse.Namespace) -> None:
    """Run in Studio API mode (single backend host)."""
    import atexit

    import uvicorn

    from .config import Config
    from .ops.doctor import format_doctor_report, run_startup_self_check
    from .utils.single_instance import SingleInstanceManager

    if args.approval_profile:
        os.environ["MINI_AGENT_APPROVAL_PROFILE"] = args.approval_profile

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

    try:
        config = Config.load()
    except Exception as exc:
        print(f"{Colors.RED}[X] Failed to load configuration: {exc}{Colors.RESET}")
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
    print(f"  runtime_mode: single_main")
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

    print_banner()

    # Determine workspace
    workspace = Path(args.workspace) if args.workspace else Path.cwd()
    workspace.mkdir(parents=True, exist_ok=True)

    # Run interactive or single task
    asyncio.run(
        run_interactive_session(
            workspace=workspace,
            task=args.task,
            approval_profile=args.approval_profile,
        )
    )


def run_security_audit_command(args: argparse.Namespace) -> None:
    """Run security audit command."""
    from .config import Config
    from .security.audit import format_security_audit_report, run_security_audit

    try:
        config = Config.load()
    except Exception as exc:
        print(f"{Colors.RED}[X] Failed to load configuration: {exc}{Colors.RESET}")
        return

    if args.approval_profile:
        config.security.approval_profile = args.approval_profile

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
    from .config import Config
    from .ops.doctor import format_doctor_report, run_doctor

    try:
        config = Config.load()
    except Exception as exc:
        print(f"{Colors.RED}[X] Failed to load configuration: {exc}{Colors.RESET}")
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
    from .config import Config
    from .logger import AgentLogger, EventLogRetentionPolicy

    try:
        config = Config.load()
    except Exception as exc:
        print(f"{Colors.RED}[X] Failed to load configuration: {exc}{Colors.RESET}")
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
        try:
            from .config import Config

            config = Config.load()
            log_dir = config.observability.log_dir
        except Exception:
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

    from mini_agent.model_manager.preset_providers import list_preset_providers
    from mini_agent.model_manager.model_discovery import (
        list_available_models,
        get_latest_model_id,
        ProviderType,
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
        print(f"Usage: mini-agent models <provider>")
        print(f"Providers: openai, anthropic, gemini, minimax")
        print(f"\nTo list preset providers: mini-agent models --list-presets")
        return

    provider = args.provider.lower()

    # Validate provider
    try:
        provider_type = ProviderType(provider)
    except ValueError:
        print(f"{Colors.RED}Unknown provider: {provider}{Colors.RESET}")
        print(f"Supported providers: {', '.join([p.value for p in ProviderType])}")
        return

    # Get API key
    api_key = args.api_key
    if not api_key:
        # Try environment variables
        env_key_map = {
            "openai": "OPENAI_API_KEY",
            "anthropic": "ANTHROPIC_API_KEY",
            "gemini": "GEMINI_API_KEY",
            "minimax": "MINIMAX_API_KEY",
        }
        env_key = env_key_map.get(provider)
        if env_key:
            api_key = os.getenv(env_key)

        if not api_key:
            print(f"{Colors.RED}Error: No API key provided.{Colors.RESET}")
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
    from mini_agent.model_manager import (
        ProviderConfig,
        ProviderCatalog,
        normalize_provider_catalog,
    )

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

    elif args.action == "add":
        if not args.name or not args.url or not args.key:
            print(
                f"{Colors.RED}Error: --name, --url, and --key are required for add action.{Colors.RESET}"
            )
            return

        models = []
        if args.models:
            models = [m.strip() for m in args.models.split(",") if m.strip()]
        if not models:
            models = ["default"]

        new_provider = ProviderConfig(
            id=args.id,
            name=args.name,
            api_type=args.type,
            api_base=args.url,
            api_key=args.key,
            models=models,
            enabled=True,
            priority=args.priority,
        )

        existing_providers = []
        if catalog_path.exists():
            try:
                payload = json.loads(catalog_path.read_text(encoding="utf-8"))
                existing_catalog = normalize_provider_catalog(payload)
                existing_providers = [
                    p.model_dump() for p in existing_catalog.providers
                ]
            except Exception:
                pass

        existing_providers.append(new_provider.model_dump())

        catalog_path.parent.mkdir(parents=True, exist_ok=True)
        catalog_path.write_text(
            json.dumps({"providers": existing_providers}, indent=2), encoding="utf-8"
        )

        print(f"{Colors.GREEN}Provider added successfully:{Colors.RESET}")
        print(f"  id: {new_provider.id}")
        print(f"  name: {new_provider.name}")
        print(f"  catalog: {catalog_path}")

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
    from .launcher.scanner import discover_all

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


def run_dev_command(args: argparse.Namespace) -> None:
    """Run Studio dev process manager command."""
    from .dev import StudioDevManager

    repo_root = Path(__file__).resolve().parents[1]
    manager = StudioDevManager(repo_root=repo_root)
    action = args.action

    try:
        if action == "profile":
            if args.init_profile:
                path = manager.ensure_profile_template(args.profile)
                print(f"{Colors.GREEN}Profile template ensured.{Colors.RESET}")
                print(f"  profile: {args.profile}")
                print(f"  file: {path}")
            profile = manager.resolve_profile(
                profile_name=args.profile,
                host=args.host,
                gateway_port=args.gateway_port,
                frontend_port=args.frontend_port,
                backend_reload=args.backend_reload,
                startup_timeout=args.startup_timeout,
                ensure_exists=args.init_profile,
            )
            payload = manager.profile_to_dict(profile)
            print(f"Profile: {payload['name']}")
            print(f"  source: {payload['source']}")
            print(f"  desc: {payload['description']}")
            print(f"  backend:  http://{payload['host']}:{payload['gateway_port']}")
            print(f"  frontend: http://{payload['host']}:{payload['frontend_port']}")
            print(f"  backend_reload: {payload['backend_reload']}")
            print(f"  startup_timeout: {payload['startup_timeout']}")
            if args.show_json:
                print(json.dumps(payload, ensure_ascii=False, indent=2))
            return

        if action == "up":
            status = manager.up(
                profile_name=args.profile,
                host=args.host,
                gateway_port=args.gateway_port,
                frontend_port=args.frontend_port,
                backend_reload=args.backend_reload,
                frontend_install=bool(args.frontend_install),
                startup_timeout=args.startup_timeout,
            )
            print(f"{Colors.GREEN}Studio dev stack is running.{Colors.RESET}")
            print(
                f"  backend:  http://{status.host}:{status.gateway_port} (PID {status.backend_pid})"
            )
            print(
                f"  frontend: http://{status.host}:{status.frontend_port} (PID {status.frontend_pid})"
            )
            if status.profile_name:
                print(f"  profile: {status.profile_name}")
            if status.profile_source:
                print(f"  profile_source: {status.profile_source}")
            print(f"  state: {status.state_file}")
            print(f"  logs:  {status.backend_log} | {status.frontend_log}")
            return

        if action == "down":
            status = manager.down(force=bool(args.force))
            print(f"{Colors.GREEN}Studio dev stack stopped.{Colors.RESET}")
            if status.message:
                print(f"  {status.message}")
            print(f"  state: {status.state_file}")
            return

        if action == "status":
            status = manager.status()
            overall = (
                f"{Colors.GREEN}running{Colors.RESET}"
                if status.running
                else f"{Colors.YELLOW}stopped{Colors.RESET}"
            )
            backend = (
                f"{Colors.GREEN}running{Colors.RESET} (PID {status.backend_pid})"
                if status.backend_running
                else f"{Colors.YELLOW}stopped{Colors.RESET}"
            )
            frontend = (
                f"{Colors.GREEN}running{Colors.RESET} (PID {status.frontend_pid})"
                if status.frontend_running
                else f"{Colors.YELLOW}stopped{Colors.RESET}"
            )
            print(f"Studio dev status: {overall}")
            print(f"  backend:  {backend} @ http://{status.host}:{status.gateway_port}")
            print(f"  frontend: {frontend} @ http://{status.host}:{status.frontend_port}")
            if status.profile_name:
                print(f"  profile: {status.profile_name}")
            if status.profile_source:
                print(f"  profile_source: {status.profile_source}")
            print(f"  state: {status.state_file}")
            print(f"  logs:  {status.backend_log} | {status.frontend_log}")
            if status.message:
                print(f"  note: {status.message}")
            return

        if action == "logs":
            if args.follow:
                print(
                    f"{Colors.CYAN}Following {args.target} logs (Ctrl+C to stop)...{Colors.RESET}"
                )
                try:
                    manager.follow_logs(target=args.target)
                except KeyboardInterrupt:
                    print()
                return
            payload = manager.read_logs(target=args.target, lines=max(1, int(args.lines)))
            if "backend" in payload:
                print("===== backend.log =====")
                print_safe_text(payload["backend"] or "(empty)")
            if "frontend" in payload:
                print("===== frontend.log =====")
                print_safe_text(payload["frontend"] or "(empty)")
            return

        raise RuntimeError(f"Unsupported dev action: {action}")
    except RuntimeError as exc:
        print(f"{Colors.RED}Error: {exc}{Colors.RESET}")
        raise SystemExit(1) from exc


def main() -> None:
    """Main entry point for Mini-Agent CLI."""
    parser = create_main_parser()
    args = parser.parse_args()

    # Handle subcommands
    if args.command == "cli":
        run_cli_mode(args)
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
    elif args.command == "dev":
        run_dev_command(args)
    elif args.command == "provider":
        run_provider_command(args)
    else:
        # Default: Studio API mode
        run_gateway_mode(args)


if __name__ == "__main__":
    main()
