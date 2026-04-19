from __future__ import annotations

import asyncio

from mini_agent.interfaces.agent import (
    MainAgentRunApprovalRequest,
    MainAgentRunCancelRequest,
    MainAgentRunInterruptRequest,
    MainAgentRunResumeRequest,
)
from mini_agent.transport.remote_run_client import RemoteRunClient


class _DummyGatewayClient:
    async def get_run(self, run_id: str):
        return {
            "run_id": run_id,
            "session_id": "sess-1",
            "status": "paused",
            "phase": "executing_tools",
            "busy": False,
            "waiting_on_approval": True,
            "active_surface": "qq",
            "channel_type": "qq",
            "conversation_id": "group:demo",
            "sender_id": "user-1",
            "running_state": "interrupted",
            "control_mode": "paused",
            "interrupt_requested": False,
            "cancel_requested": False,
            "resumable": True,
            "active_wait_id": "run:sess-1:approval:approval-1",
            "approval_wait": {
                "wait_id": "run:sess-1:approval:approval-1",
                "run_id": run_id,
                "session_id": "sess-1",
                "workspace_id": "ws-default",
                "approval_token": "approval-1",
                "tool_name": "shell",
                "tool_arguments_summary": {"command": "dir"},
                "approval_kind": "tool",
                "policy_reason": "write access",
                "cache_key": "shell:dir",
                "can_escalate": False,
                "wait_state": "pending",
                "decision_result": None,
                "created_at": "2026-04-18T09:00:00+00:00",
                "resolved_at": None,
                "invalidated_reason": None,
            },
            "checkpoint": {
                "checkpoint_id": "snap-run-1",
                "kind": "workspace_runtime_snapshot",
                "source": "persisted_workspace_runtime",
                "created_at": "2026-04-18T09:00:00+00:00",
                "workspace_dir": "D:/workspace/demo",
                "runtime_mode": "direct",
                "access_scope": "workspace_only",
                "mutation_count": 2,
            },
        }

    def get_run_sync(self, run_id: str):
        return asyncio.run(self.get_run(run_id))

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        assert resume_token == "approval-1"
        assert surface == "qq"
        assert channel_type == "qq"
        assert conversation_id == "group:demo"
        assert sender_id == "user-1"
        return await self.get_run(run_id)

    def resume_run_sync(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return asyncio.run(
            self.resume_run(
                run_id,
                resume_token=resume_token,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
        )

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        assert reason == "pause"
        assert surface == "qq"
        assert channel_type == "qq"
        assert conversation_id == "group:demo"
        assert sender_id == "user-1"
        return await self.get_run(run_id)

    def interrupt_run_sync(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return asyncio.run(
            self.interrupt_run(
                run_id,
                reason=reason,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
        )

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        assert reason == "stop"
        assert surface == "qq"
        assert channel_type == "qq"
        assert conversation_id == "group:demo"
        assert sender_id == "user-1"
        return await self.get_run(run_id)

    def cancel_run_sync(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return asyncio.run(
            self.cancel_run(
                run_id,
                reason=reason,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
        )

    async def resolve_run_approval(
        self,
        run_id: str,
        *,
        approved: bool,
        token: str | None = None,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        assert approved is False
        assert token == "approval-1"
        assert reason == "deny"
        assert surface == "qq"
        assert channel_type == "qq"
        assert conversation_id == "group:demo"
        assert sender_id == "user-1"
        return await self.get_run(run_id)

    def resolve_run_approval_sync(
        self,
        run_id: str,
        *,
        approved: bool,
        token: str | None = None,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return asyncio.run(
            self.resolve_run_approval(
                run_id,
                approved=approved,
                token=token,
                reason=reason,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
        )


def test_remote_run_client_shapes_gateway_payloads_into_typed_models() -> None:
    async def _run() -> None:
        service = RemoteRunClient(run_transport=_DummyGatewayClient())

        run = await service.get_run("run:sess-1")
        interrupted = await service.interrupt_run(
            "run:sess-1",
            MainAgentRunInterruptRequest(
                reason="pause",
                surface="qq",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            ),
        )
        resumed = await service.resume_run(
            "run:sess-1",
            MainAgentRunResumeRequest(
                resume_token="approval-1",
                surface="qq",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            ),
        )
        cancelled = await service.cancel_run(
            "run:sess-1",
            MainAgentRunCancelRequest(
                reason="stop",
                surface="qq",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            ),
        )
        denied = await service.respond_to_approval(
            "run:sess-1",
            MainAgentRunApprovalRequest(
                approved=False,
                token="approval-1",
                reason="deny",
                surface="qq",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            ),
        )

        assert run.status == "paused"
        assert run.approval_wait is not None
        assert run.approval_wait.tool_name == "shell"
        assert run.checkpoint is not None
        assert run.checkpoint.checkpoint_id == "snap-run-1"
        assert interrupted.phase == "executing_tools"
        assert resumed.run_id == "run:sess-1"
        assert resumed.resumable is True
        assert cancelled.status == "paused"
        assert denied.waiting_on_approval is True

    asyncio.run(_run())


def test_remote_run_client_sync_helpers_shape_gateway_payloads_into_typed_models() -> None:
    service = RemoteRunClient(run_transport=_DummyGatewayClient())

    run = service.get_run_sync("run:sess-1")
    interrupted = service.interrupt_run_sync(
        "run:sess-1",
        MainAgentRunInterruptRequest(
            reason="pause",
            surface="qq",
            channel_type="qq",
            conversation_id="group:demo",
            sender_id="user-1",
        ),
    )
    resumed = service.resume_run_sync(
        "run:sess-1",
        MainAgentRunResumeRequest(
            resume_token="approval-1",
            surface="qq",
            channel_type="qq",
            conversation_id="group:demo",
            sender_id="user-1",
        ),
    )
    cancelled = service.cancel_run_sync(
        "run:sess-1",
        MainAgentRunCancelRequest(
            reason="stop",
            surface="qq",
            channel_type="qq",
            conversation_id="group:demo",
            sender_id="user-1",
        ),
    )
    denied = service.respond_to_approval_sync(
        "run:sess-1",
        MainAgentRunApprovalRequest(
            approved=False,
            token="approval-1",
            reason="deny",
            surface="qq",
            channel_type="qq",
            conversation_id="group:demo",
            sender_id="user-1",
        ),
    )

    assert run.status == "paused"
    assert run.checkpoint is not None
    assert run.checkpoint.checkpoint_id == "snap-run-1"
    assert interrupted.phase == "executing_tools"
    assert resumed.run_id == "run:sess-1"
    assert cancelled.status == "paused"
    assert denied.waiting_on_approval is True
