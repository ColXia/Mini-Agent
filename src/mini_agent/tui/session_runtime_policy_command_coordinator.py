"""Shared TUI runtime-policy command orchestration."""

from __future__ import annotations

from collections.abc import Awaitable, Mapping
from dataclasses import dataclass
from typing import Any, Callable

from mini_agent.runtime.runtime_policy_service import SessionRuntimePolicyPlan, SessionRuntimePolicyService


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _response_value(response: Any, field: str) -> Any:
    if isinstance(response, Mapping):
        return response.get(field)
    return getattr(response, field, None)


@dataclass(slots=True)
class TuiSessionRuntimePolicyCommandCoordinator:
    """Own local-vs-remote runtime policy command execution for the TUI."""

    session_runtime_policy: Callable[[Any], tuple[str, str]]
    runs_via_gateway: Callable[[Any], bool]
    apply_local_session_runtime_policy: Callable[[Any, str, str], Awaitable[dict[str, Any]]]
    apply_remote_session_runtime_policy: Callable[[Any, str, str], Awaitable[Any]]
    normalize_sandbox_diagnostics_payload: Callable[[Any], dict[str, Any]]
    append_command_feedback: Callable[..., None]
    set_status: Callable[[str], None]
    render_all: Callable[[], None]

    async def update(
        self,
        session: Any,
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        command_label: str | None = None,
    ) -> bool:
        current_profile, current_access = self.session_runtime_policy(session)
        resolved_profile = SessionRuntimePolicyService.normalize_approval_profile(approval_profile) or current_profile
        resolved_access = SessionRuntimePolicyService.normalize_access_level(access_level) or current_access
        command_text = _safe_text(command_label) or f"{resolved_profile} {resolved_access}"

        if (resolved_profile, resolved_access) == (current_profile, current_access):
            unchanged_details = SessionRuntimePolicyService.unchanged_details(
                session_label=session.title,
                approval_profile=resolved_profile,
                access_level=resolved_access,
            )
            self.append_command_feedback(
                command_text,
                summary=SessionRuntimePolicyService.unchanged_summary(),
                details=unchanged_details,
            )
            self.set_status(
                SessionRuntimePolicyService.unchanged_status_text(
                    session_label=session.title,
                    approval_profile=resolved_profile,
                    access_level=resolved_access,
                )
            )
            self.render_all()
            return True

        try:
            remote_response = None
            diagnostics = None
            if self.runs_via_gateway(session):
                remote_response = await self.apply_remote_session_runtime_policy(
                    session,
                    approval_profile=resolved_profile,
                    access_level=resolved_access,
                )
                diagnostics = _response_value(remote_response, "sandbox_diagnostics")
            else:
                diagnostics = await self.apply_local_session_runtime_policy(
                    session,
                    approval_profile=resolved_profile,
                    access_level=resolved_access,
                )
        except Exception as exc:
            message = SessionRuntimePolicyService.failure_details(str(exc))
            self.append_command_feedback(
                command_text,
                summary=SessionRuntimePolicyService.failure_summary(),
                details=message,
                level="error",
            )
            self.set_status(SessionRuntimePolicyService.failure_status_text(str(exc)))
            self.render_all()
            return False

        session.projection.sandbox_diagnostics = self.normalize_sandbox_diagnostics_payload(diagnostics)
        feedback_plan = SessionRuntimePolicyPlan(
            approval_profile=resolved_profile,
            access_level=resolved_access,
        )
        summary = (
            _safe_text(_response_value(remote_response, "summary"))
            or SessionRuntimePolicyService.command_summary(feedback_plan)
        )
        details = (
            str(_response_value(remote_response, "details") or "").strip()
            or SessionRuntimePolicyService.command_details(
                feedback_plan,
                session_label=session.title,
            )
        )
        status_text = SessionRuntimePolicyService.command_status_text(
            feedback_plan,
            session_label=session.title,
        )
        self.append_command_feedback(
            command_text,
            summary=summary,
            details=details,
            metadata={"threads_visible": False},
        )
        self.set_status(status_text)
        self.render_all()
        return True


__all__ = ["TuiSessionRuntimePolicyCommandCoordinator"]
