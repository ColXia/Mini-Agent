"""Tests for event schema version compatibility checks."""

import json

import pytest

from mini_agent.logger import AgentLogger


def test_schema_compatibility_allows_same_major():
    events = [
        {"index": 1, "schema_version": "1.0.0", "type": "run.start"},
        {"index": 2, "schema_version": "1.3.5", "type": "run.completed"},
    ]

    result = AgentLogger.check_event_schema_compatibility(events, expected_version="1.2.0")
    assert result["compatible"] is True


def test_schema_compatibility_rejects_legacy_for_v1_expectation():
    events = [
        {"index": 1, "type": "run.start"},  # legacy event without schema_version
    ]

    result = AgentLogger.check_event_schema_compatibility(events, expected_version="1.0.0")
    assert result["compatible"] is False
    assert result["legacy_event_count"] == 1


def test_schema_compatibility_rejects_invalid_expected_version():
    events = [{"index": 1, "schema_version": "1.0.0", "type": "run.start"}]

    with pytest.raises(ValueError):
        AgentLogger.check_event_schema_compatibility(events, expected_version="v1")


def test_migrate_event_schema_file_backfills_legacy_events(tmp_path):
    event_file = tmp_path / "agent_run_legacy.events.jsonl"
    event_file.write_text(
        "\n".join(
            [
                json.dumps({"index": 1, "type": "run.start"}),
                json.dumps({"index": 2, "type": "run.completed", "schema_version": "1.2.0"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    result = AgentLogger.migrate_event_schema_file(event_file)
    assert result["changed"] is True
    assert result["migrated_events"] == 1
    assert result["already_versioned_events"] == 1
    assert result["backup_file"] is not None

    migrated = AgentLogger.read_events(event_file)
    assert migrated[0]["schema_version"] == "1.0.0"
    assert migrated[1]["schema_version"] == "1.2.0"


def test_migrate_event_schema_file_dry_run_does_not_modify_file(tmp_path):
    event_file = tmp_path / "agent_run_dry.events.jsonl"
    event_file.write_text(json.dumps({"index": 1, "type": "run.start"}) + "\n", encoding="utf-8")
    before = event_file.read_text(encoding="utf-8")

    result = AgentLogger.migrate_event_schema_file(event_file, dry_run=True)
    assert result["changed"] is True
    assert result["migrated_events"] == 1
    assert result["backup_file"] is None
    assert event_file.read_text(encoding="utf-8") == before


def test_migrate_event_schema_file_without_backup(tmp_path):
    event_file = tmp_path / "agent_run_no_backup.events.jsonl"
    event_file.write_text(json.dumps({"index": 1, "type": "run.start"}) + "\n", encoding="utf-8")

    result = AgentLogger.migrate_event_schema_file(event_file, backup=False)
    assert result["changed"] is True
    assert result["backup_file"] is None
    assert not (tmp_path / "agent_run_no_backup.events.jsonl.bak").exists()
    assert AgentLogger.read_events(event_file)[0]["schema_version"] == "1.0.0"


def test_migrate_event_schema_file_rejects_invalid_target_version(tmp_path):
    event_file = tmp_path / "agent_run_invalid.events.jsonl"
    event_file.write_text(json.dumps({"index": 1, "type": "run.start"}) + "\n", encoding="utf-8")

    with pytest.raises(ValueError):
        AgentLogger.migrate_event_schema_file(event_file, target_version="v1")
