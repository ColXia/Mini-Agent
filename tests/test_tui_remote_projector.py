from __future__ import annotations

from types import SimpleNamespace

from mini_agent.tui.session_remote_projector import TuiRemoteSessionProjector


def _session():
    return SimpleNamespace(
        session_id="sess-1",
        title="Local Session",
        projection=SimpleNamespace(
            origin_surface="tui",
            active_surface="tui",
            reply_enabled=False,
            busy=False,
            running_state="",
            is_default=False,
            channel_type=None,
            conversation_id=None,
            sender_id=None,
            shared=False,
            token_usage=0,
            token_limit=0,
            knowledge_base_enabled=None,
            pending_approvals=[],
            last_prepared_context={},
            prepared_context_diagnostics={},
            memory_diagnostics={},
            sandbox_diagnostics={},
            context_policy={},
            supplemental=SimpleNamespace(
                remote_message_count=0,
                remote_updated_at=None,
                remote_recovery_state="",
                remote_recovery_summary="",
                remote_last_activity_summary="",
                remote_last_command_summary="",
                recovery_pending_approvals=[],
                remote_run_id="",
                remote_run_status="",
                remote_run_phase="",
                remote_run_busy=False,
                remote_run_running_state="",
                remote_run_control_mode="",
                remote_run_interrupt_requested=False,
                remote_run_cancel_requested=False,
                remote_run_resumable=False,
                remote_run_waiting_on_approval=False,
                remote_run_active_wait_id=None,
                remote_run_approval_wait={},
            ),
        ),
        operator=SimpleNamespace(
            pending_model_source=None,
            pending_provider_id=None,
            pending_model_id=None,
            pending_skill_reload=False,
            pending_skill_reload_reason="",
        ),
        view=SimpleNamespace(messages=[]),
        selected_identity=None,
        pending_identity=None,
    )


def _projector(replace_calls: list[bool]) -> TuiRemoteSessionProjector:
    def _normalize_model_identity(*, source, provider_id, model_id):  # noqa: ANN001
        if not source or not provider_id or not model_id:
            return None
        return (str(source).strip().lower(), str(provider_id).strip(), str(model_id).strip())

    def _set_selected(session, identity) -> None:  # noqa: ANN001
        session.selected_identity = identity

    def _set_pending(session, identity) -> None:  # noqa: ANN001
        session.pending_identity = identity

    def _normalize_pending(items) -> list[dict[str, object]]:  # noqa: ANN001
        return [dict(item) for item in items or [] if isinstance(item, dict)]

    def _replace_messages(session, messages, preserve_follow_output) -> None:  # noqa: ANN001
        replace_calls.append(bool(preserve_follow_output))
        session.view.messages = list(messages)

    return TuiRemoteSessionProjector(
        resolve_session_title=lambda projection, fallback: str(projection.title or fallback),
        normalize_model_identity=_normalize_model_identity,
        set_selected_model_identity=_set_selected,
        set_pending_model_identity=_set_pending,
        normalize_pending_approvals_payload=_normalize_pending,
        normalize_memory_diagnostics_payload=lambda value: dict(value or {}),
        normalize_sandbox_diagnostics_payload=lambda value: dict(value or {}),
        normalize_context_policy_payload=lambda value: dict(value or {}),
        normalize_prepared_context_payload=lambda value: dict(value or {}),
        normalize_prepared_context_diagnostics_payload=lambda value: dict(value or {}),
        build_chat_entries=lambda items: [item.get("content", "") for item in items if isinstance(item, dict)],
        replace_messages=_replace_messages,
        last_command_summary=lambda session: f"messages={len(session.view.messages)}",
    )


