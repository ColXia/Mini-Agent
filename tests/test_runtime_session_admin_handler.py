from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from mini_agent.runtime.handlers.session_admin_handler import RuntimeSessionAdminHandler
from tests.runtime_contract_fixtures import (
    runtime_projection_stub,
    runtime_session_stub,
    runtime_state_stub,
    transcript_state_stub,
)


def _dt() -> datetime:
    return datetime(2026, 4, 13, 13, 0, 0, tzinfo=timezone.utc)


def _session():
    touch_calls: list[datetime | None] = []

    def _touch(*, now_utc=None):  # noqa: ANN001
        touch_calls.append(now_utc)

    return runtime_session_stub(
        session_id="sess-1",
        projection=runtime_projection_stub(
            title="Session 1",
            shared=False,
            active_surface="qq",
            origin_surface="qq",
        ),
        runtime=runtime_state_stub(lock=asyncio.Lock()),
        transcript_state=transcript_state_stub(
            transcript=[{"role": "user", "content": "hello"}],
            next_transcript_index=2,
        ),
        lifecycle_state=SimpleNamespace(state="active"),
        touch=_touch,
        _touch_calls=touch_calls,
    )


def test_runtime_session_admin_handler_rename_and_share_mutations() -> None:
    session = _session()
    persisted: list[str] = []

    handler = RuntimeSessionAdminHandler(
        rename_session_mutation=lambda s, title: setattr(s.projection, "title", title),
        set_session_shared_mutation=lambda s, shared: setattr(s.projection, "shared", bool(shared)),
        reset_runtime_state_mutation=lambda s, clear_runtime_task_memory: None,
        bind_surface_mutation=lambda s, **kwargs: None,
        reset_session_lifecycle_mutation=lambda s, now_utc=None: None,
        build_session_summary=lambda s: {
            "title": s.projection.title,
            "shared": s.projection.shared,
        },
        persist_session=lambda s: persisted.append(s.session_id),
    )

    async def _run() -> None:
        renamed = await handler.rename_session(session, title="Demo")
        shared = await handler.set_session_shared(session, shared=True)
        assert renamed == {"title": "Demo", "shared": False}
        assert shared == {"title": "Demo", "shared": True}

    asyncio.run(_run())

    assert persisted == ["sess-1", "sess-1"]
    assert len(session._touch_calls) == 2


def test_runtime_session_admin_handler_reset_clears_transcript_and_resets_lifecycle() -> None:
    session = _session()
    reset_runtime_calls: list[bool] = []
    lifecycle_reset_calls: list[datetime | None] = []
    persisted: list[str] = []

    handler = RuntimeSessionAdminHandler(
        rename_session_mutation=lambda s, title: None,
        set_session_shared_mutation=lambda s, shared: None,
        reset_runtime_state_mutation=lambda s, clear_runtime_task_memory: reset_runtime_calls.append(
            bool(clear_runtime_task_memory)
        ),
        bind_surface_mutation=lambda s, **kwargs: None,
        reset_session_lifecycle_mutation=lambda s, now_utc=None: lifecycle_reset_calls.append(now_utc),
        build_session_summary=lambda s: {},
        persist_session=lambda s: persisted.append(s.session_id),
    )

    async def _run() -> None:
        await handler.reset_session(session, now_utc=_dt())

    asyncio.run(_run())

    assert session.transcript_state.transcript == []
    assert session.transcript_state.next_transcript_index == 1
    assert reset_runtime_calls == [True]
    assert lifecycle_reset_calls == [_dt()]
    assert persisted == ["sess-1"]
    assert session._touch_calls == [_dt()]


def test_runtime_session_admin_handler_set_active_surface_disables_reply_and_persists() -> None:
    session = _session()
    bind_calls: list[dict[str, object]] = []
    persisted: list[str] = []

    handler = RuntimeSessionAdminHandler(
        rename_session_mutation=lambda s, title: None,
        set_session_shared_mutation=lambda s, shared: None,
        reset_runtime_state_mutation=lambda s, clear_runtime_task_memory: None,
        bind_surface_mutation=lambda s, **kwargs: bind_calls.append(dict(kwargs)),
        reset_session_lifecycle_mutation=lambda s, now_utc=None: None,
        build_session_summary=lambda s: {
            "active_surface": s.projection.active_surface,
        },
        persist_session=lambda s: persisted.append(s.session_id),
    )

    async def _run() -> None:
        summary = await handler.set_active_surface(session, surface="tui", now_utc=_dt())
        assert summary == {"active_surface": "qq"}

    asyncio.run(_run())

    assert bind_calls == [
        {
            "surface": "tui",
            "reply_enabled": False,
            "now_utc": _dt(),
        }
    ]
    assert persisted == ["sess-1"]
    assert session._touch_calls == [_dt()]



