"""Tests for P14 T2.2 agent-core execution sandbox baseline."""

from __future__ import annotations

from pathlib import Path
import platform

import pytest

if platform.system() == "Windows":
    import win32api
    import win32con
    import win32job
    import win32security
else:  # pragma: no cover - import only on Windows
    win32api = None
    win32con = None
    win32job = None
    win32security = None

from mini_agent.agent_core.execution.sandbox.manager import SandboxBackend, SandboxManager
from mini_agent.agent_core.execution.sandbox.network import (
    NetworkAccessMode,
    NetworkDomainPolicy,
    extract_domains_from_command,
)
from mini_agent.agent_core.execution.sandbox.windows import WindowsRestrictedSandbox, WindowsSandboxPolicy


def test_extract_domains_from_command_detects_urls_and_hosts():
    command = "curl https://api.openai.com/v1/models ; ping github.com ; Invoke-WebRequest https://sub.example.org/path"
    domains = extract_domains_from_command(command)
    assert "api.openai.com" in domains
    assert "github.com" in domains
    assert "sub.example.org" in domains


def test_network_policy_allowlist_blocks_unknown_domain():
    policy = NetworkDomainPolicy(
        mode=NetworkAccessMode.ALLOWLIST,
        allow_domains=("api.openai.com",),
    )
    allowed, blocked = policy.validate_command("curl https://api.openai.com/v1/models")
    assert allowed is True
    assert blocked == []

    allowed, blocked = policy.validate_command("curl https://evil.example.com/x")
    assert allowed is False
    assert blocked == ["evil.example.com"]


def test_windows_restricted_sandbox_blocks_elevated_command(tmp_path: Path):
    policy = WindowsSandboxPolicy.from_workspace(tmp_path)
    sandbox = WindowsRestrictedSandbox(policy)

    with pytest.raises(PermissionError, match="elevated-command"):
        sandbox.transform("Start-Process -Verb RunAs notepad.exe", cwd=tmp_path)


def test_windows_restricted_sandbox_blocks_disallowed_network_domain(tmp_path: Path):
    policy = WindowsSandboxPolicy.from_workspace(
        tmp_path,
        network_policy=NetworkDomainPolicy(
            mode=NetworkAccessMode.ALLOWLIST,
            allow_domains=("api.openai.com",),
        ),
    )
    sandbox = WindowsRestrictedSandbox(policy)

    with pytest.raises(PermissionError, match="network policy"):
        sandbox.transform("Invoke-WebRequest https://example.com", cwd=tmp_path)


def test_windows_restricted_sandbox_transforms_safe_command(tmp_path: Path):
    policy = WindowsSandboxPolicy.from_workspace(tmp_path)
    sandbox = WindowsRestrictedSandbox(policy)

    transformed = sandbox.transform("Get-ChildItem", cwd=tmp_path)
    assert "Get-ChildItem" in transformed.command
    assert transformed.cwd == str(tmp_path.resolve())
    assert transformed.env_overrides["MINI_AGENT_SANDBOX_BACKEND"] == "windows_restricted_token"
    assert transformed.env_overrides["MINI_AGENT_SANDBOX_RESTRICTED_TOKEN"] == "1"
    assert transformed.env_overrides["MINI_AGENT_SANDBOX_NATIVE_LAUNCH"] == "1"
    assert transformed.env_overrides["MINI_AGENT_SANDBOX_INTEGRITY_LEVEL"] == "low"
    assert transformed.env_overrides["MINI_AGENT_SANDBOX_MANDATORY_POLICY"] == "3"
    assert transformed.metadata["backend"] == "windows_restricted_token"
    assert transformed.metadata["low_integrity"] is True
    assert transformed.metadata["mandatory_policy"] == 3
    assert transformed.metadata["disable_admin_groups"] is True
    assert transformed.metadata["restrict_ui"] is True
    assert transformed.metadata["die_on_unhandled_exception"] is True
    assert transformed.metadata["max_processes"] == 32
    assert transformed.metadata["max_process_memory_mb"] == 2048
    assert transformed.env_overrides["MINI_AGENT_SANDBOX_MAX_PROCESSES"] == "32"
    assert transformed.env_overrides["MINI_AGENT_SANDBOX_PROCESS_MEMORY_MB"] == "2048"


