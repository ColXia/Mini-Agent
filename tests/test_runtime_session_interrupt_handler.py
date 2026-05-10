from __future__ import annotations

import asyncio

from mini_agent.runtime.live_control.session_cancel_service import SessionCancelService
from mini_agent.runtime.live_control.session_interrupt_handler import RuntimeSessionInterruptHandler
from tests.runtime_contract_fixtures import (
    runtime_projection_stub,
    runtime_session_stub,
    runtime_state_stub,
)


def test_interrupt_handler_cancel_sets_event_and_releases_pending_waiters() -> None:
    async def _run() -> None:
        cancel_event = asyncio.Event()
        approval_waiter = asyncio.get_running_loop().create_future()
        session = runtime_session_stub(
            session_id="sess-cancel",
            projection=runtime_projection_stub(
                busy=True,
                active_surface="qq",
                origin_surface="cli",
            ),
            runtime=runtime_state_stub(
                cancel_event=cancel_event,
                pending_approval_waiters={"tok-1": approval_waiter},
            ),
        )
        handler = RuntimeSessionInterruptHandler(
            normalize_surface=lambda value: value,
        )

        execution = handler.execute_cancel(session, reason="user_cancel")

        assert cancel_event.is_set() is True
        assert approval_waiter.done() is True
        assert approval_waiter.result() is None
        assert session.projection.running_state == SessionCancelService.REQUESTED_STATE
        assert execution.response.status == SessionCancelService.CANCEL_REQUESTED_STATUS
        assert execution.response.active_surface == "qq"
        assert execution.transcript_summary == SessionCancelService.requested_summary()
        assert execution.transcript_details == (
            "Action: cancel\n"
            "State: cancellation requested\n"
            "Reason: user_cancel"
        )

    asyncio.run(_run())


def test_interrupt_handler_resolves_single_pending_approval_and_finalizes_waiter() -> None:
    async def _run() -> None:
        approval_waiter = asyncio.get_running_loop().create_future()
        session = runtime_session_stub(
            session_id="sess-approval",
            projection=runtime_projection_stub(
                active_surface="qq",
                origin_surface="cli",
            ),
            runtime=runtime_state_stub(
                pending_approvals=[{"token": "tok-1", "tool_name": "shell", "arguments": {}}],
                pending_approval_waiters={"tok-1": approval_waiter},
            ),
        )
        handler = RuntimeSessionInterruptHandler(
            normalize_surface=lambda value: value,
        )

        execution = handler.execute_approval(session, approved=True, token=None)

        assert execution.response.status == "resolved"
        assert execution.response.token == "tok-1"
        assert execution.response.tool_name == "shell"
        assert execution.response.decision == "approved"
        assert execution.response.active_surface == "qq"
        assert execution.transcript_command == "approve"
        assert execution.transcript_summary == "approved shell"
        assert execution.transcript_details == "Action: approve\nToken: tok-1\nTool: shell"

        execution.finalize()

        assert approval_waiter.done() is True
        assert approval_waiter.result() is True

    asyncio.run(_run())


