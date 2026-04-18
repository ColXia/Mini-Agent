from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.application import (
    RuntimeBackedUserServicePorts,
    SessionApplicationService,
    UserServiceAssembly,
    assemble_runtime_backed_user_services,
    assemble_typed_user_services,
    resolve_runtime_backed_user_service_ports,
)
from mini_agent.application.legacy import RuntimeBackedSessionApplicationAssembly
from mini_agent.application.session_runtime_compat import SessionBackedRunRuntimeAdapter
from mini_agent.application.user_service_assembly import (
    RuntimeBackedUserServicePorts as CompatRuntimeBackedUserServicePorts,
    UserServiceAssembly as CompatUserServiceAssembly,
    assemble_runtime_backed_user_services as compat_assemble_runtime_backed_user_services,
    assemble_typed_user_services as compat_assemble_typed_user_services,
    resolve_runtime_backed_user_service_ports as compat_resolve_runtime_backed_user_service_ports,
)
from mini_agent.application.user_services import (
    AgentUserService,
    CommandUserService,
    ModelUserService,
    WorkspaceUserService,
)
from mini_agent.interfaces import MainAgentSessionCancelRequest
from mini_agent.runtime.support.session_backed_run_id import build_session_backed_run_id


class _SessionTaskRuntimeStub:
    def validate_workspace(self, workspace_dir: Path) -> None:
        self.workspace_dir = workspace_dir

    async def list_sessions(self, *, workspace_dir=None, shared_only=False):  # noqa: ANN001, ANN003
        return [{"workspace_dir": str(workspace_dir), "shared_only": shared_only}]


class _SessionTaskPortStub:
    async def get_session_task(self, session_id: str):
        return {"session_id": session_id}

    async def resolve_run_id_for_session(self, session_id: str) -> str | None:
        _ = session_id
        return None

    async def cancel_session_turn(self, session_id: str, **kwargs):
        return {"kind": "cancelled", "session_id": session_id, "kwargs": kwargs}

    async def resolve_pending_approval(self, session_id: str, **kwargs):
        return {"kind": "approval", "session_id": session_id, "kwargs": kwargs}


class _SessionAgentRuntimeStub:
    async def update_session_runtime_policy(self, session_id: str, **kwargs):
        return {"kind": "policy", "session_id": session_id, "kwargs": kwargs}

    async def control_session_context(self, session_id: str, **kwargs):
        return {"kind": "control", "session_id": session_id, "kwargs": kwargs}

    async def update_session_context_policy(self, session_id: str, **kwargs):
        return {"kind": "context", "session_id": session_id, "kwargs": kwargs}

    async def manage_session_memory(self, session_id: str, **kwargs):
        return {"kind": "memory", "session_id": session_id, "kwargs": kwargs}

    async def manage_session_skills(self, session_id: str, **kwargs):
        return {"kind": "skills", "session_id": session_id, "kwargs": kwargs}


class _SessionModelRuntimeStub:
    async def update_session_model_selection(self, session_id: str, **kwargs):
        return {"kind": "model", "session_id": session_id, "kwargs": kwargs}


class _WorkspaceRuntimeStub:
    async def list_workspaces(self):
        return [{"workspace_id": "ws-1"}]

    async def get_workspace(self, workspace_id: str):
        return {"workspace_id": workspace_id}

    async def get_active_workspace(self):
        return {"workspace_id": "ws-1", "active": True}

    async def switch_workspace(self, workspace_id: str):
        return {"workspace_id": workspace_id, "switched": True}

    async def get_workspace_runtime_summary(self, workspace_id: str | None = None):
        return {"workspace_id": workspace_id or "ws-1", "summary": True}


class _CommandRuntimeStub:
    def execute_command(self, raw_command: str, **kwargs):
        return {"command": raw_command, "kwargs": kwargs}


