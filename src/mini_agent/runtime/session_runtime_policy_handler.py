"""Session runtime-policy routing extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from fastapi import HTTPException

from mini_agent.runtime.sandbox_state import normalize_sandbox_diagnostics

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True, slots=True)
class RuntimeSessionRuntimePolicyPlan:
    approval_profile: str
    access_level: str
    local_sandbox_diagnostics: dict[str, Any] | None = None


@dataclass(slots=True)
class RuntimeSessionRuntimePolicyHandler:
    desired_runtime_policy_for_session: Callable[["MainAgentSessionState"], tuple[str | None, str | None]]
    effective_runtime_policy_for_agent: Callable[[Any], tuple[str, str]]

    def build_plan(
        self,
        session: "MainAgentSessionState",
        *,
        approval_profile: str | None,
        access_level: str | None,
    ) -> RuntimeSessionRuntimePolicyPlan:
        current_profile, current_access = self.desired_runtime_policy_for_session(session)
        if session.runtime.agent is not None:
            current_profile, current_access = self.effective_runtime_policy_for_agent(session.runtime.agent)

        resolved_profile = _safe_text(approval_profile).lower() or current_profile or "build"
        resolved_access = _safe_text(access_level).lower() or current_access or "default"

        if session.projection.busy and not session.runtime.pending_approvals:
            raise HTTPException(
                status_code=409,
                detail="Session is busy. Runtime mode can only change while idle or waiting on approval.",
            )

        if session.runtime.agent is not None:
            return RuntimeSessionRuntimePolicyPlan(
                approval_profile=resolved_profile,
                access_level=resolved_access,
            )

        return RuntimeSessionRuntimePolicyPlan(
            approval_profile=resolved_profile,
            access_level=resolved_access,
            local_sandbox_diagnostics=normalize_sandbox_diagnostics(
                {
                    **dict(session.projection.sandbox_diagnostics or {}),
                    "approval_profile": resolved_profile,
                    "access_level": resolved_access,
                    "sandbox_mode": "unrestricted" if resolved_access == "full-access" else "workspace",
                }
            ),
        )

    @staticmethod
    def transcript_content(plan: RuntimeSessionRuntimePolicyPlan) -> str:
        return (
            "Runtime Policy Updated\n"
            f"- execution: {plan.approval_profile}\n"
            f"- access: {plan.access_level}"
        )

    @staticmethod
    def transcript_summary(plan: RuntimeSessionRuntimePolicyPlan) -> str:
        return f"{plan.approval_profile} / {plan.access_level}"


__all__ = [
    "RuntimeSessionRuntimePolicyHandler",
    "RuntimeSessionRuntimePolicyPlan",
]
