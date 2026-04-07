"""Tests for runtime policy engine and bash policy gates."""

import platform

import pytest

from mini_agent.config import AgentConfig, Config, LLMConfig, SecurityConfig, ToolsConfig
from mini_agent.runtime.tooling import resolve_runtime_policy
from mini_agent.tools.bash_tool import BashTool
from mini_agent.tools.file_tools import ReadTool, WriteTool


def _make_config(security: SecurityConfig | None = None) -> Config:
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_mcp=False, enable_skills=False),
        security=security or SecurityConfig(),
    )


@pytest.mark.asyncio
async def test_suggest_profile_blocks_bash_execution(tmp_path):
    config = _make_config(SecurityConfig(approval_profile="suggest"))
    engine = resolve_runtime_policy(config)
    bash = BashTool(workspace_dir=str(tmp_path), policy_engine=engine)

    command = "Write-Output 'hello'" if platform.system() == "Windows" else "echo 'hello'"
    result = await bash.execute(command=command)

    assert not result.success
    assert "suggest" in (result.error or "").lower()


def test_auto_edit_blocks_elevated_commands():
    config = _make_config(SecurityConfig(approval_profile="auto-edit"))
    engine = resolve_runtime_policy(config)

    allowed, reason = engine.check_bash_command("sudo ls")
    assert allowed is False
    assert reason is not None
    assert "elevated" in reason.lower() or "approval" in reason.lower()


def test_full_auto_allows_elevated_commands():
    config = _make_config(SecurityConfig(approval_profile="full-auto"))
    engine = resolve_runtime_policy(config)

    allowed, reason = engine.check_bash_command("sudo ls")
    assert allowed is True
    assert reason is None


def test_tool_allowlist_filters_tools(tmp_path):
    config = _make_config(SecurityConfig(approval_profile="auto-edit", tool_allow=["read_file"]))
    engine = resolve_runtime_policy(config)

    tools = [
        ReadTool(workspace_dir=str(tmp_path)),
        WriteTool(workspace_dir=str(tmp_path)),
    ]
    filtered = engine.filter_tools(tools)

    assert len(filtered) == 1
    assert filtered[0].name == "read_file"
