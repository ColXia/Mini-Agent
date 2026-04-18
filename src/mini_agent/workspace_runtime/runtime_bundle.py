"""Workspace-runtime composition bundle for direct execution mode."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mini_agent.agent_core.execution.sandbox import NetworkAccessMode, NetworkDomainPolicy, SandboxManager
from mini_agent.security.policy import RuntimePolicyEngine

from .adapters import DirectWorkspaceExecutor
from .boundary import WorkspaceBoundary
from .mutation_ledger import InMemoryMutationLedger
from .outside_zone_policy import DefaultOutsideZonePolicy
from .permission_table import WorkspacePermissionTable
from .workspace_executor import WorkspaceAccessScope, WorkspaceExecutor


@dataclass(slots=True)
class WorkspaceRuntimeBundle:
    """Composed direct workspace runtime shared by workspace-bound tools."""

    boundary: WorkspaceBoundary
    executor: WorkspaceExecutor
    sandbox_manager: SandboxManager
    scope: WorkspaceAccessScope
    outside_zone_policy: DefaultOutsideZonePolicy
    permission_table: WorkspacePermissionTable
    mutation_ledger: InMemoryMutationLedger

    @property
    def workspace_dir(self) -> Path:
        return self.boundary.root

    @property
    def descriptor(self):
        return self.executor.runtime_descriptor

    def to_summary(self) -> dict[str, Any]:
        selection = self.sandbox_manager.select_initial()
        return {
            "workspace_root": str(self.workspace_dir),
            "mode": self.descriptor.mode.value,
            "scope": self.scope.value,
            "sandbox_backend": selection.backend.value,
            "sandbox_reason": selection.reason,
            "permission_rule_count": len(self.permission_table.rules),
            "mutation_count": len(self.mutation_ledger),
        }


def _resolve_network_policy(config) -> NetworkDomainPolicy:
    security = getattr(config, "security", None)
    raw_network_mode = str(getattr(security, "network_mode", "") or "").strip().lower()
    try:
        network_mode = (
            NetworkAccessMode(raw_network_mode)
            if raw_network_mode
            else NetworkAccessMode.ALLOW_ALL
        )
    except ValueError:
        network_mode = NetworkAccessMode.ALLOW_ALL
    return NetworkDomainPolicy(
        mode=network_mode,
        allow_domains=tuple(getattr(security, "network_allow_domains", []) or ()),
        block_domains=tuple(getattr(security, "network_block_domains", []) or ()),
    ).normalized()


def build_direct_workspace_runtime_bundle(
    config,
    workspace_dir: str | Path,
    *,
    policy_engine: RuntimePolicyEngine | None = None,
    scope: WorkspaceAccessScope = WorkspaceAccessScope.WORKSPACE_ONLY,
    outside_zone_policy: DefaultOutsideZonePolicy | None = None,
    permission_table: WorkspacePermissionTable | None = None,
    mutation_ledger: InMemoryMutationLedger | None = None,
) -> WorkspaceRuntimeBundle:
    """Compose the maintained direct workspace-runtime bundle."""

    active_policy = policy_engine or RuntimePolicyEngine.from_config(config)
    boundary = WorkspaceBoundary(workspace_dir)
    resolved_outside_zone_policy = outside_zone_policy or DefaultOutsideZonePolicy()
    resolved_permission_table = permission_table or WorkspacePermissionTable()
    resolved_mutation_ledger = mutation_ledger or InMemoryMutationLedger()
    executor = DirectWorkspaceExecutor(
        boundary,
        scope=scope,
        outside_zone_policy=resolved_outside_zone_policy,
        permission_table=resolved_permission_table,
        mutation_ledger=resolved_mutation_ledger,
    )
    security = getattr(config, "security", None)
    sandbox_manager = SandboxManager(
        workspace_dir=boundary.root,
        sandbox_mode=active_policy.policy.sandbox_mode,
        network_policy=_resolve_network_policy(config),
        max_processes=getattr(security, "sandbox_max_processes", None),
        max_process_memory_mb=getattr(security, "sandbox_max_process_memory_mb", None),
    )
    return WorkspaceRuntimeBundle(
        boundary=boundary,
        executor=executor,
        sandbox_manager=sandbox_manager,
        scope=scope,
        outside_zone_policy=resolved_outside_zone_policy,
        permission_table=resolved_permission_table,
        mutation_ledger=resolved_mutation_ledger,
    )


__all__ = [
    "WorkspaceRuntimeBundle",
    "build_direct_workspace_runtime_bundle",
]
