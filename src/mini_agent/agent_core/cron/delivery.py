"""Delivery routing for scheduled job execution outcomes."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable

from mini_agent.agent_core.cron.isolated_run import IsolatedRunResult


class DeliveryMode(str, Enum):
    """Supported delivery modes for cron jobs."""

    NONE = "none"
    ANNOUNCE = "announce"
    WEBHOOK = "webhook"


@dataclass(frozen=True)
class DeliveryConfig:
    """Delivery configuration bound to a cron job."""

    mode: DeliveryMode = DeliveryMode.NONE
    target: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @staticmethod
    def none() -> "DeliveryConfig":
        return DeliveryConfig(mode=DeliveryMode.NONE, target=None)


@dataclass(frozen=True)
class DeliveryPayload:
    """Payload emitted to delivery handlers."""

    job_id: str
    mode: DeliveryMode
    target: str | None
    message: str
    run_result: IsolatedRunResult
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class DeliveryOutcome:
    """Delivery execution result."""

    mode: DeliveryMode
    delivered: bool
    skipped: bool = False
    error: str | None = None


DeliveryHandler = Callable[[DeliveryPayload], Awaitable[None] | None]


class DeliveryRouter:
    """Route run outcomes to optional announce/webhook handlers."""

    def __init__(
        self,
        *,
        announce_handler: DeliveryHandler | None = None,
        webhook_handler: DeliveryHandler | None = None,
    ) -> None:
        self.announce_handler = announce_handler
        self.webhook_handler = webhook_handler

    async def deliver(
        self,
        *,
        job_id: str,
        message: str,
        delivery: DeliveryConfig,
        run_result: IsolatedRunResult,
    ) -> DeliveryOutcome:
        if delivery.mode == DeliveryMode.NONE:
            return DeliveryOutcome(mode=delivery.mode, delivered=False, skipped=True, error=None)

        handler: DeliveryHandler | None = None
        if delivery.mode == DeliveryMode.ANNOUNCE:
            handler = self.announce_handler
        elif delivery.mode == DeliveryMode.WEBHOOK:
            handler = self.webhook_handler

        if handler is None:
            return DeliveryOutcome(
                mode=delivery.mode,
                delivered=False,
                skipped=False,
                error=f"delivery handler not configured for mode '{delivery.mode.value}'",
            )

        payload = DeliveryPayload(
            job_id=job_id,
            mode=delivery.mode,
            target=delivery.target,
            message=message,
            run_result=run_result,
            metadata=dict(delivery.metadata),
        )

        try:
            result = handler(payload)
            if inspect.isawaitable(result):
                await result
            return DeliveryOutcome(mode=delivery.mode, delivered=True, skipped=False, error=None)
        except Exception as exc:
            return DeliveryOutcome(
                mode=delivery.mode,
                delivered=False,
                skipped=False,
                error=f"{type(exc).__name__}: {exc}",
            )
