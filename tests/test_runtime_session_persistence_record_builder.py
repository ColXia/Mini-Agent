from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mini_agent.runtime.session_persistence_record_builder import RuntimeSessionPersistenceRecordBuilder
from tests.runtime_contract_fixtures import (
    RuntimeContractAgentStub,
    lineage_state_stub,
    runtime_projection_stub,
    runtime_session_stub,
    transcript_state_stub,
)


def _dt() -> datetime:
    return datetime(2026, 4, 15, 8, 0, 0, tzinfo=timezone.utc)


def test_runtime_session_persistence_record_builder_reads_agent_runtime_state_via_support(tmp_path: Path) -> None:
    builder = RuntimeSessionPersistenceRecordBuilder(
        session_kind="shared",
        session_token_usage=lambda _session: 64,
        session_token_limit=lambda _session: 128000,
        agent_last_memory_automation=lambda _agent: {"stored": True},
        agent_last_runtime_task_memory=lambda _agent: {"synced": True},
    )
    session = runtime_session_stub(
        session_id="sess-persist",
        workspace_dir=tmp_path,
        created_at=_dt(),
        updated_at=_dt(),
        projection=runtime_projection_stub(
            title="Persisted",
            origin_surface="tui",
            active_surface="qq",
            reply_enabled=True,
            is_default=False,
            busy=False,
            running_state="",
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
            pending_skill_reload=False,
            pending_skill_reload_reason="",
            recovery_context_pending=False,
            recovery_state="",
            recovery_summary="",
            recovery_last_activity=None,
            recovery_last_user_message=None,
            recovery_last_assistant_message=None,
            recovery_pending_approvals=[],
            context_policy={},
            last_prepared_context={"summary": "ctx"},
            prepared_context_diagnostics={"turn_count": 1},
            memory_diagnostics={"memory": True},
            sandbox_diagnostics={"backend": "none"},
        ),
        lineage_state=lineage_state_stub(
            parent_session_id=None,
            root_session_id="sess-persist",
            reason="root",
            created_at=_dt(),
            metadata={},
        ),
        transcript_state=transcript_state_stub(transcript=[], next_transcript_index=1),
        agent=RuntimeContractAgentStub(),
    )

    record = builder.build_metadata_record(
        session,
        transcript_path=tmp_path / "transcript.jsonl",
        sandbox_diagnostics={"backend": "none"},
    )

    assert record["last_memory_automation"] == {"stored": True}
    assert record["last_runtime_task_memory"] == {"synced": True}


def test_runtime_session_persistence_record_builder_falls_back_to_legacy_agent_attributes(tmp_path: Path) -> None:
    builder = RuntimeSessionPersistenceRecordBuilder(
        session_kind="shared",
        session_token_usage=lambda _session: 64,
        session_token_limit=lambda _session: 128000,
    )
    session = runtime_session_stub(
        session_id="sess-persist-legacy",
        workspace_dir=tmp_path,
        created_at=_dt(),
        updated_at=_dt(),
        projection=runtime_projection_stub(
            title="Persisted",
            origin_surface="tui",
            active_surface="qq",
            reply_enabled=True,
            is_default=False,
            busy=False,
            running_state="",
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
            pending_skill_reload=False,
            pending_skill_reload_reason="",
            recovery_context_pending=False,
            recovery_state="",
            recovery_summary="",
            recovery_last_activity=None,
            recovery_last_user_message=None,
            recovery_last_assistant_message=None,
            recovery_pending_approvals=[],
            context_policy={},
            last_prepared_context={"summary": "ctx"},
            prepared_context_diagnostics={"turn_count": 1},
            memory_diagnostics={"memory": True},
            sandbox_diagnostics={"backend": "none"},
        ),
        lineage_state=lineage_state_stub(
            parent_session_id=None,
            root_session_id="sess-persist-legacy",
            reason="root",
            created_at=_dt(),
            metadata={},
        ),
        transcript_state=transcript_state_stub(transcript=[], next_transcript_index=1),
        agent=RuntimeContractAgentStub(
            last_memory_automation={"legacy": "memory"},
            last_runtime_task_memory={"legacy": "task"},
        ),
    )

    record = builder.build_metadata_record(
        session,
        transcript_path=tmp_path / "transcript.jsonl",
        sandbox_diagnostics={"backend": "none"},
    )

    assert record["last_memory_automation"] == {"legacy": "memory"}
    assert record["last_runtime_task_memory"] == {"legacy": "task"}
