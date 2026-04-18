from __future__ import annotations

import pytest

from mini_agent.agent_core.contracts import (
    AgentInstance,
    AgentInstanceLifecycleState,
    AgentProfile,
    CapabilitySnapshot,
    Checkpoint,
    CheckpointType,
    ExecutionJournal,
    Run,
    RunInterruptState,
    RunPhase,
    RunStatus,
    RunWaitKind,
    SessionAttachment,
    WorkspaceAttachment,
    WorkspaceKind,
    WorkspaceRuntimeBackend,
)


def test_agent_profile_and_instance_track_identity_and_lifecycle() -> None:
    profile = AgentProfile(
        agent_profile_id=" main-agent ",
        role=" coding ",
        identity_label=" Mini Agent ",
        built_in_tool_names=("core.file.read", " core.shell.exec "),
        built_in_internal_skill_names=("core.edit", " core.review "),
        capability_hints=("approval", " recovery "),
        default_model_routing_intent=" tool-heavy ",
        static_policy_hints={"approval_default": "run"},
    )

    assert profile.agent_profile_id == "main-agent"
    assert profile.role == "coding"
    assert profile.identity_label == "Mini Agent"
    assert profile.built_in_tool_names == ("core.file.read", "core.shell.exec")
    assert profile.built_in_internal_skill_names == ("core.edit", "core.review")
    assert profile.capability_hints == ("approval", "recovery")
    assert profile.default_model_routing_intent == "tool-heavy"
    assert profile.has_tool("core.file.read") is True
    assert profile.has_internal_skill("core.review") is True

    instance = AgentInstance(
        agent_instance_id=" inst-1 ",
        agent_profile_id=profile.agent_profile_id,
    )
    assert instance.lifecycle_state is AgentInstanceLifecycleState.COLD

    ready = instance.transition_lifecycle(AgentInstanceLifecycleState.READY)
    attached = ready.attach(
        workspace_id="workspace-default",
        session_id="session-1",
        workspace_attachment_id="wa-1",
        session_attachment_id="sa-1",
    )
    running = attached.activate_run("run-1")
    interrupted = running.request_interrupt()
    waiting = interrupted.mark_waiting(wait_kind=RunWaitKind.APPROVAL, wait_id="wait-1")
    checkpointed = waiting.record_checkpoint("cp-1", journal_head_seq=2)
    paused = checkpointed.mark_paused(wait_id="wait-1")
    cleared = paused.clear_active_run()

    assert attached.lifecycle_state is AgentInstanceLifecycleState.ATTACHED
    assert attached.current_workspace_id == "workspace-default"
    assert attached.current_session_id == "session-1"
    assert running.lifecycle_state is AgentInstanceLifecycleState.RUNNING
    assert running.active_run_id == "run-1"
    assert interrupted.interrupt_requested is True
    assert waiting.lifecycle_state is AgentInstanceLifecycleState.WAITING
    assert waiting.pending_wait_kind is RunWaitKind.APPROVAL
    assert waiting.pending_wait_id == "wait-1"
    assert checkpointed.checkpoint_head_id == "cp-1"
    assert checkpointed.journal_head_seq == 2
    assert paused.lifecycle_state is AgentInstanceLifecycleState.PAUSED
    assert cleared.lifecycle_state is AgentInstanceLifecycleState.ATTACHED
    assert cleared.active_run_id is None


