from __future__ import annotations

from mini_agent.runtime.support.runtime_policy_service import (
    SessionRuntimePolicyAutofixRequest,
    SessionRuntimePolicyExecution,
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


def test_runtime_policy_service_builds_pre_turn_autofix_only_for_private_desktop_plan_sessions() -> None:
    assert SessionRuntimePolicyService.build_pre_turn_autofix_request(
        requested_surface="desktop",
        origin_surface="desktop",
        active_surface="desktop",
        shared=False,
        current_approval_profile="plan",
        current_access_level="default",
    ) == SessionRuntimePolicyAutofixRequest(
        approval_profile="build",
        access_level="default",
    )

    assert (
        SessionRuntimePolicyService.build_pre_turn_autofix_request(
            requested_surface="desktop",
            origin_surface="desktop",
            active_surface="desktop",
            shared=True,
            current_approval_profile="plan",
            current_access_level="default",
        )
        is None
    )


def test_runtime_policy_service_executes_attached_runtime_update_via_shared_helper() -> None:
    calls: list[tuple[str, str]] = []

    execution = SessionRuntimePolicyService.execute_update(
        current_approval_profile="build",
        current_access_level="default",
        requested_approval_profile="plan",
        requested_access_level="full-access",
        busy=False,
        waiting_on_approval=False,
        runtime_attached=True,
        sandbox_diagnostics={"backend": "sandbox"},
        normalize_sandbox_diagnostics_payload=lambda value: {
            **dict(value or {}),
            "normalized": True,
        },
        reconfigure_attached_runtime=lambda approval_profile, access_level: calls.append(
            (approval_profile, access_level)
        )
        or {
            "approval_profile": approval_profile,
            "access_level": access_level,
            "sandbox_mode": "unrestricted",
        },
    )

    assert execution == SessionRuntimePolicyExecution(
        plan=SessionRuntimePolicyPlan(
            approval_profile="plan",
            access_level="full-access",
        ),
        diagnostics={
            "approval_profile": "plan",
            "access_level": "full-access",
            "sandbox_mode": "unrestricted",
            "normalized": True,
        },
    )
    assert calls == [("plan", "full-access")]


def test_runtime_policy_service_executes_detached_runtime_update_via_shared_helper() -> None:
    execution = SessionRuntimePolicyService.execute_update(
        current_approval_profile="build",
        current_access_level="default",
        requested_approval_profile="plan",
        requested_access_level="default",
        busy=False,
        waiting_on_approval=False,
        runtime_attached=False,
        sandbox_diagnostics={"backend": "none"},
        normalize_sandbox_diagnostics_payload=lambda value: {
            **dict(value or {}),
            "normalized": True,
        },
    )

    assert execution.plan.approval_profile == "plan"
    assert execution.plan.access_level == "default"
    assert execution.diagnostics["approval_profile"] == "plan"
    assert execution.diagnostics["access_level"] == "default"
    assert execution.diagnostics["sandbox_mode"] == "workspace"
    assert execution.diagnostics["normalized"] is True
    assert (
        SessionRuntimePolicyService.build_pre_turn_autofix_request(
            requested_surface="desktop",
            origin_surface="qq",
            active_surface="desktop",
            shared=False,
            current_approval_profile="plan",
            current_access_level="full-access",
        )
        is None
    )
    assert (
        SessionRuntimePolicyService.build_pre_turn_autofix_request(
            requested_surface="qq",
            origin_surface="desktop",
            active_surface="desktop",
            shared=False,
            current_approval_profile="plan",
            current_access_level="default",
        )
        is None
    )
