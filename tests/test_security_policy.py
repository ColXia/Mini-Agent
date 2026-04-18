"""Tests for runtime policy engine and bash policy gates."""

import platform

import pytest

from mini_agent.agent_core.execution import PermissionDecision, ToolBuilder, ToolKind
from mini_agent.agent_core.execution.tools import DeclarativeToolAttributes
from mini_agent.config import AgentConfig, Config, LLMConfig, SecurityConfig, ToolsConfig
from mini_agent.agent_core.execution.sandbox import NetworkAccessMode
from mini_agent.runtime.tooling import (
    add_workspace_tools,
    build_approval_engine,
    build_workspace_sandbox_manager,
    resolve_runtime_policy,
)
from mini_agent.tools.base import ToolResult
from mini_agent.tools.bash_tool import BashTool
from mini_agent.tools.file_tools import EditTool, ReadTool, WriteTool


@pytest.fixture(autouse=True)
def _clear_runtime_policy_env(monkeypatch):
    for name in (
        "MINI_AGENT_APPROVAL_PROFILE",
        "MINI_AGENT_AGENT_MODE",
        "MINI_AGENT_ACCESS_LEVEL",
    ):
        monkeypatch.delenv(name, raising=False)


def _make_config(security: SecurityConfig | None = None) -> Config:
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_mcp=False, enable_skills=False),
        security=security or SecurityConfig(),
    )


