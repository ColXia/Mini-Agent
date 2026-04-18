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


def test_runtime_session_persistence_record_builder_prefers_injected_model_identity_callbacks(
    tmp_path: Path,
) -> None:
    builder = RuntimeSessionPersistenceRecordBuilder(
        session_kind="shared",
        session_token_usage=lambda _session: 64,
        session_token_limit=lambda _session: 128000,
        selected_model_identity_for_session=lambda _session: ("custom", "maas", "astron-code-latest"),
        pending_model_identity_for_session=lambda _session: ("preset", "openai", "gpt-5.4"),
    )
    session = runtime_session_stub(
        session_id="sess-persist-model-truth",
        workspace_dir=tmp_path,
        created_at=_dt(),
        updated_at=_dt(),
        projection=runtime_projection_stub(
            title="Persisted",
            origin_surface="tui",
            active_surface="tui",
            reply_enabled=True,
            is_default=False,
            busy=False,
            running_state="",
            channel_type=None,
            conversation_id=None,
            sender_id=None,
            shared=False,
            knowledge_base_enabled=True,
            selected_model_source="preset",
            selected_provider_id="openai",
            selected_model_id="gpt-5.3",
            pending_model_source="custom",
            pending_provider_id="legacy",
            pending_model_id="stale-model",
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
            sandbox_diagnostics={},
        ),
        lineage_state=lineage_state_stub(
            root_session_id="sess-persist-model-truth",
            created_at=_dt(),
        ),
        transcript_state=transcript_state_stub(transcript=[], next_transcript_index=1),
        agent=RuntimeContractAgentStub(),
    )

    record = builder.build_metadata_record(
        session,
        transcript_path=tmp_path / "transcript.jsonl",
        sandbox_diagnostics={},
    )

    assert record["selected_model_source"] == "custom"
    assert record["selected_provider_id"] == "maas"
    assert record["selected_model_id"] == "astron-code-latest"
    assert record["pending_model_source"] == "preset"
    assert record["pending_provider_id"] == "openai"
    assert record["pending_model_id"] == "gpt-5.4"


def test_runtime_session_persistence_record_builder_can_include_run_control_truth(tmp_path: Path) -> None:
    builder = RuntimeSessionPersistenceRecordBuilder(
        session_kind="shared",
        session_token_usage=lambda _session: 1,
        session_token_limit=lambda _session: 2,
        active_run_control_state=lambda _session: {
            "run_id": "run-1",
            "control_mode": "approval_wait",
        },
        active_approval_wait=lambda _session: {
            "wait_id": "wait-1",
            "run_id": "run-1",
            "approval_token": "approval-1",
            "tool_name": "bash",
            "wait_state": "pending",
        },
    )
    session = runtime_session_stub(
        session_id="sess-run-truth",
        workspace_dir=tmp_path,
        created_at=_dt(),
        updated_at=_dt(),
        projection=runtime_projection_stub(
            title="Run truth",
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
            sandbox_diagnostics={},
        ),
        lineage_state=lineage_state_stub(
            root_session_id="sess-run-truth",
            created_at=_dt(),
        ),
        transcript_state=transcript_state_stub(transcript=[], next_transcript_index=1),
        agent=RuntimeContractAgentStub(),
    )

    record = builder.build_metadata_record(
        session,
        transcript_path=tmp_path / "transcript.jsonl",
        sandbox_diagnostics={},
    )

    assert record["run_control"] == {
        "run_id": "run-1",
        "control_mode": "approval_wait",
    }
    assert record["approval_wait"] == {
        "wait_id": "wait-1",
        "run_id": "run-1",
        "approval_token": "approval-1",
        "tool_name": "bash",
        "wait_state": "pending",
    }