def test_sandbox_manager_selects_windows_backend_and_transforms(tmp_path: Path):
    manager = SandboxManager(
        workspace_dir=tmp_path,
        sandbox_mode="workspace",
        runtime_platform="Windows",
    )
    selection = manager.select_initial()
    assert selection.backend == SandboxBackend.WINDOWS_RESTRICTED_TOKEN
    assert selection.metadata["low_integrity"] is True
    assert selection.metadata["mandatory_policy"] == 3
    assert selection.metadata["disable_admin_groups"] is True
    assert selection.metadata["restrict_ui"] is True
    assert selection.metadata["die_on_unhandled_exception"] is True
    assert selection.metadata["max_processes"] == 32
    assert selection.metadata["max_process_memory_mb"] == 2048
    transformed = manager.transform("Get-ChildItem", cwd=tmp_path)
    assert transformed.metadata["backend"] == "windows_restricted_token"


def test_windows_policy_normalization_keeps_new_restriction_defaults(tmp_path: Path):
    policy = WindowsSandboxPolicy.from_workspace(tmp_path).normalized()

    assert policy.low_integrity is True
    assert policy.disable_admin_groups is True
    assert policy.restrict_ui is True
    assert policy.die_on_unhandled_exception is True
    assert policy.max_processes == 32
    assert policy.max_process_memory_mb == 2048


def test_windows_policy_normalization_allows_disabling_resource_caps(tmp_path: Path):
    policy = WindowsSandboxPolicy.from_workspace(
        tmp_path,
        max_processes=0,
        max_process_memory_mb=0,
    ).normalized()

    assert policy.max_processes is None
    assert policy.max_process_memory_mb is None


@pytest.mark.skipif(platform.system() != "Windows", reason="Windows-only native sandbox test")
@pytest.mark.asyncio
async def test_windows_restricted_sandbox_launch_process_executes_command(tmp_path: Path):
    policy = WindowsSandboxPolicy.from_workspace(tmp_path)
    sandbox = WindowsRestrictedSandbox(policy)

    process = sandbox.launch_process(
        ["powershell.exe", "-NoProfile", "-Command", "Write-Output sandbox-ok"],
        cwd=tmp_path,
        env={"MINI_AGENT_SANDBOX_BACKEND": "windows_restricted_token"},
        merge_stderr=False,
    )

    token = win32security.OpenProcessToken(process._process_handle, win32con.TOKEN_QUERY)
    integrity_sid, _attributes = win32security.GetTokenInformation(
        token,
        win32security.TokenIntegrityLevel,
    )
    mandatory_policy = win32security.GetTokenInformation(
        token,
        win32security.TokenMandatoryPolicy,
    )
    low_sid = win32security.CreateWellKnownSid(win32security.WinLowLabelSid, None)
    job_info = win32job.QueryInformationJobObject(
        process._job_handle,
        win32job.JobObjectExtendedLimitInformation,
    )
    limit_flags = int(job_info["BasicLimitInformation"]["LimitFlags"])

    assert win32security.ConvertSidToStringSid(integrity_sid) == (
        win32security.ConvertSidToStringSid(low_sid)
    )
    assert mandatory_policy == 3
    assert limit_flags & win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
    assert job_info["BasicLimitInformation"]["ActiveProcessLimit"] == policy.max_processes
    assert limit_flags & win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
    assert job_info["ProcessMemoryLimit"] == policy.max_process_memory_mb * 1024 * 1024

    stdout, stderr = await process.communicate()

    assert b"sandbox-ok" in stdout
    assert stderr == b""


def test_sandbox_manager_unrestricted_mode_uses_passthrough_backend(tmp_path: Path):
    manager = SandboxManager(
        workspace_dir=tmp_path,
        sandbox_mode="unrestricted",
        runtime_platform="Windows",
    )
    selection = manager.select_initial()
    assert selection.backend == SandboxBackend.NONE

    transformed = manager.transform("Write-Output 'ok'", cwd=tmp_path)
    assert transformed.metadata["backend"] == "none"
    assert transformed.command == "Write-Output 'ok'"
    assert transformed.cwd == str(tmp_path.resolve())
