"""Webhook support for external event triggers."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

import aiohttp


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


class WebhookEvent(str, Enum):
    """Supported webhook events."""

    # Agent events
    AGENT_STARTED = "agent.started"
    AGENT_STOPPED = "agent.stopped"
    AGENT_ERROR = "agent.error"

    # Provider events
    PROVIDER_ADDED = "provider.added"
    PROVIDER_REMOVED = "provider.removed"
    PROVIDER_ERROR = "provider.error"

    # Skill events
    SKILL_LOADED = "skill.loaded"
    SKILL_EXECUTED = "skill.executed"
    SKILL_EVOLVED = "skill.evolved"

    # Session events
    SESSION_STARTED = "session.started"
    SESSION_ENDED = "session.ended"
    SESSION_MESSAGE = "session.message"

    # Custom events
    CUSTOM = "custom"


@dataclass
class WebhookEndpoint:
    """A registered webhook endpoint."""

    endpoint_id: str
    url: str
    events: list[WebhookEvent]
    secret: str | None = None
    headers: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    timeout_seconds: float = 10.0
    retry_count: int = 3
    created_at: str = ""
    last_triggered_at: str | None = None
    trigger_count: int = 0
    failure_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "url": self.url,
            "events": [e.value for e in self.events],
            "secret": "***" if self.secret else None,
            "headers": self.headers,
            "enabled": self.enabled,
            "timeout_seconds": self.timeout_seconds,
            "retry_count": self.retry_count,
            "created_at": self.created_at,
            "last_triggered_at": self.last_triggered_at,
            "trigger_count": self.trigger_count,
            "failure_count": self.failure_count,
        }


@dataclass
class WebhookPayload:
    """Payload sent to webhook endpoints."""

    event: WebhookEvent
    timestamp: str
    data: dict[str, Any]
    source: str = "mini-agent"
    event_id: str = ""

    def __post_init__(self) -> None:
        if not self.event_id:
            self.event_id = self._generate_id()

    def _generate_id(self) -> str:
        data = f"{self.event}:{self.timestamp}:{json.dumps(self.data, sort_keys=True)}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event": self.event.value,
            "timestamp": self.timestamp,
            "data": self.data,
            "source": self.source,
            "event_id": self.event_id,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict())


@dataclass
class WebhookDelivery:
    """Record of a webhook delivery attempt."""

    endpoint_id: str
    event_id: str
    success: bool
    status_code: int | None = None
    error: str | None = None
    response_time_ms: float = 0.0
    attempt: int = 1
    timestamp: str = ""


class WebhookManager:
    """Manager for webhook registration and delivery."""

    def __init__(self) -> None:
        self._endpoints: dict[str, WebhookEndpoint] = {}
        self._delivery_history: list[WebhookDelivery] = []
        self._max_history: int = 1000
        self._session: aiohttp.ClientSession | None = None
        self._lock = asyncio.Lock()

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create HTTP session."""
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    def register(
        self,
        endpoint_id: str,
        url: str,
        events: list[WebhookEvent | str],
        *,
        secret: str | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 10.0,
        retry_count: int = 3,
    ) -> WebhookEndpoint:
        """Register a webhook endpoint."""
        normalized_events = [
            e if isinstance(e, WebhookEvent) else WebhookEvent(e)
            for e in events
        ]

        endpoint = WebhookEndpoint(
            endpoint_id=endpoint_id,
            url=url,
            events=normalized_events,
            secret=secret,
            headers=headers or {},
            timeout_seconds=timeout_seconds,
            retry_count=retry_count,
            created_at=_utc_iso(_utc_now()) or "",
        )

        self._endpoints[endpoint_id] = endpoint
        return endpoint

    def unregister(self, endpoint_id: str) -> bool:
        """Unregister a webhook endpoint."""
        if endpoint_id in self._endpoints:
            del self._endpoints[endpoint_id]
            return True
        return False

    def get_endpoint(self, endpoint_id: str) -> WebhookEndpoint | None:
        """Get a webhook endpoint by ID."""
        return self._endpoints.get(endpoint_id)

    def list_endpoints(self) -> list[WebhookEndpoint]:
        """List all registered endpoints."""
        return list(self._endpoints.values())

    def enable(self, endpoint_id: str) -> bool:
        """Enable a webhook endpoint."""
        endpoint = self._endpoints.get(endpoint_id)
        if endpoint:
            endpoint.enabled = True
            return True
        return False

    def disable(self, endpoint_id: str) -> bool:
        """Disable a webhook endpoint."""
        endpoint = self._endpoints.get(endpoint_id)
        if endpoint:
            endpoint.enabled = False
            return True
        return False

    def _compute_signature(self, payload: str, secret: str) -> str:
        """Compute HMAC signature for payload."""
        return hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

    async def _deliver(
        self,
        endpoint: WebhookEndpoint,
        payload: WebhookPayload,
        attempt: int = 1,
    ) -> WebhookDelivery:
        """Deliver a webhook to an endpoint."""
        session = await self._get_session()
        payload_json = payload.to_json()

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mini-Agent-Webhook/1.0",
            "X-Webhook-Event": payload.event.value,
            "X-Webhook-Id": payload.event_id,
            **endpoint.headers,
        }

        if endpoint.secret:
            signature = self._compute_signature(payload_json, endpoint.secret)
            headers["X-Webhook-Signature"] = signature

        start_time = time.time()
        status_code = None
        error = None
        success = False

        try:
            async with session.post(
                endpoint.url,
                data=payload_json,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=endpoint.timeout_seconds),
            ) as response:
                status_code = response.status
                success = 200 <= status_code < 300

                if not success:
                    error = f"HTTP {status_code}"

        except asyncio.TimeoutError:
            error = "Timeout"
        except aiohttp.ClientError as e:
            error = str(e)
        except Exception as e:
            error = str(e)

        response_time_ms = (time.time() - start_time) * 1000

        delivery = WebhookDelivery(
            endpoint_id=endpoint.endpoint_id,
            event_id=payload.event_id,
            success=success,
            status_code=status_code,
            error=error,
            response_time_ms=response_time_ms,
            attempt=attempt,
            timestamp=_utc_iso(_utc_now()) or "",
        )

        # Update endpoint stats
        endpoint.last_triggered_at = _utc_iso(_utc_now())
        endpoint.trigger_count += 1
        if not success:
            endpoint.failure_count += 1

        return delivery

    async def trigger(
        self,
        event: WebhookEvent | str,
        data: dict[str, Any],
        *,
        source: str = "mini-agent",
    ) -> list[WebhookDelivery]:
        """Trigger a webhook event to all subscribed endpoints."""
        normalized_event = event if isinstance(event, WebhookEvent) else WebhookEvent(event)

        payload = WebhookPayload(
            event=normalized_event,
            timestamp=_utc_iso(_utc_now()) or "",
            data=data,
            source=source,
        )

        deliveries = []

        for endpoint in self._endpoints.values():
            if not endpoint.enabled:
                continue

            if normalized_event not in endpoint.events:
                continue

            # Try delivery with retries
            for attempt in range(1, endpoint.retry_count + 1):
                delivery = await self._deliver(endpoint, payload, attempt)
                deliveries.append(delivery)

                if delivery.success:
                    break

                if attempt < endpoint.retry_count:
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff

        # Record delivery history
        async with self._lock:
            self._delivery_history.extend(deliveries)
            if len(self._delivery_history) > self._max_history:
                self._delivery_history = self._delivery_history[-self._max_history:]

        return deliveries

    async def trigger_async(
        self,
        event: WebhookEvent | str,
        data: dict[str, Any],
        *,
        source: str = "mini-agent",
    ) -> None:
        """Trigger a webhook event asynchronously (fire and forget)."""
        asyncio.create_task(self.trigger(event, data, source=source))

    def get_delivery_history(
        self,
        endpoint_id: str | None = None,
        limit: int = 100,
    ) -> list[WebhookDelivery]:
        """Get webhook delivery history."""
        history = self._delivery_history

        if endpoint_id:
            history = [d for d in history if d.endpoint_id == endpoint_id]

        return history[-limit:]

    def get_stats(self) -> dict[str, Any]:
        """Get webhook statistics."""
        total = len(self._delivery_history)
        successful = sum(1 for d in self._delivery_history if d.success)
        failed = total - successful

        return {
            "total_endpoints": len(self._endpoints),
            "enabled_endpoints": sum(1 for e in self._endpoints.values() if e.enabled),
            "total_deliveries": total,
            "successful_deliveries": successful,
            "failed_deliveries": failed,
            "success_rate": successful / total if total > 0 else 0,
        }

    async def close(self) -> None:
        """Close the HTTP session."""
        if self._session and not self._session.closed:
            await self._session.close()


