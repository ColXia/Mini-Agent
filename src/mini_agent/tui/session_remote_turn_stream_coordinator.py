"""Shared TUI owner for remote turn stream consumption."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from mini_agent.transport import RemoteStreamErrorService


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _normalize_chat_content(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.expandtabs(4)


@dataclass(frozen=True, slots=True)
class TuiRemoteTurnStreamResult:
    """Terminal result of one remote turn stream or fallback request."""

    response: dict[str, Any] | None
    stop_reason: str
    reply_text: str
    assistant_message_index: int | None = None


@dataclass(slots=True)
class TuiRemoteTurnStreamCoordinator:
    """Consume remote gateway turn events while keeping UI mutations injected."""

    append_activity_line: Callable[..., None]
    update_running_state: Callable[[Any, str], None]
    record_pending_approval: Callable[[Any, dict[str, Any]], str | None]
    handle_approval_requested: Callable[[Any, str, str | None], None]
    pending_approval_token: Callable[[dict[str, Any]], str]
    clear_pending_approval: Callable[[Any, str | None], None]
    handle_approval_resolved: Callable[[Any], None]
    append_assistant_stream_chunk: Callable[[Any, str, int | None], int]
    schedule_stream_render: Callable[[], None]
    render_all: Callable[[], None]

    async def consume(
        self,
        *,
        gateway_client: Any,
        session: Any,
        message: str,
        workspace_dir: str,
        surface: str = "tui",
    ) -> TuiRemoteTurnStreamResult:
        stream_chat = getattr(gateway_client, "stream_chat_events", None)
        assistant_message_index: int | None = None
        stop_reason = "end_turn"
        reply_text = ""
        response: dict[str, Any] | None = None

        if callable(stream_chat):
            async for event_type, payload in stream_chat(
                session_id=session.session_id,
                message=message,
                workspace_dir=workspace_dir,
                surface=surface,
            ):
                normalized_event = _safe_text(event_type).lower() or "message"
                data = payload if isinstance(payload, dict) else {}
                if normalized_event == "activity":
                    self.append_activity_line(
                        session,
                        label=_safe_text(data.get("label")) or "activity",
                        detail=_safe_text(data.get("detail")) or "running",
                        activity_id=_safe_text(data.get("activity_id") or data.get("id")) or None,
                        preview=_safe_text(data.get("preview")),
                        output_text=_normalize_chat_content(data.get("output_text")).strip(),
                        state=_safe_text(data.get("state")),
                    )
                    running_state = _safe_text(data.get("running_state")) or _safe_text(data.get("detail"))
                    if running_state:
                        self.update_running_state(session, running_state)
                    continue
                if normalized_event == "approval_requested":
                    token = self.record_pending_approval(session, data)
                    tool_name = _safe_text(data.get("tool_name")) or "tool"
                    self.handle_approval_requested(session, tool_name, token)
                    continue
                if normalized_event == "approval_resolved":
                    token = self.pending_approval_token(data)
                    if token:
                        self.clear_pending_approval(session, token)
                    self.handle_approval_resolved(session)
                    continue
                if normalized_event.startswith("delegation."):
                    status_detail = normalized_event.split(".", 1)[-1] or "delegation"
                    self.append_activity_line(
                        session,
                        label="delegation",
                        detail=status_detail,
                        activity_id=_safe_text(data.get("task_id")) or normalized_event,
                        preview=_safe_text(data.get("worker_id") or data.get("owner")),
                        output_text=_normalize_chat_content(data.get("error")).strip(),
                        state=_safe_text(data.get("success")),
                    )
                    self.update_running_state(session, f"delegation {status_detail}")
                    continue
                if normalized_event == "status":
                    stage = _safe_text(data.get("stage")) or "running"
                    self.update_running_state(session, stage)
                    continue
                if normalized_event == "delta":
                    chunk = str(data.get("chunk", ""))
                    if chunk:
                        assistant_message_index = self.append_assistant_stream_chunk(
                            session,
                            chunk,
                            assistant_message_index,
                        )
                        self.schedule_stream_render()
                    continue
                if normalized_event == "heartbeat":
                    self.render_all()
                    continue
                if normalized_event == "error":
                    raise RuntimeError(RemoteStreamErrorService.payload_detail(data))
                if normalized_event == "done":
                    response = data
                    stop_reason = _safe_text(data.get("stop_reason")).lower() or "end_turn"
                    reply_text = _safe_text(data.get("reply"))
                    break
            return TuiRemoteTurnStreamResult(
                response=response,
                stop_reason=stop_reason,
                reply_text=reply_text,
                assistant_message_index=assistant_message_index,
            )

        response = await gateway_client.run_chat(
            session_id=session.session_id,
            message=message,
            workspace_dir=workspace_dir,
            surface=surface,
        )
        stop_reason = _safe_text(response.get("stop_reason")).lower() or "end_turn"
        reply_text = _safe_text(response.get("reply"))
        return TuiRemoteTurnStreamResult(
            response=response,
            stop_reason=stop_reason,
            reply_text=reply_text,
            assistant_message_index=None,
        )


__all__ = [
    "TuiRemoteTurnStreamCoordinator",
    "TuiRemoteTurnStreamResult",
]
