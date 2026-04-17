"""Application-layer request adapters for interaction-bound chat flows."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from mini_agent.interaction import resolve_interaction_binding
from mini_agent.interfaces import ChannelMessageRequest, MainAgentChatRequest

if TYPE_CHECKING:
    from ..surface_chat_flow_handler import SurfaceChatExecutionRequest


@dataclass(frozen=True)
class ApplicationInteractionBinding:
    """Normalized interaction binding shared by application-layer chat entrances."""

    surface: str | None = None
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    entrance: str | None = None
    remote_channel: str | None = None

    @classmethod
    def from_values(
        cls,
        *,
        surface: str | None,
        channel_type: str | None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        default_surface: str | None = None,
    ) -> "ApplicationInteractionBinding":
        binding = resolve_interaction_binding(
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            default_surface=default_surface,
        )
        return cls(
            surface=binding.surface,
            channel_type=binding.channel_type,
            conversation_id=binding.conversation_id,
            sender_id=binding.sender_id,
            entrance=binding.entrance,
            remote_channel=binding.remote_channel,
        )

    @classmethod
    def from_request(
        cls,
        request: Any,
        *,
        default_surface: str | None = None,
    ) -> "ApplicationInteractionBinding":
        return cls.from_values(
            surface=getattr(request, "surface", None),
            channel_type=getattr(request, "channel_type", None),
            conversation_id=getattr(request, "conversation_id", None),
            sender_id=getattr(request, "sender_id", None),
            default_surface=default_surface,
        )

    @classmethod
    def from_main_agent_chat_request(cls, request: MainAgentChatRequest) -> "ApplicationInteractionBinding":
        return cls.from_request(request, default_surface="api")

    @classmethod
    def from_channel_message_request(cls, request: ChannelMessageRequest) -> "ApplicationInteractionBinding":
        return cls.from_values(
            surface=request.channel_type,
            channel_type=request.channel_type,
            conversation_id=request.conversation_id,
            sender_id=request.sender_id,
        )

    def as_kwargs(self) -> dict[str, str | None]:
        return {
            "surface": self.surface,
            "channel_type": self.channel_type,
            "conversation_id": self.conversation_id,
            "sender_id": self.sender_id,
        }

    @property
    def remote_binding_key(self) -> str | None:
        if self.entrance != "remote" or not self.channel_type or not self.conversation_id:
            return None
        return f"{self.channel_type}|{self.conversation_id}"

    def to_main_agent_chat_request(
        self,
        *,
        message: str,
        session_id: str | None = None,
        session_title_hint: str | None = None,
        workspace_dir: str | None = None,
        dry_run: bool = False,
    ) -> MainAgentChatRequest:
        return MainAgentChatRequest(
            message=message,
            session_id=session_id,
            session_title_hint=session_title_hint,
            workspace_dir=workspace_dir,
            dry_run=bool(dry_run),
            surface=self.surface or "api",
            channel_type=self.channel_type,
            conversation_id=self.conversation_id,
            sender_id=self.sender_id,
        )

    def to_surface_chat_execution_request(
        self,
        *,
        message: str,
        workspace_dir: Path,
        session_id: str | None = None,
        session_title_hint: str | None = None,
        dry_run: bool = False,
        running_detail: str = "",
    ) -> "SurfaceChatExecutionRequest":
        from ..surface_chat_flow_handler import SurfaceChatExecutionRequest

        return SurfaceChatExecutionRequest(
            message=message,
            workspace_dir=workspace_dir,
            session_id=session_id,
            session_title_hint=session_title_hint,
            surface=self.surface,
            channel_type=self.channel_type,
            conversation_id=self.conversation_id,
            sender_id=self.sender_id,
            dry_run=bool(dry_run),
            running_detail=running_detail,
        )


__all__ = ["ApplicationInteractionBinding"]