class WebhookReceiver:
    """Receiver for incoming webhooks."""

    def __init__(self, secret: str | None = None) -> None:
        self.secret = secret
        self._handlers: dict[str, list[Callable[[dict[str, Any]], None]]] = {}

    def on_event(
        self,
        event: WebhookEvent | str,
        handler: Callable[[dict[str, Any]], None],
    ) -> None:
        """Register a handler for a webhook event."""
        event_name = event.value if isinstance(event, WebhookEvent) else event
        if event_name not in self._handlers:
            self._handlers[event_name] = []
        self._handlers[event_name].append(handler)

    def verify_signature(
        self,
        payload: str,
        signature: str,
    ) -> bool:
        """Verify webhook signature."""
        if not self.secret:
            return True

        expected = hmac.new(
            self.secret.encode(),
            payload.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(signature, expected)

    async def handle(
        self,
        payload: str,
        signature: str | None = None,
    ) -> bool:
        """Handle an incoming webhook."""
        # Verify signature
        if self.secret and signature:
            if not self.verify_signature(payload, signature):
                return False

        try:
            data = json.loads(payload)
            event = data.get("event", "")
            event_data = data.get("data", {})

            handlers = self._handlers.get(event, [])
            for handler in handlers:
                try:
                    if asyncio.iscoroutinefunction(handler):
                        await handler(event_data)
                    else:
                        handler(event_data)
                except Exception:
                    pass

            return True

        except json.JSONDecodeError:
            return False


# Global instances
_webhook_manager: WebhookManager | None = None


def get_webhook_manager() -> WebhookManager:
    """Get the global webhook manager."""
    global _webhook_manager
    if _webhook_manager is None:
        _webhook_manager = WebhookManager()
    return _webhook_manager