def _build_invocation(*, tool_name: str, kind: ToolKind, is_read_only: bool):
    declarative = ToolBuilder.from_callable(
        name=tool_name,
        description=f"tool {tool_name}",
        schema={
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        execute=lambda _args: ToolResult(success=True, content="ok"),
        attributes=DeclarativeToolAttributes(kind=kind, is_read_only=is_read_only),
    )
    return declarative.build({"value": "x"})


@pytest.mark.asyncio
async def test_plan_mode_blocks_bash_execution(tmp_path):
    config = _make_config(SecurityConfig(approval_profile="plan"))
    engine = resolve_runtime_policy(config)
    bash = BashTool(workspace_dir=str(tmp_path), policy_engine=engine)

    command = "Write-Output 'hello'" if platform.system() == "Windows" else "echo 'hello'"
    result = await bash.execute(command=command)

    assert not result.success
    assert "plan" in (result.error or "").lower()


def test_build_default_elevated_commands_require_approval():
    config = _make_config(SecurityConfig(approval_profile="build", access_level="default"))
    engine = resolve_runtime_policy(config)

    decision = engine.inspect_bash_command("sudo ls")
    assert decision.allowed is True
    assert decision.requires_approval is True
    assert decision.reason is not None
    assert "approval" in decision.reason.lower()


def test_build_full_access_allows_elevated_commands():
    config = _make_config(SecurityConfig(approval_profile="build", access_level="full-access"))
    engine = resolve_runtime_policy(config)

    allowed, reason = engine.check_bash_command("sudo ls")
    assert allowed is True
    assert reason is None


def test_build_default_requires_approval_for_destructive_shell_targets_outside_workspace():
    config = _make_config(
        SecurityConfig(
            approval_profile="build",
            access_level="default",
            sandbox_mode="workspace",
        )
    )
    engine = resolve_runtime_policy(config)

    for command in (
        r"Remove-Item ..\outside\victim.txt -Force",
        r"Remove-Item C:\temp\victim.txt -Force",
        r"del ..\outside\victim.txt",
        r"rm ../outside/victim.txt",
    ):
        decision = engine.inspect_bash_command(command)
        assert decision.allowed is True
        assert decision.requires_approval is True
        assert decision.host_access_required is True
        assert "approval" in (decision.reason or "").lower()


def test_build_default_allows_destructive_shell_targets_inside_workspace_without_approval():
    config = _make_config(
        SecurityConfig(
            approval_profile="build",
            access_level="default",
            sandbox_mode="workspace",
        )
    )
    engine = resolve_runtime_policy(config)

    decision = engine.inspect_bash_command(r"Remove-Item .\victim.txt -Force")

    assert decision.allowed is True
    assert decision.requires_approval is False
    assert decision.host_access_required is False


def test_tool_allowlist_filters_tools(tmp_path):
    config = _make_config(SecurityConfig(approval_profile="build", tool_allow=["read_file"]))
    engine = resolve_runtime_policy(config)

    tools = [
        ReadTool(workspace_dir=str(tmp_path)),
        WriteTool(workspace_dir=str(tmp_path)),
    ]
    filtered = engine.filter_tools(tools)

    assert len(filtered) == 1
    assert filtered[0].name == "read_file"


def test_workspace_tooling_injects_sandbox_manager_into_bash(tmp_path):
    config = _make_config(SecurityConfig(approval_profile="build", sandbox_mode="workspace"))
    engine = resolve_runtime_policy(config)

    tools: list[object] = []
    add_workspace_tools(
        tools,
        config,
        tmp_path,
        policy_engine=engine,
    )

    bash_tool = next(tool for tool in tools if isinstance(tool, BashTool))
    read_tool = next(tool for tool in tools if isinstance(tool, ReadTool))
    write_tool = next(tool for tool in tools if isinstance(tool, WriteTool))
    edit_tool = next(tool for tool in tools if isinstance(tool, EditTool))
    assert bash_tool.sandbox_manager is not None
    assert bash_tool.workspace_executor is not None
    assert bash_tool.workspace_executor.boundary.root == tmp_path.resolve()
    assert read_tool.workspace_executor is bash_tool.workspace_executor
    assert write_tool.workspace_executor is bash_tool.workspace_executor
    assert edit_tool.workspace_executor is bash_tool.workspace_executor
    transformed = bash_tool.sandbox_manager.transform("echo ok", cwd=tmp_path)
    assert transformed.env_overrides["MINI_AGENT_SANDBOX_BACKEND"]


def test_workspace_sandbox_manager_uses_configured_network_policy(tmp_path):
    config = _make_config(
        SecurityConfig(
            approval_profile="build",
            sandbox_mode="workspace",
            network_mode="allowlist",
            network_allow_domains=["api.openai.com"],
        )
    )
    engine = resolve_runtime_policy(config)

    manager = build_workspace_sandbox_manager(
        config,
        tmp_path,
        policy_engine=engine,
    )

    assert manager.network_policy.mode == NetworkAccessMode.ALLOWLIST
    assert manager.network_policy.allow_domains == ("api.openai.com",)


def test_workspace_sandbox_manager_uses_configured_resource_caps(tmp_path):
    config = _make_config(
        SecurityConfig(
            approval_profile="build",
            sandbox_mode="workspace",
            sandbox_max_processes=12,
            sandbox_max_process_memory_mb=768,
        )
    )
    engine = resolve_runtime_policy(config)

    manager = build_workspace_sandbox_manager(
        config,
        tmp_path,
        policy_engine=engine,
    )

    selection = manager.select_initial()
    assert selection.metadata["max_processes"] == 12
    assert selection.metadata["max_process_memory_mb"] == 768


def test_build_default_approval_engine_allows_workspace_edits_but_requires_selected_sensitive_mutations():
    config = _make_config(SecurityConfig(approval_profile="build", access_level="default"))
    engine = build_approval_engine(config)

    write_outcome = engine.evaluate(
        _build_invocation(tool_name="write_file", kind=ToolKind.WRITE, is_read_only=False)
    )
    edit_outcome = engine.evaluate(
        _build_invocation(tool_name="edit_file", kind=ToolKind.EDIT, is_read_only=False)
    )
    read_outcome = engine.evaluate(
        _build_invocation(tool_name="read_file", kind=ToolKind.READ, is_read_only=True)
    )
    profile_outcome = engine.evaluate(
        _build_invocation(tool_name="user_modeling", kind=ToolKind.EDIT, is_read_only=False)
    )
    skill_outcome = engine.evaluate(
        _build_invocation(tool_name="install_skill", kind=ToolKind.WRITE, is_read_only=False)
    )

    assert write_outcome.requires_confirmation is False
    assert edit_outcome.requires_confirmation is False
    assert read_outcome.requires_confirmation is False
    assert engine.evaluate(
        _build_invocation(tool_name="record_note", kind=ToolKind.EDIT, is_read_only=False)
    ).requires_confirmation is False
    assert profile_outcome.requires_confirmation is True
    assert skill_outcome.requires_confirmation is True


def test_build_default_tool_exclude_still_overrides_workspace_edit_allow():
    config = _make_config(
        SecurityConfig(
            approval_profile="build",
            tool_exclude=["write_file"],
        )
    )
    engine = build_approval_engine(config)

    write_outcome = engine.evaluate(
        _build_invocation(tool_name="write_file", kind=ToolKind.WRITE, is_read_only=False)
    )

    assert write_outcome.requires_confirmation is False
    assert write_outcome.decision == PermissionDecision.DENY


def test_full_access_approval_engine_allows_workspace_mutations_without_confirmation():
    config = _make_config(SecurityConfig(approval_profile="build", access_level="full-access"))
    engine = build_approval_engine(config)

    write_outcome = engine.evaluate(
        _build_invocation(tool_name="write_file", kind=ToolKind.WRITE, is_read_only=False)
    )
    edit_outcome = engine.evaluate(
        _build_invocation(tool_name="edit_file", kind=ToolKind.EDIT, is_read_only=False)
    )

    assert write_outcome.requires_confirmation is False
    assert edit_outcome.requires_confirmation is False
