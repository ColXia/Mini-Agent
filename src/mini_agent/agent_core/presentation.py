"""Presentation adapters for agent-core runtime execution."""

from __future__ import annotations

import json
import sys
from typing import Callable

from mini_agent.tools.base import ToolResult
from mini_agent.utils.terminal_utils import calculate_display_width


def _safe_encode_text(text: str) -> str:
    """Safely encode text for terminal output, replacing unencodable characters.

    On Windows with GBK/CP936 encoding, many Unicode characters (emoji, etc.)
    cannot be displayed. This function replaces them with safe alternatives.
    """
    if text is None:
        return ""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    try:
        # Try to encode with the terminal's encoding
        text.encode(encoding)
        return text
    except UnicodeEncodeError:
        # Replace unencodable characters with their closest ASCII equivalent
        # or a placeholder
        return text.encode(encoding, errors="replace").decode(encoding)


class AgentRuntimePresenter:
    """Semantic presenter interface for agent-core operator feedback."""

    def context_overflow_detected(self) -> None:
        pass

    def context_overflow_recovery_failed(self) -> None:
        pass

    def context_recovery_applied(self, *, estimated_before: int, estimated_after: int) -> None:
        pass

    def incomplete_message_cleanup(self, *, removed_count: int) -> None:
        pass

    def tool_calls_truncated(
        self,
        *,
        step: int,
        requested_tool_calls: int,
        planned_tool_calls: int,
    ) -> None:
        pass

    def step_header(self, *, step: int, max_steps: int) -> None:
        pass

    def cancelled(self, *, message: str) -> None:
        pass

    def planner_retry_failed(self, *, error_message: str) -> None:
        pass

    def planner_error(self, *, error_message: str) -> None:
        pass

    def step_timing(
        self,
        *,
        step: int,
        step_elapsed: float,
        total_elapsed: float,
    ) -> None:
        pass

    def retrying_planner_generation(self) -> None:
        pass

    def assistant_thinking(self, *, thinking: str) -> None:
        pass

    def assistant_response(self, *, content: str) -> None:
        pass

    def run_log_paths(self, *, log_file_path: str | None, event_file_path: str | None) -> None:
        pass

    def max_steps_reached(self, *, error_message: str) -> None:
        pass

    def tool_call(self, *, function_name: str, arguments: dict[str, object]) -> None:
        pass

    def tool_result(self, *, result: ToolResult) -> None:
        pass

    def history_summary_triggered(
        self,
        *,
        estimated_tokens: int,
        api_total_tokens: int,
        token_limit: int,
    ) -> None:
        pass

    def history_summary_insufficient_messages(self) -> None:
        pass

    def history_summary_generated(self, *, round_num: int) -> None:
        pass

    def history_summary_generation_failed(self, *, round_num: int, error: str) -> None:
        pass

    def history_summary_completed(
        self,
        *,
        estimated_tokens: int,
        compacted_tokens: int,
        user_message_count: int,
        summary_message_count: int,
    ) -> None:
        pass


class NullAgentRuntimePresenter(AgentRuntimePresenter):
    """Headless presenter that intentionally emits nothing."""


