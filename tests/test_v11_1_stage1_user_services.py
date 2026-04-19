from __future__ import annotations

import pytest

from mini_agent.application.ports import (
    AgentRuntimePort,
    ModelRuntimePort,
    RunRuntimePort,
    SessionAgentRuntimePort,
    SessionTaskPort,
    SessionTaskRuntimePort,
    WorkspaceRuntimePort,
)
from mini_agent.application.use_cases import (
    AgentApplicationService,
    CommandApplicationService,
    ModelBindingApplicationService,
    RunControlApplicationService,
    WorkspaceApplicationService,
)
from mini_agent.application.user_services import (
    AgentUserService,
    CommandUserService,
    ModelUserService,
    WorkspaceUserService,
)
from mini_agent.interfaces import MainAgentChatRequest


class RunRuntimeStub:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []

    async def get_run(self, run_id: str):
        self.calls.append(("get_run", run_id))
        return {"run_id": run_id}

    async def interrupt_run(self, run_id: str, *, reason: str | None = None, source: str | None = None):
        self.calls.append(("interrupt_run", run_id, reason, source))
        return {"kind": "interrupt", "run_id": run_id}

    async def resume_run(self, run_id: str, *, resume_token: str | None = None, source: str | None = None):
        self.calls.append(("resume_run", run_id, resume_token, source))
        return {"kind": "resume", "run_id": run_id, "resume_token": resume_token}

    async def cancel_run(self, run_id: str, *, reason: str | None = None, source: str | None = None):
        self.calls.append(("cancel_run", run_id, reason, source))
        return {"kind": "cancel", "run_id": run_id}

    async def resolve_approval_wait(
        self,
        run_id: str,
        *,
        approved: bool,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ):
        self.calls.append(("resolve_approval_wait", run_id, approved, token, source, reason))
        return {"kind": "approval", "run_id": run_id, "approved": approved, "token": token}