class _RuntimeManagerStub(_SessionTaskRuntimeStub):
    async def get_session_task(self, session_id: str):
        return {"kind": "task", "session_id": session_id}

    async def resolve_run_id_for_session(self, session_id: str) -> str | None:
        return build_session_backed_run_id(session_id)

    async def interrupt_run(self, run_id: str, *, reason: str | None = None, source: str | None = None):
        return {"kind": "interrupt", "run_id": run_id, "reason": reason, "source": source}

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 50):
        _ = recent_limit
        return {
            "session_id": session_id,
            "busy": True,
            "pending_approvals": [{"token": "approval-1"}],
            "active_surface": "desktop",
            "channel_type": "desktop",
            "conversation_id": "local:1",
            "sender_id": "operator",
            "running_state": "desktop request running",
        }

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


def test_stage3_user_service_assembly_exports_stable_entrypoints() -> None:
    assert RuntimeBackedSessionApplicationAssembly is UserServiceAssembly
    assert CompatRuntimeBackedUserServicePorts is RuntimeBackedUserServicePorts
    assert CompatUserServiceAssembly is UserServiceAssembly
    assert compat_assemble_runtime_backed_user_services is assemble_runtime_backed_user_services
    assert compat_assemble_typed_user_services is assemble_typed_user_services
    assert compat_resolve_runtime_backed_user_service_ports is resolve_runtime_backed_user_service_ports


@pytest.mark.asyncio
async def test_stage3_typed_user_service_assembly_builds_explicit_user_services() -> None:
    assembly = assemble_typed_user_services(
        session_task_runtime=_SessionTaskRuntimeStub(),
        session_task_port=_SessionTaskPortStub(),
        session_agent_runtime=_SessionAgentRuntimeStub(),
        session_model_runtime=_SessionModelRuntimeStub(),
        workspace_runtime=_WorkspaceRuntimeStub(),
        command_runtime=_CommandRuntimeStub(),
    )

    assert isinstance(assembly, UserServiceAssembly)
    assert isinstance(assembly.agent_service, AgentUserService)
    assert isinstance(assembly.workspace_service, WorkspaceUserService)
    assert isinstance(assembly.model_service, ModelUserService)
    assert isinstance(assembly.command_service, CommandUserService)

    listed = await assembly.session_task_service.list_sessions(
        workspace_dir=Path("D:/workspace/demo"),
        shared_only=True,
    )
    policy = await assembly.agent_service.update_session_runtime_policy(
        "sess-typed",
        approval_profile="build",
        surface="desktop",
    )
    switched = await assembly.workspace_service.switch_workspace("ws-2")  # type: ignore[union-attr]
    model = await assembly.model_service.update_session_model_selection(
        "sess-typed",
        provider_source="preset",
        provider_id="openai",
        model_id="gpt-5.4",
        surface="desktop",
    )
    command = await assembly.command_service.dispatch_command("/help", surface="desktop")  # type: ignore[union-attr]

    assert listed == [{"workspace_dir": "D:\\workspace\\demo", "shared_only": True}]
    assert policy["kind"] == "policy"
    assert switched == {"workspace_id": "ws-2", "switched": True}
    assert model["kind"] == "model"
    assert command == {"command": "/help", "kwargs": {"surface": "desktop"}}


@pytest.mark.asyncio
async def test_stage3_runtime_backed_user_service_assembly_wraps_broad_runtime_with_explicit_services() -> None:
    runtime_manager = _RuntimeManagerStub()
    assembly = assemble_runtime_backed_user_services(runtime_manager=runtime_manager)

    assert isinstance(assembly, UserServiceAssembly)
    assert assembly.workspace_service is None
    assert assembly.command_service is None
    assert assembly.agent_service.session_agent_runtime is runtime_manager
    assert assembly.model_service.session_model_runtime is runtime_manager

    listed = await assembly.session_task_service.list_sessions(
        workspace_dir=Path("D:/workspace/runtime"),
        shared_only=False,
    )
    cancelled = await assembly.run_control_service.cancel_session_run(
        "sess-runtime",
        reason="stop",
        surface="desktop",
    )
    policy = await assembly.agent_service.update_session_runtime_policy(
        "sess-runtime",
        approval_profile="plan",
        surface="desktop",
    )
    model = await assembly.model_service.update_session_model_selection(
        "sess-runtime",
        provider_source="preset",
        provider_id="openai",
        model_id="gpt-5.4",
        surface="desktop",
    )

    assert listed == [{"workspace_dir": "D:\\workspace\\runtime", "shared_only": False}]
    assert cancelled["kind"] == "cancelled"
    assert policy["kind"] == "policy"
    assert model["kind"] == "model"


