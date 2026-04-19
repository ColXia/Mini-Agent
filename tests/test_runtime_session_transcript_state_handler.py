from __future__ import annotations

from datetime import datetime, timezone

from mini_agent.runtime.live_control.session_transcript_state_handler import (
    RuntimeSessionTranscriptStateHandler,
)
from tests.runtime_contract_fixtures import (
    runtime_projection_stub,
    runtime_session_stub,
    transcript_state_stub,
)


def _dt() -> datetime:
    return datetime(2026, 4, 16, 9, 0, 0, tzinfo=timezone.utc)


def test_transcript_state_handler_record_message_binds_surface_and_appends_entry() -> None:
    persisted: list[str] = []
    session = runtime_session_stub(
        session_id="sess-transcript",
        projection=runtime_projection_stub(
            active_surface="",
            origin_surface="",
            channel_type=None,
            conversation_id=None,
            sender_id=None,
            reply_enabled=False,
        ),
        transcript_state=transcript_state_stub(transcript=[], next_transcript_index=1),
    )
    handler = RuntimeSessionTranscriptStateHandler(
        persist_session_fn=lambda target: persisted.append(target.session_id),
    )

    handler.record_message(
        session,
        role="user",
        content="hello",
        surface="desktop",
        channel_type="desktop",
        conversation_id="conv-1",
        sender_id="sender-1",
        now_utc=_dt(),
    )

    assert session.projection.origin_surface == "desktop"
    assert session.projection.active_surface == "desktop"
    assert session.projection.channel_type == "desktop"
    assert session.projection.conversation_id == "conv-1"
    assert session.projection.sender_id == "sender-1"
    assert session.projection.reply_enabled is True
    assert [entry.role for entry in session.transcript_state.transcript] == ["user"]
    assert session.transcript_state.transcript[0].content == "hello"
    assert session.transcript_state.next_transcript_index == 2
    assert persisted == ["sess-transcript", "sess-transcript"]


def test_transcript_state_handler_record_activity_reuses_current_turn_entry() -> None:
    session = runtime_session_stub(
        session_id="sess-activity",
        projection=runtime_projection_stub(
            active_surface="desktop",
            origin_surface="desktop",
        ),
        transcript_state=transcript_state_stub(
            transcript=[],
            next_transcript_index=1,
            current_turn_id="turn-1",
        ),
    )
    handler = RuntimeSessionTranscriptStateHandler()

    first = handler.record_activity(
        session,
        label="shell",
        detail="running",
        surface="desktop",
        activity_id="step-1",
        preview="dir",
        output_text="line1\nline2",
        state="running",
        now_utc=_dt(),
    )
    second = handler.record_activity(
        session,
        label="shell",
        detail="done",
        surface="desktop",
        activity_id="step-1",
        output_text="done",
        state="done",
        now_utc=_dt(),
    )

    assert first["id"] == "step-1"
    assert second["id"] == "step-1"
    assert len(session.transcript_state.transcript) == 1
    entry = session.transcript_state.transcript[0]
    assert entry.role == "tool"
    assert entry.metadata["kind"] == "activity"
    assert entry.metadata["turn_id"] == "turn-1"
    assert entry.metadata["activity_items"] == [
        {
            "id": "step-1",
            "label": "shell",
            "detail": "done",
            "preview": "dir",
            "output_text": "done",
            "output_summary": "done",
            "state": "done",
        }
    ]
