from __future__ import annotations

import asyncio

from mini_agent.application.session_remote_service import RemoteSessionService
from mini_agent.interfaces import (
    MainAgentSessionApprovalRequest,
    MainAgentSessionContextRequest,
    MainAgentSessionControlRequest,
    MainAgentSessionForkRequest,
    MainAgentSessionModelSelectionRequest,
)


class _DummyGatewayClient:
    async def list_sessions(self, *, workspace_dir: str | None = None, shared_only: bool = False):
        return [
            {
                "session_id": "sess-1",
                "workspace_dir": workspace_dir or ".",
                "created_at": "2026-04-12T08:00:00+00:00",
                "updated_at": "2026-04-12T08:00:01+00:00",
                "title": "nyonyo",
                "message_count": 3,
                "origin_surface": "qq",
                "active_surface": "qq",
                "reply_enabled": True,
                "busy": False,
                "shared": True,
                "knowledge_base_enabled": True,
            }
        ]

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 80):
        return {
            "session_id": session_id,
            "workspace_dir": ".",
            "created_at": "2026-04-12T08:00:00+00:00",
            "updated_at": "2026-04-12T08:00:01+00:00",
            "message_count": 1,
            "origin_surface": "qq",
            "active_surface": "qq",
            "reply_enabled": True,
            "busy": False,
            "shared": True,
            "knowledge_base_enabled": True,
            "recent_messages": [
                {
                    "index": 1,
                    "role": "user",
                    "content": "hello",
                    "surface": "qq",
                    "created_at": "2026-04-12T08:00:01+00:00",
                }
            ],
        }

    async def control_session(
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
            "status": "controlled",
            "session_id": session_id,
            "action": action,
            "applied": True,
            "active_surface": surface or "tui",
            "reason": reason,
            "message_count_before": 10,
            "message_count_after": 6,
            "token_count_before": 1000,
            "token_count_after": 600,
            "stats": {
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
            },
        }

    async def update_session_context(
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
            "status": "ok",
            "session_id": session_id,
            "action": action,
            "active_surface": surface or "tui",
            "context_policy": {
                "sources": sources or [],
                "max_items": max_items,
                "max_total_chars": max_total_chars,
                "max_items_per_source": max_items_per_source,
                "channel_type": channel_type,
                "conversation_id": conversation_id,
                "sender_id": sender_id,
            },
        }

    async def update_session_model(
        self,
        session_id: str,
        *,
        provider_source: str | None,
        provider_id: str,
        model_id: str,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return {
            "status": "ok",
            "session_id": session_id,
            "active_surface": surface or "tui",
            "applied": True,
            "queued": False,
            "selected_model_source": provider_source,
            "selected_provider_id": provider_id,
            "selected_model_id": model_id,
            "pending_model_source": None,
            "pending_provider_id": None,
            "pending_model_id": None,
            "channel_type": channel_type,
            "conversation_id": conversation_id,
            "sender_id": sender_id,
        }

    async def respond_to_approval(
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
        return {
            "status": "ok",
            "session_id": session_id,
            "token": token or "tok-1",
            "tool_name": "shell",
            "decision": "approved" if approved else "denied",
            "active_surface": surface or "tui",
            "channel_type": channel_type,
            "conversation_id": conversation_id,
            "sender_id": sender_id,
        }

    async def create_derived_session(
        self,
        parent_session_id: str,
        *,
        title: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        return {
            "session_id": f"{parent_session_id}:child",
            "workspace_dir": ".",
            "created_at": "2026-04-12T08:00:00+00:00",
            "updated_at": "2026-04-12T08:00:01+00:00",
            "title": title,
            "message_count": 0,
            "origin_surface": surface or "tui",
            "active_surface": surface or "tui",
            "channel_type": channel_type,
            "conversation_id": conversation_id,
            "sender_id": sender_id,
            "shared": False,
            "knowledge_base_enabled": True,
            "recent_messages": [],
        }


def test_remote_session_service_shapes_gateway_payloads_into_typed_models() -> None:
    async def _run() -> None:
        service = RemoteSessionService(gateway_client=_DummyGatewayClient())

        listed = await service.list_sessions(workspace_dir="D:/file/Mini-Agent")
        detail = await service.get_session_detail("sess-1", recent_limit=20)
        controlled = await service.control_session(
            "sess-1",
            MainAgentSessionControlRequest(
                action="compact",
                reason="trim history",
                surface="tui",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            ),
        )
        context = await service.update_session_context(
            "sess-1",
            MainAgentSessionContextRequest(
                action="configure",
                sources=["memory", "workspace"],
                max_items=6,
                max_total_chars=2400,
                max_items_per_source=3,
                surface="tui",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            ),
        )
        model = await service.update_session_model(
            "sess-1",
            MainAgentSessionModelSelectionRequest(
                provider_source="custom",
                provider_id="maas",
                model_id="astron-code-latest",
                surface="tui",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            ),
        )
        approval = await service.respond_to_approval(
            "sess-1",
            MainAgentSessionApprovalRequest(
                approved=True,
                token="tok-1",
                surface="tui",
                channel_type="qq",
                conversation_id="group:demo",
                sender_id="user-1",
            ),
        )

        assert listed[0].title == "nyonyo"
        assert detail.recent_messages[0].content == "hello"
        assert controlled.applied is True
        assert controlled.stats["conversation_id"] == "group:demo"
        assert context.context_policy["max_items"] == 6
        assert model.selected_provider_id == "maas"
        assert approval.decision == "approved"

    asyncio.run(_run())


def test_remote_session_service_derived_session_prefers_remote_channel_when_surface_missing() -> None:
    async def _run() -> None:
        service = RemoteSessionService(gateway_client=_DummyGatewayClient())

        detail = await service.create_derived_session(
            "sess-1",
            MainAgentSessionForkRequest(
                title="remote fork",
                channel_type="qqbot",
                conversation_id="group:demo",
                sender_id="user-1",
            ),
        )

        assert detail.origin_surface == "qq"
        assert detail.active_surface == "qq"
        assert detail.channel_type == "qq"
        assert detail.conversation_id == "group:demo"
        assert detail.sender_id == "user-1"

    asyncio.run(_run())
