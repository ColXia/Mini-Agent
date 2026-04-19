from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.agent_core.contracts.approval_wait import (
    ApprovalDecision,
    ApprovalWait,
    ApprovalWaitState,
)
from mini_agent.agent_core.contracts.run_control_state import (
    RunControlMode,
    RunControlState,
    RunWaitKind,
)
from mini_agent.workspace_runtime.boundary import WorkspaceBoundary
from mini_agent.workspace_runtime.mutation_ledger import InMemoryMutationLedger, MutationKind
from mini_agent.workspace_runtime.outside_zone_policy import (
    DefaultOutsideZonePolicy,
    OutsideZoneOperation,
)


def test_run_control_state_tracks_stage1_transitions() -> None:
    state = RunControlState(run_id="run-1")

    interrupted = state.request_interrupt(source="desktop", reason="pause requested")
    assert interrupted.control_mode is RunControlMode.INTERRUPT_REQUESTED
    assert interrupted.interrupt_requested is True
    assert interrupted.last_command == "interrupt"
    assert interrupted.last_command_source == "desktop"

    paused = interrupted.pause(reason="safe boundary reached")
    assert paused.control_mode is RunControlMode.PAUSED
    assert paused.interrupt_requested is False
    assert paused.last_pause_reason == "safe boundary reached"

    waiting = paused.enter_approval_wait("wait-1", approval_token="approval-1")
    assert waiting.control_mode is RunControlMode.APPROVAL_WAIT
    assert waiting.active_wait_kind is RunWaitKind.APPROVAL
    assert waiting.active_wait_id == "wait-1"
    assert waiting.last_approval_token == "approval-1"

    resumed = waiting.clear_wait().request_resume(source="desktop", resume_token="resume-1")
    assert resumed.control_mode is RunControlMode.RESUME_REQUESTED
    assert resumed.active_wait_kind is RunWaitKind.NONE
    assert resumed.last_resume_token == "resume-1"

    cancelled = resumed.request_cancel(reason="stop now", force_stop=True)
    assert cancelled.control_mode is RunControlMode.CANCEL_REQUESTED
    assert cancelled.cancel_requested is True
    assert cancelled.force_stop_requested is True
    assert cancelled.last_cancel_reason == "stop now"

    terminal = cancelled.mark_terminal()
    assert terminal.control_mode is RunControlMode.TERMINAL
    assert terminal.resumable is False
    assert terminal.active_wait_id is None


def test_approval_wait_resolve_and_invalidate() -> None:
    wait = ApprovalWait(
        wait_id="wait-1",
        run_id="run-1",
        session_id="session-1",
        workspace_id="workspace-1",
        approval_token="token-1",
        tool_name="bash",
        tool_arguments_summary={"command": "pytest -q"},
    )

    resolved = wait.resolve(approved=False)
    assert resolved.wait_state is ApprovalWaitState.RESOLVED
    assert resolved.decision_result is ApprovalDecision.DENIED
    assert resolved.resolved_at is not None

    invalidated = wait.invalidate("runtime bridge lost after restart")
    assert invalidated.wait_state is ApprovalWaitState.INVALIDATED
    assert invalidated.invalidated_reason == "runtime bridge lost after restart"
    assert invalidated.decision_result is None

    with pytest.raises(ValueError, match="no longer pending"):
        resolved.resolve(approved=True)


def test_workspace_boundary_and_mutation_ledger(tmp_path: Path) -> None:
    root = tmp_path / "workspace"
    root.mkdir()
    inside = root / "notes.txt"
    outside = tmp_path / "outside.txt"

    boundary = WorkspaceBoundary(root)

    assert boundary.contains_path("notes.txt") is True
    assert boundary.contains_path(inside) is True
    assert boundary.contains_path(outside) is False
    assert boundary.relative_path(inside) == Path("notes.txt")
    assert boundary.relative_path(outside) is None

    ledger = InMemoryMutationLedger()
    record = ledger.record(
        MutationKind.WRITE,
        path=inside,
        detail="created workspace note",
        inside_workspace=True,
        approved=True,
    )

    assert len(ledger) == 1
    assert ledger.snapshot() == [record]
    assert record.kind is MutationKind.WRITE
    assert record.approved is True


def test_default_outside_zone_policy_baseline(tmp_path: Path) -> None:
    protected_root = tmp_path / "system-root"
    policy = DefaultOutsideZonePolicy(protected_roots=(protected_root,))

    outside_target = tmp_path / "outside.txt"
    protected_target = protected_root / "config.ini"

    outside_read = policy.decide(OutsideZoneOperation.READ, outside_target)
    assert outside_read.allowed is True
    assert outside_read.requires_approval is False

    outside_write = policy.decide(OutsideZoneOperation.WRITE, outside_target)
    assert outside_write.allowed is False
    assert outside_write.requires_approval is True

    outside_delete = policy.decide(OutsideZoneOperation.DELETE, outside_target)
    assert outside_delete.denied is True

    protected_read = policy.decide(OutsideZoneOperation.READ, protected_target)
    assert protected_read.allowed is True
    assert protected_read.protected is True

    protected_write = policy.decide(OutsideZoneOperation.WRITE, protected_target)
    assert protected_write.denied is True
    assert protected_write.protected is True
