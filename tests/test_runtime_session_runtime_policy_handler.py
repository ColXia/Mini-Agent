from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from mini_agent.runtime.handlers.session_runtime_policy_handler import RuntimeSessionRuntimePolicyHandler
from mini_agent.runtime.orchestration.session_runtime_policy_coordinator import SessionRuntimePolicyService
from tests.runtime_contract_fixtures import (
    runtime_projection_stub,
    runtime_session_stub,
)


def _build_runtime_policy_handler(**overrides):
    defaults = dict(
        normalize_surface=lambda value: str(value or "tui"),
        normalize_sandbox_diagnostics_payload=lambda value: dict(value or {}),
        session_commands=SimpleNamespace(
            execute_locked=lambda session, **kwargs: kwargs["operation"](),  # noqa: ARG005
        ),
        session_runtime_policy=SessionRuntimePolicyService(),
        session_agent_runtime=SimpleNamespace(
            reconfigure_runtime_policy=lambda *args, **kwargs: {},  # noqa: ARG005
        ),
        session_transcript_state=SimpleNamespace(
            bind_surface=lambda *args, **kwargs: None,  # noqa: ARG005
        ),
        active_pending_approvals=None,
    )
    defaults.update(overrides)
    return RuntimeSessionRuntimePolicyHandler(**defaults)


def test_runtime_session_runtime_policy_handler_normalizes_detached_runtime_policy_writeback() -> None:
    bind_calls: list[tuple[str | None, str | None]] = []
    handler = _build_runtime_policy_handler(
        normalize_sandbox_diagnostics_payload=lambda value: {
            **dict(value or {}),
            "normalized": True,
        },
        session_transcript_state=SimpleNamespace(
            bind_surface=lambda session, *, surface, channel_type, conversation_id, sender_id: bind_calls.append(  # noqa: ARG001
                (surface, channel_type)
            )
        ),
    )
    session = runtime_session_stub(
        session_id="sess-policy",
        projection=runtime_projection_stub(
            title="Policy Session",
            busy=False,
            active_surface="tui",
            origin_surface="cli",
            sandbox_diagnostics={"backend": "none"},
        ),
    )

    execution = handler._execute_runtime_policy_update(
        session,
        approval_profile="plan",
        access_level="full-access",
        surface="qq",
        channel_type="qq",
        conversation_id="conv-1",
        sender_id="sender-1",
    )

    assert execution.plan.approval_profile == "plan"
    assert execution.plan.access_level == "full-access"
    assert execution.diagnostics["normalized"] is True
    assert execution.diagnostics["sandbox_mode"] == "unrestricted"
    assert session.projection.sandbox_diagnostics["normalized"] is True
    assert bind_calls == [("qq", "qq")]


def test_runtime_session_runtime_policy_handler_uses_active_run_pending_approvals() -> None:
    handler = _build_runtime_policy_handler(
        active_pending_approvals=lambda _session: [{"token": "approval-run", "tool_name": "shell"}],
    )
    session = runtime_session_stub(
        session_id="sess-policy-wait",
        projection=runtime_projection_stub(
            title="Policy Session",
            busy=True,
            active_surface="tui",
            origin_surface="cli",
            sandbox_diagnostics={"backend": "none"},
        ),
    )

    execution = handler._execute_runtime_policy_update(
        session,
        approval_profile="plan",
        access_level="full-access",
        surface="tui",
        channel_type=None,
        conversation_id=None,
        sender_id=None,
    )

    assert execution.plan.approval_profile == "plan"
    assert execution.plan.access_level == "full-access"


def test_runtime_session_runtime_policy_handler_does_not_fall_back_to_runtime_pending_payloads() -> None:
    handler = _build_runtime_policy_handler()
    session = runtime_session_stub(
        session_id="sess-policy-no-fallback",
        projection=runtime_projection_stub(
            title="Policy Session",
            busy=True,
            active_surface="tui",
            origin_surface="cli",
            sandbox_diagnostics={"backend": "none"},
        ),
        runtime=SimpleNamespace(
            agent=None,
            pending_approvals=[{"token": "approval-stale", "tool_name": "shell"}],
        ),
    )

    with pytest.raises(HTTPException, match="Session is busy"):
        handler._execute_runtime_policy_update(
            session,
            approval_profile="plan",
            access_level="full-access",
            surface="tui",
            channel_type=None,
            conversation_id=None,
            sender_id=None,
        )
