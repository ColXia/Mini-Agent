"""Agent loop context and per-turn snapshot models."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _positive_int_or_default(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except Exception:
        return default
    return parsed if parsed > 0 else default


def _optional_positive_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


@dataclass(frozen=True)
class TurnPolicySnapshot:
    """Per-turn execution policy snapshot."""

    max_steps: int
    max_tool_calls_per_step: int | None = None

    def normalized(self) -> "TurnPolicySnapshot":
        return TurnPolicySnapshot(
            max_steps=max(1, int(self.max_steps)),
            max_tool_calls_per_step=_optional_positive_int(self.max_tool_calls_per_step),
        )


@dataclass(frozen=True)
class TurnContext:
    """One immutable turn context captured at submission time."""

    submission_id: str
    session_id: str
    user_input: str
    policy: TurnPolicySnapshot
    metadata: dict[str, Any] = field(default_factory=dict)
    start_new_run: bool = True
    created_at: datetime = field(default_factory=_utc_now)


@dataclass
class AgentLoopContext:
    """Runtime dependencies shared by the submission loop."""

    config: Any | None = None
    tool_registry: Any | None = None
    message_bus: Any | None = None
    llm_client: Any | None = None
    sandbox_manager: Any | None = None
    session_id: str = "default"

    def snapshot_turn_context(
        self,
        *,
        submission_id: str,
        user_input: str,
        policy_overrides: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        start_new_run: bool = True,
    ) -> TurnContext:
        """Capture one independent turn snapshot."""
        default_max_steps = 50
        default_max_tool_calls_per_step: int | None = None

        config_agent = getattr(self.config, "agent", None)
        if config_agent is not None:
            default_max_steps = _positive_int_or_default(
                getattr(config_agent, "max_steps", 50),
                50,
            )
            default_max_tool_calls_per_step = _optional_positive_int(
                getattr(config_agent, "max_tool_calls_per_step", None)
            )

        overrides = dict(policy_overrides or {})
        max_steps = _positive_int_or_default(overrides.get("max_steps"), default_max_steps)
        max_tool_calls_per_step = (
            _optional_positive_int(overrides.get("max_tool_calls_per_step"))
            if "max_tool_calls_per_step" in overrides
            else default_max_tool_calls_per_step
        )

        return TurnContext(
            submission_id=str(submission_id).strip() or "submission",
            session_id=str(self.session_id).strip() or "default",
            user_input=str(user_input),
            policy=TurnPolicySnapshot(
                max_steps=max_steps,
                max_tool_calls_per_step=max_tool_calls_per_step,
            ).normalized(),
            metadata=dict(metadata or {}),
            start_new_run=bool(start_new_run),
        )