class AnsiConsoleAgentRuntimePresenter(AgentRuntimePresenter):
    """ANSI console presenter used as a compatibility bridge for CLI/TUI."""

    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"

    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"

    BRIGHT_BLACK = "\033[90m"
    BRIGHT_RED = "\033[91m"
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_BLUE = "\033[94m"
    BRIGHT_MAGENTA = "\033[95m"
    BRIGHT_CYAN = "\033[96m"
    BRIGHT_WHITE = "\033[97m"

    def __init__(self, *, emit: Callable[[str], None] | None = None) -> None:
        self._emit = emit or print

    def _write(self, text: str) -> None:
        self._emit(_safe_encode_text(text))

    @staticmethod
    def _truncate_tool_arguments(arguments: dict[str, object]) -> dict[str, object]:
        truncated_args: dict[str, object] = {}
        for key, value in arguments.items():
            value_str = str(value)
            if len(value_str) > 200:
                truncated_args[key] = value_str[:200] + "..."
            else:
                truncated_args[key] = value
        return truncated_args

    def context_overflow_detected(self) -> None:
        self._write(
            f"{self.BRIGHT_YELLOW}[...] Context overflow detected. Attempting automatic recovery...{self.RESET}"
        )

    def context_overflow_recovery_failed(self) -> None:
        self._write(
            f"{self.BRIGHT_YELLOW}[!]  Context overflow recovery could not reduce message history.{self.RESET}"
        )

    def context_recovery_applied(self, *, estimated_before: int, estimated_after: int) -> None:
        self._write(
            f"{self.BRIGHT_GREEN}[OK] Context recovery applied: {estimated_before} -> {estimated_after} tokens{self.RESET}"
        )

    def incomplete_message_cleanup(self, *, removed_count: int) -> None:
        self._write(f"{self.DIM}   Cleaned up {removed_count} incomplete message(s){self.RESET}")

    def tool_calls_truncated(
        self,
        *,
        step: int,
        requested_tool_calls: int,
        planned_tool_calls: int,
    ) -> None:
        self._write(
            f"{self.BRIGHT_YELLOW}[Guard] Step {step} tool calls truncated: "
            f"{requested_tool_calls} -> {planned_tool_calls}{self.RESET}"
        )

    def step_header(self, *, step: int, max_steps: int) -> None:
        box_width = 58
        step_text = f"{self.BOLD}{self.BRIGHT_CYAN}[Thinking] Step {step}/{max_steps}{self.RESET}"
        step_display_width = calculate_display_width(step_text)
        padding = max(0, box_width - 1 - step_display_width)
        horizontal = "-" * box_width
        self._write(f"\n{self.DIM}+{horizontal}+{self.RESET}")
        self._write(f"{self.DIM}|{self.RESET} {step_text}{' ' * padding}{self.DIM}|{self.RESET}")
        self._write(f"{self.DIM}+{horizontal}+{self.RESET}")

    def cancelled(self, *, message: str) -> None:
        self._write(f"\n{self.BRIGHT_YELLOW}[!]  {message}{self.RESET}")

    def planner_retry_failed(self, *, error_message: str) -> None:
        self._write(f"\n{self.BRIGHT_RED}[Error] Retry failed:{self.RESET} {error_message}")

    def planner_error(self, *, error_message: str) -> None:
        self._write(f"\n{self.BRIGHT_RED}[Error] Error:{self.RESET} {error_message}")

    def step_timing(
        self,
        *,
        step: int,
        step_elapsed: float,
        total_elapsed: float,
    ) -> None:
        self._write(
            f"\n{self.DIM}[Time]  Step {step} completed in {step_elapsed:.2f}s (total: {total_elapsed:.2f}s){self.RESET}"
        )

    def retrying_planner_generation(self) -> None:
        self._write(
            f"{self.BRIGHT_CYAN}[...] Retrying planner generation once after context recovery...{self.RESET}"
        )

    def assistant_thinking(self, *, thinking: str) -> None:
        self._write(f"\n{self.BOLD}{self.MAGENTA}[Brain] Thinking:{self.RESET}")
        self._write(f"{self.DIM}{thinking}{self.RESET}")

    def assistant_response(self, *, content: str) -> None:
        self._write(f"\n{self.BOLD}{self.BRIGHT_BLUE}[Agent] Assistant:{self.RESET}")
        self._write(content)

    def run_log_paths(self, *, log_file_path: str | None, event_file_path: str | None) -> None:
        self._write(f"{self.DIM}[Note] Log file: {log_file_path}{self.RESET}")
        self._write(f"{self.DIM}[Note] Event log: {event_file_path}{self.RESET}")

    def max_steps_reached(self, *, error_message: str) -> None:
        self._write(f"\n{self.BRIGHT_YELLOW}[!]  {error_message}{self.RESET}")

    def tool_call(self, *, function_name: str, arguments: dict[str, object]) -> None:
        self._write(
            f"\n{self.BRIGHT_YELLOW}[Tool] Tool Call:{self.RESET} "
            f"{self.BOLD}{self.CYAN}{function_name}{self.RESET}"
        )
        self._write(f"{self.DIM}   Arguments:{self.RESET}")
        args_json = json.dumps(
            self._truncate_tool_arguments(arguments),
            indent=2,
            ensure_ascii=False,
        )
        for line in args_json.split("\n"):
            self._write(f"   {self.DIM}{line}{self.RESET}")

    def tool_result(self, *, result: ToolResult) -> None:
        if result.success:
            result_text = result.content
            if len(result_text) > 300:
                result_text = result_text[:300] + f"{self.DIM}...{self.RESET}"
            self._write(f"{self.BRIGHT_GREEN}[OK] Result:{self.RESET} {result_text}")
            return
        self._write(f"{self.BRIGHT_RED}[X] Error:{self.RESET} {self.RED}{result.error}{self.RESET}")

    def history_summary_triggered(
        self,
        *,
        estimated_tokens: int,
        api_total_tokens: int,
        token_limit: int,
    ) -> None:
        self._write(
            f"\n{self.BRIGHT_YELLOW}[Stats] Token usage - Local estimate: {estimated_tokens}, "
            f"API reported: {api_total_tokens}, Limit: {token_limit}{self.RESET}"
        )
        self._write(
            f"{self.BRIGHT_YELLOW}[...] Triggering message history summarization...{self.RESET}"
        )

    def history_summary_insufficient_messages(self) -> None:
        self._write(f"{self.BRIGHT_YELLOW}[!]  Insufficient messages, cannot summarize{self.RESET}")

    def history_summary_generated(self, *, round_num: int) -> None:
        self._write(f"{self.BRIGHT_GREEN}[OK] Summary for round {round_num} generated successfully{self.RESET}")

    def history_summary_generation_failed(self, *, round_num: int, error: str) -> None:
        self._write(f"{self.BRIGHT_RED}[X] Summary generation failed for round {round_num}: {error}{self.RESET}")

    def history_summary_completed(
        self,
        *,
        estimated_tokens: int,
        compacted_tokens: int,
        user_message_count: int,
        summary_message_count: int,
    ) -> None:
        self._write(
            f"{self.BRIGHT_GREEN}[OK] Summary completed, local tokens: {estimated_tokens} -> {compacted_tokens}{self.RESET}"
        )
        self._write(
            f"{self.DIM}  Structure: system + {user_message_count} user messages + {summary_message_count} summaries{self.RESET}"
        )
        self._write(f"{self.DIM}  Note: API token count will update on next LLM call{self.RESET}")


__all__ = [
    "AgentRuntimePresenter",
    "AnsiConsoleAgentRuntimePresenter",
    "NullAgentRuntimePresenter",
]
