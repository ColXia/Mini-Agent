"""Sandbox backend selector and command transformer."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path
import platform
from typing import Any

from mini_agent.code_agent.sandbox.network import NetworkDomainPolicy
from mini_agent.code_agent.sandbox.windows import (
    SandboxTransformResult,
    WindowsRestrictedSandbox,
    WindowsSandboxPolicy,
)


class SandboxBackend(str, Enum):
    """Sandbox backend names."""

    NONE = "none"
    WINDOWS_RESTRICTED_TOKEN = "windows_restricted_token"


@dataclass(frozen=True)
class SandboxSelection:
    """Selected sandbox backend metadata."""

    backend: SandboxBackend
    reason: str
    metadata: dict[str, Any]


class SandboxManager:
    """Sandbox selection and command transform entrypoint."""

    def __init__(
        self,
        *,
        workspace_dir: str | Path,
        sandbox_mode: str = "workspace",
        runtime_platform: str | None = None,
        network_policy: NetworkDomainPolicy | None = None,
    ):
        self.workspace_dir = str(Path(workspace_dir).expanduser().resolve())
        self.sandbox_mode = str(sandbox_mode).strip().lower() or "workspace"
        self.runtime_platform = (runtime_platform or platform.system()).strip().lower()
        self.network_policy = (network_policy or NetworkDomainPolicy()).normalized()

        self._selection = self._select_initial_unlocked()
        if self._selection.backend == SandboxBackend.WINDOWS_RESTRICTED_TOKEN:
            self._windows_backend = WindowsRestrictedSandbox(
                WindowsSandboxPolicy.from_workspace(
                    self.workspace_dir,
                    network_policy=self.network_policy,
                )
            )
        else:
            self._windows_backend = None

    def _select_initial_unlocked(self) -> SandboxSelection:
        if self.sandbox_mode == "unrestricted":
            return SandboxSelection(
                backend=SandboxBackend.NONE,
                reason="sandbox_mode_unrestricted",
                metadata={
                    "sandbox_mode": self.sandbox_mode,
                    "workspace_root": self.workspace_dir,
                },
            )

        if self.runtime_platform == "windows":
            preview = WindowsSandboxPolicy.from_workspace(
                self.workspace_dir,
                network_policy=self.network_policy,
            ).normalized()
            return SandboxSelection(
                backend=SandboxBackend.WINDOWS_RESTRICTED_TOKEN,
                reason="windows_workspace_sandbox",
                metadata={
                    "sandbox_mode": self.sandbox_mode,
                    "workspace_root": preview.workspace_root,
                    "network_mode": preview.network_policy.mode.value,
                    "restricted_token": preview.restricted_token,
                },
            )

        return SandboxSelection(
            backend=SandboxBackend.NONE,
            reason="non_windows_runtime",
            metadata={
                "sandbox_mode": self.sandbox_mode,
                "workspace_root": self.workspace_dir,
                "runtime_platform": self.runtime_platform,
            },
        )

    def select_initial(self) -> SandboxSelection:
        return self._selection

    def transform(
        self,
        command: str,
        *,
        cwd: str | Path | None = None,
    ) -> SandboxTransformResult:
        if self._selection.backend == SandboxBackend.WINDOWS_RESTRICTED_TOKEN:
            assert self._windows_backend is not None
            return self._windows_backend.transform(command, cwd=cwd)

        normalized_cwd = None
        if cwd is not None:
            normalized_cwd = str(Path(cwd).expanduser().resolve())
        return SandboxTransformResult(
            command=str(command or "").strip(),
            cwd=normalized_cwd,
            env_overrides={
                "MINI_AGENT_SANDBOX_BACKEND": SandboxBackend.NONE.value,
            },
            metadata={
                "backend": SandboxBackend.NONE.value,
                "reason": self._selection.reason,
            },
        )

