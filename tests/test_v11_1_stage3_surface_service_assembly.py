from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.application import (
    MainAgentSurfaceAssembly,
    MainAgentSurfaceService,
    assemble_main_agent_surface_service,
    assemble_runtime_backed_main_agent_surface_service,
    assemble_runtime_backed_user_services,
    build_main_agent_surface_service,
    build_runtime_backed_main_agent_surface_service,
)
from mini_agent.application.facades import (
    MainAgentSurfaceAssembly as FacadeMainAgentSurfaceAssembly,
    assemble_main_agent_surface_service as facade_assemble_main_agent_surface_service,
    assemble_runtime_backed_main_agent_surface_service as facade_assemble_runtime_backed_main_agent_surface_service,
    build_main_agent_surface_service as facade_build_main_agent_surface_service,
    build_runtime_backed_main_agent_surface_service as facade_build_runtime_backed_main_agent_surface_service,
)
from mini_agent.application.user_service_assembly import (
    assemble_runtime_backed_user_services as compat_assemble_runtime_backed_user_services,
)
from mini_agent.interfaces import (
    MainAgentSessionApprovalRequest,
    MainAgentSessionApprovalResponse,
    MainAgentSessionCancelRequest,
    MainAgentSessionMutationResponse,
)


def _resolve_workspace_dir(workspace_dir: str | None) -> Path:
    return Path(workspace_dir or ".").resolve()


def _to_utc_iso(value):  # noqa: ANN001
    return str(value)


def _sse_event(event: str, data: dict[str, object]) -> str:
    return f"{event}:{data}"


def _format_bootstrap_error(exc: Exception):  # noqa: ANN001
    return exc


