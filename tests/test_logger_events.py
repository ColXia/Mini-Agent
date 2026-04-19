"""Tests for structured run event logging and replay formatting."""

from pathlib import Path

from mini_agent.logger import AgentLogger
from mini_agent.schema.schema import LLMCompletionResult, Message


def test_event_journal_is_written_and_replayable(tmp_path: Path):
    logger = AgentLogger(log_dir=tmp_path)
    logger.start_new_run(workspace=tmp_path / "workspace")

    logger.log_event("step.start", {"step": 1})
    logger.log_request(messages=[Message(role="user", content="hello")], tools=None)
    logger.log_completion(LLMCompletionResult(content="world", finish_reason="stop"))
    logger.log_tool_result(
        tool_name="read_file",
        arguments={"path": "README.md"},
        result_success=True,
        result_content="ok",
    )

    event_file = logger.get_event_file_path()
    assert event_file is not None
    assert event_file.exists()

    events = AgentLogger.read_events(event_file)
    event_types = [event["type"] for event in events]

    assert "run.init" in event_types
    assert "step.start" in event_types
    assert "llm.request" in event_types
    assert "llm.response" in event_types
    assert "tool.result" in event_types
    assert all("schema_version" in event for event in events)

    replay = AgentLogger.format_replay(events)
    assert "Run Event Replay" in replay
    assert "Schema:" in replay
    assert "Total events:" in replay


def test_log_response_compatibility_wrapper_still_records_llm_response(tmp_path: Path) -> None:
    logger = AgentLogger(log_dir=tmp_path)
    logger.start_new_run(workspace=tmp_path / "workspace")

    logger.log_response(content="legacy", finish_reason="stop")

    event_file = logger.get_event_file_path()
    assert event_file is not None

    events = AgentLogger.read_events(event_file)
    response_event = next(event for event in events if event["type"] == "llm.response")
    assert response_event["payload"]["content_preview"] == "legacy"
    assert response_event["payload"]["finish_reason"] == "stop"
