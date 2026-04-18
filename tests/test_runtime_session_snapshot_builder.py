from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from mini_agent.runtime.session_snapshot_builder import RuntimeSessionSnapshotBuilder
from tests.runtime_contract_fixtures import (
    RuntimeContractAgentStub,
    lineage_state_stub,
    runtime_projection_stub,
    runtime_session_stub,
    transcript_entry_stub,
    transcript_state_stub,
)


def _dt() -> datetime:
    return datetime(2026, 4, 14, 13, 0, 0, tzinfo=timezone.utc)


def _builder() -> RuntimeSessionSnapshotBuilder:
    def _agent_messages(agent):
        return list(getattr(agent, "messages", None) or [])

    def _serialize_agent_messages(messages):
        serialized = []
        for item in messages:
            if isinstance(item, dict):
                serialized.append({"role": item.get("role"), "content": item.get("content")})
            else:
                serialized.append(
                    {
                        "role": getattr(item, "role", None),
                        "content": getattr(item, "content", None),
                    }
                )
        return serialized

    return RuntimeSessionSnapshotBuilder(
        normalize_surface=lambda value: " ".join(str(value or "").strip().lower().split()) or "api",
        normalize_model_source=lambda value: (" ".join(str(value or "").strip().lower().split()) or None),
        normalize_context_policy_payload=lambda value: dict(value or {}),
        normalize_prepared_context_payload=lambda value: dict(value or {}),
        normalize_prepared_context_diagnostics_payload=lambda value: dict(value or {}),
        build_memory_diagnostics_for_session=lambda session: {"memory": session.session_id},
        build_memory_diagnostics_from_record=lambda record: {"memory": str(record.get("session_id"))},
        build_sandbox_diagnostics_for_session=lambda session: {"approval_profile": "build"},
        build_sandbox_diagnostics_from_record=lambda record: {"approval_profile": "default"},
        build_workspace_runtime_snapshot_for_session=lambda session: {
            "snapshot_id": f"live-{session.session_id}",
            "workspace_dir": str(session.workspace_dir),
            "mutation_count": 2,
        },
        build_workspace_runtime_snapshot_from_record=lambda record: dict(
            record.get("workspace_runtime_snapshot") or {}
        ),
        snapshot_runtime_task_memory_payload=lambda **kwargs: {"session_id": kwargs.get("session_id")},
        snapshot_workspace_shared_runtime_task_memory_payload=lambda **kwargs: {
            "workspace_dir": str(kwargs.get("workspace_dir"))
        },
        session_token_usage=lambda session: 64,
        session_token_limit=lambda session: 128000,
        record_token_usage=lambda record: int(record.get("token_usage") or 0),
        record_token_limit=lambda record: int(record.get("token_limit") or 0),
        transcript_entries_from_record=lambda record: list(record.get("_transcript_entries") or []),
        agent_messages=_agent_messages,
        serialize_agent_messages=_serialize_agent_messages,
    )