class _RuntimeManagerStub:
    def validate_workspace(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir

    async def list_sessions(self, *, workspace_dir=None, shared_only=False):  # noqa: ANN001, ANN003
        return [{"workspace_dir": str(workspace_dir), "shared_only": shared_only}]

    async def cancel_session_turn(self, session_id: str, **kwargs):
        return {"kind": "cancelled", "session_id": session_id, "kwargs": kwargs}

    async def resolve_pending_approval(self, session_id: str, **kwargs):
        return {"kind": "approval", "session_id": session_id, "kwargs": kwargs}

    async def update_session_runtime_policy(self, session_id: str, **kwargs):
        return {"kind": "policy", "session_id": session_id, "kwargs": kwargs}

    async def update_session_model_selection(self, session_id: str, **kwargs):
        return {"kind": "model", "session_id": session_id, "kwargs": kwargs}

    async def control_session_context(self, session_id: str, **kwargs):
        return {"kind": "control", "session_id": session_id, "kwargs": kwargs}

    async def update_session_context_policy(self, session_id: str, **kwargs):
        return {"kind": "context", "session_id": session_id, "kwargs": kwargs}

    async def manage_session_memory(self, session_id: str, **kwargs):
        return {"kind": "memory", "session_id": session_id, "kwargs": kwargs}

    async def manage_session_skills(self, session_id: str, **kwargs):
        return {"kind": "skills", "session_id": session_id, "kwargs": kwargs}


def test_stage3_surface_assembly_exports_stable_entrypoints() -> None:
    assert FacadeMainAgentSurfaceAssembly is MainAgentSurfaceAssembly
    assert facade_assemble_main_agent_surface_service is assemble_main_agent_surface_service
    assert facade_assemble_runtime_backed_main_agent_surface_service is assemble_runtime_backed_main_agent_surface_service
    assert facade_build_main_agent_surface_service is build_main_agent_surface_service
    assert facade_build_runtime_backed_main_agent_surface_service is build_runtime_backed_main_agent_surface_service
    assert compat_assemble_runtime_backed_user_services is assemble_runtime_backed_user_services


def test_stage3_surface_builder_prefers_explicit_user_service_assembly() -> None:
    user_assembly = assemble_runtime_backed_user_services(runtime_manager=_RuntimeManagerStub())

    surface_service = build_main_agent_surface_service(
        user_service_assembly=user_assembly,
        resolve_workspace_dir=_resolve_workspace_dir,
        to_utc_iso=_to_utc_iso,
        sse_event=_sse_event,
        format_bootstrap_error=_format_bootstrap_error,
        stream_chunk_size=64,
    )

    assert isinstance(surface_service, MainAgentSurfaceService)
    assert not hasattr(surface_service, "_session_service")
    assert surface_service._session_task_service is user_assembly.session_task_service
    assert surface_service._run_control_service is user_assembly.agent_service
    assert surface_service._agent_service is user_assembly.agent_service
    assert surface_service._model_service is user_assembly.model_service


def test_stage4_runtime_backed_surface_builder_preserves_runtime_manager_access() -> None:
    runtime_manager = _RuntimeManagerStub()

    assembly = assemble_runtime_backed_main_agent_surface_service(
        runtime_manager=runtime_manager,
        resolve_workspace_dir=_resolve_workspace_dir,
        to_utc_iso=_to_utc_iso,
        sse_event=_sse_event,
        format_bootstrap_error=_format_bootstrap_error,
        stream_chunk_size=64,
    )
    surface_service = build_runtime_backed_main_agent_surface_service(
        runtime_manager=_RuntimeManagerStub(),
        resolve_workspace_dir=_resolve_workspace_dir,
        to_utc_iso=_to_utc_iso,
        sse_event=_sse_event,
        format_bootstrap_error=_format_bootstrap_error,
        stream_chunk_size=64,
    )

    assert isinstance(assembly, MainAgentSurfaceAssembly)
    assert assembly.runtime_manager is runtime_manager
    assert not hasattr(assembly.surface_service, "_session_service")
    assert isinstance(surface_service, MainAgentSurfaceService)
    assert not hasattr(surface_service, "_session_service")


@pytest.mark.asyncio
async def test_stage4_surface_assembly_resolves_legacy_session_service_only_at_assembly_boundary() -> None:
    class _LegacySessionTaskService:
        async def list_sessions(self, *, workspace_dir=None, shared_only=False):  # noqa: ANN001, ANN003
            return [{"workspace_dir": str(workspace_dir), "shared_only": shared_only}]

    class _LegacyRunControlService:
        def __init__(self) -> None:
            self.calls: list[tuple[str, str, object]] = []

        async def cancel_session_run(self, session_id: str, **kwargs):
            self.calls.append(("cancel_session_run", session_id, kwargs))
            return MainAgentSessionMutationResponse(status="cancel_requested", session_id=session_id)

        async def approve_session_wait(self, session_id: str, **kwargs):
            self.calls.append(("approve_session_wait", session_id, kwargs))
            return MainAgentSessionApprovalResponse(
                status="resolved",
                session_id=session_id,
                token=str(kwargs.get("token") or ""),
                tool_name="shell",
                decision="approved",
            )

    class _LegacySessionService:
        def __init__(self) -> None:
            self.session_task_service = _LegacySessionTaskService()
            self.run_control_service = _LegacyRunControlService()
            self.agent_service = object()
            self.model_service = object()
            self.workspace_service = object()

    legacy_session_service = _LegacySessionService()
    assembly = assemble_main_agent_surface_service(
        session_service=legacy_session_service,
        resolve_workspace_dir=_resolve_workspace_dir,
        to_utc_iso=_to_utc_iso,
        sse_event=_sse_event,
        format_bootstrap_error=_format_bootstrap_error,
        stream_chunk_size=64,
    )

    sessions = await assembly.surface_service.list_sessions(workspace_dir=".", shared_only=True)
    cancel = await assembly.surface_service.cancel_session(
        "sess-legacy",
        MainAgentSessionCancelRequest(reason="stop", surface="desktop"),
    )
    approved = await assembly.surface_service.respond_to_approval(
        "sess-legacy",
        MainAgentSessionApprovalRequest(approved=True, token="approval-1", surface="desktop"),
    )

    assert isinstance(assembly, MainAgentSurfaceAssembly)
    assert assembly.legacy_session_service is legacy_session_service
    assert not hasattr(assembly.surface_service, "_session_service")
    assert assembly.surface_service._session_task_service is legacy_session_service.session_task_service
    assert assembly.surface_service._run_control_service is legacy_session_service.run_control_service
    assert sessions == [{"workspace_dir": str(Path(".").resolve()), "shared_only": True}]
    assert cancel.status == "cancel_requested"
    assert approved.decision == "approved"
