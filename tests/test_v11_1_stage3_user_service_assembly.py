from __future__ import annotations

from pathlib import Path

import pytest

import mini_agent.application as application_module
from mini_agent.application import (
    RuntimeBackedUserServicePorts,
    UserServiceAssembly,
    assemble_typed_user_services,
    resolve_runtime_backed_user_service_ports,
)
from mini_agent.application.user_services import (
    AgentUserService,
    CommandUserService,
    ModelUserService,
    WorkspaceUserService,
)
from mini_agent.application.user_services.service_assembly import assemble_runtime_backed_user_services
from mini_agent.application.user_services.session_runtime_compat_adapters import SessionBackedRunRuntimeAdapter
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


class _ModelRuntimeStub:
    async def list_model_bindings(self):
        return [{"model_id": "model-1"}]

    async def get_model_binding(self, agent_id: str | None = None):
        return {"agent_id": agent_id, "model_id": "model-1"}

    async def update_model_binding(
        self,
        *,
        agent_id: str | None = None,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
    ):
        return {
            "agent_id": agent_id,
            "provider_source": provider_source,
            "provider_id": provider_id,
            "model_id": model_id,
        }

    async def list_model_capabilities(self, agent_id: str | None = None):
        return {"agent_id": agent_id, "supports_tools": True}

    async def get_model_binding_diagnostics(self, agent_id: str | None = None):
        return {"agent_id": agent_id, "current_binding": {"agent_id": agent_id, "model_id": "model-1"}}


class _CommandRuntimeStub:
    def execute_command(self, raw_command: str, **kwargs):
        return {"command": raw_command, "kwargs": kwargs}


class _RuntimeManagerStub(_SessionTaskRuntimeStub):
    async def get_session_task(self, session_id: str):
        return {"kind": "task", "session_id": session_id}

    async def resolve_run_id_for_session(self, session_id: str) -> str | None:
        return build_session_backed_run_id(session_id)

    async def get_run(self, run_id: str):
        return {
            "kind": "run",
            "run_id": run_id,
            "status": "waiting",
            "phase": "awaiting_approval",
        }

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

    async def cancel_session_turn(self, session_id: str, **kwargs):
        return {"kind": "cancelled", "session_id": session_id, "kwargs": kwargs}

    async def resolve_pending_approval(self, session_id: str, **kwargs):
        return {"kind": "approval", "session_id": session_id, "kwargs": kwargs}

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


def test_stage3_root_application_exposes_only_active_user_service_assembly_symbols() -> None:
    assert RuntimeBackedUserServicePorts is not None
    assert UserServiceAssembly is not None
    assert assemble_typed_user_services is not None
    assert resolve_runtime_backed_user_service_ports is not None
    assert not hasattr(application_module, "SessionApplicationService")
    assert not hasattr(application_module, "assemble_runtime_backed_user_services")


