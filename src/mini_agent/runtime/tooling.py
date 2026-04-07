"""Tool initialization helpers shared by CLI and ACP runtimes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_agent.security.policy import RuntimePolicyEngine


def add_workspace_tools(
    tools: list,
    config,
    workspace_dir: Path,
    policy_engine: RuntimePolicyEngine | None = None,
) -> None:
    """Add workspace-scoped tools (bash/file/note/user-modeling)."""
    from mini_agent.tools.bash_tool import BashKillTool, BashOutputTool, BashTool
    from mini_agent.tools.file_tools import EditTool, ReadTool, WriteTool
    from mini_agent.tools.note_tool import RecallNoteTool, SessionNoteTool
    from mini_agent.tools.user_modeling import UserModelingTool

    is_allowed = policy_engine.is_tool_allowed if policy_engine else (lambda _name: True)

    if config.tools.enable_bash and is_allowed("bash"):
        tools.append(BashTool(workspace_dir=str(workspace_dir), policy_engine=policy_engine))
    if config.tools.enable_bash and is_allowed("bash_output"):
        tools.append(BashOutputTool())
    if config.tools.enable_bash and is_allowed("bash_kill"):
        tools.append(BashKillTool())

    if config.tools.enable_file_tools and is_allowed("read_file"):
        tools.append(ReadTool(workspace_dir=str(workspace_dir)))
    if config.tools.enable_file_tools and is_allowed("write_file"):
        tools.append(WriteTool(workspace_dir=str(workspace_dir)))
    if config.tools.enable_file_tools and is_allowed("edit_file"):
        tools.append(EditTool(workspace_dir=str(workspace_dir)))

    if config.tools.enable_note and is_allowed("record_note"):
        tools.append(SessionNoteTool(memory_root=str(workspace_dir)))
    if config.tools.enable_note and is_allowed("recall_notes"):
        tools.append(RecallNoteTool(memory_root=str(workspace_dir)))
    if config.tools.enable_note and is_allowed("user_modeling"):
        tools.append(UserModelingTool(memory_root=str(workspace_dir)))


def resolve_runtime_policy(config, approval_profile_override: str | None = None) -> RuntimePolicyEngine:
    return RuntimePolicyEngine.from_config(config, approval_profile_override=approval_profile_override)


async def initialize_shared_tools(
    config,
    policy_engine: RuntimePolicyEngine | None = None,
) -> tuple[list, Any]:
    """Initialize tools that are not tied to a single workspace (skills + MCP)."""
    from mini_agent.config import Config
    from mini_agent.tools.mcp_loader import load_mcp_tools_async, set_mcp_timeout_config
    from mini_agent.tools.skill_tool import create_skill_tools

    tools: list = []
    skill_loader = None

    if config.tools.enable_skills:
        try:
            skill_tools, skill_loader = create_skill_tools(str(Path(__file__).parent.parent / "skills"))
            tools.extend(skill_tools)
        except Exception:
            pass

    if config.tools.enable_mcp:
        try:
            mcp_config = config.tools.mcp
            set_mcp_timeout_config(
                connect_timeout=mcp_config.connect_timeout,
                execute_timeout=mcp_config.execute_timeout,
                sse_read_timeout=mcp_config.sse_read_timeout,
            )
            mcp_config_path = Config.find_config_file(config.tools.mcp_config_path)
            if mcp_config_path:
                mcp_tools = await load_mcp_tools_async(str(mcp_config_path))
                tools.extend(mcp_tools)
        except Exception:
            pass

    if policy_engine:
        tools = policy_engine.filter_tools(tools)

    return tools, skill_loader


async def initialize_agent_tools(
    config,
    workspace_dir: Path,
    approval_profile_override: str | None = None,
) -> tuple[list, Any]:
    """Initialize complete toolset for an agent session."""
    policy_engine = resolve_runtime_policy(config, approval_profile_override=approval_profile_override)
    tools: list = []
    add_workspace_tools(tools, config, workspace_dir, policy_engine=policy_engine)

    shared_tools, skill_loader = await initialize_shared_tools(config, policy_engine=policy_engine)
    tools.extend(shared_tools)
    return tools, skill_loader