def test_tui_remote_session_projector_applies_summary_and_detail_payloads() -> None:
    replace_calls: list[bool] = []
    projector = _projector(replace_calls)
    session = _session()

    summary_payload = {
        "session_id": "sess-1",
        "workspace_dir": "workspace-1",
        "created_at": "2026-04-15T10:00:00+00:00",
        "updated_at": "2026-04-15T10:05:00+00:00",
        "title": "Remote Session",
        "message_count": 4,
        "origin_surface": "qq",
        "active_surface": "remote",
        "reply_enabled": True,
        "busy": True,
        "running_state": "gateway request running",
        "is_default": False,
        "channel_type": "qq",
        "conversation_id": "conv-1",
        "sender_id": "sender-1",
        "token_usage": 120,
        "token_limit": 4000,
        "shared": True,
        "knowledge_base_enabled": False,
        "selected_model_source": "PRESET",
        "selected_provider_id": "openai",
        "selected_model_id": "gpt-5.4",
        "pending_model_source": "CUSTOM",
        "pending_provider_id": "maas",
        "pending_model_id": "astron-code",
        "pending_skill_reload": True,
        "pending_skill_reload_reason": " workspace changed ",
        "pending_approvals": [{"token": "tok-1", "tool_name": "shell"}],
        "recovery": {
            "state": "interrupted",
            "summary": "resume required",
            "last_activity": "tool running",
            "pending_approvals": [{"token": "tok-r", "tool_name": "python"}],
        },
        "memory_diagnostics": {"items": 2},
        "sandbox_diagnostics": {"approval_profile": "build"},
    }

    assert projector.apply_summary(session, summary_payload) is True
    assert session.title == "Remote Session"
    assert session.projection.origin_surface == "qq"
    assert session.projection.active_surface == "remote"
    assert session.projection.knowledge_base_enabled is False
    assert session.selected_identity == ("preset", "openai", "gpt-5.4")
    assert session.pending_identity == ("custom", "maas", "astron-code")
    assert session.operator.pending_skill_reload is True
    assert session.operator.pending_skill_reload_reason == "workspace changed"
    assert session.projection.pending_approvals == [
        {
            "token": "tok-1",
            "tool_name": "shell",
            "arguments": {},
            "kind": None,
            "reason": None,
            "cache_key": None,
            "can_escalate": False,
            "step": None,
        }
    ]
    assert session.projection.supplemental.remote_recovery_state == "interrupted"
    assert session.projection.supplemental.recovery_pending_approvals == [
        {
            "token": "tok-r",
            "tool_name": "python",
            "arguments": {},
            "kind": None,
            "reason": None,
            "cache_key": None,
            "can_escalate": False,
            "step": None,
        }
    ]

    detail_payload = {
        **summary_payload,
        "context_policy": {"sources": ["knowledge_base"]},
        "last_prepared_context": {"summary": "ctx"},
        "prepared_context_diagnostics": {"chunks": 3},
        "recent_messages": [
            {
                "index": 1,
                "role": "assistant",
                "content": "hello remote",
                "surface": "remote",
                "created_at": "2026-04-15T10:05:01+00:00",
                "metadata": {"kind": "reply"},
            }
        ],
    }

    assert projector.apply_detail(session, detail_payload, preserve_follow_output=False) is True
    assert session.projection.context_policy == {"sources": ["knowledge_base"]}
    assert session.projection.last_prepared_context == {"summary": "ctx"}
    assert session.projection.prepared_context_diagnostics == {"chunks": 3}
    assert session.view.messages == ["hello remote"]
    assert session.projection.supplemental.remote_last_command_summary == "messages=1"
    assert replace_calls == [False]


def test_tui_remote_session_projector_applies_message_list_payloads() -> None:
    replace_calls: list[bool] = []
    projector = _projector(replace_calls)
    session = _session()

    projector.apply_messages(
        session,
        [
            {
                "index": 1,
                "role": "assistant",
                "content": "remote message",
                "surface": "remote",
                "created_at": "2026-04-15T10:05:01+00:00",
            },
            "bad-item",
        ],
    )

    assert session.view.messages == ["remote message"]
    assert replace_calls == [True]


def test_tui_remote_session_projector_applies_run_payloads() -> None:
    replace_calls: list[bool] = []
    projector = _projector(replace_calls)
    session = _session()

    assert projector.apply_run(
        session,
        {
            "run_id": "session-run:sess-1",
            "session_id": "sess-1",
            "status": "waiting",
            "phase": "awaiting_approval",
            "busy": True,
            "running_state": "approval wait",
            "control_mode": "approval_wait",
            "interrupt_requested": False,
            "cancel_requested": False,
            "resumable": True,
            "waiting_on_approval": True,
            "active_wait_id": "wait-1",
            "approval_wait": {
                "wait_id": "wait-1",
                "approval_token": "tok-1",
                "tool_name": "shell",
                "tool_arguments_summary": {"command": "pytest -q"},
                "approval_kind": "tool",
                "policy_reason": "write access",
                "cache_key": "shell:pytest",
                "can_escalate": False,
                "wait_state": "pending",
            },
        },
    ) is True

    supplemental = session.projection.supplemental
    assert supplemental.remote_run_id == "session-run:sess-1"
    assert supplemental.remote_run_status == "waiting"
    assert supplemental.remote_run_phase == "awaiting_approval"
    assert supplemental.remote_run_running_state == "approval wait"
    assert supplemental.remote_run_waiting_on_approval is True
    assert supplemental.remote_run_approval_wait == {
        "wait_id": "wait-1",
        "run_id": "session-run:sess-1",
        "session_id": "sess-1",
        "token": "tok-1",
        "tool_name": "shell",
        "arguments": {"command": "pytest -q"},
        "kind": "tool",
        "reason": "write access",
        "cache_key": "shell:pytest",
        "can_escalate": False,
        "wait_state": "pending",
    }


def test_tui_remote_session_projector_ignores_invalid_payloads() -> None:
    replace_calls: list[bool] = []
    projector = _projector(replace_calls)
    session = _session()

    assert projector.apply_summary(session, {}) is False
    assert projector.apply_detail(session, {}, preserve_follow_output=True) is False
    assert session.title == "Local Session"
    assert replace_calls == []