class SessionTaskStub:
    def __init__(self, run_ids: dict[str, str] | None = None) -> None:
        self.run_ids = dict(run_ids or {})
        self.calls: list[tuple[str, object]] = []

    async def get_session_task(self, session_id: str):
        self.calls.append(("get_session_task", session_id))
        return {"session_id": session_id}

    async def resolve_run_id_for_session(self, session_id: str) -> str | None:
        self.calls.append(("resolve_run_id_for_session", session_id))
        return self.run_ids.get(session_id)

    async def cancel_session_turn(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        self.calls.append(("cancel_session_turn", session_id, reason, surface, channel_type, conversation_id, sender_id))
        return {"kind": "session-cancel", "session_id": session_id}

    async def resolve_pending_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        self.calls.append(
            ("resolve_pending_approval", session_id, approved, token, surface, channel_type, conversation_id, sender_id)
        )
        return {"kind": "session-approval", "session_id": session_id, "approved": approved, "token": token}


class AgentRuntimeStub:
    async def list_agents(self):
        return [{"agent_id": "agent-1"}]

    async def get_agent(self, agent_id: str):
        return {"agent_id": agent_id}

    async def get_active_agent(self):
        return {"agent_id": "agent-1", "active": True}


class WorkspaceRuntimeStub:
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


class ModelRuntimeStub:
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


class SessionRuntimePolicyRuntimeStub:
    async def update_session_runtime_policy(
        self,
        session_id: str,
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return {
            "session_id": session_id,
            "approval_profile": approval_profile,
            "access_level": access_level,
            "surface": surface,
            "channel_type": channel_type,
            "conversation_id": conversation_id,
            "sender_id": sender_id,
        }


class SessionControlRuntimeStub:
    async def control_session_context(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return {
            "session_id": session_id,
            "action": action,
            "reason": reason,
            "surface": surface,
            "channel_type": channel_type,
            "conversation_id": conversation_id,
            "sender_id": sender_id,
        }


class SessionContextRuntimeStub:
    async def update_session_context_policy(
        self,
        session_id: str,
        *,
        action: str,
        sources: list[str] | None = None,
        max_items: int | None = None,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return {
            "session_id": session_id,
            "action": action,
            "sources": sources,
            "max_items": max_items,
            "max_total_chars": max_total_chars,
            "max_items_per_source": max_items_per_source,
            "surface": surface,
            "channel_type": channel_type,
            "conversation_id": conversation_id,
            "sender_id": sender_id,
        }


class SessionMemoryRuntimeStub:
    async def manage_session_memory(
        self,
        session_id: str,
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return {
            "session_id": session_id,
            "action": action,
            "engram_id": engram_id,
            "content": content,
            "query": query,
            "day": day,
            "export_format": export_format,
            "detail_mode": detail_mode,
            "surface": surface,
            "channel_type": channel_type,
            "conversation_id": conversation_id,
            "sender_id": sender_id,
        }


class SessionSkillRuntimeStub:
    async def manage_session_skills(
        self,
        session_id: str,
        *,
        action: str,
        skill_name: str | None = None,
        path: str | None = None,
        query: str | None = None,
        mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return {
            "session_id": session_id,
            "action": action,
            "skill_name": skill_name,
            "path": path,
            "query": query,
            "mode": mode,
            "surface": surface,
            "channel_type": channel_type,
            "conversation_id": conversation_id,
            "sender_id": sender_id,
        }


class CommandRuntimeStub:
    def catalog(self):
        return ["help", "session"]

    def describe(self, command_name: str):
        return {"command": command_name, "description": "stub"}

    def complete(self, prefix: str):
        return [prefix + "pletion"]

    def execute_command(self, raw_command: str, **kwargs):
        return {"command": raw_command, "kwargs": kwargs}


def test_stage1_port_packages_export_expected_contracts() -> None:
    assert AgentRuntimePort is not None
    assert ModelRuntimePort is not None
    assert RunRuntimePort is not None
    assert SessionAgentRuntimePort is not None
    assert SessionTaskRuntimePort is not None
    assert SessionTaskPort is not None
    assert WorkspaceRuntimePort is not None


@pytest.mark.asyncio
async def test_run_control_application_service_prefers_run_runtime_when_run_is_attached() -> None:
    run_runtime = RunRuntimeStub()
    session_tasks = SessionTaskStub({"session-1": "run-1"})
    service = RunControlApplicationService(run_runtime=run_runtime, session_tasks=session_tasks)

    result = await service.approve_session_wait(
        "session-1",
        token="approval-1",
        source="desktop",
        reason="user approved",
    )

    assert result == {"kind": "approval", "run_id": "run-1", "approved": True, "token": "approval-1"}
    assert ("resolve_run_id_for_session", "session-1") in session_tasks.calls
    assert (
        "resolve_approval_wait",
        "run-1",
        True,
        "approval-1",
        "desktop",
        "user approved",
    ) in run_runtime.calls


@pytest.mark.asyncio
async def test_run_control_application_service_requires_run_attachment_for_session_control() -> None:
    run_runtime = RunRuntimeStub()
    session_tasks = SessionTaskStub()
    service = RunControlApplicationService(run_runtime=run_runtime, session_tasks=session_tasks)

    with pytest.raises(LookupError, match="not attached to a run"):
        await service.cancel_session_run(
            "session-2",
            reason="stop",
            surface="desktop",
            channel_type="desktop",
        )

    with pytest.raises(LookupError, match="not attached to a run"):
        await service.deny_session_wait(
            "session-2",
            token="approval-2",
            surface="desktop",
        )

    assert not [call for call in run_runtime.calls if call[0] == "cancel_run"]


@pytest.mark.asyncio
async def test_stage1_user_services_delegate_to_runtime_ports() -> None:
    run_control = RunControlApplicationService(
        run_runtime=RunRuntimeStub(),
        session_tasks=SessionTaskStub({"session-1": "run-1"}),
    )
    agent_service = AgentUserService(agent_runtime=AgentRuntimeStub(), run_control=run_control)
    workspace_service = WorkspaceUserService(workspace_runtime=WorkspaceRuntimeStub())
    model_service = ModelUserService(model_runtime=ModelRuntimeStub())
    command_service = CommandUserService(command_runtime=CommandRuntimeStub())

    assert await agent_service.list_agents() == [{"agent_id": "agent-1"}]
    assert await agent_service.get_active_agent() == {"agent_id": "agent-1", "active": True}
    assert await workspace_service.switch_workspace("ws-2") == {"workspace_id": "ws-2", "switched": True}
    assert await model_service.list_model_candidates() == [{"model_id": "model-1"}]
    assert await model_service.get_current_model_binding("agent-1") == {
        "agent_id": "agent-1",
        "model_id": "model-1",
    }
    assert await model_service.set_agent_model_binding(
        agent_id="agent-1",
        provider_source="preset",
        provider_id="openai",
        model_id="gpt-5.4",
    ) == {
        "agent_id": "agent-1",
        "provider_source": "preset",
        "provider_id": "openai",
        "model_id": "gpt-5.4",
    }
    assert await command_service.dispatch_command("/help", surface="desktop") == {
        "command": "/help",
        "kwargs": {"surface": "desktop"},
    }


@pytest.mark.asyncio
async def test_stage1_user_services_support_session_scoped_runtime_actions() -> None:
    agent_service = AgentUserService(session_agent_runtime=SessionRuntimePolicyRuntimeStub())

    policy_response = await agent_service.update_session_runtime_policy(
        "session-4",
        approval_profile="plan",
        access_level="full-access",
        surface="desktop",
    )

    assert policy_response["approval_profile"] == "plan"


@pytest.mark.asyncio
async def test_stage1_agent_user_service_supports_session_control_memory_and_skill_actions() -> None:
    control_service = AgentUserService(session_agent_runtime=SessionControlRuntimeStub())
    context_service = AgentUserService(session_agent_runtime=SessionContextRuntimeStub())
    memory_service = AgentUserService(session_agent_runtime=SessionMemoryRuntimeStub())
    skill_service = AgentUserService(session_agent_runtime=SessionSkillRuntimeStub())

    controlled = await control_service.control_session(
        "session-4b",
        action="compact",
        reason="trim",
        surface="desktop",
    )
    contextual = await context_service.update_session_context(
        "session-4c",
        action="include",
        sources=["workspace_memory"],
        max_items=2,
        surface="desktop",
    )
    memory = await memory_service.manage_session_memory(
        "session-5",
        action="show",
        query="recent",
        detail_mode="brief",
        surface="desktop",
    )
    skill = await skill_service.manage_session_skills(
        "session-6",
        action="search",
        query="foundry",
        mode="allowlist",
        surface="desktop",
    )

    assert controlled["action"] == "compact"
    assert contextual["sources"] == ["workspace_memory"]
    assert memory["query"] == "recent"
    assert skill["query"] == "foundry"


@pytest.mark.asyncio
async def test_stage1_application_services_delegate_to_runtime_ports() -> None:
    run_control = RunControlApplicationService(
        run_runtime=RunRuntimeStub(),
        session_tasks=SessionTaskStub({"session-1": "run-1"}),
    )
    agent_application = AgentApplicationService(
        agent_runtime=AgentRuntimeStub(),
        run_control=run_control,
        session_agent_runtime=SessionControlRuntimeStub(),
    )
    workspace_application = WorkspaceApplicationService(workspace_runtime=WorkspaceRuntimeStub())
    model_application = ModelBindingApplicationService(model_runtime=ModelRuntimeStub())
    command_application = CommandApplicationService(command_runtime=CommandRuntimeStub())

    assert await agent_application.get_active_agent() == {"agent_id": "agent-1", "active": True}
    assert await workspace_application.get_active_workspace() == {"workspace_id": "ws-1", "active": True}
    assert await model_application.list_model_candidates() == [{"model_id": "model-1"}]
    assert await model_application.get_current_model_capabilities("agent-1") == {
        "agent_id": "agent-1",
        "supports_tools": True,
    }
    assert await command_application.complete_command("he") == ["hepletion"]


@pytest.mark.asyncio
async def test_stage1_user_services_can_delegate_to_injected_application_services() -> None:
    class _AgentAppStub:
        async def get_active_agent(self):
            return {"agent_id": "agent-app"}

    class _WorkspaceAppStub:
        async def switch_workspace(self, workspace_id: str):
            return {"workspace_id": workspace_id, "source": "workspace-app"}

    class _ModelAppStub:
        async def list_model_bindings(self):
            return [{"model_id": "from-app"}]

    class _CommandAppStub:
        async def dispatch_command(self, raw_command: str, **kwargs):
            return {"command": raw_command, "kwargs": kwargs, "source": "command-app"}

    agent_service = AgentUserService(application_service=_AgentAppStub())
    workspace_service = WorkspaceUserService(application_service=_WorkspaceAppStub())
    model_service = ModelUserService(application_service=_ModelAppStub())
    command_service = CommandUserService(application_service=_CommandAppStub())

    assert await agent_service.get_active_agent() == {"agent_id": "agent-app"}
    assert await workspace_service.switch_workspace("ws-2") == {
        "workspace_id": "ws-2",
        "source": "workspace-app",
    }
    assert await model_service.list_model_bindings() == [{"model_id": "from-app"}]
    assert await command_service.dispatch_command("/help", surface="desktop") == {
        "command": "/help",
        "kwargs": {"surface": "desktop"},
        "source": "command-app",
    }


@pytest.mark.asyncio
async def test_stage1_agent_user_service_exposes_interaction_entrypoints() -> None:
    class _InteractionStub:
        async def submit_message(self, request: MainAgentChatRequest):
            return {"kind": "chat", "message": request.message, "surface": request.surface}

        async def get_routing_diagnostics(self):
            return {"kind": "routing", "total_resolutions": 3}

        def stream_message(self, **kwargs):
            async def _stream():
                yield f"event: session data={kwargs['message']}"
                yield "event: done"

            return _stream()

    agent_service = AgentUserService(interaction_service=_InteractionStub())

    reply = await agent_service.submit_message(
        MainAgentChatRequest(message="hello", workspace_dir=".", surface="desktop")
    )
    diagnostics = await agent_service.get_routing_diagnostics()
    streamed = [item async for item in agent_service.stream_message(message="stream hello", workspace_dir=".")]

    assert reply == {"kind": "chat", "message": "hello", "surface": "desktop"}
    assert diagnostics == {"kind": "routing", "total_resolutions": 3}
    assert streamed == ["event: session data=stream hello", "event: done"]