@pytest.mark.asyncio
async def test_stage4_session_task_service_absorbs_session_scoped_compatibility_actions() -> None:
    runtime_manager = _RuntimeManagerStub()
    assembly = assemble_runtime_backed_user_services(runtime_manager=runtime_manager)

    controlled = await assembly.session_task_service.control_session(
        "sess-runtime",
        action="compact",
        reason="trim",
        surface="desktop",
    )
    context = await assembly.session_task_service.update_session_context(
        "sess-runtime",
        action="include",
        sources=["workspace_memory"],
        max_items=2,
        surface="desktop",
    )
    memory = await assembly.session_task_service.manage_session_memory(
        "sess-runtime",
        action="show",
        query="recent",
        detail_mode="brief",
        surface="desktop",
    )
    skills = await assembly.session_task_service.manage_session_skills(
        "sess-runtime",
        action="search",
        query="foundry",
        mode="allowlist",
        surface="desktop",
    )
    model = await assembly.session_task_service.update_session_model_selection(
        "sess-runtime",
        provider_source="preset",
        provider_id="openai",
        model_id="gpt-5.4",
        surface="desktop",
    )
    policy = await assembly.session_task_service.update_session_runtime_policy(
        "sess-runtime",
        approval_profile="plan",
        access_level="default",
        surface="desktop",
    )

    assert controlled["kind"] == "control"
    assert context["kind"] == "context"
    assert memory["kind"] == "memory"
    assert skills["kind"] == "skills"
    assert model["kind"] == "model"
    assert policy["kind"] == "policy"


@pytest.mark.asyncio
async def test_stage5_runtime_backed_user_service_ports_accept_narrow_structural_support_owner() -> None:
    class _RuntimeBackedSupportStub:
        async def get_session_task(self, session_id: str):
            return {"kind": "task", "session_id": session_id}

        async def resolve_run_id_for_session(self, session_id: str) -> str | None:
            return build_session_backed_run_id(session_id)

        async def cancel_session_turn(self, session_id: str, **kwargs):
            return {"kind": "cancelled", "session_id": session_id, "kwargs": kwargs}

        async def resolve_pending_approval(self, session_id: str, **kwargs):
            return {"kind": "approval", "session_id": session_id, "kwargs": kwargs}

        async def get_session_detail(self, session_id: str, *, recent_limit: int = 50):
            _ = recent_limit
            return {
                "session_id": session_id,
                "busy": False,
                "pending_approvals": [],
                "active_surface": "desktop",
                "running_state": "",
            }

    ports = resolve_runtime_backed_user_service_ports(runtime_manager=_RuntimeBackedSupportStub())
    task = await ports.session_task_port.get_session_task("sess-structural")
    run = await ports.run_runtime.get_run(build_session_backed_run_id("sess-structural"))

    assert task == {"kind": "task", "session_id": "sess-structural"}
    assert run["run_id"] == build_session_backed_run_id("sess-structural")
    assert run["status"] == "completed"


