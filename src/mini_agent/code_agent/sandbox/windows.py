"""Windows restricted-token sandbox baseline for code-agent execution."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

from mini_agent.code_agent.sandbox.network import NetworkDomainPolicy


_ELEVATION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bstart-process\b[^\n]*\s-verb\s+runas\b", re.IGNORECASE), "runas_elevation"),
    (re.compile(r"\bset-executionpolicy\b", re.IGNORECASE), "execution_policy_mutation"),
    (re.compile(r"\breg(\.exe)?\s+add\s+HKLM\\", re.IGNORECASE), "hklm_registry_write"),
    (re.compile(r"\bsc(\.exe)?\s+", re.IGNORECASE), "service_control"),
    (re.compile(r"\bshutdown\b|\brestart-computer\b", re.IGNORECASE), "host_shutdown"),
)


def _normalize_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except Exception:
        return False


@dataclass(frozen=True)
class SandboxTransformResult:
    """Transformed command payload for sandbox-aware execution."""

    command: str
    cwd: str | None
    env_overrides: dict[str, str]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class WindowsSandboxPolicy:
    """Windows sandbox policy baseline."""

    workspace_root: str
    readable_roots: tuple[str, ...] = field(default_factory=tuple)
    writable_roots: tuple[str, ...] = field(default_factory=tuple)
    restricted_token: bool = True
    enforce_no_profile: bool = True
    deny_elevation: bool = True
    network_policy: NetworkDomainPolicy = field(default_factory=NetworkDomainPolicy)

    @staticmethod
    def from_workspace(
        workspace_root: str | Path,
        *,
        network_policy: NetworkDomainPolicy | None = None,
    ) -> "WindowsSandboxPolicy":
        root = _normalize_path(workspace_root)
        return WindowsSandboxPolicy(
            workspace_root=str(root),
            readable_roots=(str(root),),
            writable_roots=(str(root),),
            network_policy=(network_policy or NetworkDomainPolicy()).normalized(),
        )

    def normalized(self) -> "WindowsSandboxPolicy":
        workspace_root = str(_normalize_path(self.workspace_root))
        readable = {
            str(_normalize_path(value))
            for value in self.readable_roots
            if str(value).strip()
        }
        writable = {
            str(_normalize_path(value))
            for value in self.writable_roots
            if str(value).strip()
        }
        if not readable:
            readable = {workspace_root}
        if not writable:
            writable = {workspace_root}
        return WindowsSandboxPolicy(
            workspace_root=workspace_root,
            readable_roots=tuple(sorted(readable)),
            writable_roots=tuple(sorted(writable)),
            restricted_token=bool(self.restricted_token),
            enforce_no_profile=bool(self.enforce_no_profile),
            deny_elevation=bool(self.deny_elevation),
            network_policy=self.network_policy.normalized(),
        )


class WindowsRestrictedSandbox:
    """Windows command sandbox with lightweight policy validation."""

    def __init__(self, policy: WindowsSandboxPolicy):
        self.policy = policy.normalized()

    def select_initial(self) -> dict[str, Any]:
        return {
            "backend": "windows_restricted_token",
            "restricted_token": self.policy.restricted_token,
            "workspace_root": self.policy.workspace_root,
            "network_mode": self.policy.network_policy.mode.value,
        }

    def validate_cwd(self, cwd: str | Path | None) -> str | None:
        if cwd is None:
            return None
        normalized_cwd = _normalize_path(cwd)
        allowed_roots = [Path(value) for value in self.policy.writable_roots]
        if not any(_is_relative_to(normalized_cwd, root) for root in allowed_roots):
            raise PermissionError(
                f"cwd '{normalized_cwd}' is outside writable sandbox roots: {self.policy.writable_roots}"
            )
        return str(normalized_cwd)

    def _check_elevation(self, command: str) -> None:
        if not self.policy.deny_elevation:
            return
        for pattern, reason in _ELEVATION_PATTERNS:
            if pattern.search(command):
                raise PermissionError(f"Blocked by Windows sandbox elevated-command policy: {reason}")

    def _check_network(self, command: str) -> None:
        allowed, blocked = self.policy.network_policy.validate_command(command)
        if not allowed:
            raise PermissionError(
                f"Blocked by Windows sandbox network policy ({self.policy.network_policy.mode.value}): {blocked}"
            )

    def transform(
        self,
        command: str,
        *,
        cwd: str | Path | None = None,
    ) -> SandboxTransformResult:
        normalized_command = str(command or "").strip()
        if not normalized_command:
            raise ValueError("command must not be empty.")

        self._check_elevation(normalized_command)
        self._check_network(normalized_command)
        normalized_cwd = self.validate_cwd(cwd)

        prefix_parts = [
            "$ErrorActionPreference='Stop'",
            "$ProgressPreference='SilentlyContinue'",
        ]
        if self.policy.enforce_no_profile:
            prefix_parts.append("$env:MINI_AGENT_SANDBOX_PROFILE='no_profile'")
        wrapped = "; ".join(prefix_parts + [normalized_command])

        env_overrides = {
            "MINI_AGENT_SANDBOX_BACKEND": "windows_restricted_token",
            "MINI_AGENT_SANDBOX_RESTRICTED_TOKEN": "1" if self.policy.restricted_token else "0",
            "MINI_AGENT_SANDBOX_WORKSPACE": self.policy.workspace_root,
            "MINI_AGENT_SANDBOX_NETWORK_MODE": self.policy.network_policy.mode.value,
        }

        return SandboxTransformResult(
            command=wrapped,
            cwd=normalized_cwd,
            env_overrides=env_overrides,
            metadata={
                "backend": "windows_restricted_token",
                "restricted_token": self.policy.restricted_token,
                "readable_roots": list(self.policy.readable_roots),
                "writable_roots": list(self.policy.writable_roots),
                "network_mode": self.policy.network_policy.mode.value,
            },
        )