def test_run_attachment_and_checkpoint_follow_v11_1_contract() -> None:
    workspace_attachment = WorkspaceAttachment(
        workspace_attachment_id="wa-1",
        workspace_id="workspace-default",
        workspace_kind=WorkspaceKind.DEFAULT,
        root_dir="D:/file/Mini-Agent/.mini-agent/default-workspace",
        runtime_backend=WorkspaceRuntimeBackend.DIRECT,
        runtime_ref="workspace-runtime:default",
        boundary_manifest_hash="boundary-1",
        permission_table_ref="permission-table:default",
        outside_zone_policy_ref="outside-zone:v11_1",
        mutation_ledger_ref="ledger:default",
    )
    session_attachment = SessionAttachment(
        session_attachment_id="sa-1",
        session_id="session-1",
        workspace_id="workspace-default",
        transcript_ref="transcript:session-1",
        session_memory_ref="memory:session-1",
        approval_scope_ref="approval-scope:session-1",
        context_policy_ref="context-policy:session-1",
        lineage_ref="lineage:session-1",
    )

    run = Run(
        run_id="run-1",
        agent_instance_id="inst-1",
        agent_profile_id="main-agent",
        workspace_id="workspace-default",
        session_id="session-1",
        trigger_source="desktop",
    )
    assert run.status is RunStatus.QUEUED
    assert run.phase is RunPhase.CREATED

    bound = run.bind_attachments(
        workspace_attachment_id=workspace_attachment.workspace_attachment_id,
        session_attachment_id=session_attachment.session_attachment_id,
    )
    running = bound.transition(status=RunStatus.RUNNING, phase=RunPhase.BINDING)
    prepared = running.attach_capability_snapshot("cap-1").advance_step()
    waiting = prepared.transition(
        status=RunStatus.WAITING,
        phase=RunPhase.AWAITING_APPROVAL,
        waiting_reason="approval required for shell",
        interrupt_state=RunInterruptState.REQUESTED,
    )
    checkpointed = waiting.activate_checkpoint("cp-1", checkpoint_seq=1)

    checkpoint = Checkpoint(
        checkpoint_id="cp-1",
        run_id=checkpointed.run_id,
        agent_instance_id=checkpointed.agent_instance_id,
        checkpoint_seq=1,
        checkpoint_type=CheckpointType.WAITING,
        status=checkpointed.status,
        phase=checkpointed.phase,
        step_index=checkpointed.step_index,
        workspace_attachment_id=workspace_attachment.workspace_attachment_id,
        session_attachment_id=session_attachment.session_attachment_id,
        capability_snapshot_hash="cap-hash-1",
        journal_offset=2,
        waiting_reason=checkpointed.waiting_reason,
        resume_token="resume-1",
    )

    assert workspace_attachment.workspace_id == "workspace-default"
    assert session_attachment.session_id == "session-1"
    assert running.started_at is not None
    assert prepared.step_index == 1
    assert waiting.waiting_reason == "approval required for shell"
    assert waiting.interrupt_state is RunInterruptState.REQUESTED
    assert checkpointed.active_checkpoint_id == "cp-1"
    assert checkpointed.last_checkpoint_seq == 1
    assert checkpoint.is_waiting_checkpoint is True
    assert checkpoint.resume_token == "resume-1"

    with pytest.raises(ValueError, match="invalid run status/phase pairing"):
        Run(
            run_id="run-bad",
            agent_instance_id="inst-1",
            agent_profile_id="main-agent",
            workspace_id="workspace-default",
            session_id="session-1",
            trigger_source="desktop",
            status=RunStatus.COMPLETED,
            phase=RunPhase.PLANNING,
        )


def test_capability_snapshot_and_execution_journal_capture_stable_run_view() -> None:
    snapshot = CapabilitySnapshot(
        capability_snapshot_id="cap-1",
        agent_profile_id="main-agent",
        agent_instance_id="inst-1",
        run_id="run-1",
        workspace_id="workspace-default",
        session_id="session-1",
        resolved_tool_names=("core.file.read", " core.shell.exec "),
        resolved_tool_policies={"core.shell.exec": {"decision": "approval_required"}},
        visible_skill_names=("core.edit", " ws.project.note "),
        visible_memory_scopes=("session", "workspace"),
        enabled_external_capabilities=("mcp",),
        agent_model_provider_id="maas-openai",
        agent_model_id="astron-code-latest",
        agent_model_capability_profile={"supports_tools": True, "supports_thinking": True},
        workspace_runtime_mode="direct",
        approval_profile={"default_scope": "run"},
        context_policy={"allow_workspace_memory": True},
        refresh_reason="run start",
    )
    journal = ExecutionJournal(
        journal_stream_id="journal-1",
        run_id="run-1",
        agent_instance_id="inst-1",
        workspace_id="workspace-default",
        session_id="session-1",
    )
    journal = journal.append(
        event_type="control.run_created",
        status=RunStatus.QUEUED,
        phase=RunPhase.CREATED,
        step_index=0,
        payload={"trigger_source": "desktop"},
    )
    journal = journal.append(
        event_type="context.capability_snapshot_resolved",
        status=RunStatus.RUNNING,
        phase=RunPhase.RESOLVING_CAPABILITIES,
        step_index=0,
        correlation_id="corr-1",
        causation_id="control.run_created",
        payload={"capability_snapshot_id": snapshot.capability_snapshot_id},
    )
    closed = journal.close()

    assert snapshot.model_identity == ("maas-openai", "astron-code-latest")
    assert snapshot.exposes_tool("core.shell.exec") is True
    assert snapshot.visible_skill_names == ("core.edit", "ws.project.note")
    assert journal.last_event_seq == 2
    assert journal.latest_event is not None
    assert journal.latest_event.event_type == "context.capability_snapshot_resolved"
    assert journal.latest_event.payload == {"capability_snapshot_id": "cap-1"}
    assert closed.closed_at is not None

