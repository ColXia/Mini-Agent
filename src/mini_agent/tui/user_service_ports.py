"""TUI-specific runtime port adapters for user service integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mini_agent.runtime.live_control.run_control_store import RuntimeSessionRunControlStore

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


class TuiLocalRunRuntimePort:
    """RunRuntimePort implementation for TUI local mode.

    Adapts RuntimeSessionRunControlStore to the RunRuntimePort protocol,
    allowing TUI to use RunControlApplicationService for cancel/interrupt/resume.
    """

    def __init__(
        self,
        run_control_store: RuntimeSessionRunControlStore | None = None,
        session_resolver: callable | None = None,
    ) -> None:
        self._store = run_control_store or RuntimeSessionRunControlStore()
        self._session_resolver = session_resolver

    def _resolve_session(self, run_id: str) -> "MainAgentSessionState | None":
        """Resolve session from run_id using the session resolver if available."""
        if self._session_resolver is None:
            return None
        session_id = RuntimeSessionRunControlStore.session_id_for_run_id(run_id)
        if session_id is None:
            return None
        return self._session_resolver(session_id)

    async def get_run(self, run_id: str) -> Any:
        """Get run summary for the given run_id."""
        session_id = RuntimeSessionRunControlStore.session_id_for_run_id(run_id)
        if session_id is None:
            return None
        # TUI local mode doesn't have a separate run summary
        # Return a minimal dict with run_id
        return {"run_id": run_id, "session_id": session_id}

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Request interrupt for the run.

        Uses the run control store to request interrupt on the session.
        """
        session = self._resolve_session(run_id)
        if session is None:
            return {"run_id": run_id, "interrupt_requested": False, "error": "session not found"}

        state = self._store.request_interrupt(session, source=source, reason=reason)
        return {
            "run_id": run_id,
            "interrupt_requested": True,
            "state": state.state if state else None,
            "reason": reason,
        }

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Request resume for the run.

        Uses the run control store to request resume on the session.
        """
        session = self._resolve_session(run_id)
        if session is None:
            return {"run_id": run_id, "resume_requested": False, "error": "session not found"}

        state = self._store.request_resume(session, source=source, resume_token=resume_token)
        return {
            "run_id": run_id,
            "resume_requested": True,
            "state": state.state if state else None,
            "resume_token": resume_token,
        }

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any:
        """Request cancel for the run.

        Uses the run control store to request cancel on the session.
        """
        session = self._resolve_session(run_id)
        if session is None:
            return {"run_id": run_id, "cancel_requested": False, "error": "session not found"}

        state = self._store.request_cancel(session, source=source, reason=reason)
        return {
            "run_id": run_id,
            "cancel_requested": True,
            "state": state.state if state else None,
            "reason": reason,
        }

    async def resolve_approval_wait(
        self,
        run_id: str,
        *,
        approved: bool,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any:
        """Resolve approval wait for the run.

        Uses the run control store to resolve the approval wait.
        """
        session = self._resolve_session(run_id)
        if session is None:
            return {"run_id": run_id, "resolved": False, "error": "session not found"}

        result = self._store.resolve_active_approval_wait(session, token=token, approved=approved)
        decision = "approved" if approved else "denied"
        return {
            "run_id": run_id,
            "resolved": True,
            "decision": decision,
            "token": token,
        }


class TuiLocalSessionTaskPort:
    """SessionTaskPort implementation for TUI local mode.

    Resolves run_id from session using RuntimeSessionRunControlStore.
    """

    async def resolve_run_id_for_session(self, session_id: str) -> str | None:
        """Resolve run_id for the given session_id."""
        if not session_id:
            return None
        return RuntimeSessionRunControlStore.run_id_for_session(session_id)


__all__ = [
    "TuiLocalRunRuntimePort",
    "TuiLocalSessionTaskPort",
]