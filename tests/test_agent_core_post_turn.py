from __future__ import annotations

from dataclasses import dataclass

from mini_agent.agent_core.post_turn import AgentPostTurnSideEffectService
from mini_agent.schema import Message


@dataclass(frozen=True)
class _PayloadResult:
    payload: dict[str, object]

    def to_payload(self) -> dict[str, object]:
        return dict(self.payload)


class _CaptureLogger:
    def __init__(self) -> None:
        self.events: list[dict[str, object]] = []

    def log_event(
        self,
        event_type: str,
        payload: dict[str, object],
        *,
        level: str = "info",
    ) -> None:
        self.events.append(
            {
                "type": event_type,
                "payload": dict(payload),
                "level": level,
            }
        )


class _StubAutomation:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def process_turn(self, **kwargs: object) -> _PayloadResult:
        self.calls.append(dict(kwargs))
        return _PayloadResult(self.payload)


class _StubRuntimeTaskMemory:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload
        self.calls: list[dict[str, object]] = []

    def process_turn(self, **kwargs: object) -> _PayloadResult:
        self.calls.append(dict(kwargs))
        return _PayloadResult(self.payload)


class _FailingProcessor:
    def __init__(self, message: str) -> None:
        self.message = message

    def process_turn(self, **kwargs: object) -> _PayloadResult:
        _ = kwargs
        raise RuntimeError(self.message)


def test_post_turn_service_processes_handlers_and_logs_payloads() -> None:
    logger = _CaptureLogger()
    automation = _StubAutomation(
        {
            "enabled": True,
            "skipped_reason": "",
            "action_count": 1,
            "actions": ["daily_note"],
        }
    )
    runtime_memory = _StubRuntimeTaskMemory(
        {
            "enabled": True,
            "skipped_reason": "",
            "stored": True,
            "duplicate": False,
            "namespace": "session:sess-1",
            "engram_id": "eng-1",
            "content": "task: keep tui | latest: confirmed",
        }
    )
    service = AgentPostTurnSideEffectService(
        logger=logger,
        workspace_dir="D:/workspace-a",
        turn_memory_automation=automation,
        turn_runtime_task_memory=runtime_memory,
    )

    messages = [
        Message(role="system", content="system"),
        Message(role="user", content="keep tui"),
        Message(role="assistant", content="confirmed"),
    ]
    result = service.process_turn(
        stop_reason="end_turn",
        messages=messages,
        turn_start_index=1,
        turn_context={"session_id": "sess-1"},
        assistant_message="confirmed",
    )

    assert result.memory_automation["action_count"] == 1
    assert result.runtime_task_memory["stored"] is True
    assert automation.calls[0]["turn_messages"] == messages[1:]
    assert runtime_memory.calls[0]["turn_messages"] == messages[1:]
    assert [event["type"] for event in logger.events] == [
        "memory.auto_writeback",
        "memory.runtime_task_writeback",
    ]


def test_post_turn_service_returns_missing_anchor_payloads_without_running_processors() -> None:
    logger = _CaptureLogger()
    automation = _StubAutomation({"enabled": True})
    runtime_memory = _StubRuntimeTaskMemory({"enabled": True})
    service = AgentPostTurnSideEffectService(
        logger=logger,
        workspace_dir="D:/workspace-b",
        turn_memory_automation=automation,
        turn_runtime_task_memory=runtime_memory,
    )

    result = service.process_turn(
        stop_reason="end_turn",
        messages=[Message(role="assistant", content="confirmed")],
        turn_start_index=None,
        turn_context={"session_id": "sess-2"},
        assistant_message="confirmed",
    )

    assert result.memory_automation["skipped_reason"] == "missing_turn_anchor"
    assert result.runtime_task_memory["skipped_reason"] == "missing_turn_anchor"
    assert automation.calls == []
    assert runtime_memory.calls == []
    assert logger.events == []


def test_post_turn_service_captures_processor_failures_and_logs_warnings() -> None:
    logger = _CaptureLogger()
    service = AgentPostTurnSideEffectService(
        logger=logger,
        workspace_dir="D:/workspace-c",
        turn_memory_automation=_FailingProcessor("auto boom"),
        turn_runtime_task_memory=_FailingProcessor("runtime boom"),
    )

    result = service.process_turn(
        stop_reason="end_turn",
        messages=[
            Message(role="user", content="keep tui"),
            Message(role="assistant", content="confirmed"),
        ],
        turn_start_index=0,
        turn_context={"session_id": "sess-3"},
        assistant_message="confirmed",
    )

    assert result.memory_automation["skipped_reason"] == "automation_failed"
    assert "RuntimeError: auto boom" in str(result.memory_automation["error"])
    assert result.runtime_task_memory["skipped_reason"] == "runtime_task_memory_failed"
    assert "RuntimeError: runtime boom" in str(result.runtime_task_memory["error"])
    assert [event["type"] for event in logger.events] == [
        "memory.auto_writeback_failed",
        "memory.runtime_task_writeback_failed",
    ]
    assert all(event["level"] == "warning" for event in logger.events)
