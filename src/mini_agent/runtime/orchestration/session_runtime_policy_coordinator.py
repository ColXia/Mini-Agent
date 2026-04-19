"""Runtime policy and lifecycle coordination helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from fastapi import HTTPException

from mini_agent.agent_core.runtime_bindings import get_agent_runtime_services
from mini_agent.agent_core.session.lifecycle import (
    SessionLifecycleManager,
    SessionLifecyclePolicy,
    SessionResetMode,
)
from mini_agent.runtime.support.sandbox_state import normalize_sandbox_diagnostics


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _mode_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return _safe_text(raw).lower()


MAIN_AGENT_RUNTIME_MODE_ENV = "MINI_AGENT_RUNTIME_MODE"
MAIN_AGENT_MAIN_WORKSPACE_ENV = "MINI_AGENT_MAIN_WORKSPACE"
MAIN_AGENT_TEAM_MAX_AGENTS_ENV = "MINI_AGENT_TEAM_MAX_AGENTS"
SESSION_RESET_MODE_ENV = "MINI_AGENT_SESSION_RESET_MODE"
SESSION_IDLE_SECONDS_ENV = "MINI_AGENT_SESSION_IDLE_SECONDS"


class MainAgentRuntimeMode(str, Enum):
    """Runtime policy modes for main-agent orchestration."""

    SINGLE_MAIN = "single_main"
    TEAM = "team"


@dataclass(frozen=True)
class MainAgentRuntimePolicy:
    """Policy for current single-main mode and future team expansion."""

    mode: MainAgentRuntimeMode = MainAgentRuntimeMode.SINGLE_MAIN
    main_workspace_dir: Path | None = None
    max_active_sessions: int = 1
    reserved_team_slots: int = 4
    workspace_application_required: bool = True
    session_lifecycle: SessionLifecyclePolicy = field(default_factory=SessionLifecyclePolicy)


def _read_env(environ: Mapping[str, str], name: str, default: str) -> str:
    return str(environ.get(name, default)).strip()


def _resolve_runtime_mode(raw_value: str) -> MainAgentRuntimeMode:
    normalized = str(raw_value or "").strip().lower()
    if normalized == MainAgentRuntimeMode.TEAM.value:
        return MainAgentRuntimeMode.TEAM
    return MainAgentRuntimeMode.SINGLE_MAIN


def _resolve_main_workspace_dir(repo_root: Path, raw_value: str) -> Path:
    raw_workspace = str(raw_value or "").strip() or str(repo_root)
    workspace_path = Path(raw_workspace).expanduser()
    return (workspace_path if workspace_path.is_absolute() else (repo_root / workspace_path)).resolve()


def _resolve_team_max_agents(raw_value: str) -> int:
    try:
        parsed = int(str(raw_value or "").strip() or "4")
    except ValueError:
        parsed = 4
    return max(1, parsed)


def resolve_session_lifecycle_policy(
    *,
    reset_mode_raw: str | None = None,
    idle_seconds_raw: str | None = None,
) -> SessionLifecyclePolicy:
    raw_mode = (
        reset_mode_raw
        if reset_mode_raw is not None
        else os.getenv(SESSION_RESET_MODE_ENV, "none")
    ).strip().lower()
    raw_idle = (
        idle_seconds_raw
        if idle_seconds_raw is not None
        else os.getenv(SESSION_IDLE_SECONDS_ENV, "1800")
    ).strip()

    try:
        mode = SessionResetMode(raw_mode or SessionResetMode.NONE.value)
    except ValueError:
        mode = SessionResetMode.NONE

    try:
        idle_seconds = int(raw_idle or "1800")
    except ValueError:
        idle_seconds = 1800

    return SessionLifecyclePolicy(
        mode=mode,
        idle_seconds=max(1, idle_seconds),
    )


def load_main_agent_runtime_policy(
    repo_root: Path,
    *,
    environ: Mapping[str, str] | None = None,
) -> MainAgentRuntimePolicy:
    env = environ or os.environ
    mode = _resolve_runtime_mode(
        _read_env(env, MAIN_AGENT_RUNTIME_MODE_ENV, MainAgentRuntimeMode.SINGLE_MAIN.value)
    )
    main_workspace_dir = _resolve_main_workspace_dir(
        repo_root.resolve(),
        _read_env(env, MAIN_AGENT_MAIN_WORKSPACE_ENV, str(repo_root)),
    )
    team_max_agents = _resolve_team_max_agents(_read_env(env, MAIN_AGENT_TEAM_MAX_AGENTS_ENV, "4"))
    session_lifecycle = resolve_session_lifecycle_policy()

    if mode == MainAgentRuntimeMode.SINGLE_MAIN:
        return MainAgentRuntimePolicy(
            mode=mode,
            main_workspace_dir=main_workspace_dir,
            max_active_sessions=1,
            reserved_team_slots=team_max_agents,
            workspace_application_required=True,
            session_lifecycle=session_lifecycle,
        )

    return MainAgentRuntimePolicy(
        mode=mode,
        main_workspace_dir=main_workspace_dir,
        max_active_sessions=team_max_agents,
        reserved_team_slots=team_max_agents,
        workspace_application_required=True,
        session_lifecycle=session_lifecycle,
    )


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
        resolved_profile = (
            cls.normalize_approval_profile(requested_approval_profile)
            or current_approval_profile
            or "build"
        )
        resolved_access = (
            cls.normalize_access_level(requested_access_level)
            or current_access_level
            or "default"
        )

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


@dataclass(slots=True)
class RuntimeSessionPolicyCoordinator:
    policy: Any
    ttl_seconds: int
    lifecycle_manager: SessionLifecycleManager
    team_saturation_rejections: int = 0
    team_workspace_conflict_rejections: int = 0
    lifecycle_auto_resets: int = 0

    def clear_counters(self) -> None:
        self.team_saturation_rejections = 0
        self.team_workspace_conflict_rejections = 0
        self.lifecycle_auto_resets = 0

    def enforce_main_workspace(
        self,
        workspace_dir: Path,
        *,
        same_workspace: Callable[[Path, Path], bool],
    ) -> None:
        if _mode_value(getattr(self.policy, "mode", None)) != "single_main":
            return
        main_workspace = getattr(self.policy, "main_workspace_dir", None)
        if main_workspace is None:
            return
        resolved_main_workspace = Path(main_workspace).resolve()
        if same_workspace(workspace_dir, resolved_main_workspace):
            return
        raise HTTPException(
            status_code=409,
            detail=(
                "Main-agent single-main mode requires the main workspace. "
                f"requested_workspace={workspace_dir.resolve()} "
                f"main_workspace={resolved_main_workspace} "
                "agent_team_mode=reserved"
            ),
        )

    def enforce_workspace_entry(
        self,
        active_sessions: Iterable[Any],
        workspace_dir: Path,
        *,
        same_workspace: Callable[[Path, Path], bool],
    ) -> None:
        self.enforce_main_workspace(workspace_dir, same_workspace=same_workspace)
        if _mode_value(getattr(self.policy, "mode", None)) != "single_main":
            return
        for existing in active_sessions:
            existing_workspace = getattr(existing, "workspace_dir", None)
            if isinstance(existing_workspace, Path) and not same_workspace(existing_workspace, workspace_dir):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Main-agent runtime is already active in another workspace. "
                        f"active_session_id={getattr(existing, 'session_id', '')}"
                    ),
                )

    def note_workspace_conflict(self) -> None:
        if _mode_value(getattr(self.policy, "mode", None)) == "team":
            self.team_workspace_conflict_rejections += 1

    def raise_workspace_mismatch(self) -> None:
        self.note_workspace_conflict()
        raise HTTPException(status_code=400, detail="Session workspace mismatch.")

    def enforce_capacity(self, active_sessions: int) -> None:
        max_active_sessions = max(1, int(getattr(self.policy, "max_active_sessions", 1)))
        if active_sessions < max_active_sessions:
            return
        if _mode_value(getattr(self.policy, "mode", None)) == "team":
            self.team_saturation_rejections += 1
        raise HTTPException(
            status_code=409,
            detail=(
                "Main-agent runtime reached max_active_sessions. "
                f"max_active_sessions={max_active_sessions}"
            ),
        )

    def expired_session_ids(
        self,
        sessions: Mapping[str, Any],
        *,
        now_utc: datetime | None = None,
    ) -> list[str]:
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        expired: list[str] = []
        for session_id, session in sessions.items():
            updated_at = getattr(session, "updated_at", None)
            if not isinstance(updated_at, datetime):
                continue
            if (now - updated_at).total_seconds() > self.ttl_seconds:
                expired.append(session_id)
        return expired

    def refresh_session_lifecycle(
        self,
        session: Any,
        *,
        now_utc: datetime | None = None,
        reset_runtime_state: Callable[[], None],
    ) -> bool:
        lifecycle_state = getattr(session, "lifecycle_state", None)
        result = self.lifecycle_manager.ensure_active(lifecycle_state, now_utc=now_utc)
        session.lifecycle_state = result.state
        if result.reset:
            reset_runtime_state()
            self.lifecycle_auto_resets += 1
        session.lifecycle_state = self.lifecycle_manager.touch(session.lifecycle_state, now_utc=now_utc)
        return result.reset

    def diagnostics_payload(
        self,
        *,
        active_sessions: int,
    ) -> dict[str, Any]:
        max_active_sessions = max(1, int(getattr(self.policy, "max_active_sessions", 1)))
        available_slots = max(0, max_active_sessions - active_sessions)
        main_workspace = getattr(self.policy, "main_workspace_dir", None)
        resolved_main_workspace = str(Path(main_workspace).resolve()) if main_workspace is not None else None
        session_lifecycle = getattr(self.policy, "session_lifecycle", None)
        return {
            "mode": _mode_value(getattr(self.policy, "mode", None)),
            "active_sessions": active_sessions,
            "max_active_sessions": max_active_sessions,
            "available_session_slots": available_slots,
            "reserved_team_slots": max(1, int(getattr(self.policy, "reserved_team_slots", 1))),
            "workspace_application_required": bool(getattr(self.policy, "workspace_application_required", True)),
            "team_saturation_rejections": max(0, int(self.team_saturation_rejections)),
            "team_workspace_conflict_rejections": max(0, int(self.team_workspace_conflict_rejections)),
            "lifecycle_auto_resets": max(0, int(self.lifecycle_auto_resets)),
            "session_reset_mode": _mode_value(getattr(session_lifecycle, "mode", None)) or "none",
            "session_idle_seconds": max(1, int(getattr(session_lifecycle, "idle_seconds", 1) or 1)),
            "main_workspace_dir": resolved_main_workspace,
        }


__all__ = [
    "MAIN_AGENT_MAIN_WORKSPACE_ENV",
    "MAIN_AGENT_RUNTIME_MODE_ENV",
    "MAIN_AGENT_TEAM_MAX_AGENTS_ENV",
    "SESSION_IDLE_SECONDS_ENV",
    "SESSION_RESET_MODE_ENV",
    "MainAgentRuntimeMode",
    "MainAgentRuntimePolicy",
    "SessionRuntimePolicyAutofixRequest",
    "SessionRuntimePolicyExecution",
    "SessionRuntimePolicyPlan",
    "SessionRuntimePolicyService",
    "RuntimeSessionPolicyCoordinator",
    "load_main_agent_runtime_policy",
    "resolve_session_lifecycle_policy",
]
