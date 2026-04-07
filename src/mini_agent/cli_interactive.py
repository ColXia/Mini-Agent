"""Interactive CLI session for Mini-Agent.

This module provides the interactive terminal session for Mini-Agent,
supporting both interactive mode and single-task execution.
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.key_binding import KeyBindings

from .agent import Agent
from .config import Config
from .logger import create_agent_logger
from .model_manager.failover import FailoverLLMClient
from .model_manager.runtime import resolve_routed_llm_candidates
from .runtime.tooling import initialize_agent_tools
from .retry import RetryConfig
from .tools.mcp_loader import cleanup_mcp_connections


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
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"


def print_banner():
    """Print the CLI banner."""
    try:
        banner = f"""
{Colors.BRIGHT_CYAN}╔═══════════════════════════════════════════════════════════╗
║   {Colors.BOLD}Mini-Agent CLI{Colors.RESET}{Colors.BRIGHT_CYAN} - Interactive Session                ║
╚═══════════════════════════════════════════════════════════╝{Colors.RESET}
"""
        print(banner)
    except UnicodeEncodeError:
        # Fallback for Windows terminals with limited encoding
        print("=" * 60)
        print("  Mini-Agent CLI - Interactive Session")
        print("=" * 60)


def print_help():
    """Print help information."""
    help_text = f"""
{Colors.BOLD}{Colors.BRIGHT_YELLOW}Available Commands:{Colors.RESET}
  {Colors.BRIGHT_GREEN}/help{Colors.RESET}      Show this help message
  {Colors.BRIGHT_GREEN}/clear{Colors.RESET}     Clear session history
  {Colors.BRIGHT_GREEN}/history{Colors.RESET}   Show message count
  {Colors.BRIGHT_GREEN}/stats{Colors.RESET}     Show session statistics
  {Colors.BRIGHT_GREEN}/exit{Colors.RESET}      Exit program

{Colors.BOLD}{Colors.BRIGHT_YELLOW}Keyboard Shortcuts:{Colors.RESET}
  {Colors.CYAN}Ctrl+C{Colors.RESET}     Exit program
  {Colors.CYAN}Ctrl+J{Colors.RESET}     Insert newline
  {Colors.CYAN}Tab{Colors.RESET}        Auto-complete commands
