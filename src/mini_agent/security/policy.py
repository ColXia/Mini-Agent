"""Runtime safety policy engine for tool execution."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable

from mini_agent.tools.base import Tool


APPROVAL_PROFILES = ("suggest", "auto-edit", "full-auto")
SANDBOX_MODES = ("workspace", "unrestricted")
ELEVATED_EXEC_MODES = ("deny", "require_approval", "allow")


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
    return "auto-edit"


@dataclass
class RuntimePolicy:
    approval_profile: str
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


def _profile_defaults(profile: str) -> tuple[str, str, set[str]]:
    if profile == "suggest":
        return ("workspace", "deny", {"bash", "bash_output", "bash_kill"})
    if profile == "full-auto":
        return ("unrestricted", "allow", set())
    return ("workspace", "require_approval", set())


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

    _DESTRUCTIVE_WORKSPACE_ESCAPE_PATTERNS = (
        (re.compile(r"\brm\s+-rf\s+/\b", re.IGNORECASE), "Detected root-level destructive remove."),
        (re.compile(r"\brm\s+-rf\s+~/?\b", re.IGNORECASE), "Detected home-level destructive remove."),
        (
            re.compile(r"\bremove-item\b[^\n]*-recurse[^\n]*(?:\s/[A-Za-z]?|[A-Za-z]:\\|\\\\)", re.IGNORECASE),
            "Detected recursive Remove-Item outside workspace scope.",
        ),
        (
            re.compile(r"\b(del|erase)\b[^\n]*(?:[A-Za-z]:\\|\\\\|/)", re.IGNORECASE),
            "Detected delete command on absolute path.",
        ),
    )

    def __init__(self, policy: RuntimePolicy):
        self.policy = policy

    @classmethod
    def from_config(cls, config, approval_profile_override: str | None = None) -> "RuntimePolicyEngine":
        env_profile = os.getenv("MINI_AGENT_APPROVAL_PROFILE")
        profile = _to_profile(approval_profile_override or env_profile or config.security.approval_profile)
        default_sandbox, default_elevated, default_exclude = _profile_defaults(profile)

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

    def check_bash_command(self, command: str, run_in_background: bool = False) -> tuple[bool, str | None]:
        if self.policy.approval_profile == "suggest":
            return False, "Approval profile 'suggest' blocks shell command execution."

        if run_in_background and self.policy.approval_profile == "auto-edit":
            # Keep auto-edit conservative: avoid unattended long-running host processes.
            return False, "Approval profile 'auto-edit' blocks background shell processes."

        elevated_reason = self._detect_elevated_command(command)
        if elevated_reason:
            if self.policy.elevated_exec == "allow":
                return True, None
            if self.policy.elevated_exec == "require_approval":
                return False, f"Blocked by elevated-exec policy (requires approval): {elevated_reason}"
            return False, f"Blocked by elevated-exec policy: {elevated_reason}"

        if self.policy.sandbox_mode == "workspace":
            escape_reason = self._detect_workspace_escape(command)
            if escape_reason:
                return False, f"Blocked by workspace sandbox policy: {escape_reason}"

        return True, None

    def _detect_elevated_command(self, command: str) -> str | None:
        for pattern, reason in self._ELEVATED_PATTERNS:
            if pattern.search(command):
                return reason
        return None

    def _detect_workspace_escape(self, command: str) -> str | None:
        for pattern, reason in self._DESTRUCTIVE_WORKSPACE_ESCAPE_PATTERNS:
            if pattern.search(command):
                return reason
        return None

