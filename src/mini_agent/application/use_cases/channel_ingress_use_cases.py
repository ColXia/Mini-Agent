"""Application-layer use cases for channel ingress orchestration."""

from __future__ import annotations

from typing import Awaitable, Callable

from mini_agent.application.support.interaction_request_adapter import ApplicationInteractionBinding
from mini_agent.interfaces.agent import MainAgentChatRequest, MainAgentChatResponse
from mini_agent.interfaces.channel import ChannelMessageRequest, ChannelMessageResponse
from mini_agent.session.bindings import ConversationBindingPort


RunMainAgentChatFn = Callable[[MainAgentChatRequest], Awaitable[MainAgentChatResponse]]


class ChannelIngressUseCases:
    """Channel ingress orchestration for remote conversation surfaces."""

    def __init__(
        self,
        *,
        run_main_agent_chat: RunMainAgentChatFn,
        conversation_binding: ConversationBindingPort,
    ) -> None:
        self._run_main_agent_chat = run_main_agent_chat
        self._conversation_binding = conversation_binding

    async def handle_message(self, request: ChannelMessageRequest) -> ChannelMessageResponse:
        binding = ApplicationInteractionBinding.from_channel_message_request(request)
        resolved_session_id = self._conversation_binding.resolve_session_id(
            surface=binding.surface,
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
            explicit_session_id=request.session_id,
            dry_run=bool(request.dry_run),
        )
        chat_response = await self._run_main_agent_chat(
            binding.to_main_agent_chat_request(
                message=request.message,
                session_id=resolved_session_id,
                workspace_dir=request.workspace_dir,
                dry_run=request.dry_run,
            )
        )
        self._conversation_binding.persist_binding(
            surface=binding.surface,
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
            session_id=chat_response.session_id,
            workspace_dir=chat_response.workspace_dir,
            dry_run=bool(request.dry_run),
        )
        return ChannelMessageResponse(
            session_id=chat_response.session_id,
            reply=chat_response.reply,
            message_count=chat_response.message_count,
            token_usage=chat_response.token_usage,
            workspace_dir=chat_response.workspace_dir,
            updated_at=chat_response.updated_at,
        )


__all__ = ["ChannelIngressUseCases"]
