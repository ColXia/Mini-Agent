"""Post-turn side-effect processing for agent-core."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mini_agent.memory.automation import TurnMemoryAutomation
from mini_agent.memory.runtime_task_memory import TurnRuntimeTaskMemory


@dataclass(frozen=True)
class PostTurnSideEffectResult:
    """Collected payloads from one post-turn side-effect pass."""

    memory_automation: dict[str, Any]
    runtime_task_memory: dict[str, Any]


class AgentPostTurnSideEffectService:
    """Own post-turn memory side effects after the run loop completes."""

    def __init__(
        self,
        *,
        logger: Any,
        workspace_dir: str | Path,
        turn_memory_automation: TurnMemoryAutomation | None = None,
        turn_runtime_task_memory: TurnRuntimeTaskMemory | None = None,
    ) -> None:
        self.logger = logger
        self.workspace_dir = str(workspace_dir)
        self.turn_memory_automation = turn_memory_automation
        self.turn_runtime_task_memory = turn_runtime_task_memory

    def process_turn(
        self,
        *,
        stop_reason: str,
        messages: list[Any],
        turn_start_index: int | None,
        turn_context: Any | None,
        assistant_message: str,
    ) -> PostTurnSideEffectResult:
        turn_messages = self._turn_messages_from_anchor(
            messages=messages,
            turn_start_index=turn_start_index,
        )
        return PostTurnSideEffectResult(
            memory_automation=self._run_memory_automation(
                stop_reason=stop_reason,
                turn_messages=turn_messages,
                turn_context=turn_context,
                assistant_message=assistant_message,
            ),
            runtime_task_memory=self._run_runtime_task_memory(
                stop_reason=stop_reason,
                turn_messages=turn_messages,
                turn_context=turn_context,
                assistant_message=assistant_message,
            ),
        )

    @staticmethod
    def _turn_messages_from_anchor(
        *,
        messages: list[Any],
        turn_start_index: int | None,
    ) -> list[Any] | None:
        if (
            turn_start_index is None
            or turn_start_index < 0
            or turn_start_index >= len(messages)
        ):
            return None
        return list(messages[turn_start_index:])

    def _log_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        level: str = "info",
    ) -> None:
        logger = self.logger
        if logger is None or not hasattr(logger, "log_event"):
            return
        logger.log_event(
            event_type,
            {
                **payload,
                "workspace_dir": self.workspace_dir,
            },
            level=level,
        )

    def _run_memory_automation(
        self,
        *,
        stop_reason: str,
        turn_messages: list[Any] | None,
        turn_context: Any | None,
        assistant_message: str,
    ) -> dict[str, Any]:
        automation = self.turn_memory_automation
        if automation is None:
            return {}
        if turn_messages is None:
            return {
                "enabled": True,
                "skipped_reason": "missing_turn_anchor",
                "action_count": 0,
                "actions": [],
            }

        try:
            payload = automation.process_turn(
                stop_reason=stop_reason,
                turn_messages=turn_messages,
                turn_context=turn_context,
                assistant_message=assistant_message,
            ).to_payload()
            self._log_event("memory.auto_writeback", payload)
            return payload
        except Exception as exc:
            payload = {
                "enabled": True,
                "skipped_reason": "automation_failed",
                "action_count": 0,
                "actions": [],
                "error": f"{type(exc).__name__}: {exc}",
            }
            self._log_event(
                "memory.auto_writeback_failed",
                payload,
                level="warning",
            )
            return payload

    def _run_runtime_task_memory(
        self,
        *,
        stop_reason: str,
        turn_messages: list[Any] | None,
        turn_context: Any | None,
        assistant_message: str,
    ) -> dict[str, Any]:
        runtime_memory = self.turn_runtime_task_memory
        if runtime_memory is None:
            return {}
        if turn_messages is None:
            return {
                "enabled": True,
                "skipped_reason": "missing_turn_anchor",
                "stored": False,
                "duplicate": False,
                "namespace": None,
                "engram_id": None,
                "content": "",
            }

        try:
            payload = runtime_memory.process_turn(
                stop_reason=stop_reason,
                turn_messages=turn_messages,
                turn_context=turn_context,
                assistant_message=assistant_message,
            ).to_payload()
            self._log_event("memory.runtime_task_writeback", payload)
            return payload
        except Exception as exc:
            payload = {
                "enabled": True,
                "skipped_reason": "runtime_task_memory_failed",
                "stored": False,
                "duplicate": False,
                "namespace": None,
                "engram_id": None,
                "content": "",
                "error": f"{type(exc).__name__}: {exc}",
            }
            self._log_event(
                "memory.runtime_task_writeback_failed",
                payload,
                level="warning",
            )
            return payload


__all__ = [
    "AgentPostTurnSideEffectService",
    "PostTurnSideEffectResult",
]
