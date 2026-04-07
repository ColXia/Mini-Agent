"""Tests for P14 T2.2 code-agent sandbox baseline."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.code_agent.sandbox import (
    NetworkAccessMode,
    NetworkDomainPolicy,
    SandboxBackend,
    SandboxManager,
    WindowsRestrictedSandbox,
    WindowsSandboxPolicy,
    extract_domains_from_command,
)


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
    assert transformed.metadata["backend"] == "windows_restricted_token"


def test_sandbox_manager_selects_windows_backend_and_transforms(tmp_path: Path):
    manager = SandboxManager(
        workspace_dir=tmp_path,
        sandbox_mode="workspace",
        runtime_platform="Windows",
    )
    selection = manager.select_initial()
    assert selection.backend == SandboxBackend.WINDOWS_RESTRICTED_TOKEN
    transformed = manager.transform("Get-ChildItem", cwd=tmp_path)
    assert transformed.metadata["backend"] == "windows_restricted_token"


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

