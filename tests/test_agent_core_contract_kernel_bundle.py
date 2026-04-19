from __future__ import annotations

from pathlib import Path

from mini_agent.agent_core.contracts._kernel_state_bundle import (
    AgentKernelStateSeed,
    build_agent_kernel_state_record,
    build_checkpoint_for_record,
    deserialize_agent_kernel_state_record,
    serialize_agent_kernel_state_record,
)
from mini_agent.agent_core.contracts.checkpoint import CheckpointType
from mini_agent.agent_core.contracts.run import RunPhase, RunStatus
from mini_agent.agent_core.contracts.run_control_state import RunWaitKind


def test_agent_kernel_state_builder_materializes_v11_1_truth_bundle(tmp_path: Path) -> None:
    workspace_root = str((tmp_path / "workspace").resolve())
    seed = AgentKernelStateSeed(
        run_id="run-1",
        session_id="session-1",
        workspace_id=workspace_root,
        workspace_root=workspace_root,
        trigger_source="desktop",
        initial_status=RunStatus.WAITING,
        initial_phase=RunPhase.AWAITING_APPROVAL,
        waiting_reason="approval required for shell",
        built_in_tool_names=(" shell ", "read_file"),
        capability_hints=("approval", " memory "),
        agent_model_provider_id="maas",
        agent_model_id="astron-code-latest",
        approval_profile={"default_scope": "run"},
        context_policy={"allow_workspace_memory": True},
        recovery_context_pending=True,
    )

    record = build_agent_kernel_state_record(seed)

    assert record.run_id == "run-1"
    assert record.agent_profile.agent_profile_id == "agent-profile:main-agent"
    assert record.agent_profile.built_in_tool_names == ("read_file", "shell")
    assert record.agent_profile.capability_hints == ("approval", "memory")
    assert record.workspace_attachment.root_dir == workspace_root
    assert record.session_attachment.recovery_context_ref == "recovery:session-1"
    assert record.agent_instance.active_run_id == "run-1"
    assert record.agent_instance.lifecycle_state.value == "waiting"
    assert record.agent_instance.pending_wait_kind is RunWaitKind.APPROVAL
    assert record.run.status is RunStatus.WAITING
    assert record.run.phase is RunPhase.AWAITING_APPROVAL
    assert record.run.capability_snapshot_id == "capability-snapshot:run-1"
    assert record.capability_snapshot.agent_model_provider_id == "maas"
    assert record.capability_snapshot.agent_model_id == "astron-code-latest"
    assert record.capability_snapshot.context_policy == {"allow_workspace_memory": True}


def test_agent_kernel_state_checkpoint_builder_advances_run_checkpoint(tmp_path: Path) -> None:
    workspace_root = str((tmp_path / "workspace").resolve())
    seed = AgentKernelStateSeed(
        run_id="run-2",
        session_id="session-2",
        workspace_id=workspace_root,
        workspace_root=workspace_root,
        trigger_source="tui",
        initial_status=RunStatus.RUNNING,
        initial_phase=RunPhase.PLANNING,
        built_in_tool_names=("shell",),
    )
    record = build_agent_kernel_state_record(seed)

    updated_run, checkpoint = build_checkpoint_for_record(
        record,
        checkpoint_type=CheckpointType.WAITING,
        waiting_reason="approval required for shell",
        resume_token="approval-1",
    )

    assert checkpoint.checkpoint_id == "checkpoint:run-2:1"
    assert checkpoint.capability_snapshot_hash == record.capability_snapshot.capability_snapshot_id
    assert checkpoint.resume_token == "approval-1"
    assert checkpoint.waiting_reason == "approval required for shell"
    assert updated_run.active_checkpoint_id == checkpoint.checkpoint_id
    assert updated_run.last_checkpoint_seq == 1
    assert updated_run.restorable is True


def test_agent_kernel_state_record_round_trips_through_payload(tmp_path: Path) -> None:
    workspace_root = str((tmp_path / "workspace").resolve())
    seed = AgentKernelStateSeed(
        run_id="run-3",
        session_id="session-3",
        workspace_id=workspace_root,
        workspace_root=workspace_root,
        trigger_source="desktop",
        initial_status=RunStatus.RUNNING,
        initial_phase=RunPhase.PLANNING,
        built_in_tool_names=("shell", "read_file"),
        agent_model_provider_id="maas",
        agent_model_id="astron-code-latest",
    )
    record = build_agent_kernel_state_record(seed)
    record.execution_journal = record.execution_journal.append(
        event_type="run.turn_started",
        status=record.run.status,
        phase=record.run.phase,
        step_index=record.run.step_index,
        payload={"surface": "desktop"},
    )
    record.run_control = record.run_control.request_interrupt(source="desktop", reason="pause")

    payload = serialize_agent_kernel_state_record(record)
    restored = deserialize_agent_kernel_state_record(payload)

    assert restored is not None
    assert restored.run.run_id == "run-3"
    assert restored.agent_profile.built_in_tool_names == ("read_file", "shell")
    assert restored.capability_snapshot.agent_model_provider_id == "maas"
    assert restored.execution_journal.last_event_seq == 1
    assert restored.execution_journal.latest_event is not None
    assert restored.execution_journal.latest_event.event_type == "run.turn_started"
    assert restored.run_control.interrupt_requested is True
    assert restored.run_control.last_pause_reason == "pause"