def test_stage5_runtime_backed_user_service_ports_prefers_direct_runtime_for_agent_and_model_paths() -> None:
    runtime_manager = _RuntimeManagerStub()

    ports = resolve_runtime_backed_user_service_ports(runtime_manager=runtime_manager)

    assert isinstance(ports, RuntimeBackedUserServicePorts)
    assert ports.session_task_runtime is runtime_manager
    assert ports.session_task_port is runtime_manager
    assert ports.session_agent_runtime is runtime_manager
    assert ports.session_model_runtime is runtime_manager
    assert ports.run_runtime is not None


@pytest.mark.asyncio
async def test_stage5_runtime_backed_user_service_ports_attach_session_backed_run_runtime() -> None:
    runtime_manager = _RuntimeManagerStub()

    ports = resolve_runtime_backed_user_service_ports(runtime_manager=runtime_manager)
    run = await ports.run_runtime.get_run(build_session_backed_run_id("sess-runtime"))
    interrupted = await ports.run_runtime.interrupt_run(
        build_session_backed_run_id("sess-runtime"),
        reason="pause",
        source="desktop",
    )
    cancelled = await ports.run_runtime.cancel_run(
        build_session_backed_run_id("sess-runtime"),
        reason="stop",
        source="desktop",
    )
    resumed = await ports.run_runtime.resume_run(
        build_session_backed_run_id("sess-runtime"),
        resume_token="approval-1",
        source="desktop",
    )
    approved = await ports.run_runtime.resolve_approval_wait(
        build_session_backed_run_id("sess-runtime"),
        approved=True,
        token="approval-1",
        source="desktop",
    )

    assert isinstance(ports.run_runtime, SessionBackedRunRuntimeAdapter)
    assert run["run_id"] == build_session_backed_run_id("sess-runtime")
    assert run["status"] == "waiting"
    assert run["phase"] == "awaiting_approval"
    assert interrupted["kind"] == "interrupt"
    assert cancelled["kind"] == "cancelled"
    assert resumed["kind"] == "approval"
    assert approved["kind"] == "approval"


@pytest.mark.asyncio
async def test_stage5_session_backed_run_runtime_reports_interrupt_requested_state() -> None:
    class _RuntimeManager:
        async def get_session_detail(self, session_id: str, *, recent_limit: int = 50):
            _ = recent_limit
            return {
                "session_id": session_id,
                "busy": True,
                "pending_approvals": [],
                "active_surface": "desktop",
                "running_state": "interrupt requested",
            }

    adapter = SessionBackedRunRuntimeAdapter(_RuntimeManager())

    run = await adapter.get_run(build_session_backed_run_id("sess-interrupt"))

    assert run["status"] == "interrupt_requested"
    assert run["phase"] == "interrupting"
    assert run["waiting_on_approval"] is False


@pytest.mark.asyncio
async def test_stage5_session_backed_run_runtime_reports_cancel_requested_state() -> None:
    class _RuntimeManager:
        async def get_session_detail(self, session_id: str, *, recent_limit: int = 50):
            _ = recent_limit
            return {
                "session_id": session_id,
                "busy": True,
                "pending_approvals": [{"token": "approval-1"}],
                "active_surface": "desktop",
                "running_state": "cancellation requested",
            }

    adapter = SessionBackedRunRuntimeAdapter(_RuntimeManager())

    run = await adapter.get_run(build_session_backed_run_id("sess-cancel"))

    assert run["status"] == "cancel_requested"
    assert run["phase"] == "cancelling"
    assert run["waiting_on_approval"] is True


@pytest.mark.asyncio
async def test_stage5_session_backed_run_runtime_interrupt_requires_direct_runtime_support() -> None:
    class _RuntimeManager:
        async def get_session_detail(self, session_id: str, *, recent_limit: int = 50):
            _ = (session_id, recent_limit)
            return {
                "session_id": "sess-no-direct-interrupt",
                "busy": True,
                "pending_approvals": [],
                "active_surface": "desktop",
            }

    adapter = SessionBackedRunRuntimeAdapter(_RuntimeManager())

    with pytest.raises(LookupError, match="does not support interrupt"):
        await adapter.interrupt_run(
            build_session_backed_run_id("sess-no-direct-interrupt"),
            reason="pause",
            source="desktop",
        )


