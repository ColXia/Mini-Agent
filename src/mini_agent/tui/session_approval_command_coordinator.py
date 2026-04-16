"""Shared TUI approval command orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Any, Callable

from mini_agent.runtime.session_pending_approval_service import (
    PendingApprovalResolutionError,
    SessionPendingApprovalService,
)
from mini_agent.transport import extract_gateway_error_info


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _response_value(response: Any, field: str) -> Any:
    if isinstance(response, Mapping):
        return response.get(field)
    return getattr(response, field, None)


def _command_text(action_name: str, token: str | None) -> str:
    normalized_token = _safe_text(token)
    return f"{action_name} {normalized_token}".strip() if normalized_token else action_name


@dataclass(slots=True)
class TuiSessionApprovalCommandCoordinator:
    """Own local-vs-remote approval command execution for the TUI."""

    runs_via_gateway: Callable[[Any], bool]
    has_local_runtime_state: Callable[[Any], bool]
    pending_approval_token: Callable[[dict[str, Any]], str]
    remote_respond_to_approval: Callable[[Any, bool, str | None], Awaitable[Any]]
    sync_remote_session_detail: Callable[[Any], Awaitable[None]]
    clear_pending_approval: Callable[[Any, str | None], None]
    close_approval_modal: Callable[[], None]
    append_command_feedback: Callable[..., None]
    set_status: Callable[[str], None]
    render_all: Callable[[], None]

    async def respond(
        self,
        *,
        session: Any,
        approved: bool,
        token: str | None = None,
    ) -> bool:
        action_name = "approve" if approved else "deny"
        normalized_token = _safe_text(token) or None
        if self.runs_via_gateway(session):
            return await self._respond_remote(
                session=session,
                approved=approved,
                action_name=action_name,
                normalized_token=normalized_token,
            )
        return await self._respond_local(
            session=session,
            approved=approved,
            action_name=action_name,
            normalized_token=normalized_token,
        )

    async def _respond_remote(
        self,
        *,
        session: Any,
        approved: bool,
        action_name: str,
        normalized_token: str | None,
    ) -> bool:
        projection = session.projection
        try:
            response = await self.remote_respond_to_approval(session, approved, normalized_token)
        except Exception as exc:
            detail = extract_gateway_error_info(exc).detail
            self.append_command_feedback(
                _command_text(action_name, normalized_token),
                summary=SessionPendingApprovalService.error_summary(detail=detail),
                details=detail,
                level="error",
            )
            self.set_status(SessionPendingApprovalService.error_status_text(detail=detail))
            self.render_all()
            return False

        resolved_token = _safe_text(_response_value(response, "token"))
        tool_name = _safe_text(_response_value(response, "tool_name")) or "tool"
        decision = _safe_text(_response_value(response, "decision")) or ("approved" if approved else "denied")
        self.clear_pending_approval(session, resolved_token)
        try:
            await self.sync_remote_session_detail(session)
        except Exception:
            pass
        self.append_command_feedback(
            _command_text(action_name, resolved_token),
            summary=f"{decision} {tool_name}",
            details=f"{decision.capitalize()} pending tool call for {tool_name}.",
        )
        if not projection.pending_approvals:
            self.close_approval_modal()
        self.set_status(f"{decision.capitalize()} {tool_name} for {session.title}.")
        self.render_all()
        return True

    async def _respond_local(
        self,
        *,
        session: Any,
        approved: bool,
        action_name: str,
        normalized_token: str | None,
    ) -> bool:
        projection = session.projection
        runtime = session.runtime
        loop = runtime.submission_loop
        pending = [item for item in projection.pending_approvals if self.pending_approval_token(item)]
        if not pending:
            return self._emit_nothing_pending(action_name)

        if self.has_local_runtime_state(session) and loop is None:
            return self._emit_nothing_pending(action_name)

        try:
            target = SessionPendingApprovalService.resolve_target(
                pending=pending,
                token=normalized_token,
            )
        except PendingApprovalResolutionError as exc:
            message = exc.detail
            summary = SessionPendingApprovalService.error_summary(code=exc.code, detail=message)
            status = SessionPendingApprovalService.error_status_text(code=exc.code, detail=message)
            self.append_command_feedback(
                action_name,
                summary=summary,
                details=message,
                level="error",
            )
            self.set_status(status)
            self.render_all()
            return False

        resolution = SessionPendingApprovalService.build_decision(
            approved=approved,
            token=target.token,
            tool_name=target.tool_name,
        )
        await loop.submit_exec_approval(approved=approved, token=target.token)
        self.clear_pending_approval(session, target.token)
        self.append_command_feedback(
            _command_text(action_name, target.token),
            summary=resolution.summary,
            details=f"{resolution.decision.capitalize()} pending tool call for {target.tool_name}.",
        )
        if not projection.pending_approvals:
            self.close_approval_modal()
        self.set_status(f"{resolution.decision.capitalize()} {target.tool_name} for {session.title}.")
        self.render_all()
        return True

    def _emit_nothing_pending(self, action_name: str) -> bool:
        message = "No pending approval request."
        self.append_command_feedback(
            action_name,
            summary="nothing pending",
            details=message,
            level="error",
        )
        self.set_status(message)
        self.render_all()
        return False


__all__ = ["TuiSessionApprovalCommandCoordinator"]
