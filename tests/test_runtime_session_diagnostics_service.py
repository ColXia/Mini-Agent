from __future__ import annotations

from pathlib import Path

from mini_agent.runtime.session_diagnostics_service import RuntimeSessionDiagnosticsService
from mini_agent.workspace_runtime import clear_shared_workspace_snapshot_stores
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


def test_runtime_session_diagnostics_service_can_capture_and_restore_workspace_runtime_snapshot(
    tmp_path,
) -> None:
    clear_shared_workspace_snapshot_stores()
    service = RuntimeSessionDiagnosticsService(
        normalize_prepared_context_payload=lambda value: dict(value or {}),
        normalize_memory_diagnostics_payload=lambda value: dict(value or {}),
        normalize_sandbox_diagnostics_payload=lambda value: dict(value or {}),
        collect_sandbox_diagnostics=lambda agent: {"backend": "none", "agent": bool(agent)},
    )
    session = runtime_session_stub(
        workspace_dir=tmp_path,
        session_id="sess-runtime-snap",
        projection=runtime_projection_stub(
            memory_diagnostics={},
            sandbox_diagnostics={},
        ),
        transcript_state=type(
            "_TranscriptState",
            (),
            {"transcript": [object(), object()]},
        )(),
        agent=RuntimeContractAgentStub(),
    )

    payload = service.build_workspace_runtime_snapshot_for_session(session)
    restored = service.restore_workspace_runtime_snapshot_payload(
        payload,
        workspace_dir=Path(tmp_path),
    )

    assert payload is not None
    assert payload["workspace_dir"] == str(Path(tmp_path).resolve())
    assert payload["metadata"]["trigger"] == "session_snapshot_export"
    assert payload["metadata"]["session_id"] == "sess-runtime-snap"
    assert restored is not None
    assert restored["snapshot_id"] == payload["snapshot_id"]
    assert restored["workspace_dir"] == payload["workspace_dir"]
    assert restored["mutation_count"] == payload["mutation_count"]