@pytest.mark.asyncio
async def test_stage5_session_backed_run_runtime_prefers_direct_runtime_methods_when_available() -> None:
    class _RuntimeManager:
        async def get_run(self, run_id: str):
            return {"kind": "run", "run_id": run_id}

        async def interrupt_run(self, run_id: str, *, reason: str | None = None, source: str | None = None):
            return {"kind": "interrupt", "run_id": run_id, "reason": reason, "source": source}

        async def resume_run(self, run_id: str, *, resume_token: str | None = None, source: str | None = None):
            return {"kind": "resume", "run_id": run_id, "resume_token": resume_token, "source": source}

        async def cancel_run(self, run_id: str, *, reason: str | None = None, source: str | None = None):
            return {"kind": "cancel", "run_id": run_id, "reason": reason, "source": source}

        async def resolve_approval_wait(
            self,
            run_id: str,
            *,
            approved: bool,
            token: str | None = None,
            source: str | None = None,
            reason: str | None = None,
        ):
            return {
                "kind": "approval",
                "run_id": run_id,
                "approved": approved,
                "token": token,
                "source": source,
                "reason": reason,
            }

    adapter = SessionBackedRunRuntimeAdapter(_RuntimeManager())

    run_id = build_session_backed_run_id("sess-direct")
    run = await adapter.get_run(run_id)
    interrupted = await adapter.interrupt_run(run_id, reason="pause", source="desktop")
    resumed = await adapter.resume_run(run_id, resume_token="approval-1", source="desktop")
    cancelled = await adapter.cancel_run(run_id, reason="stop", source="desktop")
    approved = await adapter.resolve_approval_wait(
        run_id,
        approved=True,
        token="approval-1",
        source="desktop",
        reason="continue",
    )

    assert run == {"kind": "run", "run_id": run_id}
    assert interrupted == {"kind": "interrupt", "run_id": run_id, "reason": "pause", "source": "desktop"}
    assert resumed == {
        "kind": "resume",
        "run_id": run_id,
        "resume_token": "approval-1",
        "source": "desktop",
    }
    assert cancelled == {"kind": "cancel", "run_id": run_id, "reason": "stop", "source": "desktop"}
    assert approved == {
        "kind": "approval",
        "run_id": run_id,
        "approved": True,
        "token": "approval-1",
        "source": "desktop",
        "reason": "continue",
    }


@pytest.mark.asyncio
async def test_stage5_session_backed_run_runtime_resume_rejects_recovery_only_runs() -> None:
    class _RuntimeManager:
        async def get_session_detail(self, session_id: str, *, recent_limit: int = 50):
            _ = (session_id, recent_limit)
            return {
                "session_id": "sess-recovery",
                "busy": False,
                "pending_approvals": [],
                "active_surface": "desktop",
                "recovery": {"state": "interrupted", "summary": "resume required"},
            }

    adapter = SessionBackedRunRuntimeAdapter(_RuntimeManager())

    with pytest.raises(LookupError, match="cannot be resumed directly"):
        await adapter.resume_run(build_session_backed_run_id("sess-recovery"))


@pytest.mark.asyncio
async def test_stage3_legacy_session_service_constructor_accepts_runtime_manager_compatibility() -> None:
    runtime_manager = _RuntimeManagerStub()
    service = SessionApplicationService(runtime_manager=runtime_manager)

    listed = await service.list_sessions(
        workspace_dir=Path("D:/workspace/runtime"),
        shared_only=True,
    )
    cancelled = await service.cancel_session(
        "sess-runtime",
        request=MainAgentSessionCancelRequest(reason="stop", surface="desktop"),
    )

    assert listed == [{"workspace_dir": "D:\\workspace\\runtime", "shared_only": True}]
    assert cancelled["kind"] == "cancelled"
    assert service.runtime_manager is runtime_manager
