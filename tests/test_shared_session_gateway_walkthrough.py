from __future__ import annotations

import asyncio
from pathlib import Path

import scripts.shared_session_gateway_walkthrough as walkthrough


def test_shared_session_gateway_walkthrough_run_all_passes(tmp_path: Path) -> None:
    results = asyncio.run(walkthrough._run_all(tmp_path / "shared-session"))

    assert [item.name for item in results] == [
        "shared-activity-and-takeover",
        "shared-control-and-cancel",
        "import-export-roundtrip",
        "restart-recovery-snapshot",
        "restart-persistence",
    ]
    assert all(item.ok for item in results)

    activity_step = next(item for item in results if item.name == "shared-activity-and-takeover")
    assert "origin=qq active=qq" in activity_step.excerpts["detail_before_takeover"]
    assert "origin=qq active=tui" in activity_step.excerpts["detail_after_takeover"]

    control_step = next(item for item in results if item.name == "shared-control-and-cancel")
    assert "Task cancelled by user." in control_step.excerpts["cancel_detail"]

    recovery_step = next(item for item in results if item.name == "restart-recovery-snapshot")
    assert "approval pending for shell" in recovery_step.excerpts["detail_after_restart"]
    assert "last_activity=shell ok | pytest -q | 32 passed" in recovery_step.excerpts["detail_after_restart"]
    assert "approval pending for shell" in recovery_step.excerpts["detail_after_takeover"]
    assert "pending_approvals" in recovery_step.excerpts["turn_context_recovery"]
    assert "continue after interruption" in recovery_step.excerpts["detail_after_continue"]

    restart_step = next(item for item in results if item.name == "restart-persistence")
    assert "continue after restart" in restart_step.excerpts["detail_after_continue"]
