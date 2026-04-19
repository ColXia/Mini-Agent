from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.config import AgentConfig, Config, LLMConfig, SecurityConfig, ToolsConfig
from mini_agent.workspace_runtime.adapters.direct_executor import DirectWorkspaceExecutor
from mini_agent.workspace_runtime.mutation_ledger import InMemoryMutationLedger, MutationKind
from mini_agent.workspace_runtime.outside_zone_policy import DefaultOutsideZonePolicy
from mini_agent.workspace_runtime.permission_table import (
    WorkspacePermissionEffect,
    WorkspacePermissionRule,
    WorkspacePermissionTable,
)
from mini_agent.workspace_runtime.workspace_executor import build_direct_workspace_runtime_bundle
from mini_agent.workspace_runtime.runtime_modes import WorkspaceRuntimeMode
from mini_agent.workspace_runtime.workspace_executor import WorkspaceAccessScope


def _make_config(security: SecurityConfig | None = None) -> Config:
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_mcp=False, enable_skills=False),
        security=security or SecurityConfig(),
    )


def test_direct_workspace_executor_uses_direct_runtime_mode(tmp_path: Path) -> None:
    executor = DirectWorkspaceExecutor(tmp_path)

    assert executor.mode is WorkspaceRuntimeMode.DIRECT
    assert executor.boundary.root == tmp_path.resolve()
    assert executor.runtime_descriptor.mode is WorkspaceRuntimeMode.DIRECT


def test_direct_workspace_executor_rejects_outside_path_in_workspace_only_scope(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    ledger = InMemoryMutationLedger()
    executor = DirectWorkspaceExecutor(workspace, mutation_ledger=ledger)

    with pytest.raises(PermissionError, match="escapes workspace root"):
        executor.resolve_access(outside, kind=MutationKind.READ, detail="attempt outside read")

    records = ledger.snapshot()
    assert len(records) == 1
    assert records[0].kind is MutationKind.READ
    assert records[0].inside_workspace is False
    assert records[0].approved is False


def test_direct_workspace_executor_allows_outside_read_when_outside_zone_scope_enabled(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    ledger = InMemoryMutationLedger()
    executor = DirectWorkspaceExecutor(
        workspace,
        scope=WorkspaceAccessScope.WITH_OUTSIDE_ZONE,
        outside_zone_policy=DefaultOutsideZonePolicy(protected_roots=()),
        mutation_ledger=ledger,
    )

    content = executor.read_text(outside)

    assert content == "outside"
    records = ledger.snapshot()
    assert len(records) == 1
    assert all(record.kind is MutationKind.READ for record in records)
    assert all(record.inside_workspace is False for record in records)


def test_direct_workspace_executor_requires_approval_for_outside_write(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    ledger = InMemoryMutationLedger()
    executor = DirectWorkspaceExecutor(
        workspace,
        scope=WorkspaceAccessScope.WITH_OUTSIDE_ZONE,
        outside_zone_policy=DefaultOutsideZonePolicy(protected_roots=()),
        mutation_ledger=ledger,
    )

    with pytest.raises(PermissionError, match="requires approval"):
        executor.write_text(outside, "blocked")

    records = ledger.snapshot()
    assert len(records) == 1
    assert records[0].kind is MutationKind.WRITE
    assert records[0].inside_workspace is False
    assert records[0].approved is False
    assert outside.exists() is False


def test_direct_workspace_executor_allows_approved_outside_write(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    ledger = InMemoryMutationLedger()
    executor = DirectWorkspaceExecutor(
        workspace,
        scope=WorkspaceAccessScope.WITH_OUTSIDE_ZONE,
        outside_zone_policy=DefaultOutsideZonePolicy(protected_roots=()),
        mutation_ledger=ledger,
    )

    written = executor.write_text(outside, "approved", approved=True)

    assert written == outside.resolve()
    assert outside.read_text(encoding="utf-8") == "approved"
    records = ledger.snapshot()
    assert len(records) == 1
    assert records[0].approved is True
    assert all(record.kind is MutationKind.WRITE for record in records)


def test_direct_workspace_executor_can_apply_workspace_internal_permission_rules(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    blocked = workspace / "secrets" / "note.txt"
    blocked.parent.mkdir()
    blocked.write_text("hidden", encoding="utf-8")
    executor = DirectWorkspaceExecutor(
        workspace,
        permission_table=WorkspacePermissionTable(
            rules=(
                WorkspacePermissionRule(
                    effect=WorkspacePermissionEffect.DENY,
                    kinds=(MutationKind.READ,),
                    relative_path="secrets",
                    reason="secrets are not readable from this workspace profile",
                ),
            )
        ),
    )

    with pytest.raises(PermissionError, match="secrets are not readable"):
        executor.read_text(blocked)


def test_direct_workspace_executor_resolves_execution_root_and_records_execute_mutation(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = InMemoryMutationLedger()
    executor = DirectWorkspaceExecutor(workspace, mutation_ledger=ledger)

    access = executor.resolve_execution_root(detail="bash command execution")

    assert access.resolved_path == workspace.resolve()
    assert access.inside_workspace is True
    records = ledger.snapshot()
    assert len(records) == 1
    assert records[0].kind is MutationKind.EXECUTE
    assert records[0].path == workspace.resolve()


def test_build_direct_workspace_runtime_bundle_composes_shared_runtime_parts(tmp_path: Path) -> None:
    bundle = build_direct_workspace_runtime_bundle(
        _make_config(SecurityConfig(approval_profile="build", sandbox_mode="workspace")),
        tmp_path,
    )

    assert bundle.workspace_dir == tmp_path.resolve()
    assert bundle.boundary.root == tmp_path.resolve()
    assert bundle.descriptor.mode is WorkspaceRuntimeMode.DIRECT
    assert bundle.executor.boundary.root == tmp_path.resolve()
    assert bundle.executor.permission_table is bundle.permission_table
    assert bundle.executor.mutation_ledger is bundle.mutation_ledger
    assert bundle.executor.outside_zone_policy is bundle.outside_zone_policy
    summary = bundle.to_summary()
    assert summary["workspace_root"] == str(tmp_path.resolve())
    assert summary["mode"] == WorkspaceRuntimeMode.DIRECT.value
    assert summary["scope"] == WorkspaceAccessScope.WORKSPACE_ONLY.value
    assert summary["permission_rule_count"] == 0
    assert summary["snapshot_count"] == 0
    assert summary["latest_snapshot_id"] is None
