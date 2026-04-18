from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

from mini_agent.transport import RemoteChatClient
from mini_agent.tui.session_remote_turn_stream_coordinator import TuiRemoteTurnStreamCoordinator


def _session() -> Any:
    return SimpleNamespace(
        session_id="remote-1",
        title="Remote Session",
        projection=SimpleNamespace(
            pending_approvals=[],
        ),
    )


def test_tui_remote_turn_stream_coordinator_consumes_stream_events() -> None:
    session = _session()
    activity_calls: list[dict[str, Any]] = []
    running_states: list[str] = []
    chunk_calls: list[tuple[str, int | None]] = []
    schedule_calls: list[str] = []
    render_calls: list[str] = []

    class _ChatClient:
        async def stream_chat_events(
            self,
            *,
            session_id: str,
            message: str,
            workspace_dir: str,
            surface: str = "tui",
        ):
            assert session_id == "remote-1"
            assert message == "ship p37"
            assert workspace_dir == "D:/file/Mini-Agent"
            assert surface == "tui"
            yield ("status", {"stage": "running"})
            yield (
                "activity",
                {
                    "activity_id": "activity-1",
                    "label": "thinking",
                    "detail": "planning",
                    "running_state": "step 1: planning",
                },
            )
            yield (
                "delegation.started",
                {
                    "task_id": "worker-1",
                    "worker_id": "worker-1",
                    "success": "",
                },
            )
            yield ("delta", {"chunk": "remote:"})
            yield ("delta", {"chunk": "ship p37"})
            yield ("heartbeat", {})
            yield (
                "done",
                {
                    "reply": "remote:ship p37",
                    "stop_reason": "end_turn",
                    "message_count": 4,
                },
            )

    coordinator = TuiRemoteTurnStreamCoordinator(
        append_activity_line=lambda _session, **kwargs: activity_calls.append(dict(kwargs)),
        update_running_state=lambda _session, text: running_states.append(text),
        record_pending_approval=lambda _session, payload: str(payload.get("token") or "") or None,
        handle_approval_requested=lambda _session, tool_name, token: None,
        pending_approval_token=lambda payload: str(payload.get("token") or ""),
        clear_pending_approval=lambda _session, token: None,
        handle_approval_resolved=lambda _session: None,
        append_assistant_stream_chunk=lambda _session, chunk, message_index: (
            chunk_calls.append((chunk, message_index)) or (message_index if isinstance(message_index, int) else 7)
        ),
        schedule_stream_render=lambda: schedule_calls.append("scheduled"),
        render_all=lambda: render_calls.append("rendered"),
    )

    result = asyncio.run(
        coordinator.consume(
            chat_client=_ChatClient(),
            session=session,
            message="ship p37",
            workspace_dir="D:/file/Mini-Agent",
            surface="tui",
        )
    )

    assert result.reply_text == "remote:ship p37"
    assert result.stop_reason == "end_turn"
    assert result.assistant_message_index == 7
    assert result.response == {
        "reply": "remote:ship p37",
        "stop_reason": "end_turn",
        "message_count": 4,
    }
    assert activity_calls == [
        {
            "label": "thinking",
            "detail": "planning",
            "activity_id": "activity-1",
            "preview": "",
            "output_text": "",
            "state": "",
        },
        {
            "label": "delegation",
            "detail": "started",
            "activity_id": "worker-1",
            "preview": "worker-1",
            "output_text": "",
            "state": "",
        },
    ]
    assert running_states == [
        "running",
        "step 1: planning",
        "delegation started",
    ]
    assert chunk_calls == [
        ("remote:", None),
        ("ship p37", 7),
    ]
    assert schedule_calls == ["scheduled", "scheduled"]
    assert render_calls == ["rendered"]


def test_tui_remote_turn_stream_coordinator_handles_approval_roundtrip() -> None:
    session = _session()
    approval_requests: list[tuple[str, str | None]] = []
    cleared_tokens: list[str | None] = []
    approval_resolved: list[str] = []

    class _ChatClient:
        async def stream_chat_events(
            self,
            *,
            session_id: str,
            message: str,
            workspace_dir: str,
            surface: str = "tui",
        ):
            _ = (session_id, message, workspace_dir, surface)
            yield ("approval_requested", {"token": "tok-1", "tool_name": "shell"})
            yield ("approval_resolved", {"token": "tok-1"})
            yield ("done", {"reply": "", "stop_reason": "cancelled"})

    def _record_pending_approval(_session: Any, payload: dict[str, Any]) -> str | None:
        token = str(payload.get("token") or "") or None
        if token:
            _session.projection.pending_approvals.append({"token": token})
        return token

    def _clear_pending_approval(_session: Any, token: str | None) -> None:
        cleared_tokens.append(token)
        _session.projection.pending_approvals = []

    coordinator = TuiRemoteTurnStreamCoordinator(
        append_activity_line=lambda _session, **kwargs: None,
        update_running_state=lambda _session, text: None,
        record_pending_approval=_record_pending_approval,
        handle_approval_requested=lambda _session, tool_name, token: approval_requests.append((tool_name, token)),
        pending_approval_token=lambda payload: str(payload.get("token") or ""),
        clear_pending_approval=_clear_pending_approval,
        handle_approval_resolved=lambda _session: approval_resolved.append("resolved"),
        append_assistant_stream_chunk=lambda _session, chunk, message_index: 0,
        schedule_stream_render=lambda: None,
        render_all=lambda: None,
    )

    result = asyncio.run(
        coordinator.consume(
            chat_client=_ChatClient(),
            session=session,
            message="approve this",
            workspace_dir="D:/file/Mini-Agent",
        )
    )

    assert approval_requests == [("shell", "tok-1")]
    assert cleared_tokens == ["tok-1"]
    assert approval_resolved == ["resolved"]
    assert session.projection.pending_approvals == []
    assert result.stop_reason == "cancelled"


