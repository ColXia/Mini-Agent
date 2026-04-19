from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from mini_agent.interfaces.agent import MainAgentSessionApprovalResponse
from mini_agent.runtime.handlers.session_run_control_handler import RuntimeSessionRunControlHandler
from mini_agent.runtime.live_control.run_control_store import RuntimeSessionRunControlStore
from mini_agent.runtime.read_models.run_projection_builder import RuntimeSessionRunProjectionBuilder
from tests.runtime_contract_fixtures import (
    runtime_projection_stub,
    runtime_session_stub,
    runtime_state_stub,
)


def _build_run_control_handler(**overrides):
    run_control_store = overrides.pop("run_control_store", RuntimeSessionRunControlStore())
    run_projection_builder = overrides.pop(
        "run_projection_builder",
        RuntimeSessionRunProjectionBuilder(run_control_store=run_control_store),
    )
    defaults = dict(
        run_control_store=run_control_store,
        run_projection_builder=run_projection_builder,
        session_commands=SimpleNamespace(
            record=lambda *args, **kwargs: None,  # noqa: ARG005
        ),
        session_interrupt=SimpleNamespace(),
        load_persisted_record=lambda _session_id: None,
        persist_session=lambda _session: None,
    )
    defaults.update(overrides)
    return RuntimeSessionRunControlHandler(**defaults)


def _run_session(tmp_path: Path, *, session_id: str = "sess-run-handler"):
    return runtime_session_stub(
        session_id=session_id,
        workspace_dir=tmp_path / "workspace",
        projection=runtime_projection_stub(
            busy=False,
            active_surface="desktop",
            origin_surface="desktop",
            running_state="",
            channel_type="desktop",
            conversation_id="conv-1",
            sender_id="sender-1",
        ),
        runtime=runtime_state_stub(
            pending_approvals=[],
            pending_approval_waiters={},
        ),
    )


def test_runtime_session_run_control_handler_resolves_session_backed_run_ids_for_active_and_persisted_sessions(
    tmp_path: Path,
) -> None:
    active = _run_session(tmp_path, session_id="sess-active")
    persisted_records = {"sess-persisted": {"session_id": "sess-persisted"}}
    handler = _build_run_control_handler(
        load_persisted_record=lambda session_id: persisted_records.get(session_id),
    )

    assert handler.resolve_run_id_for_session("sess-active", active_sessions={"sess-active": active}) == RuntimeSessionRunControlStore.run_id_for_session(
        "sess-active"
    )
    assert handler.resolve_run_id_for_session("sess-persisted", active_sessions={}) == RuntimeSessionRunControlStore.run_id_for_session(
        "sess-persisted"
    )
    assert handler.resolve_run_id_for_session("missing", active_sessions={}) is None


def test_runtime_session_run_control_handler_interrupt_uses_kernel_run_truth_not_projection_busy(
    tmp_path: Path,
) -> None:
    session = _run_session(tmp_path)
    store = RuntimeSessionRunControlStore()
    persisted: list[str] = []
    handler = _build_run_control_handler(
        run_control_store=store,
        persist_session=lambda candidate: persisted.append(candidate.session_id),
    )
    run_id = RuntimeSessionRunControlStore.run_id_for_session(session.session_id)

    store.begin_turn(session, surface="desktop", detail="running")
    assert session.projection.busy is False

    projection = handler.interrupt_run(
        run_id,
        active_sessions={session.session_id: session},
        reason="pause",
    )

    assert projection["status"] == "interrupt_requested"
    assert projection["phase"] == "interrupting"
    assert projection["busy"] is True
    assert session.projection.running_state == "interrupt requested"
    assert persisted == [session.session_id]


def test_runtime_session_run_control_handler_resume_waiting_run_routes_through_pending_approval_resolution(
    tmp_path: Path,
) -> None:
    session = _run_session(tmp_path)
    store = RuntimeSessionRunControlStore()
    approvals: list[tuple[bool, str | None]] = []

    class _ApprovalExecution:
        transcript_command = "approve"
        transcript_summary = "approved"
        transcript_details = "approved"
        token = "approval-1"
        tool_name = "shell"
        response = MainAgentSessionApprovalResponse(
            status="resolved",
            session_id=session.session_id,
            token="approval-1",
            tool_name="shell",
            decision="approved",
            active_surface="desktop",
        )

        def finalize(self) -> None:
            return None

    handler = _build_run_control_handler(
        run_control_store=store,
        session_interrupt=SimpleNamespace(
            execute_approval=lambda _session, *, approved, token: (
                approvals.append((approved, token)) or _ApprovalExecution()
            )
        ),
    )
    run_id = RuntimeSessionRunControlStore.run_id_for_session(session.session_id)

    store.begin_turn(session, surface="desktop", detail="running")
    store.replace_active_approval_wait(
        session,
        payload={"token": "approval-1", "tool_name": "shell"},
        future=None,
    )

    response = handler.resume_run(
        run_id,
        active_sessions={session.session_id: session},
        resume_token="approval-1",
    )

    assert response.decision == "approved"
    assert approvals == [(True, "approval-1")]
