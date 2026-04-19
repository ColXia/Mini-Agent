from __future__ import annotations

from pathlib import Path

from mini_agent.config import AgentConfig, Config, LLMConfig, SecurityConfig, ToolsConfig
from mini_agent.workspace_runtime.mutation_ledger import (
    InMemoryMutationLedger,
    MutationKind,
    clear_shared_mutation_ledgers,
)
from mini_agent.workspace_runtime.runtime_bundle import build_direct_workspace_runtime_bundle
from mini_agent.workspace_runtime.runtime_modes import WorkspaceRuntimeMode
from mini_agent.workspace_runtime.snapshot_store import (
    InMemoryWorkspaceSnapshotStore,
    WorkspaceRuntimeSnapshot,
    clear_shared_workspace_snapshot_stores,
    restore_shared_workspace_snapshot,
    shared_workspace_snapshot_store,
    workspace_runtime_snapshot_from_payload,
    workspace_runtime_snapshot_payload,
)
from mini_agent.workspace_runtime.workspace_executor import WorkspaceAccessScope


def _make_config(security: SecurityConfig | None = None) -> Config:
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_mcp=False, enable_skills=False),
        security=security or SecurityConfig(),
    )


def test_snapshot_store_tracks_latest_snapshot_per_workspace(tmp_path: Path) -> None:
    workspace_a = tmp_path / "workspace-a"
    workspace_b = tmp_path / "workspace-b"
    store = InMemoryWorkspaceSnapshotStore()

    first = store.create(
        workspace_dir=workspace_a,
        mode=WorkspaceRuntimeMode.DIRECT,
        scope=WorkspaceAccessScope.WORKSPACE_ONLY,
        snapshot_id="snap-a-1",
        metadata={"step": "first"},
    )
    second = store.create(
        workspace_dir=workspace_a,
        mode=WorkspaceRuntimeMode.DIRECT,
        scope=WorkspaceAccessScope.WORKSPACE_ONLY,
        snapshot_id="snap-a-2",
        metadata={"step": "second"},
    )
    third = store.save(
        WorkspaceRuntimeSnapshot(
            snapshot_id="snap-b-1",
            workspace_dir=workspace_b,
            mode=WorkspaceRuntimeMode.DIRECT,
            scope=WorkspaceAccessScope.WORKSPACE_ONLY,
        )
    )

    assert store.get("snap-a-1") == first
    assert store.latest() == third
    assert store.latest(workspace_a) == second
    assert store.latest(workspace_b) == third
    assert [snapshot.snapshot_id for snapshot in store.list(workspace_a)] == ["snap-a-1", "snap-a-2"]
    assert len(store) == 3


def test_workspace_runtime_bundle_reuses_shared_workspace_state_across_instances(tmp_path: Path) -> None:
    clear_shared_mutation_ledgers()
    clear_shared_workspace_snapshot_stores()
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    first = build_direct_workspace_runtime_bundle(_make_config(), workspace)
    first.executor.write_text(workspace / "shared.txt", "shared-state")
    first_snapshot = first.capture_snapshot(snapshot_id="shared-snap-1")

    second = build_direct_workspace_runtime_bundle(_make_config(), workspace)
    summary = second.to_summary()

    assert second.mutation_ledger is first.mutation_ledger
    assert second.snapshot_store is first.snapshot_store
    assert summary["mutation_count"] == 1
    assert summary["snapshot_count"] == 1
    assert summary["latest_snapshot_id"] == "shared-snap-1"
    assert summary["latest_snapshot"]["snapshot_id"] == first_snapshot.snapshot_id
    assert summary["latest_snapshot"]["mutation_count"] == 1


def test_runtime_bundle_can_capture_workspace_snapshot(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    ledger = InMemoryMutationLedger()
    bundle = build_direct_workspace_runtime_bundle(
        _make_config(SecurityConfig(approval_profile="build", sandbox_mode="workspace")),
        workspace,
        mutation_ledger=ledger,
    )

    bundle.executor.write_text(workspace / "note.txt", "hello")
    snapshot = bundle.capture_snapshot(snapshot_id="snap-1", metadata={"source": "test"})

    assert snapshot.snapshot_id == "snap-1"
    assert snapshot.workspace_dir == workspace.resolve()
    assert snapshot.mode is WorkspaceRuntimeMode.DIRECT
    assert snapshot.scope is WorkspaceAccessScope.WORKSPACE_ONLY
    assert snapshot.descriptor == bundle.descriptor
    assert len(snapshot.mutation_records) == 1
    assert snapshot.mutation_records[0].kind is MutationKind.WRITE
    assert snapshot.metadata == {"source": "test"}
    assert bundle.latest_snapshot() == snapshot

    summary = bundle.to_summary()
    assert summary["snapshot_count"] == 1
    assert summary["latest_snapshot_id"] == "snap-1"
    assert summary["latest_snapshot"]["snapshot_id"] == "snap-1"


def test_workspace_runtime_snapshot_payload_can_roundtrip_through_shared_restore(tmp_path: Path) -> None:
    clear_shared_workspace_snapshot_stores()
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    payload = {
        "snapshot_id": "roundtrip-snap",
        "workspace_dir": str(workspace.resolve()),
        "created_at": "2026-04-18T08:00:00+00:00",
        "mode": "direct",
        "scope": "workspace_only",
        "descriptor_mode": "direct",
        "mutation_count": 5,
        "metadata": {"source": "persisted"},
    }

    restored = restore_shared_workspace_snapshot(payload)
    serialized = workspace_runtime_snapshot_payload(restored)
    store = shared_workspace_snapshot_store(workspace)

    assert restored is not None
    assert restored.snapshot_id == "roundtrip-snap"
    assert workspace_runtime_snapshot_from_payload(payload) == restored
    assert serialized is not None
    assert serialized["snapshot_id"] == "roundtrip-snap"
    assert serialized["mutation_count"] == 5
    assert store.latest(workspace) == restored
