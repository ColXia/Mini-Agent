from __future__ import annotations

from mini_agent.session import (
    SessionDetailProjection,
    SessionRecoveryProjection,
    SessionSummaryProjection,
)
from mini_agent.tui.session_projection import TerminalSessionProjection


def test_session_summary_projection_round_trip_transport_payload() -> None:
    payload = {
        "session_id": "sess-1",
        "workspace_dir": "D:/file/Mini-Agent",
        "created_at": "2026-04-12T08:00:00+00:00",
        "updated_at": "2026-04-12T08:01:00+00:00",
        "title": "nyonyo",
        "message_count": 4,
        "origin_surface": "qq",
        "active_surface": "qq",
        "reply_enabled": True,
        "busy": False,
        "running_state": None,
        "channel_type": "qq",
        "conversation_id": "group:demo",
        "sender_id": "user-1",
        "token_usage": 1024,
        "token_limit": 128000,
        "shared": True,
        "knowledge_base_enabled": True,
        "selected_model_source": "custom",
        "selected_provider_id": "maas",
        "selected_model_id": "astron-code-latest",
        "pending_model_source": None,
        "pending_provider_id": None,
        "pending_model_id": None,
        "pending_skill_reload": True,
        "pending_skill_reload_reason": "skill added",
        "pending_approvals": [
            {
                "token": "tok-1",
                "tool_name": "shell",
                "arguments": {"command": "pytest"},
                "can_escalate": True,
                "step": 2,
            }
        ],
        "recovery": {
            "state": "interrupted",
            "summary": "interrupted after restart: approval pending for shell",
            "last_activity": "shell ok | pytest",
            "pending_approvals": [
                {
                    "token": "tok-1",
                    "tool_name": "shell",
                    "arguments": {"command": "pytest"},
                }
            ],
        },
        "remote_recovery_text": "Shared-session recovery:\nsessionId: sess-1",
        "memory_diagnostics": {"global_profile_fact_count": 2},
        "sandbox_diagnostics": {"approval_profile": "build"},
    }

    projection = SessionSummaryProjection.from_transport_payload(payload)

    assert projection is not None
    assert projection.session_id == "sess-1"
    assert projection.recovery is not None
    assert projection.recovery.state == "interrupted"
    assert projection.pending_approvals[0].tool_name == "shell"
    assert projection.remote_recovery_text == "Shared-session recovery:\nsessionId: sess-1"

    dto = projection.to_transport()

    assert dto.session_id == "sess-1"
    assert dto.selected_provider_id == "maas"
    assert dto.pending_skill_reload is True
    assert dto.recovery is not None
    assert dto.recovery.pending_approvals[0].token == "tok-1"
    assert dto.remote_recovery_text == "Shared-session recovery:\nsessionId: sess-1"


def test_session_detail_projection_round_trip_transport_payload() -> None:
    payload = {
        "session_id": "sess-2",
        "workspace_dir": ".",
        "created_at": "2026-04-12T08:00:00+00:00",
        "updated_at": "2026-04-12T08:02:00+00:00",
        "message_count": 2,
        "origin_surface": "tui",
        "active_surface": "tui",
        "reply_enabled": False,
        "busy": False,
        "shared": False,
        "knowledge_base_enabled": False,
        "context_policy": {"active": True, "max_items": 4},
        "last_prepared_context": {"memory": ["fact"]},
        "prepared_context_diagnostics": {"used_sources": ["memory"]},
        "recent_messages": [
            {
                "index": 1,
                "role": "user",
                "content": "hello",
                "surface": "tui",
                "created_at": "2026-04-12T08:00:10+00:00",
            },
            {
                "index": 2,
                "role": "assistant",
                "content": "hi",
                "surface": "tui",
                "created_at": "2026-04-12T08:00:11+00:00",
            },
        ],
    }

    projection = SessionDetailProjection.from_transport_payload(payload)

    assert projection is not None
    assert projection.context_policy["active"] is True
    assert len(projection.recent_messages) == 2

    dto = projection.to_transport()

    assert dto.context_policy["max_items"] == 4
    assert dto.recent_messages[1].content == "hi"


def test_terminal_session_projection_preserves_gateway_session_semantics() -> None:
    gateway_summary = SessionSummaryProjection(
        session_id="remote-qq-1",
        workspace_dir=".",
        created_at="",
        updated_at="",
        message_count=2,
        origin_surface="qq",
        active_surface="qq",
        reply_enabled=True,
        shared=True,
        channel_type="qq",
        conversation_id="group:demo",
        sender_id="user-1",
        recovery=SessionRecoveryProjection(
            state="interrupted",
            summary="interrupted after restart",
            last_activity="shell ok | pytest",
        ),
    )
    gateway_projection = TerminalSessionProjection.from_summary(
        gateway_summary,
        has_local_runtime_state=False,
        last_command_preview="session | continue",
    )

    assert gateway_projection.scope_summary == "shared [qq]"
    assert gateway_projection.route_summary == "qq / reply / gateway"
    assert gateway_projection.peer_summary == "qq/group:demo"
    assert gateway_projection.recovery_pending is True
    assert gateway_projection.show_gateway_panel is True

    local_summary = SessionSummaryProjection(
        session_id="local-1",
        workspace_dir=".",
        created_at="",
        updated_at="",
        message_count=0,
        origin_surface="tui",
        active_surface="tui",
        reply_enabled=False,
        shared=False,
    )
    local_projection = TerminalSessionProjection.from_summary(
        local_summary,
        has_local_runtime_state=True,
    )

    assert local_projection.scope_summary == "private [tui]"
    assert local_projection.route_summary == "tui / own / local"
    assert local_projection.share_state == "local only"
    assert local_projection.show_gateway_panel is False
