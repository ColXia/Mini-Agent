"""Shared session runtime-policy semantics across surfaces and runtime."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException

from mini_agent.agent_core.runtime_bindings import get_agent_runtime_services
from mini_agent.runtime.sandbox_state import normalize_sandbox_diagnostics


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _normalize_runtime_approval_profile(value: Any) -> str:
    normalized = _safe_text(value).lower().replace("_", "-")
    if normalized in {"plan", "build"}:
        return normalized
    return ""


def _normalize_runtime_access_level(value: Any) -> str:
    normalized = _safe_text(value).lower().replace("_", "-")
    if normalized in {"default", "full-access"}:
        return normalized
    return ""


@dataclass(frozen=True, slots=True)
class SessionRuntimePolicyPlan:
    approval_profile: str
    access_level: str
    local_sandbox_diagnostics: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class SessionRuntimePolicyExecution:
    plan: SessionRuntimePolicyPlan
    diagnostics: dict[str, Any]


@dataclass(frozen=True, slots=True)
class SessionRuntimePolicyAutofixRequest:
    approval_profile: str
    access_level: str


class SessionRuntimePolicyService:
    """Normalize and plan runtime-policy updates independent of surface/runtime."""

    @staticmethod
    def normalize_approval_profile(value: Any) -> str:
        return _normalize_runtime_approval_profile(value)

    @staticmethod
    def normalize_access_level(value: Any) -> str:
        return _normalize_runtime_access_level(value)

    @classmethod
    def effective_runtime_policy_for_agent(cls, agent: Any) -> tuple[str, str]:
        runtime_policy_engine = get_agent_runtime_services(agent).runtime_policy_engine
        policy = getattr(runtime_policy_engine, "policy", None)
        approval_profile = cls.normalize_approval_profile(getattr(policy, "approval_profile", None)) or "build"
        access_level = cls.normalize_access_level(getattr(policy, "access_level", None)) or "default"
        return approval_profile, access_level

    @classmethod
    def desired_runtime_policy_from_diagnostics(
        cls,
        sandbox_diagnostics: Any,
    ) -> tuple[str | None, str | None]:
        diagnostics = sandbox_diagnostics if isinstance(sandbox_diagnostics, dict) else {}
        approval_profile = cls.normalize_approval_profile(diagnostics.get("approval_profile")) or None
        access_level = cls.normalize_access_level(diagnostics.get("access_level")) or None
        return approval_profile, access_level

    @classmethod
    def current_runtime_policy(
        cls,
        *,
        agent: Any | None,
        sandbox_diagnostics: Any,
        default_approval_profile: str = "build",
        default_access_level: str = "default",
    ) -> tuple[str, str]:
        if agent is not None:
            return cls.effective_runtime_policy_for_agent(agent)
        approval_profile, access_level = cls.desired_runtime_policy_from_diagnostics(sandbox_diagnostics)
        return (
            approval_profile or default_approval_profile,
            access_level or default_access_level,
        )

    @classmethod
    def local_sandbox_diagnostics(
        cls,
        *,
        sandbox_diagnostics: Any,
        approval_profile: str,
        access_level: str,
    ) -> dict[str, Any]:
        return normalize_sandbox_diagnostics(
            {
                **dict(sandbox_diagnostics or {}),
                "approval_profile": approval_profile,
                "access_level": access_level,
                "sandbox_mode": "unrestricted" if access_level == "full-access" else "workspace",
            }
        )

    @classmethod
    def build_plan(
        cls,
        *,
        current_approval_profile: str | None,
        current_access_level: str | None,
        requested_approval_profile: str | None,
        requested_access_level: str | None,
        busy: bool,
        waiting_on_approval: bool,
        runtime_attached: bool,
        sandbox_diagnostics: Any,
    ) -> SessionRuntimePolicyPlan:
        resolved_profile = cls.normalize_approval_profile(requested_approval_profile) or current_approval_profile or "build"
        resolved_access = cls.normalize_access_level(requested_access_level) or current_access_level or "default"

        if busy and not waiting_on_approval:
            raise HTTPException(
                status_code=409,
                detail="Session is busy. Runtime mode can only change while idle or waiting on approval.",
            )

        if runtime_attached:
            return SessionRuntimePolicyPlan(
                approval_profile=resolved_profile,
                access_level=resolved_access,
            )

        return SessionRuntimePolicyPlan(
            approval_profile=resolved_profile,
            access_level=resolved_access,
            local_sandbox_diagnostics=cls.local_sandbox_diagnostics(
                sandbox_diagnostics=sandbox_diagnostics,
                approval_profile=resolved_profile,
                access_level=resolved_access,
            ),
        )

    @classmethod
    def execute_update(
        cls,
        *,
        current_approval_profile: str | None,
        current_access_level: str | None,
        requested_approval_profile: str | None,
        requested_access_level: str | None,
        busy: bool,
        waiting_on_approval: bool,
        runtime_attached: bool,
        sandbox_diagnostics: Any,
        normalize_sandbox_diagnostics_payload: Callable[[Any], dict[str, Any]],
        reconfigure_attached_runtime: Callable[[str, str], Any] | None = None,
    ) -> SessionRuntimePolicyExecution:
        plan = cls.build_plan(
            current_approval_profile=current_approval_profile,
            current_access_level=current_access_level,
            requested_approval_profile=requested_approval_profile,
            requested_access_level=requested_access_level,
            busy=busy,
            waiting_on_approval=waiting_on_approval,
            runtime_attached=runtime_attached,
            sandbox_diagnostics=sandbox_diagnostics,
        )
        if runtime_attached:
            if reconfigure_attached_runtime is None:
                raise RuntimeError("Attached runtime policy updates require a reconfigure callback.")
            diagnostics = normalize_sandbox_diagnostics_payload(
                reconfigure_attached_runtime(plan.approval_profile, plan.access_level)
            )
        else:
            diagnostics = normalize_sandbox_diagnostics_payload(plan.local_sandbox_diagnostics)
        return SessionRuntimePolicyExecution(
            plan=plan,
            diagnostics=dict(diagnostics),
        )

    @classmethod
    def build_pre_turn_autofix_request(
        cls,
        *,
        requested_surface: str | None,
        origin_surface: str | None,
        active_surface: str | None,
        shared: bool,
        current_approval_profile: str | None,
        current_access_level: str | None,
    ) -> SessionRuntimePolicyAutofixRequest | None:
        normalized_requested_surface = _safe_text(requested_surface).lower()
        normalized_origin_surface = _safe_text(origin_surface).lower()
        normalized_active_surface = _safe_text(active_surface).lower()
        approval_profile = cls.normalize_approval_profile(current_approval_profile) or "build"
        access_level = cls.normalize_access_level(current_access_level) or "default"

        is_desktop_owned = normalized_origin_surface == "desktop" or (
            not normalized_origin_surface and normalized_active_surface == "desktop"
        )
        should_upgrade = (
            normalized_requested_surface == "desktop"
            and not bool(shared)
            and is_desktop_owned
            and approval_profile == "plan"
        )
        if not should_upgrade:
            return None

        return SessionRuntimePolicyAutofixRequest(
            approval_profile="build",
            access_level=access_level,
        )

    @staticmethod
    def transcript_content(plan: SessionRuntimePolicyPlan) -> str:
        return (
            "Runtime Policy Updated\n"
            f"- execution: {plan.approval_profile}\n"
            f"- access: {plan.access_level}"
        )

    @staticmethod
    def transcript_summary(plan: SessionRuntimePolicyPlan) -> str:
        return f"{plan.approval_profile} / {plan.access_level}"

    @staticmethod
    def command_summary(plan: SessionRuntimePolicyPlan) -> str:
        return f"runtime {plan.approval_profile} / {plan.access_level}"

    @staticmethod
    def command_details(
        plan: SessionRuntimePolicyPlan,
        *,
        session_label: str | None = None,
        session_id: str | None = None,
        active_surface: str | None = None,
    ) -> str:
        lines = ["Runtime policy updated."]
        label = _safe_text(session_label)
        if label:
            lines.append(f"- session: {label}")
        identifier = _safe_text(session_id)
        if identifier:
            lines.append(f"- session_id: {identifier}")
        surface = _safe_text(active_surface)
        if surface:
            lines.append(f"- surface: {surface}")
        lines.append(f"- execution: {plan.approval_profile}")
        lines.append(f"- access: {plan.access_level}")
        return "\n".join(lines)

    @staticmethod
    def command_status_text(
        plan: SessionRuntimePolicyPlan,
        *,
        session_label: str | None = None,
    ) -> str:
        label = _safe_text(session_label)
        if label:
            return f"{label}: runtime set to {plan.approval_profile} / {plan.access_level}."
        return f"Runtime set to {plan.approval_profile} / {plan.access_level}."

    @staticmethod
    def unchanged_summary() -> str:
        return "runtime unchanged"

    @staticmethod
    def unchanged_details(
        *,
        session_label: str | None,
        approval_profile: str,
        access_level: str,
    ) -> str:
        label = _safe_text(session_label) or "This session"
        return f"{label} already uses {approval_profile} / {access_level}."

    @classmethod
    def unchanged_status_text(
        cls,
        *,
        session_label: str | None,
        approval_profile: str,
        access_level: str,
    ) -> str:
        return cls.unchanged_details(
            session_label=session_label,
            approval_profile=approval_profile,
            access_level=access_level,
        )

    @staticmethod
    def failure_summary() -> str:
        return "runtime policy failed"

    @staticmethod
    def failure_details(detail: str) -> str:
        normalized = _safe_text(detail)
        if not normalized:
            return "Runtime policy update failed."
        if normalized.lower().startswith("runtime policy update failed:"):
            return normalized
        return f"Runtime policy update failed: {normalized}"

    @classmethod
    def failure_status_text(cls, detail: str) -> str:
        return cls.failure_details(detail)


__all__ = [
    "SessionRuntimePolicyAutofixRequest",
    "SessionRuntimePolicyExecution",
    "SessionRuntimePolicyPlan",
    "SessionRuntimePolicyService",
]
