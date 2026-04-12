"""Runtime safety policy engine for tool execution."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable

from mini_agent.tools.base import Tool


APPROVAL_PROFILES = ("plan", "build")
ACCESS_LEVELS = ("default", "full-access")
SANDBOX_MODES = ("workspace", "unrestricted")
ELEVATED_EXEC_MODES = ("deny", "require_approval", "allow")
_TOKEN_PATTERN = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|\S+')
_DESTRUCTIVE_POWERSHELL_COMMANDS = frozenset({"remove-item", "ri"})
_DESTRUCTIVE_SHELL_COMMANDS = frozenset({"rm", "del", "erase", "rd", "rmdir", "unlink"})
_POWERSHELL_PATH_OPTIONS = frozenset({"-path", "-literalpath"})


def _normalize_list(values: Iterable[str] | None) -> set[str]:
    if values is None:
        return set()
    normalized: set[str] = set()
    for value in values:
        name = str(value).strip()
        if name:
            normalized.add(name)
    return normalized


def _to_profile(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    if candidate in APPROVAL_PROFILES:
        return candidate
    return "build"


def _to_access_level(value: str | None) -> str:
    candidate = (value or "").strip().lower()
    if candidate in ACCESS_LEVELS:
        return candidate
    return "default"


@dataclass
class RuntimePolicy:
    approval_profile: str
    access_level: str
    sandbox_mode: str
    elevated_exec: str
    tool_allow: set[str]
    tool_exclude: set[str]

    def is_tool_allowed(self, tool_name: str) -> bool:
        if self.tool_allow and tool_name not in self.tool_allow:
            return False
        if tool_name in self.tool_exclude:
            return False
        return True


@dataclass(frozen=True)
class BashCommandPolicyDecision:
    allowed: bool
    reason: str | None = None
    requires_approval: bool = False
    elevated: bool = False
    host_access_required: bool = False


def _strip_matching_quotes(value: str) -> str:
    text = str(value or "").strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {"'", '"'}:
        return text[1:-1]
    return text


def _split_shell_clauses(command: str) -> list[str]:
    clauses: list[str] = []
    buffer: list[str] = []
    quote: str | None = None
    index = 0
    text = str(command or "")
    while index < len(text):
        char = text[index]
        next_two = text[index : index + 2]
        if quote is not None:
            buffer.append(char)
            if char == quote:
                quote = None
            index += 1
            continue
        if char in {"'", '"'}:
            quote = char
            buffer.append(char)
            index += 1
            continue
        if next_two in {"&&", "||"}:
            clause = "".join(buffer).strip()
            if clause:
                clauses.append(clause)
            buffer = []
            index += 2
            continue
        if char in {";", "\n", "|"}:
            clause = "".join(buffer).strip()
            if clause:
                clauses.append(clause)
            buffer = []
            index += 1
            continue
        buffer.append(char)
        index += 1
    clause = "".join(buffer).strip()
    if clause:
        clauses.append(clause)
    return clauses


def _tokenize_clause(command: str) -> list[str]:
    return _TOKEN_PATTERN.findall(str(command or ""))


def _classify_workspace_escape_target(target: str) -> str | None:
    candidate = _strip_matching_quotes(target)
    if not candidate:
        return None
    normalized = candidate.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if re.match(r"^[A-Za-z]:[\\/]", candidate):
        return f"Detected destructive shell target on absolute path '{candidate}'."
    if candidate.startswith("\\\\"):
        return f"Detected destructive shell target on UNC path '{candidate}'."
    if candidate.startswith("/"):
        return f"Detected destructive shell target on absolute path '{candidate}'."
    if normalized == "~" or normalized.startswith("~/"):
        return f"Detected destructive shell target on home path '{candidate}'."
    if normalized == ".." or normalized.startswith("../") or "/../" in normalized:
        return f"Detected destructive shell target using parent traversal '{candidate}'."
    return None


def _extract_destructive_targets_from_clause(clause: str) -> list[str]:
    tokens = _tokenize_clause(clause)
    if not tokens:
        return []
    command_name = _strip_matching_quotes(tokens[0]).lower()
    if command_name in _DESTRUCTIVE_POWERSHELL_COMMANDS:
        targets: list[str] = []
        index = 1
        while index < len(tokens):
            token = _strip_matching_quotes(tokens[index])
            lowered = token.lower()
            if lowered in _POWERSHELL_PATH_OPTIONS:
                if index + 1 < len(tokens):
                    targets.append(_strip_matching_quotes(tokens[index + 1]))
                    index += 2
                    continue
                break
            if token.startswith("-"):
                index += 1
                continue
            targets.append(token)
            index += 1
        return targets
    if command_name in _DESTRUCTIVE_SHELL_COMMANDS:
        targets = []
        option_prefixes = ("-", "/") if command_name in {"del", "erase", "rd", "rmdir"} else ("-",)
        for token in tokens[1:]:
            stripped = _strip_matching_quotes(token)
            if not stripped:
                continue
            if stripped.startswith(option_prefixes):
                continue
            targets.append(stripped)
        return targets
    return []


def _profile_defaults(profile: str, access_level: str) -> tuple[str, str, set[str]]:
    default_sandbox = "unrestricted" if access_level == "full-access" else "workspace"
    default_elevated = "allow" if access_level == "full-access" else "require_approval"
    if profile == "plan":
        return (
            default_sandbox,
            default_elevated,
            {
                "bash",
                "bash_output",
                "bash_kill",
                "write_file",
                "edit_file",
                "record_note",
                "user_modeling",
                "install_skill",
                "install_skill_from_path",
                "uninstall_skill",
                "rollback_skill",
            },
        )
    return (default_sandbox, default_elevated, set())


class RuntimePolicyEngine:
    """Three-layer runtime policy: sandbox/tool/elevated execution."""

    _ELEVATED_PATTERNS = (
        (re.compile(r"\bsudo\b", re.IGNORECASE), "Detected sudo privilege escalation."),
        (re.compile(r"\bset-executionpolicy\b", re.IGNORECASE), "Detected PowerShell execution-policy change."),
        (re.compile(r"\bnetsh\b", re.IGNORECASE), "Detected network stack mutation command."),
        (re.compile(r"\bsc(\.exe)?\s+", re.IGNORECASE), "Detected Windows service control command."),
        (re.compile(r"\bshutdown\b|\breboot\b", re.IGNORECASE), "Detected host shutdown/reboot command."),
        (re.compile(r"\bmount\b|\bumount\b", re.IGNORECASE), "Detected filesystem mount operation."),
        (re.compile(r"\bchmod\s+[0-7]{3,4}\s+/", re.IGNORECASE), "Detected privileged chmod on root path."),
        (re.compile(r"\buseradd\b|\bpasswd\b", re.IGNORECASE), "Detected user management command."),
    )

    def __init__(self, policy: RuntimePolicy):
        self.policy = policy

    @classmethod
    def from_config(
        cls,
        config,
        approval_profile_override: str | None = None,
        access_level_override: str | None = None,
    ) -> "RuntimePolicyEngine":
        env_profile = os.getenv("MINI_AGENT_APPROVAL_PROFILE") or os.getenv("MINI_AGENT_AGENT_MODE")
        env_access_level = os.getenv("MINI_AGENT_ACCESS_LEVEL")
        profile = _to_profile(approval_profile_override or env_profile or config.security.approval_profile)
        access_level = _to_access_level(
            access_level_override or env_access_level or getattr(config.security, "access_level", None)
        )
        default_sandbox, default_elevated, default_exclude = _profile_defaults(profile, access_level)

        sandbox_mode = (config.security.sandbox_mode or default_sandbox).strip().lower()
        if sandbox_mode not in SANDBOX_MODES:
            sandbox_mode = default_sandbox

        elevated_exec = (config.security.elevated_exec or default_elevated).strip().lower()
        if elevated_exec not in ELEVATED_EXEC_MODES:
            elevated_exec = default_elevated

        tool_allow = _normalize_list(config.security.tool_allow)
        tool_exclude = default_exclude | _normalize_list(config.security.tool_exclude)

        return cls(
            RuntimePolicy(
                approval_profile=profile,
                access_level=access_level,
                sandbox_mode=sandbox_mode,
                elevated_exec=elevated_exec,
                tool_allow=tool_allow,
                tool_exclude=tool_exclude,
            )
        )

    def is_tool_allowed(self, tool_name: str) -> bool:
        return self.policy.is_tool_allowed(tool_name)

    def filter_tools(self, tools: list[Tool]) -> list[Tool]:
        return [tool for tool in tools if self.is_tool_allowed(tool.name)]

    def inspect_bash_command(
        self,
        command: str,
        run_in_background: bool = False,
    ) -> BashCommandPolicyDecision:
        if self.policy.approval_profile == "plan":
            return BashCommandPolicyDecision(
                allowed=False,
                reason="Execution mode 'plan' blocks shell command execution.",
            )

        if run_in_background and self.policy.access_level != "full-access":
            # Keep default access conservative: avoid unattended host processes.
            return BashCommandPolicyDecision(
                allowed=False,
                reason="Access level 'default' blocks background shell processes.",
            )

        elevated_reason = self._detect_elevated_command(command)
        if elevated_reason:
            if self.policy.elevated_exec == "allow":
                return BashCommandPolicyDecision(
                    allowed=True,
                    reason=None,
                    elevated=True,
                )
            if self.policy.elevated_exec == "require_approval":
                return BashCommandPolicyDecision(
                    allowed=True,
                    reason=f"Elevated shell command requires approval: {elevated_reason}",
                    requires_approval=True,
                    elevated=True,
                    host_access_required=True,
                )
            return BashCommandPolicyDecision(
                allowed=False,
                reason=f"Blocked by elevated-exec policy: {elevated_reason}",
                elevated=True,
            )

        if self.policy.sandbox_mode == "workspace":
            escape_reason = self._detect_workspace_escape(command)
            if escape_reason:
                return BashCommandPolicyDecision(
                    allowed=True,
                    reason=f"Shell command requires full-access approval: {escape_reason}",
                    requires_approval=True,
                    host_access_required=True,
                )

        return BashCommandPolicyDecision(allowed=True)

    def check_bash_command(self, command: str, run_in_background: bool = False) -> tuple[bool, str | None]:
        decision = self.inspect_bash_command(
            command,
            run_in_background=run_in_background,
        )
        if not decision.allowed:
            return False, decision.reason
        if decision.requires_approval:
            return False, decision.reason or "Shell command requires approval."
        return True, decision.reason

    def _detect_elevated_command(self, command: str) -> str | None:
        for pattern, reason in self._ELEVATED_PATTERNS:
            if pattern.search(command):
                return reason
        return None

    def _detect_workspace_escape(self, command: str) -> str | None:
        for clause in _split_shell_clauses(command):
            for target in _extract_destructive_targets_from_clause(clause):
                reason = _classify_workspace_escape_target(target)
                if reason:
                    return reason
        return None

