from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from mini_agent.runtime.orchestration.session_hydration_builder import RuntimeSessionHydrationPayload
from mini_agent.runtime.orchestration.session_runtime_state_hydrator import RuntimeSessionStateHydrator
from tests.runtime_contract_fixtures import RuntimeContractAgentStub, runtime_projection_stub, runtime_session_stub


def _dt() -> datetime:
    return datetime(2026, 4, 18, 9, 0, 0, tzinfo=timezone.utc)


def test_runtime_session_state_hydrator_captures_prepared_context_via_support_contract() -> None:
    hydrator = RuntimeSessionStateHydrator(
        agent_knowledge_base_enabled=lambda _agent: False,
        agent_last_prepared_context=lambda _agent: {"item_count": 1},
        agent_prepared_context_diagnostics=lambda _agent: {"turn_count": 2},
        restore_session_runtime_task_memory=lambda **_kwargs: {},
        restore_workspace_shared_runtime_task_memory=lambda **_kwargs: {},
        build_memory_diagnostics_for_session=lambda session: session.projection.memory_diagnostics.update({"ok": True})
        or session.projection.memory_diagnostics,
        build_sandbox_diagnostics_for_session=lambda session: session.projection.sandbox_diagnostics.update(
            {"backend": "none"}
        )
        or session.projection.sandbox_diagnostics,
    )
    session = runtime_session_stub(
        agent=RuntimeContractAgentStub(),
        projection=runtime_projection_stub(),
    )

    hydrator.capture_agent_prepared_context_state(session)

    assert session.projection.knowledge_base_enabled is False
    assert session.projection.last_prepared_context == {"item_count": 1}
    assert session.projection.prepared_context_diagnostics == {"turn_count": 2}
    assert session.projection.memory_diagnostics == {"ok": True}
    assert session.projection.sandbox_diagnostics == {"backend": "none"}


def test_runtime_session_state_hydrator_refreshes_runtime_projection_state() -> None:
    hydrator = RuntimeSessionStateHydrator(
        agent_knowledge_base_enabled=lambda _agent: False,
        agent_last_prepared_context=lambda _agent: {},
        agent_prepared_context_diagnostics=lambda _agent: {},
        restore_session_runtime_task_memory=lambda **_kwargs: {},
        restore_workspace_shared_runtime_task_memory=lambda **_kwargs: {},
        build_memory_diagnostics_for_session=lambda session: session.projection.memory_diagnostics.update({"memory": "ok"})
        or session.projection.memory_diagnostics,
        build_sandbox_diagnostics_for_session=lambda session: session.projection.sandbox_diagnostics.update(
            {"approval_profile": "plan"}
        )
        or session.projection.sandbox_diagnostics,
    )
    session = runtime_session_stub(
        agent=RuntimeContractAgentStub(),
        projection=runtime_projection_stub(
            memory_diagnostics={"stale": True},
            sandbox_diagnostics={"stale": True},
        ),
    )

    memory, sandbox = hydrator.refresh_runtime_projection(session)

    assert session.projection.knowledge_base_enabled is False
    assert memory == {"stale": True, "memory": "ok"}
    assert sandbox == {"stale": True, "approval_profile": "plan"}


def test_runtime_session_state_hydrator_supports_legacy_context_normalizers() -> None:
    hydrator = RuntimeSessionStateHydrator(
        agent_knowledge_base_enabled=lambda _agent: True,
        restore_session_runtime_task_memory=lambda **_kwargs: {},
        restore_workspace_shared_runtime_task_memory=lambda **_kwargs: {},
        build_memory_diagnostics_for_session=lambda session: session.projection.memory_diagnostics.update({"ok": True})
        or session.projection.memory_diagnostics,
        build_sandbox_diagnostics_for_session=lambda session: session.projection.sandbox_diagnostics.update(
            {"backend": "none"}
        )
        or session.projection.sandbox_diagnostics,
        normalize_prepared_context_payload=lambda value: dict(value or {}),
        normalize_prepared_context_diagnostics_payload=lambda value: dict(value or {}),
    )
    session = runtime_session_stub(
        agent=RuntimeContractAgentStub(
            prepared_context={"legacy": "ctx"},
            prepared_context_diagnostics={"legacy": "diag"},
        ),
        projection=runtime_projection_stub(),
    )

    hydrator.capture_agent_prepared_context_state(session)

    assert session.projection.knowledge_base_enabled is True
    assert session.projection.last_prepared_context == {"legacy": "ctx"}
    assert session.projection.prepared_context_diagnostics == {"legacy": "diag"}


def test_runtime_session_state_hydrator_restores_workspace_runtime_snapshot() -> None:
    captured: dict[str, object] = {}
    hydrator = RuntimeSessionStateHydrator(
        agent_knowledge_base_enabled=lambda _agent: True,
        restore_session_runtime_task_memory=lambda **_kwargs: {},
        restore_workspace_shared_runtime_task_memory=lambda **_kwargs: {},
        restore_workspace_runtime_snapshot=lambda **kwargs: captured.update(kwargs) or kwargs["payload"],
        build_memory_diagnostics_for_session=lambda session: session.projection.memory_diagnostics,
        build_sandbox_diagnostics_for_session=lambda session: session.projection.sandbox_diagnostics,
    )
    session = runtime_session_stub(
        session_id="sess-restore-runtime-snapshot",
        workspace_dir=Path(".").resolve(),
        agent=RuntimeContractAgentStub(),
        projection=runtime_projection_stub(),
    )

    hydrator.hydrate_runtime_state(
        session,
        payload=RuntimeSessionHydrationPayload(
            session_id="sess-restore-runtime-snapshot",
            workspace_dir=Path(".").resolve(),
            created_at=_dt(),
            updated_at=_dt(),
            selected_identity=None,
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
            lineage_root_session_id="sess-restore-runtime-snapshot",
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
            workspace_runtime_snapshot={"snapshot_id": "restored-snap"},
        ),
    )

    assert captured["workspace_dir"] == Path(".").resolve()
    assert captured["payload"] == {"snapshot_id": "restored-snap"}
