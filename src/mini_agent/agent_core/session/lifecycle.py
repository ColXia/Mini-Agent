"""Session lifecycle reset policy for agent-core."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from mini_agent.agent_core.session.session_key import AgentSessionKey


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class SessionResetMode(str, Enum):
    """Reset policy modes."""

    NONE = "none"
    DAILY = "daily"
    IDLE = "idle"
    BOTH = "both"


@dataclass(frozen=True)
class SessionLifecyclePolicy:
    """Lifecycle reset policy."""

    mode: SessionResetMode = SessionResetMode.NONE
    idle_seconds: int = 1800

    def normalized(self) -> "SessionLifecyclePolicy":
        idle = max(1, int(self.idle_seconds))
        return SessionLifecyclePolicy(mode=self.mode, idle_seconds=idle)


@dataclass(frozen=True)
class SessionLifecycleState:
    """Mutable session lifecycle state stored per session."""

    session_key: AgentSessionKey
    created_utc: datetime
    last_activity_utc: datetime
    revision: int = 0


@dataclass(frozen=True)
class SessionLifecycleResult:
    """Lifecycle decision result."""

    state: SessionLifecycleState
    reset: bool
    reason: str | None = None


class SessionLifecycleManager:
    """Apply lifecycle reset policy for one session."""

    def __init__(self, policy: SessionLifecyclePolicy):
        self.policy = policy.normalized()

    def should_reset(self, state: SessionLifecycleState, *, now_utc: datetime | None = None) -> tuple[bool, str | None]:
        now = (now_utc or _utc_now()).astimezone(timezone.utc)
        mode = self.policy.mode
        if mode == SessionResetMode.NONE:
            return False, None

        day_changed = now.date() != state.created_utc.astimezone(timezone.utc).date()
        idle_elapsed = (now - state.last_activity_utc.astimezone(timezone.utc)).total_seconds() >= self.policy.idle_seconds

        if mode == SessionResetMode.DAILY:
            return (day_changed, "daily" if day_changed else None)
        if mode == SessionResetMode.IDLE:
            return (idle_elapsed, "idle" if idle_elapsed else None)
        if mode == SessionResetMode.BOTH:
            if day_changed:
                return True, "daily"
            if idle_elapsed:
                return True, "idle"
        return False, None

    def touch(self, state: SessionLifecycleState, *, now_utc: datetime | None = None) -> SessionLifecycleState:
        now = (now_utc or _utc_now()).astimezone(timezone.utc)
        return SessionLifecycleState(
            session_key=state.session_key,
            created_utc=state.created_utc,
            last_activity_utc=now,
            revision=state.revision,
        )

    def reset(
        self,
        state: SessionLifecycleState,
        *,
        now_utc: datetime | None = None,
    ) -> SessionLifecycleState:
        now = (now_utc or _utc_now()).astimezone(timezone.utc)
        return SessionLifecycleState(
            session_key=state.session_key,
            created_utc=now,
            last_activity_utc=now,
            revision=state.revision + 1,
        )

    def ensure_active(
        self,
        state: SessionLifecycleState,
        *,
        now_utc: datetime | None = None,
    ) -> SessionLifecycleResult:
        should_reset, reason = self.should_reset(state, now_utc=now_utc)
        if should_reset:
            return SessionLifecycleResult(
                state=self.reset(state, now_utc=now_utc),
                reset=True,
                reason=reason,
            )
        return SessionLifecycleResult(state=state, reset=False, reason=None)

    @staticmethod
    def bootstrap(session_key: AgentSessionKey, *, now_utc: datetime | None = None) -> SessionLifecycleState:
        now = (now_utc or _utc_now()).astimezone(timezone.utc)
        return SessionLifecycleState(
            session_key=session_key,
            created_utc=now,
            last_activity_utc=now,
            revision=0,
        )
