from __future__ import annotations

from mini_agent.runtime.session_diagnostics_service import RuntimeSessionDiagnosticsService
from tests.runtime_contract_fixtures import RuntimeContractAgentStub, runtime_projection_stub, runtime_session_stub


def test_runtime_session_diagnostics_service_reads_agent_memory_state_from_support(
    monkeypatch,
    tmp_path,
) -> None:
    captured: dict[str, object] = {}

    def _fake_build_memory_diagnostics(**kwargs):
        captured.update(kwargs)
        return {"preview": ["ok"]}

    monkeypatch.setattr(
        "mini_agent.runtime.session_diagnostics_service.build_memory_diagnostics",
        _fake_build_memory_diagnostics,
    )

    service = RuntimeSessionDiagnosticsService(
        normalize_prepared_context_payload=lambda value: dict(value or {}),
        normalize_memory_diagnostics_payload=lambda value: dict(value or {}),
        normalize_sandbox_diagnostics_payload=lambda value: dict(value or {}),
        collect_sandbox_diagnostics=lambda agent: {"backend": "none", "agent": bool(agent)},
        agent_last_memory_automation=lambda agent: {"stored": bool(agent)},
        agent_last_runtime_task_memory=lambda agent: {"synced": bool(agent)},
    )
    session = runtime_session_stub(
        workspace_dir=tmp_path,
        session_id="sess-diag",
        projection=runtime_projection_stub(
            last_prepared_context={"summary": "ctx"},
            memory_diagnostics={},
            sandbox_diagnostics={},
        ),
        agent=RuntimeContractAgentStub(),
    )

    diagnostics = service.build_memory_diagnostics_for_session(session)

    assert diagnostics == {"preview": ["ok"]}
    assert captured["last_memory_automation"] == {"stored": True}
    assert captured["last_runtime_task_memory"] == {"synced": True}


def test_runtime_session_diagnostics_service_falls_back_to_legacy_agent_attributes(
    monkeypatch,
    tmp_path,
) -> None:
    captured: dict[str, object] = {}

    def _fake_build_memory_diagnostics(**kwargs):
        captured.update(kwargs)
        return {"preview": ["legacy"]}

    monkeypatch.setattr(
        "mini_agent.runtime.session_diagnostics_service.build_memory_diagnostics",
        _fake_build_memory_diagnostics,
    )

    service = RuntimeSessionDiagnosticsService(
        normalize_prepared_context_payload=lambda value: dict(value or {}),
        normalize_memory_diagnostics_payload=lambda value: dict(value or {}),
        normalize_sandbox_diagnostics_payload=lambda value: dict(value or {}),
        collect_sandbox_diagnostics=lambda agent: {"backend": "none", "agent": bool(agent)},
    )
    session = runtime_session_stub(
        workspace_dir=tmp_path,
        session_id="sess-diag-legacy",
        projection=runtime_projection_stub(
            last_prepared_context={"summary": "ctx"},
            memory_diagnostics={},
            sandbox_diagnostics={},
        ),
        agent=RuntimeContractAgentStub(
            last_memory_automation={"legacy": "memory"},
            last_runtime_task_memory={"legacy": "task"},
        ),
    )

    diagnostics = service.build_memory_diagnostics_for_session(session)

    assert diagnostics == {"preview": ["legacy"]}
    assert captured["last_memory_automation"] == {"legacy": "memory"}
    assert captured["last_runtime_task_memory"] == {"legacy": "task"}
