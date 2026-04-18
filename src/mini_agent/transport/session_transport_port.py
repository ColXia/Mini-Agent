"""Transport-facing contract for remote session client operations."""

from __future__ import annotations

from typing import Any, Protocol


class RemoteSessionTransportPort(Protocol):
    """Transport contract consumed by `RemoteSessionClient`."""

    async def list_sessions(
        self,
        *,
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> list[dict[str, Any]]: ...

    def list_sessions_sync(
        self,
        *,
        workspace_dir: str | None = None,
        shared_only: bool = False,
    ) -> list[dict[str, Any]]: ...

    async def ensure_default_session(
        self,
        *,
        workspace_dir: str,
        surface: str = "tui",
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

    def ensure_default_session_sync(
        self,
        *,
        workspace_dir: str,
        surface: str = "tui",
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def get_session_detail(self, session_id: str, *, recent_limit: int = 80) -> dict[str, Any]: ...

    def get_session_detail_sync(self, session_id: str, *, recent_limit: int = 80) -> dict[str, Any]: ...

    async def get_session_messages(self, session_id: str, *, limit: int = 10) -> list[dict[str, Any]]: ...

    async def create_session(
        self,
        *,
        workspace_dir: str,
        title: str | None = None,
        surface: str = "tui",
        shared: bool = False,
    ) -> dict[str, Any]: ...

    def create_session_sync(
        self,
        *,
        workspace_dir: str,
        title: str | None = None,
        surface: str = "tui",
        shared: bool = False,
    ) -> dict[str, Any]: ...

    async def create_derived_session(
        self,
        parent_session_id: str,
        *,
        title: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

    def create_derived_session_sync(
        self,
        parent_session_id: str,
        *,
        title: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def rename_session(self, session_id: str, *, title: str) -> dict[str, Any]: ...

    def rename_session_sync(self, session_id: str, *, title: str) -> dict[str, Any]: ...

    async def set_session_shared(self, session_id: str, *, shared: bool) -> dict[str, Any]: ...

    def set_session_shared_sync(self, session_id: str, *, shared: bool) -> dict[str, Any]: ...

    async def reset_session(self, session_id: str) -> dict[str, Any]: ...

    async def delete_session(self, session_id: str) -> dict[str, Any]: ...

    async def cancel_session(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def interrupt_session(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...

    def control_session_sync(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...

    async def manage_session_skill(
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
    ) -> dict[str, Any]: ...

    async def update_session_model(
        self,
        session_id: str,
        *,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

    def update_session_model_sync(
        self,
        session_id: str,
        *,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...

    def respond_to_approval_sync(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...


__all__ = ["RemoteSessionTransportPort"]
