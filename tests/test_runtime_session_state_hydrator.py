from __future__ import annotations

from mini_agent.runtime.session_runtime_state_hydrator import RuntimeSessionStateHydrator
from tests.runtime_contract_fixtures import RuntimeContractAgentStub, runtime_projection_stub, runtime_session_stub


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
