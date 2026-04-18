from __future__ import annotations

from types import SimpleNamespace

from mini_agent.agent_core.context.command_service import ContextCommandService, ContextCommandRequest
from mini_agent.runtime.runtime_policy_service import SessionRuntimePolicyService
from mini_agent.runtime.session_operator_handler import RuntimeSessionOperatorHandler
from tests.runtime_contract_fixtures import runtime_projection_stub, runtime_session_stub


def _build_operator_handler(**overrides):
    defaults = dict(
        normalize_surface=lambda value: str(value or "tui"),
        normalize_context_policy_payload=lambda value: dict(value or {}),
        normalize_sandbox_diagnostics_payload=lambda value: dict(value or {}),
        session_commands=SimpleNamespace(),
        session_agent_control=SimpleNamespace(),
        session_mcp_control=SimpleNamespace(),
        session_context_commands=ContextCommandService(),
        session_memory_commands=SimpleNamespace(),
        session_skill_commands=SimpleNamespace(),
        session_model_selection=SimpleNamespace(),
        session_runtime_policy=SessionRuntimePolicyService(),
        session_interrupt=SimpleNamespace(),
        session_agent_runtime=SimpleNamespace(
            reconfigure_runtime_policy=lambda *args, **kwargs: {},  # noqa: ARG005
        ),
        session_live_state=SimpleNamespace(
            bind_surface=lambda *args, **kwargs: None,  # noqa: ARG005
        ),
        load_runtime_config=lambda: None,
        selected_model_identity=lambda _session: None,
        pending_model_identity=lambda _session: None,
        set_pending_model_identity=lambda _session, _identity: None,
        persist_session=lambda _session: None,
        queue_workspace_skill_reload=lambda *args, **kwargs: None,  # noqa: ARG005
        cleanup_mcp_connections=lambda: None,
    )
    defaults.update(overrides)
    return RuntimeSessionOperatorHandler(**defaults)


def test_runtime_session_operator_handler_normalizes_context_policy_writeback() -> None:
    handler = _build_operator_handler(
        normalize_context_policy_payload=lambda value: {
            **dict(value or {}),
            "normalized": True,
        }
    )
    session = runtime_session_stub(
        session_id="sess-context",
        projection=runtime_projection_stub(
            busy=False,
            active_surface="tui",
            origin_surface="cli",
            context_policy={},
        ),
    )

    execution = handler._execute_context_policy_update(
        session,
        ContextCommandRequest(action="include", sources=("knowledge_base",)),
    )

    assert session.projection.context_policy["normalized"] is True
    assert execution.response.context_policy["normalized"] is True
    assert execution.transcript_command == "context include"
    assert execution.response.action == "include"


def test_runtime_session_operator_handler_normalizes_detached_runtime_policy_writeback() -> None:
    bind_calls: list[tuple[str | None, str | None]] = []
    handler = _build_operator_handler(
        normalize_sandbox_diagnostics_payload=lambda value: {
            **dict(value or {}),
            "normalized": True,
        },
        session_live_state=SimpleNamespace(
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


def test_runtime_session_operator_handler_runtime_policy_uses_active_run_pending_approvals() -> None:
    handler = _build_operator_handler(
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