@pytest.mark.asyncio
async def test_stage3_typed_user_service_assembly_builds_explicit_user_services() -> None:
    assembly = assemble_typed_user_services(
        session_task_runtime=_SessionTaskRuntimeStub(),
        session_task_port=_SessionTaskPortStub(),
        session_agent_runtime=_SessionAgentRuntimeStub(),
        model_runtime=_ModelRuntimeStub(),
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
    model = await assembly.model_service.set_agent_model_binding(
        agent_id="main-agent",
        provider_source="preset",
        provider_id="openai",
        model_id="gpt-5.4",
    )
    command = await assembly.command_service.dispatch_command("/help", surface="desktop")  # type: ignore[union-attr]

    assert listed == [{"workspace_dir": "D:\\workspace\\demo", "shared_only": True}]
    assert policy["kind"] == "policy"
    assert switched == {"workspace_id": "ws-2", "switched": True}
    assert model["model_id"] == "gpt-5.4"
    assert command == {"command": "/help", "kwargs": {"surface": "desktop"}}


@pytest.mark.asyncio
async def test_stage3_runtime_backed_user_service_assembly_wraps_runtime_with_explicit_services() -> None:
    runtime_manager = _RuntimeManagerStub()
    assembly = assemble_runtime_backed_user_services(runtime_manager=runtime_manager)

    assert isinstance(assembly, UserServiceAssembly)
    assert assembly.workspace_service is None
    assert assembly.command_service is None
    assert assembly.agent_service.session_agent_runtime is runtime_manager
    assert assembly.model_service.model_runtime is None

    listed = await assembly.session_task_service.list_sessions(
        workspace_dir=Path("D:/workspace/runtime"),
        shared_only=False,
    )
    cancelled = await assembly.run_control_service.cancel_session_run(
        "sess-runtime",
        reason="stop",
        surface="desktop",
    )

    assert listed == [{"workspace_dir": "D:\\workspace\\runtime", "shared_only": False}]
    assert cancelled["kind"] == "cancel"


@pytest.mark.asyncio
async def test_stage4_session_task_service_absorbs_session_scoped_actions() -> None:
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
    assert policy["kind"] == "policy"


@pytest.mark.asyncio
async def test_stage5_runtime_backed_user_service_ports_accept_narrow_structural_support_owner() -> None:
    class _RuntimeBackedSupportStub:
        async def get_session_task(self, session_id: str):
            return {"kind": "task", "session_id": session_id}

        async def resolve_run_id_for_session(self, session_id: str) -> str | None:
            return build_session_backed_run_id(session_id)

        async def get_run(self, run_id: str):
            return {"kind": "run", "run_id": run_id, "status": "completed", "phase": "terminal"}

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

        async def cancel_session_turn(self, session_id: str, **kwargs):
            return {"kind": "cancelled", "session_id": session_id, "kwargs": kwargs}

        async def resolve_pending_approval(self, session_id: str, **kwargs):
            return {"kind": "approval", "session_id": session_id, "kwargs": kwargs}

    ports = resolve_runtime_backed_user_service_ports(runtime_manager=_RuntimeBackedSupportStub())
    task = await ports.session_task_port.get_session_task("sess-structural")
    run = await ports.run_runtime.get_run(build_session_backed_run_id("sess-structural"))

    assert task == {"kind": "task", "session_id": "sess-structural"}
    assert run["run_id"] == build_session_backed_run_id("sess-structural")
    assert run["status"] == "completed"


def test_stage5_runtime_backed_user_service_ports_prefer_direct_runtime_owners() -> None:
    runtime_manager = _RuntimeManagerStub()
    ports = resolve_runtime_backed_user_service_ports(runtime_manager=runtime_manager)

    assert isinstance(ports, RuntimeBackedUserServicePorts)
    assert ports.session_task_runtime is runtime_manager
    assert ports.session_task_port is runtime_manager
    assert ports.session_agent_runtime is runtime_manager
    assert ports.run_runtime is runtime_manager


@pytest.mark.asyncio
async def test_stage5_runtime_backed_user_service_ports_attach_direct_run_runtime() -> None:
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

    assert run["status"] == "waiting"
    assert interrupted["kind"] == "interrupt"
    assert cancelled["kind"] == "cancel"
    assert resumed["kind"] == "resume"
    assert approved["kind"] == "approval"


@pytest.mark.asyncio
async def test_stage5_session_backed_run_runtime_requires_direct_get_run_support() -> None:
    class _RuntimeManager:
        async def get_session_detail(self, session_id: str, *, recent_limit: int = 50):
            _ = (session_id, recent_limit)
            return {"session_id": session_id}

    adapter = SessionBackedRunRuntimeAdapter(_RuntimeManager())

    with pytest.raises(LookupError, match="get_run"):
        await adapter.get_run(build_session_backed_run_id("sess-interrupt"))


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
    assert interrupted["kind"] == "interrupt"
    assert resumed["kind"] == "resume"
    assert cancelled["kind"] == "cancel"
    assert approved["kind"] == "approval"


def test_stage5_runtime_backed_user_service_ports_require_direct_run_runtime_support() -> None:
    class _RuntimeManager:
        async def get_session_task(self, session_id: str):
            return {"kind": "task", "session_id": session_id}

        async def resolve_run_id_for_session(self, session_id: str) -> str | None:
            return build_session_backed_run_id(session_id)

        async def cancel_session_turn(self, session_id: str, **kwargs):
            return {"kind": "cancelled", "session_id": session_id, "kwargs": kwargs}

        async def resolve_pending_approval(self, session_id: str, **kwargs):
            return {"kind": "approval", "session_id": session_id, "kwargs": kwargs}

    with pytest.raises(RuntimeError, match="direct run-runtime methods"):
        resolve_runtime_backed_user_service_ports(runtime_manager=_RuntimeManager())


def test_stage5_runtime_backed_user_service_ports_require_direct_session_task_support() -> None:
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

    with pytest.raises(RuntimeError, match="direct session-task methods"):
        resolve_runtime_backed_user_service_ports(runtime_manager=_RuntimeManager())
