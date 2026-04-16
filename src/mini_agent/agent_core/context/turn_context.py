"""Turn-scoped context providers for Agent core.

This module gives the runtime one clean seam for injecting ephemeral
context into a single turn without polluting long-lived conversation
history. Future RAG, memory, MCP, and skill-context integrations can all
hang off this surface.
"""

from __future__ import annotations

from mini_agent.agent_core.context.turn_context_curation import (
    curate_turn_context_items,
    summarize_turn_context_items,
)
from mini_agent.agent_core.context.turn_context_diagnostics import (
    format_prepared_context_diagnostics,
    format_prepared_turn_context_details,
    format_turn_context_block,
    prepared_context_diagnostics_summary_line,
    prepared_turn_context_summary_line,
    update_prepared_context_diagnostics,
)
from mini_agent.agent_core.context.turn_context_policy import (
    context_policy_summary_line,
    format_context_policy_details,
    provider_allowed_by_policy,
    resolve_turn_context_policy,
)
from mini_agent.agent_core.context.turn_context_preparation import (
    AgentPreparedTurnContextService,
    PreparedTurnContextResult,
)
from mini_agent.agent_core.context.turn_context_providers import (
    ConsolidatedMemoryTurnContextProvider,
    MCPToolCatalogTurnContextProvider,
    RuntimeRecoveryTurnContextProvider,
    RuntimeTaskMemoryTurnContextProvider,
    SessionSearchTurnContextProvider,
    SkillCatalogTurnContextProvider,
    UserProfileTurnContextProvider,
    WorkspaceMemoryContextProvider,
)
from mini_agent.agent_core.context.turn_context_types import (
    RuntimeTurnContext,
    TurnContextItem,
    TurnContextProvider,
    coerce_runtime_turn_context,
    normalize_turn_context_items,
)


__all__ = [
    "AgentPreparedTurnContextService",
    "ConsolidatedMemoryTurnContextProvider",
    "MCPToolCatalogTurnContextProvider",
    "PreparedTurnContextResult",
    "RuntimeRecoveryTurnContextProvider",
    "RuntimeTaskMemoryTurnContextProvider",
    "RuntimeTurnContext",
    "SessionSearchTurnContextProvider",
    "SkillCatalogTurnContextProvider",
    "TurnContextItem",
    "TurnContextProvider",
    "UserProfileTurnContextProvider",
    "WorkspaceMemoryContextProvider",
    "context_policy_summary_line",
    "curate_turn_context_items",
    "coerce_runtime_turn_context",
    "format_context_policy_details",
    "format_prepared_context_diagnostics",
    "format_prepared_turn_context_details",
    "format_turn_context_block",
    "normalize_turn_context_items",
    "prepared_context_diagnostics_summary_line",
    "prepared_turn_context_summary_line",
    "provider_allowed_by_policy",
    "resolve_turn_context_policy",
    "summarize_turn_context_items",
    "update_prepared_context_diagnostics",
]
