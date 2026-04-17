"""Runtime turn-context provider assembly."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_agent.agent_core.context.turn_context import (
    ConsolidatedMemoryTurnContextProvider,
    MCPToolCatalogTurnContextProvider,
    RuntimeRecoveryTurnContextProvider,
    RuntimeTaskMemoryTurnContextProvider,
    SessionSearchTurnContextProvider,
    SkillCatalogTurnContextProvider,
    UserProfileTurnContextProvider,
    WorkspaceMemoryContextProvider,
)

from mini_agent.agent_core.skills.path_resolver import resolve_builtin_skills_dir, resolve_workspace_skills_dir


def build_turn_context_providers(
    config,
    workspace_dir: Path,
    *,
    session_store_dir: str | Path | None = None,
) -> list[Any]:
    """Build turn-scoped context providers for the active workspace."""
    from mini_agent.agent_core.skills.policy import WorkspaceSkillPolicyStore

    providers: list[Any] = [RuntimeRecoveryTurnContextProvider()]
    providers.append(RuntimeTaskMemoryTurnContextProvider(workspace_dir))
    providers.append(
        SessionSearchTurnContextProvider(
            workspace_dir,
            session_store_dir=session_store_dir,
        )
    )
    if getattr(config.tools, "enable_note", False):
        providers.append(UserProfileTurnContextProvider(workspace_dir))
        providers.append(WorkspaceMemoryContextProvider(workspace_dir))
        providers.append(
            ConsolidatedMemoryTurnContextProvider(
                workspace_dir,
                session_store_dir=session_store_dir,
            )
        )
    if getattr(config.tools, "enable_skills", False):
        providers.append(
            SkillCatalogTurnContextProvider(
                builtin_dir=resolve_builtin_skills_dir(config),
                workspace_dir=resolve_workspace_skills_dir(workspace_dir),
                policy_store=WorkspaceSkillPolicyStore(workspace_dir),
            )
        )
    if getattr(config.tools, "enable_mcp", False):
        providers.append(MCPToolCatalogTurnContextProvider())
    return providers


__all__ = ["build_turn_context_providers"]
