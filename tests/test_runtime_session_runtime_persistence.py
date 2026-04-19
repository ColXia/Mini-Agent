from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mini_agent.config import AgentConfig, Config, LLMConfig, SecurityConfig, ToolsConfig
from mini_agent.session.persistence import (
    MainAgentRuntimePersistence,
    RuntimeSessionPersistenceRecordBuilder,
    RuntimeSessionPersistenceLoader,
)
from mini_agent.workspace_runtime.workspace_executor import build_direct_workspace_runtime_bundle
from tests.runtime_contract_fixtures import (
    RuntimeContractAgentStub,
    lineage_state_stub,
    runtime_projection_stub,
    runtime_session_stub,
    transcript_state_stub,
)


def _dt() -> datetime:
    return datetime(2026, 4, 18, 8, 0, 0, tzinfo=timezone.utc)


def _make_config() -> Config:
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_mcp=False, enable_skills=False),
        security=SecurityConfig(approval_profile="build", sandbox_mode="workspace"),
    )


def _build_session(tmp_path: Path):
    return runtime_session_stub(
        session_id="sess-runtime-persist",
        workspace_dir=tmp_path,
        created_at=_dt(),
        updated_at=_dt(),
        projection=runtime_projection_stub(
            title="Persisted",
            origin_surface="tui",
            active_surface="tui",
            reply_enabled=False,
            is_default=False,
            busy=False,
            running_state="",
            channel_type=None,
            conversation_id=None,
            sender_id=None,
            shared=False,
            knowledge_base_enabled=True,
            selected_model_source=None,
            selected_provider_id=None,
            selected_model_id=None,
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
            last_prepared_context={},
            prepared_context_diagnostics={},
            memory_diagnostics={},
            sandbox_diagnostics={"backend": "none"},
        ),
        lineage_state=lineage_state_stub(
            root_session_id="sess-runtime-persist",
            created_at=_dt(),
        ),
        transcript_state=transcript_state_stub(transcript=[], next_transcript_index=1),
        agent=RuntimeContractAgentStub(messages=[]),
    )


def test_main_agent_runtime_persistence_captures_workspace_runtime_snapshot(tmp_path: Path) -> None:
    session = _build_session(tmp_path)
    runtime_bundle = build_direct_workspace_runtime_bundle(_make_config(), tmp_path)
    runtime_bundle.executor.write_text(tmp_path / "note.txt", "hello")
    persistence = MainAgentRuntimePersistence(
        storage_dir=tmp_path / "state",
        record_loader=RuntimeSessionPersistenceLoader(
            session_kind="main-agent-runtime",
            read_shared_transcript=lambda _session_id, _record: [],
        ),
        record_builder=RuntimeSessionPersistenceRecordBuilder(
            session_kind="main-agent-runtime",
            session_token_usage=lambda _session: 0,
            session_token_limit=lambda _session: 0,
        ),
    )

    persistence.save_session(session)
    record = persistence.load_session_record(session.session_id)

    assert record is not None
    assert record["workspace_runtime_snapshot"]["workspace_dir"] == str(tmp_path.resolve())
    assert record["workspace_runtime_snapshot"]["mutation_count"] >= 1
    assert record["workspace_runtime_snapshot"]["metadata"]["trigger"] == "session_persist"
    assert record["workspace_runtime_snapshot"]["metadata"]["session_id"] == session.session_id


def test_main_agent_runtime_persistence_prefers_runtime_model_identity_over_projection(tmp_path: Path) -> None:
    session = _build_session(tmp_path)
    session.projection.selected_model_source = "preset"
    session.projection.selected_provider_id = "openai"
    session.projection.selected_model_id = "gpt-5.4"
    session.runtime.agent = RuntimeContractAgentStub(
        model="astron-code-latest",
        provider_source="custom",
        provider_id="maas",
        messages=[],
    )
    persistence = MainAgentRuntimePersistence(
        storage_dir=tmp_path / "state",
        record_loader=RuntimeSessionPersistenceLoader(
            session_kind="main-agent-runtime",
            read_shared_transcript=lambda _session_id, _record: [],
        ),
        record_builder=RuntimeSessionPersistenceRecordBuilder(
            session_kind="main-agent-runtime",
            session_token_usage=lambda _session: 0,
            session_token_limit=lambda _session: 0,
            selected_model_identity_for_session=lambda current_session: (
                "custom",
                "maas",
                "astron-code-latest",
            )
            if current_session is session
            else None,
        ),
    )

    persistence.save_session(session)
    record = persistence.load_session_record(session.session_id)

    assert record is not None
    assert record["selected_model_source"] == "custom"
    assert record["selected_provider_id"] == "maas"
    assert record["selected_model_id"] == "astron-code-latest"