"""
    print(help_text)


def print_session_info(agent: Agent, workspace: Path, model: str):
    """Print session information."""
    try:
        print(f"{Colors.DIM}┌{'─' * 50}┐{Colors.RESET}")
        print(f"{Colors.DIM}│{Colors.RESET} {Colors.BRIGHT_CYAN}Session Info{Colors.RESET}{' ' * 38}{Colors.DIM}│{Colors.RESET}")
        print(f"{Colors.DIM}├{'─' * 50}┤{Colors.RESET}")
        print(f"{Colors.DIM}│{Colors.RESET} Model: {model}{' ' * (50 - 8 - len(model))}{Colors.DIM}│{Colors.RESET}")
        print(f"{Colors.DIM}│{Colors.RESET} Workspace: {workspace}{' ' * max(0, 50 - 12 - len(str(workspace)))}{Colors.DIM}│{Colors.RESET}")
        print(f"{Colors.DIM}│{Colors.RESET} Tools: {len(agent.tools)}{' ' * (50 - 8 - len(str(len(agent.tools))))}{Colors.DIM}│{Colors.RESET}")
        print(f"{Colors.DIM}└{'─' * 50}┘{Colors.RESET}")
    except UnicodeEncodeError:
        print(f"Session Info")
        print(f"  Model: {model}")
        print(f"  Workspace: {workspace}")
        print(f"  Tools: {len(agent.tools)}")
    print(f"\n{Colors.DIM}Type {Colors.BRIGHT_GREEN}/help{Colors.DIM} for help, {Colors.BRIGHT_GREEN}/exit{Colors.DIM} to quit{Colors.RESET}\n")


def print_stats(agent: Agent, session_start: datetime):
    """Print session statistics."""
    duration = datetime.now() - session_start
    hours, remainder = divmod(int(duration.total_seconds()), 3600)
    minutes, seconds = divmod(remainder, 60)

    user_msgs = sum(1 for m in agent.messages if m.role == "user")
    assistant_msgs = sum(1 for m in agent.messages if m.role == "assistant")

    print(f"\n{Colors.BOLD}{Colors.BRIGHT_CYAN}Session Statistics:{Colors.RESET}")
    try:
        print(f"{Colors.DIM}{'─' * 40}{Colors.RESET}")
    except UnicodeEncodeError:
        print("-" * 40)
    print(f"  Duration: {hours:02d}:{minutes:02d}:{seconds:02d}")
    print(f"  Messages: {len(agent.messages)}")
    print(f"    - User: {Colors.BRIGHT_GREEN}{user_msgs}{Colors.RESET}")
    print(f"    - Assistant: {Colors.BRIGHT_BLUE}{assistant_msgs}{Colors.RESET}")
    if agent.api_total_tokens > 0:
        print(f"  Tokens: {Colors.BRIGHT_MAGENTA}{agent.api_total_tokens:,}{Colors.RESET}")
    try:
        print(f"{Colors.DIM}{'─' * 40}{Colors.RESET}\n")
    except UnicodeEncodeError:
        print("-" * 40 + "\n")


async def build_agent(workspace: Path, approval_profile: str | None = None) -> Agent:
    """Build an Agent instance.

    Args:
        workspace: Workspace directory path

    Returns:
        Agent instance
    """
    config = Config.load()
    llm_routes = resolve_routed_llm_candidates(config, requested_model=config.llm.model)

    retry_config = RetryConfig(
        enabled=config.llm.retry.enabled,
        max_retries=config.llm.retry.max_retries,
        initial_delay=config.llm.retry.initial_delay,
        max_delay=config.llm.retry.max_delay,
        exponential_base=config.llm.retry.exponential_base,
    )

    llm_client = FailoverLLMClient(
        routes=llm_routes,
        retry_config=retry_config if config.llm.retry.enabled else None,
    )

    # Initialize tools
    tools, skill_loader = await initialize_agent_tools(
        config=config,
        workspace_dir=workspace,
        approval_profile_override=approval_profile,
    )

    # Load system prompt
    system_prompt_path = Config.find_config_file(config.agent.system_prompt_path)
    if system_prompt_path and system_prompt_path.exists():
        system_prompt = system_prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = "You are Mini-Agent, an intelligent assistant powered by MiniMax M2.5."

    if skill_loader:
        meta = skill_loader.get_skills_metadata_prompt()
        if meta:
            system_prompt = f"{system_prompt.rstrip()}\n\n{meta}"

    return Agent(
        llm_client=llm_client,
        system_prompt=system_prompt,
        tools=tools,
        max_steps=config.agent.max_steps,
        max_tool_calls_per_step=config.agent.max_tool_calls_per_step,
        workspace_dir=str(workspace),
        logger=create_agent_logger(config),
    )


async def run_interactive_session(
    workspace: Path,
    task: Optional[str] = None,
    approval_profile: str | None = None,
) -> None:
    """Run an interactive CLI session.

    Args:
        workspace: Workspace directory
        task: Optional single task to execute
        approval_profile: Optional runtime approval profile override.
    """
    session_start = datetime.now()

    try:
        config = Config.load()
    except Exception as e:
        print(f"{Colors.RED}[X] Failed to load configuration: {e}{Colors.RESET}")
        return

    from .ops.doctor import format_doctor_report, run_startup_self_check

    is_ready, findings = run_startup_self_check(config=config, workspace=workspace.resolve())
    print(format_doctor_report(findings, title="Startup Self-Check"))
    if not is_ready:
        print(f"{Colors.RED}[X] Startup self-check failed. Fix blocking issues before running CLI.{Colors.RESET}")
        return

    print_banner()

    # Build agent
    print(f"{Colors.DIM}Initializing agent...{Colors.RESET}")
    try:
        agent = await build_agent(workspace, approval_profile=approval_profile)
    except Exception as e:
        print(f"{Colors.RED}[X] Failed to initialize agent: {e}{Colors.RESET}")
        return

    print_session_info(agent, workspace, agent.llm_client.model)

    # Single task mode
    if task:
        print(f"{Colors.BRIGHT_BLUE}Agent{Colors.RESET} {Colors.DIM}>{Colors.RESET} {task}\n")
        agent.add_user_message(task)
        try:
            await agent.run()
        except Exception as e:
            print(f"{Colors.RED}[X] Error: {e}{Colors.RESET}")
        print_stats(agent, session_start)
        await cleanup_mcp_connections()
        return

    # Interactive mode
    kb = KeyBindings()

    @kb.add("c-j")
    def _(event):
        event.current_buffer.insert_text("\n")

    history_file = Path.home() / ".mini-agent" / ".history"
    history_file.parent.mkdir(parents=True, exist_ok=True)

    session = PromptSession(
        history=FileHistory(str(history_file)),
        auto_suggest=AutoSuggestFromHistory(),
        completer=WordCompleter(["/help", "/clear", "/history", "/stats", "/exit"]),
        key_bindings=kb,
    )

    while True:
        try:
            user_input = await session.prompt_async(
                [("class:prompt", "You"), ("", " › ")],
                multiline=False,
            )
            user_input = user_input.strip()

            if not user_input:
                continue

            # Handle commands
            if user_input.startswith("/"):
                command = user_input.lower()
                if command in ["/exit", "/quit", "/q"]:
                    print(f"\n{Colors.BRIGHT_YELLOW}Goodbye!{Colors.RESET}\n")
                    print_stats(agent, session_start)
                    break
                elif command == "/help":
                    print_help()
                    continue
                elif command == "/clear":
                    old_count = len(agent.messages)
                    agent.messages = [agent.messages[0]]
                    print(f"{Colors.GREEN}[OK] Cleared {old_count - 1} messages{Colors.RESET}\n")
                    continue
                elif command == "/history":
                    print(f"\n{Colors.BRIGHT_CYAN}Messages: {len(agent.messages)}{Colors.RESET}\n")
                    continue
                elif command == "/stats":
                    print_stats(agent, session_start)
                    continue
                else:
                    print(f"{Colors.RED}Unknown command: {user_input}{Colors.RESET}")
                    continue

            # Normal message
            print(f"\n{Colors.BRIGHT_BLUE}Agent{Colors.RESET} {Colors.DIM}> Thinking...{Colors.RESET}\n")
            agent.add_user_message(user_input)

            try:
                await agent.run()
            except Exception as e:
                print(f"{Colors.RED}[X] Error: {e}{Colors.RESET}")

            print(f"\n{Colors.DIM}{'-' * 50}{Colors.RESET}\n")

        except KeyboardInterrupt:
            print(f"\n\n{Colors.BRIGHT_YELLOW}Interrupted. Goodbye!{Colors.RESET}\n")
            print_stats(agent, session_start)
            break

    await cleanup_mcp_connections()


def main() -> None:
    """Standalone entry point for CLI mode."""
    import argparse

    parser = argparse.ArgumentParser(description="Mini-Agent CLI - Interactive Terminal")
    parser.add_argument(
        "--task", "-t",
        type=str,
        default=None,
        help="Execute a single task and exit",
    )
    parser.add_argument(
        "--workspace", "-w",
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

    args = parser.parse_args()
    workspace = Path(args.workspace) if args.workspace else Path.cwd()

    asyncio.run(
        run_interactive_session(
            workspace=workspace,
            task=args.task,
            approval_profile=args.approval_profile,
        )
    )


if __name__ == "__main__":
    main()