def test_tui_remote_turn_stream_coordinator_surfaces_thinking_deltas_as_activity_output() -> None:
    session = _session()
    activity_calls: list[dict[str, Any]] = []
    running_states: list[str] = []
    render_calls: list[str] = []

    class _ChatClient:
        async def stream_chat_events(
            self,
            *,
            session_id: str,
            message: str,
            workspace_dir: str,
            surface: str = "tui",
        ):
            _ = (session_id, message, workspace_dir, surface)
            yield ("thinking_delta", {"chunk": "plan"})
            yield ("thinking_delta", {"chunk": " next"})
            yield ("heartbeat", {})
            yield ("done", {"reply": "ok", "stop_reason": "end_turn"})

    coordinator = TuiRemoteTurnStreamCoordinator(
        append_activity_line=lambda _session, **kwargs: activity_calls.append(dict(kwargs)),
        update_running_state=lambda _session, text: running_states.append(text),
        record_pending_approval=lambda _session, payload: None,
        handle_approval_requested=lambda _session, tool_name, token: None,
        pending_approval_token=lambda payload: "",
        clear_pending_approval=lambda _session, token: None,
        handle_approval_resolved=lambda _session: None,
        append_assistant_stream_chunk=lambda _session, chunk, message_index: 0,
        schedule_stream_render=lambda: None,
        render_all=lambda: render_calls.append("rendered"),
    )

    result = asyncio.run(
        coordinator.consume(
            chat_client=_ChatClient(),
            session=session,
            message="show thinking",
            workspace_dir="D:/file/Mini-Agent",
        )
    )

    assert result.reply_text == "ok"
    assert activity_calls == [
        {
            "label": "thinking",
            "detail": "thinking",
            "activity_id": "remote-thinking",
            "output_text": "plan next",
            "state": "running",
        }
    ]
    assert running_states == ["thinking"]
    assert render_calls == ["rendered"]


def test_tui_remote_turn_stream_coordinator_falls_back_to_run_chat() -> None:
    session = _session()

    class _RunOnlyTransport:
        async def run_chat(
            self,
            *,
            session_id: str,
            message: str,
            workspace_dir: str,
            surface: str = "tui",
        ) -> dict[str, Any]:
            assert session_id == "remote-1"
            assert message == "fallback"
            assert workspace_dir == "D:/file/Mini-Agent"
            assert surface == "tui"
            return {
                "session_id": "remote-1",
                "reply": "remote:fallback",
                "stop_reason": "end_turn",
                "message_count": 2,
                "token_usage": 0,
                "workspace_dir": "D:/file/Mini-Agent",
                "updated_at": "2026-04-18T00:00:00+08:00",
            }

    chat_client = RemoteChatClient(chat_transport=_RunOnlyTransport())

    coordinator = TuiRemoteTurnStreamCoordinator(
        append_activity_line=lambda _session, **kwargs: None,
        update_running_state=lambda _session, text: None,
        record_pending_approval=lambda _session, payload: None,
        handle_approval_requested=lambda _session, tool_name, token: None,
        pending_approval_token=lambda payload: "",
        clear_pending_approval=lambda _session, token: None,
        handle_approval_resolved=lambda _session: None,
        append_assistant_stream_chunk=lambda _session, chunk, message_index: 0,
        schedule_stream_render=lambda: None,
        render_all=lambda: None,
    )

    result = asyncio.run(
        coordinator.consume(
            chat_client=chat_client,
            session=session,
            message="fallback",
            workspace_dir="D:/file/Mini-Agent",
        )
    )

    assert result.reply_text == "remote:fallback"
    assert result.stop_reason == "end_turn"
    assert result.assistant_message_index is None
    assert result.response == {
        "session_id": "remote-1",
        "reply": "remote:fallback",
        "message_count": 2,
        "token_usage": 0,
        "workspace_dir": "D:/file/Mini-Agent",
        "updated_at": "2026-04-18T00:00:00+08:00",
        "delegation": None,
    }
