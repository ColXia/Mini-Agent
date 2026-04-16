from __future__ import annotations

from mini_agent.runtime.runtime_policy_service import (
    SessionRuntimePolicyPlan,
    SessionRuntimePolicyService,
)
from tests.runtime_contract_fixtures import RuntimeContractAgentStub, runtime_policy_engine_stub


def test_runtime_policy_service_builds_command_feedback() -> None:
    plan = SessionRuntimePolicyPlan(
        approval_profile="plan",
        access_level="full-access",
    )

    assert SessionRuntimePolicyService.command_summary(plan) == "runtime plan / full-access"
    assert SessionRuntimePolicyService.command_details(
        plan,
        session_label="Session 1",
        session_id="session-1",
        active_surface="qq",
    ) == (
        "Runtime policy updated.\n"
        "- session: Session 1\n"
        "- session_id: session-1\n"
        "- surface: qq\n"
        "- execution: plan\n"
        "- access: full-access"
    )
    assert SessionRuntimePolicyService.command_status_text(
        plan,
        session_label="Session 1",
    ) == "Session 1: runtime set to plan / full-access."


def test_runtime_policy_service_builds_unchanged_and_failure_feedback() -> None:
    assert SessionRuntimePolicyService.unchanged_summary() == "runtime unchanged"
    assert SessionRuntimePolicyService.unchanged_details(
        session_label="Session 2",
        approval_profile="build",
        access_level="default",
    ) == "Session 2 already uses build / default."
    assert SessionRuntimePolicyService.failure_summary() == "runtime policy failed"
    assert SessionRuntimePolicyService.failure_details("Session is busy.") == (
        "Runtime policy update failed: Session is busy."
    )
    assert SessionRuntimePolicyService.failure_status_text("Runtime policy update failed: Session is busy.") == (
        "Runtime policy update failed: Session is busy."
    )


def test_runtime_policy_service_reads_effective_policy_from_runtime_services_contract() -> None:
    agent = RuntimeContractAgentStub()
    agent.runtime_policy_engine = runtime_policy_engine_stub(
        approval_profile="plan",
        access_level="full-access",
    )

    assert SessionRuntimePolicyService.effective_runtime_policy_for_agent(agent) == (
        "plan",
        "full-access",
    )
