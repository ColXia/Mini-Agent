"""Runtime policy and lifecycle coordination helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from fastapi import HTTPException

from mini_agent.agent_core.session import SessionLifecycleManager


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _mode_value(value: object) -> str:
    raw = getattr(value, "value", value)
    return _safe_text(raw).lower()


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


__all__ = ["RuntimeSessionPolicyCoordinator"]