def test_runtime_session_snapshot_builder_builds_snapshot_from_live_session(tmp_path: Path) -> None:
    builder = _builder()
    session = runtime_session_stub(
        session_id="sess-live",
        workspace_dir=tmp_path,
        projection=runtime_projection_stub(
            title="Live Session",
            origin_surface="TUI",
            active_surface="QQ",
            reply_enabled=True,
            is_default=False,
            channel_type="qq",
            conversation_id="group:1",
            sender_id="user-1",
            shared=True,
            knowledge_base_enabled=False,
            selected_model_source="preset",
            selected_provider_id="openai",
            selected_model_id="gpt-5.4",
            pending_model_source=None,
            pending_provider_id=None,
            pending_model_id=None,
            pending_skill_reload=True,
            pending_skill_reload_reason="skill updated",
            context_policy={"sources": ["memory"]},
            last_prepared_context={"summary": "ctx"},
            prepared_context_diagnostics={"chars": 120},
        ),
        lineage_state=lineage_state_stub(
            parent_session_id="sess-root",
            root_session_id="sess-root",
            reason="fork",
            created_at=_dt(),
            metadata={"kind": "demo"},
        ),
        agent=RuntimeContractAgentStub(messages=[SimpleNamespace(role="system", content="system prompt")]),
        transcript_state=transcript_state_stub(
            transcript=[
                transcript_entry_stub(
                    role="user",
                    content="hello",
                    surface="tui",
                    created_at=_dt(),
                    channel_type="qq",
                    conversation_id="group:1",
                    sender_id="user-1",
                    metadata={"kind": "chat"},
                )
            ]
        ),
    )

    snapshot = builder.build_session_snapshot(session)

    assert snapshot.session_id == "sess-live"
    assert snapshot.is_default is False
    assert snapshot.origin_surface == "tui"
    assert snapshot.active_surface == "qq"
    assert snapshot.selected_provider_id == "openai"
    assert snapshot.pending_skill_reload is True
    assert snapshot.memory_diagnostics == {"memory": "sess-live"}
    assert snapshot.sandbox_diagnostics == {"approval_profile": "build"}
    assert snapshot.workspace_runtime_snapshot["snapshot_id"] == "live-sess-live"
    assert snapshot.runtime_task_memory_payload == {"session_id": "sess-live"}
    assert snapshot.agent_messages == [{"role": "system", "content": "system prompt"}]
    assert [item.content for item in snapshot.transcript] == ["hello"]


def test_runtime_session_snapshot_builder_builds_snapshot_from_persisted_record(tmp_path: Path) -> None:
    builder = _builder()
    record = {
        "session_id": "sess-record",
        "workspace_dir": str(tmp_path),
        "title": "Persisted Session",
        "origin_surface": "qq",
        "active_surface": "tui",
        "reply_enabled": False,
        "is_default": True,
        "channel_type": "qq",
        "conversation_id": "group:2",
        "sender_id": "user-2",
        "token_usage": 77,
        "token_limit": 64000,
        "shared": True,
        "knowledge_base_enabled": True,
        "selected_model_source": " PRESET ",
        "selected_provider_id": "openai",
        "selected_model_id": "gpt-5.4",
        "lineage_parent_session_id": "sess-root",
        "lineage_root_session_id": "sess-root",
        "lineage_reason": "snapshot_import",
        "lineage_created_at": _dt().isoformat(),
        "lineage_metadata": {"source": "persisted"},
        "pending_skill_reload": False,
        "pending_skill_reload_reason": "",
        "context_policy": {"sources": ["workspace"]},
        "last_prepared_context": {"summary": "persisted"},
        "prepared_context_diagnostics": {"chars": 42},
        "workspace_runtime_snapshot": {
            "snapshot_id": "persisted-snap",
            "workspace_dir": str(tmp_path),
            "mutation_count": 3,
        },
        "messages": [{"role": "assistant", "content": "seed"}],
        "_transcript_entries": [
            transcript_entry_stub(
                role="assistant",
                content="persisted hello",
                surface="qq",
                created_at=_dt(),
                channel_type="qq",
                conversation_id="group:2",
                sender_id="user-2",
                metadata={"kind": "persisted"},
            )
        ],
    }

    snapshot = builder.build_session_snapshot_from_record(record)

    assert snapshot.session_id == "sess-record"
    assert snapshot.is_default is True
    assert snapshot.active_surface == "tui"
    assert snapshot.selected_model_source == "preset"
    assert snapshot.memory_diagnostics == {"memory": "sess-record"}
    assert snapshot.sandbox_diagnostics == {"approval_profile": "default"}
    assert snapshot.workspace_runtime_snapshot["snapshot_id"] == "persisted-snap"
    assert snapshot.runtime_task_memory_payload == {"session_id": "sess-record"}
    assert snapshot.agent_messages == [{"role": "assistant", "content": "seed"}]
    assert [item.content for item in snapshot.transcript] == ["persisted hello"]
