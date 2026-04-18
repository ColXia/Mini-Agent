"""Transport-facing contract for remote run client operations."""

from __future__ import annotations

from typing import Any, Protocol


class RemoteRunTransportPort(Protocol):
    """Transport contract consumed by `RemoteRunClient`."""

    async def get_run(self, run_id: str) -> dict[str, Any]: ...

    def get_run_sync(self, run_id: str) -> dict[str, Any]: ...

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

    def interrupt_run_sync(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

    def resume_run_sync(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

    def cancel_run_sync(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...

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
    ) -> dict[str, Any]: ...


__all__ = ["RemoteRunTransportPort"]
