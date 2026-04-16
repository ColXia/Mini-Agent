from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

from mini_agent.runtime.session_hydration_builder import RuntimeSessionHydrationPayload
from mini_agent.runtime.session_restore_handler import RuntimeSessionRestoreHandler
from tests.runtime_contract_fixtures import RuntimeContractAgentStub, runtime_projection_stub, runtime_session_stub


def _dt() -> datetime:
    return datetime(2026, 4, 16, 8, 0, 0, tzinfo=timezone.utc)


def test_runtime_session_restore_handler_supports_legacy_lifecycle_bootstrap() -> None:
    captured: dict[str, object] = {}
    payload = RuntimeSessionHydrationPayload(
        session_id="sess-restore",
        workspace_dir=Path(".").resolve(),
        created_at=_dt(),
        updated_at=_dt(),
        selected_identity=("preset", "openai", "gpt-5.4"),
        pending_identity=None,
        desired_approval_profile=None,
        desired_access_level=None,
        agent_messages=[],
        token_usage=0,
        token_limit=0,
        requested_knowledge_base_enabled=None,
        title="restore",
        origin_surface="tui",
        active_surface="tui",
        reply_enabled=False,
        is_default=False,
        channel_type=None,
        conversation_id=None,
        sender_id=None,
        shared=False,
        lineage_parent_session_id=None,
        lineage_root_session_id="sess-restore",
        lineage_reason="root",
        lineage_created_at=_dt(),
        lineage_metadata={},
        pending_skill_reload=False,
        pending_skill_reload_reason="",
        context_policy={},
        last_prepared_context={},
        prepared_context_diagnostics={},
        memory_diagnostics={},
        sandbox_diagnostics={},
        transcript=[],
    )

    async def _build_agent_for_identity(_workspace_dir, _identity):
        return RuntimeContractAgentStub()

    def _build_session_state(payload_value, *, lifecycle_state, agent, effective_knowledge_base_enabled):
        captured["lifecycle_state"] = lifecycle_state
        captured["effective_knowledge_base_enabled"] = effective_knowledge_base_enabled
        return runtime_session_stub(
            session_id=payload_value.session_id,
            workspace_dir=payload_value.workspace_dir,
            agent=agent,
            projection=runtime_projection_stub(),
            lifecycle_state=lifecycle_state,
            created_at=payload_value.created_at,
            updated_at=payload_value.updated_at,
        )

    handler = RuntimeSessionRestoreHandler(
        transcript_entries_from_record=lambda _record: [],
        stored_recovery_snapshot_from_record=lambda _record, _transcript: None,
        build_record_hydration_payload=lambda _record, **_kwargs: payload,
        build_agent_for_identity=_build_agent_for_identity,
        load_runtime_config=lambda: object(),
        reconfigure_agent_runtime_policy=lambda **_kwargs: {},
        restore_agent_messages_payload=lambda _messages, _agent: None,
        restore_agent_token_state=lambda _agent, **_kwargs: None,
        agent_knowledge_base_enabled=lambda _agent: True,
        apply_agent_knowledge_base_enabled=lambda _agent, enabled: bool(enabled),
        build_session_state=_build_session_state,
        apply_stored_recovery=lambda _session, _stored_recovery: None,
        set_selected_model_identity=lambda _session, _identity: None,
        route_model_identity=lambda _agent: ("preset", "openai", "gpt-5.4"),
        hydrate_runtime_state=lambda _session, _payload: None,
        build_session_key=lambda session_id, workspace_dir: (session_id, str(workspace_dir)),
        lifecycle_bootstrap=lambda session_key, now_utc: {"session_key": session_key, "now_utc": now_utc},
    )

    execution = asyncio.run(handler.hydrate_payload(payload, now_utc=_dt()))

    assert execution.created is True
    assert execution.session.session_id == "sess-restore"
    assert captured["effective_knowledge_base_enabled"] is True
    assert captured["lifecycle_state"] == {
        "session_key": ("sess-restore", str(Path(".").resolve())),
        "now_utc": _dt(),
    }