def test_runtime_session_persistence_record_builder_can_include_kernel_state_payload(tmp_path: Path) -> None:
    builder = RuntimeSessionPersistenceRecordBuilder(
        session_kind="shared",
        session_token_usage=lambda _session: 1,
        session_token_limit=lambda _session: 2,
        active_kernel_state=lambda _session: {
            "agent_profile": {"agent_profile_id": "agent-profile:main-agent"},
            "agent_instance": {"agent_instance_id": "agent-instance:sess-kernel"},
            "run": {"run_id": "run:sess-kernel", "status": "running", "phase": "planning"},
            "workspace_attachment": {"workspace_attachment_id": "workspace-attachment:run:sess-kernel"},
            "session_attachment": {"session_attachment_id": "session-attachment:run:sess-kernel"},
            "capability_snapshot": {"capability_snapshot_id": "capability-snapshot:run:sess-kernel"},
            "checkpoint": {"checkpoint_id": "checkpoint:run:sess-kernel:1"},
            "journal": {"journal_stream_id": "journal:run:sess-kernel", "last_event_seq": 3},
            "run_control": {"run_id": "run:sess-kernel", "control_mode": "normal"},
            "approval_wait": None,
        },
    )
    session = runtime_session_stub(
        session_id="sess-kernel",
        workspace_dir=tmp_path,
        created_at=_dt(),
        updated_at=_dt(),
        projection=runtime_projection_stub(
            title="Kernel payload",
            origin_surface="tui",
            active_surface="tui",
            reply_enabled=False,
            is_default=False,
            busy=True,
            running_state="running",
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
            sandbox_diagnostics={},
        ),
        lineage_state=lineage_state_stub(
            root_session_id="sess-kernel",
            created_at=_dt(),
        ),
        transcript_state=transcript_state_stub(transcript=[], next_transcript_index=1),
        agent=RuntimeContractAgentStub(),
    )

    record = builder.build_metadata_record(
        session,
        transcript_path=tmp_path / "transcript.jsonl",
        sandbox_diagnostics={},
    )

    assert record["kernel_state"] is not None
    assert record["kernel_state"]["agent_profile"]["agent_profile_id"] == "agent-profile:main-agent"
    assert record["kernel_state"]["agent_instance"]["agent_instance_id"] == "agent-instance:sess-kernel"
    assert record["kernel_state"]["run"]["run_id"] == "run:sess-kernel"
    assert record["kernel_state"]["journal"]["last_event_seq"] == 3


def test_runtime_session_persistence_record_builder_prefers_active_run_pending_approvals(tmp_path: Path) -> None:
    builder = RuntimeSessionPersistenceRecordBuilder(
        session_kind="shared",
        session_token_usage=lambda _session: 1,
        session_token_limit=lambda _session: 2,
        active_pending_approvals=lambda _session: [
            {
                "token": "approval-run",
                "tool_name": "shell",
                "arguments": {"command": "pytest -q"},
                "kind": "tool",
                "reason": "manual approval",
                "cache_key": "shell:pytest",
                "can_escalate": False,
                "step": 1,
            }
        ],
    )
    session = runtime_session_stub(
        session_id="sess-run-persist",
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
            sandbox_diagnostics={},
        ),
        lineage_state=lineage_state_stub(
            root_session_id="sess-run-persist",
            created_at=_dt(),
        ),
        transcript_state=transcript_state_stub(transcript=[], next_transcript_index=1),
        runtime=type(
            "_RuntimeState",
            (),
            {
                "agent": RuntimeContractAgentStub(),
                "pending_approvals": [{"token": "approval-stale", "tool_name": "bash"}],
            },
        )(),
    )

    record = builder.build_metadata_record(
        session,
        transcript_path=tmp_path / "transcript.jsonl",
        sandbox_diagnostics={},
    )

    assert record["pending_approvals"] == [
        {
            "token": "approval-run",
            "tool_name": "shell",
            "arguments": {"command": "pytest -q"},
            "kind": "tool",
            "reason": "manual approval",
            "cache_key": "shell:pytest",
            "can_escalate": False,
            "step": 1,
        }
    ]
