"""Isolated run executor skeleton for scheduled agent tasks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class IsolatedRunRequest:
    """One scheduled run request."""

    job_id: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    tool_allowlist: tuple[str, ...] = ()
    model_override: str | None = None
    timeout_seconds: int = 300


@dataclass(frozen=True)
class IsolatedRunResult:
    """One isolated run execution result."""

    job_id: str
    success: bool
    output: str = ""
    error: str | None = None
    started_utc: datetime = field(default_factory=_utc_now)
    finished_utc: datetime = field(default_factory=_utc_now)
    duration_seconds: float = 0.0


IsolatedRunHandler = Callable[[IsolatedRunRequest], Awaitable[IsolatedRunResult | str | dict[str, Any]]]


class IsolatedRunExecutor:
    """Minimal isolated execution wrapper with pluggable async handler."""

    def __init__(self, handler: IsolatedRunHandler | None = None):
        self._handler = handler

    async def execute(self, request: IsolatedRunRequest) -> IsolatedRunResult:
        started = _utc_now()
        try:
            if self._handler is None:
                await asyncio.sleep(0)
                output = f"[isolated-run] {request.message}".strip()
                finished = _utc_now()
                return IsolatedRunResult(
                    job_id=request.job_id,
                    success=True,
                    output=output,
                    error=None,
                    started_utc=started,
                    finished_utc=finished,
                    duration_seconds=(finished - started).total_seconds(),
                )

            raw = await self._handler(request)
            finished = _utc_now()
            if isinstance(raw, IsolatedRunResult):
                return raw
            if isinstance(raw, str):
                return IsolatedRunResult(
                    job_id=request.job_id,
                    success=True,
                    output=raw,
                    error=None,
                    started_utc=started,
                    finished_utc=finished,
                    duration_seconds=(finished - started).total_seconds(),
                )
            if isinstance(raw, dict):
                return IsolatedRunResult(
                    job_id=request.job_id,
                    success=bool(raw.get("success", True)),
                    output=str(raw.get("output", "")),
                    error=(str(raw.get("error")) if raw.get("error") else None),
                    started_utc=started,
                    finished_utc=finished,
                    duration_seconds=(finished - started).total_seconds(),
                )
            raise TypeError("Isolated run handler must return IsolatedRunResult, str, or dict.")
        except Exception as exc:
            finished = _utc_now()
            return IsolatedRunResult(
                job_id=request.job_id,
                success=False,
                output="",
                error=f"{type(exc).__name__}: {exc}",
                started_utc=started,
                finished_utc=finished,
                duration_seconds=(finished - started).total_seconds(),
            )
