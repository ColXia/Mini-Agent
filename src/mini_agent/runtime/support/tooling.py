"""Tool initialization and runtime-policy helpers shared by Mini-Agent runtimes."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_agent.agent_core.execution.permissions.approval import ApprovalEngine
from mini_agent.agent_core.execution.permissions.policy import PermissionDecision, PermissionPolicy, PermissionRule
from mini_agent.agent_core.execution.sandbox.manager import SandboxManager
from mini_agent.agent_core.runtime_bindings import set_agent_runtime_services
from mini_agent.commands.mcp_support import resolve_runtime_mcp_config_path
from mini_agent.runtime.support.sandbox_state import collect_sandbox_diagnostics
from mini_agent.agent_core.skills.path_resolver import resolve_builtin_skills_dir, resolve_workspace_skills_dir
from mini_agent.security.policy import RuntimePolicyEngine
from mini_agent.workspace_runtime.workspace_executor import (
    WorkspaceRuntimeBundle,
    build_direct_workspace_runtime_bundle,
)


def _tool_names(tools: list[Any]) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for tool in tools or []:
        name = str(getattr(tool, "name", "") or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        names.append(name)
    return names


def _format_bootstrap_error(exc: Exception) -> str:
    return f"{type(exc).__name__}: {exc}"


def _skill_runtime_diagnostics(
    *,
    enabled: bool,
    builtin_dir: Path,
    workspace_dir: Path | None,
    skill_loader: Any,
    skill_tools: list[Any],
    active_tool_names: set[str],
    error: str | None,
) -> dict[str, Any]:
    raw_loader = getattr(skill_loader, "loader", skill_loader)
    catalog_count = 0
    eligible_count = 0
    active_skill_count = 0
    if raw_loader is not None and hasattr(raw_loader, "list_tier1"):
        try:
            catalog_count = len(raw_loader.list_tier1(eligible_only=False))
            eligible_count = len(raw_loader.list_tier1(eligible_only=True))
        except Exception:
            catalog_count = 0
            eligible_count = 0
    if skill_loader is not None and hasattr(skill_loader, "list_skills"):
        try:
            active_skill_count = len(skill_loader.list_skills())
        except Exception:
            active_skill_count = 0
    return {
        "enabled": enabled,
        "builtin_dir": str(builtin_dir),
        "workspace_dir": str(workspace_dir) if workspace_dir is not None else None,
        "loader_ready": skill_loader is not None,
        "catalog_count": catalog_count,
        "eligible_count": eligible_count,
        "active_skill_count": active_skill_count,
        "tool_names": [name for name in _tool_names(skill_tools) if name in active_tool_names],
        "error": error,
    }


def _mcp_runtime_diagnostics(
    *,
    enabled: bool,
    config_path: Path | None,
    mcp_tools: list[Any],
    active_tool_names: set[str],
    error: str | None,
) -> dict[str, Any]:
    active_names = [name for name in _tool_names(mcp_tools) if name in active_tool_names]
    return {
        "enabled": enabled,
        "config_path": str(config_path) if config_path is not None else None,
        "tool_count": len(active_names),
        "tool_names": active_names,
        "error": error,
    }


def build_workspace_sandbox_manager(
    config,
    workspace_dir: Path,
    policy_engine: RuntimePolicyEngine | None = None,
) -> SandboxManager:
    """Build one workspace sandbox manager from the active runtime policy."""
    return build_direct_workspace_runtime_bundle(
        config,
        workspace_dir,
        policy_engine=policy_engine,
    ).sandbox_manager


def add_workspace_tools(
    tools: list,
    config,
    workspace_dir: Path,
    policy_engine: RuntimePolicyEngine | None = None,
) -> WorkspaceRuntimeBundle:
    """Add workspace-scoped tools (bash/file/note/user-modeling)."""
    from mini_agent.tools.bash_tool import BashKillTool, BashOutputTool, BashTool
    from mini_agent.tools.docling_parse import DoclingParseTool
    from mini_agent.tools.file_tools import EditTool, ReadTool, WriteTool
    from mini_agent.model_manager.feature_runtime import FeatureModelRuntime
    from mini_agent.tools.knowledge_base import KnowledgeBaseQueryTool
    from mini_agent.tools.note_tool import RecallNoteTool, SessionNoteTool
    from mini_agent.tools.user_modeling import UserModelingTool

    is_allowed = policy_engine.is_tool_allowed if policy_engine else (lambda _name: True)
    runtime_bundle = build_direct_workspace_runtime_bundle(
        config,
        workspace_dir,
        policy_engine=policy_engine,
    )
    sandbox_manager = runtime_bundle.sandbox_manager
    workspace_executor = runtime_bundle.executor
    feature_runtime = FeatureModelRuntime()
    embedding_provider = feature_runtime.get_embedding_provider()
    ocr_adapter = feature_runtime.get_docling_ocr_adapter()

    if config.tools.enable_bash and is_allowed("bash"):
        tools.append(
            BashTool(
                workspace_dir=str(workspace_dir),
                workspace_executor=workspace_executor,
                policy_engine=policy_engine,
                sandbox_manager=sandbox_manager,
            )
        )
    if config.tools.enable_bash and is_allowed("bash_output"):
        tools.append(BashOutputTool())
    if config.tools.enable_bash and is_allowed("bash_kill"):
        tools.append(BashKillTool())

    if config.tools.enable_file_tools and is_allowed("read_file"):
        tools.append(
            ReadTool(
                workspace_dir=str(workspace_dir),
                workspace_executor=workspace_executor,
            )
        )
    if config.tools.enable_file_tools and is_allowed("write_file"):
        tools.append(
            WriteTool(
                workspace_dir=str(workspace_dir),
                workspace_executor=workspace_executor,
            )
        )
    if config.tools.enable_file_tools and is_allowed("edit_file"):
        tools.append(
            EditTool(
                workspace_dir=str(workspace_dir),
                workspace_executor=workspace_executor,
            )
        )
    if config.tools.enable_file_tools and is_allowed("docling_parse"):
        from mini_agent.tools.docling_parse import DoclingParser

        tools.append(
            DoclingParseTool(
                parser=DoclingParser(
                    ocr_adapter=ocr_adapter,
                    workspace_executor=workspace_executor,
                )
            )
        )

    if getattr(config.tools, "enable_knowledge_base", True) and is_allowed("knowledge_base_query"):
        tools.append(
            KnowledgeBaseQueryTool(
                workspace_dir=workspace_dir,
                embedding_provider=embedding_provider,
            )
        )

    if config.tools.enable_note and is_allowed("record_note"):
        tools.append(
            SessionNoteTool(
                memory_root=str(workspace_dir),
                workspace_executor=workspace_executor,
            )
        )
    if config.tools.enable_note and is_allowed("recall_notes"):
        tools.append(
            RecallNoteTool(
                memory_root=str(workspace_dir),
                embedding_provider=embedding_provider,
                workspace_executor=workspace_executor,
            )
        )
    if config.tools.enable_note and is_allowed("user_modeling"):
        tools.append(UserModelingTool(memory_root=str(workspace_dir)))

    return runtime_bundle


def resolve_runtime_policy(
    config,
    approval_profile_override: str | None = None,
    access_level_override: str | None = None,
) -> RuntimePolicyEngine:
    return RuntimePolicyEngine.from_config(
        config,
        approval_profile_override=approval_profile_override,
        access_level_override=access_level_override,
    )


def build_approval_engine(
    config,
    approval_profile_override: str | None = None,
    access_level_override: str | None = None,
) -> ApprovalEngine:
    """Build the declarative tool-approval engine for the active runtime profile."""
    runtime_policy = resolve_runtime_policy(
        config,
        approval_profile_override=approval_profile_override,
        access_level_override=access_level_override,
    ).policy
    profile = runtime_policy.approval_profile
    access_level = getattr(runtime_policy, "access_level", "default")

    if profile == "plan":
        rules: list[PermissionRule] = []
        for tool_name in sorted(runtime_policy.tool_exclude):
            rules.append(
                PermissionRule(
                    tool_pattern=tool_name,
                    decision=PermissionDecision.DENY,
                    reason="plan_mode_tool_excluded",
                )
            )
        return ApprovalEngine(
            PermissionPolicy(
                default_decision=PermissionDecision.ALLOW,
                rules=tuple(rules),
                full_auto=False,
            )
        )

    if access_level == "full-access":
        return ApprovalEngine(PermissionPolicy.full_auto_policy())

    rules: list[PermissionRule] = []
    for tool_name in sorted(runtime_policy.tool_exclude):
        rules.append(
            PermissionRule(
                tool_pattern=tool_name,
                decision=PermissionDecision.DENY,
                reason="runtime_tool_excluded",
            )
        )

    if profile == "build":
        # Build/default should feel closer to Codex-style normal operation:
        # ordinary workspace edits and shell work proceed inside the workspace
        # sandbox, while only long-lived or environment-shaping mutations ask.
        rules.extend(
            [
                PermissionRule(
                    tool_pattern="user_modeling",
                    decision=PermissionDecision.ASK,
                    reason="default_access_profile_write",
                ),
                PermissionRule(
                    tool_pattern="install_skill",
                    decision=PermissionDecision.ASK,
                    reason="default_access_skill_install",
                ),
                PermissionRule(
                    tool_pattern="install_skill_from_path",
                    decision=PermissionDecision.ASK,
                    reason="default_access_skill_install",
                ),
                PermissionRule(
                    tool_pattern="uninstall_skill",
                    decision=PermissionDecision.ASK,
                    reason="default_access_skill_remove",
                ),
                PermissionRule(
                    tool_pattern="rollback_skill",
                    decision=PermissionDecision.ASK,
                    reason="default_access_skill_remove",
                ),
            ]
        )

    return ApprovalEngine(
        PermissionPolicy(
            default_decision=PermissionDecision.ALLOW,
            rules=tuple(rules),
            full_auto=False,
        )
    )


async def initialize_shared_tools(
    config,
    workspace_dir: Path | None = None,
    policy_engine: RuntimePolicyEngine | None = None,
) -> tuple[list, Any, dict[str, Any]]:
    """Initialize tools that are not tied to a single workspace (skills + MCP)."""
    from mini_agent.tools.mcp_loader import load_mcp_tools_async, set_mcp_timeout_config
    from mini_agent.tools.skill_tool import create_skill_tools

    tools: list = []
    skill_loader = None
    builtin_skills_dir = resolve_builtin_skills_dir(config)
    workspace_skills_dir = resolve_workspace_skills_dir(workspace_dir)
    skill_tools: list[Any] = []
    mcp_tools: list[Any] = []
    skill_error: str | None = None
    mcp_error: str | None = None
    mcp_config_path: Path | None = None

    if config.tools.enable_skills:
        try:
            skill_tools, skill_loader = create_skill_tools(
                str(builtin_skills_dir),
                workspace_skills_dir=(
                    str(workspace_skills_dir)
                    if workspace_skills_dir is not None
                    else None
                ),
                workspace_dir=(str(workspace_dir) if workspace_dir is not None else None),
            )
            tools.extend(skill_tools)
        except Exception as exc:
            skill_error = _format_bootstrap_error(exc)

    if config.tools.enable_mcp:
        try:
            mcp_config = config.tools.mcp
            set_mcp_timeout_config(
                connect_timeout=mcp_config.connect_timeout,
                execute_timeout=mcp_config.execute_timeout,
                sse_read_timeout=mcp_config.sse_read_timeout,
            )
            mcp_config_path = resolve_runtime_mcp_config_path(config)
            if mcp_config_path:
                mcp_tools = await load_mcp_tools_async(str(mcp_config_path))
                tools.extend(mcp_tools)
        except Exception as exc:
            mcp_error = _format_bootstrap_error(exc)

    if policy_engine:
        tools = policy_engine.filter_tools(tools)

    active_tool_names = set(_tool_names(tools))
    diagnostics = {
        "shared_tools": {
            "count": len(_tool_names(tools)),
            "tool_names": _tool_names(tools),
        },
        "skills": _skill_runtime_diagnostics(
            enabled=bool(config.tools.enable_skills),
            builtin_dir=builtin_skills_dir,
            workspace_dir=workspace_skills_dir,
            skill_loader=skill_loader,
            skill_tools=skill_tools,
            active_tool_names=active_tool_names,
            error=skill_error,
        ),
        "mcp": _mcp_runtime_diagnostics(
            enabled=bool(config.tools.enable_mcp),
            config_path=mcp_config_path,
            mcp_tools=mcp_tools,
            active_tool_names=active_tool_names,
            error=mcp_error,
        ),
    }
    return tools, skill_loader, diagnostics


async def initialize_agent_tools(
    config,
    workspace_dir: Path,
    approval_profile_override: str | None = None,
    access_level_override: str | None = None,
) -> tuple[list, Any, dict[str, Any]]:
    """Initialize complete toolset for an agent session."""
    policy_engine = resolve_runtime_policy(
        config,
        approval_profile_override=approval_profile_override,
        access_level_override=access_level_override,
    )
    workspace_tools: list = []
    workspace_runtime = add_workspace_tools(workspace_tools, config, workspace_dir, policy_engine=policy_engine)

    shared_tools, skill_loader, shared_diagnostics = await initialize_shared_tools(
        config,
        workspace_dir=workspace_dir,
        policy_engine=policy_engine,
    )
    tools = [*workspace_tools, *shared_tools]
    diagnostics = {
        "workspace_tools": {
            "count": len(_tool_names(workspace_tools)),
            "tool_names": _tool_names(workspace_tools),
        },
        "workspace_runtime": workspace_runtime.to_summary(),
        "shared_tools": dict(shared_diagnostics.get("shared_tools", {})),
        "skills": dict(shared_diagnostics.get("skills", {})),
        "mcp": dict(shared_diagnostics.get("mcp", {})),
        "total_tools": {
            "count": len(_tool_names(tools)),
            "tool_names": _tool_names(tools),
        },
    }
    return tools, skill_loader, diagnostics


def apply_runtime_policy_to_agent(
    agent,
    *,
    policy_engine: RuntimePolicyEngine,
    approval_engine: ApprovalEngine,
    sandbox_manager: SandboxManager,
) -> dict[str, Any]:
    """Apply a rebuilt runtime policy stack to an existing agent instance."""
    set_agent_runtime_services(
        agent,
        runtime_policy_engine=policy_engine,
        approval_engine=approval_engine,
        sandbox_manager=sandbox_manager,
    )

    current_kb_enabled = True
    kb_checker = getattr(agent, "knowledge_base_enabled", None)
    if callable(kb_checker):
        try:
            current_kb_enabled = bool(kb_checker())
        except Exception:
            current_kb_enabled = True

    tool_catalog = getattr(agent, "_tool_catalog", None)
    if isinstance(tool_catalog, dict):
        filtered_tools = policy_engine.filter_tools(list(tool_catalog.values()))
        agent.tools = {tool.name: tool for tool in filtered_tools}
        if not current_kb_enabled:
            try:
                agent.set_knowledge_base_enabled(False)
            except Exception:
                getattr(agent, "tools", {}).pop("knowledge_base_query", None)
        refresh_registry = getattr(agent, "_refresh_tool_registry", None)
        if callable(refresh_registry):
            try:
                refresh_registry()
            except Exception:
                pass

    return collect_sandbox_diagnostics(agent=agent)


def reconfigure_agent_runtime_policy(
    *,
    agent,
    config,
    workspace_dir: Path,
    approval_profile_override: str | None = None,
    access_level_override: str | None = None,
) -> dict[str, Any]:
    """Rebuild and apply runtime policy state for one already-instantiated agent."""
    policy_engine = resolve_runtime_policy(
        config,
        approval_profile_override=approval_profile_override,
        access_level_override=access_level_override,
    )
    approval_engine = build_approval_engine(
        config,
        approval_profile_override=approval_profile_override,
        access_level_override=access_level_override,
    )
    sandbox_manager = build_workspace_sandbox_manager(
        config,
        workspace_dir,
        policy_engine=policy_engine,
    )
    return apply_runtime_policy_to_agent(
        agent,
        policy_engine=policy_engine,
        approval_engine=approval_engine,
        sandbox_manager=sandbox_manager,
    )

