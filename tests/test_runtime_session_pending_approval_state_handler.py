from __future__ import annotations

import asyncio
from datetime import datetime, timezone

from mini_agent.runtime.session_pending_approval_state_handler import (
    RuntimeSessionPendingApprovalStateHandler,
)
from tests.runtime_contract_fixtures import runtime_session_stub, runtime_state_stub


def _dt() -> datetime:
    return datetime(2026, 4, 14, 12, 0, 0, tzinfo=timezone.utc)


def _session():
    touch_calls: list[datetime | None] = []

    def _touch(*, now_utc=None):  # noqa: ANN001
        touch_calls.append(now_utc)

    return runtime_session_stub(
        runtime=runtime_state_stub(
            pending_approvals=[],
            pending_approval_waiters={},
        ),
        touch=_touch,
        _touch_calls=touch_calls,
    )


def test_pending_approval_state_handler_normalizes_mutates_and_clears() -> None:
    handler = RuntimeSessionPendingApprovalStateHandler()
    session = _session()

    async def _run() -> None:
        future = asyncio.get_running_loop().create_future()
        normalized = handler.record_pending_approval(
            session,
            payload={
                "token": "tok-1",
                "tool_name": "bash",
                "arguments": {"command": "pytest -q"},
                "kind": "exec",
                "reason": "needs approval",
                "cache_key": "shell:1",
                "can_escalate": True,
                "step": 2,
            },
            future=future,
            now_utc=_dt(),
        )

        assert normalized == {
            "token": "tok-1",
            "tool_name": "bash",
            "arguments": {"command": "pytest -q"},
            "kind": "exec",
            "reason": "needs approval",
            "cache_key": "shell:1",
            "can_escalate": True,
            "step": 2,
        }
        assert session.runtime.pending_approvals == [normalized]
        assert session.runtime.pending_approval_waiters["tok-1"] is future

        future_second = asyncio.get_running_loop().create_future()
        updated = handler.record_pending_approval(
            session,
            payload={
                "token": "tok-1",
                "tool_name": "shell",
                "arguments": {"command": "uv run pytest"},
            },
            future=future_second,
        )
        assert updated["tool_name"] == "shell"
        assert session.runtime.pending_approvals == [updated]
        assert session.runtime.pending_approval_waiters["tok-1"] is future_second

        handler.clear_pending_approval(session, token="tok-1")
        assert session.runtime.pending_approvals == []
        assert session.runtime.pending_approval_waiters == {}

        other = asyncio.get_running_loop().create_future()
        handler.record_pending_approval(
            session,
            payload={"token": "tok-2", "tool_name": "shell"},
            future=other,
        )
        handler.clear_pending_approval(session)
        assert session.runtime.pending_approvals == []
        assert session.runtime.pending_approval_waiters == {}

    asyncio.run(_run())

    assert session._touch_calls == [_dt(), None, None, None, None]


def test_pending_approvals_from_raw_filters_invalid_items() -> None:
    items = RuntimeSessionPendingApprovalStateHandler.pending_approvals_from_raw(
        [
            {"token": "tok-1", "tool_name": "shell"},
            {"tool_name": "missing-token"},
            "bad-item",
        ]
    )

    assert items == [
        {
            "token": "tok-1",
            "tool_name": "shell",
            "arguments": {},
            "kind": None,
            "reason": None,
            "cache_key": None,
            "can_escalate": False,
            "step": 0,
        }
    ]
