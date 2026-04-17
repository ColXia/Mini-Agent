"""Runtime-facing run-control seams for application services."""

from __future__ import annotations

from typing import Any, Protocol


class RunRuntimePort(Protocol):
    """Application-facing contract for active run queries and control."""

    async def get_run(self, run_id: str) -> Any: ...

    async def interrupt_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any: ...

    async def resume_run(
        self,
        run_id: str,
        *,
        resume_token: str | None = None,
        source: str | None = None,
    ) -> Any: ...

    async def cancel_run(
        self,
        run_id: str,
        *,
        reason: str | None = None,
        source: str | None = None,
    ) -> Any: ...

    async def resolve_approval_wait(
        self,
        run_id: str,
        *,
        approved: bool,
        token: str | None = None,
        source: str | None = None,
        reason: str | None = None,
    ) -> Any: ...


__all__ = ["RunRuntimePort"]
