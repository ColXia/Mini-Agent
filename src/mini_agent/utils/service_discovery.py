"""Service discovery for distributed deployments."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable

try:
    import redis.asyncio as redis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    redis = None  # type: ignore


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


@dataclass
class ServiceInstance:
    """A registered service instance."""

    service_name: str
    instance_id: str
    host: str
    port: int
    metadata: dict[str, Any] = field(default_factory=dict)
    registered_at: str = ""
    last_heartbeat: str = ""
    ttl: int = 30
    status: str = "up"

    def to_dict(self) -> dict[str, Any]:
        return {
            "service_name": self.service_name,
            "instance_id": self.instance_id,
            "host": self.host,
            "port": self.port,
            "metadata": self.metadata,
            "registered_at": self.registered_at,
            "last_heartbeat": self.last_heartbeat,
            "ttl": self.ttl,
            "status": self.status,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ServiceInstance":
        return cls(
            service_name=data.get("service_name", ""),
            instance_id=data.get("instance_id", ""),
            host=data.get("host", ""),
            port=data.get("port", 0),
            metadata=data.get("metadata", {}),
            registered_at=data.get("registered_at", ""),
            last_heartbeat=data.get("last_heartbeat", ""),
            ttl=data.get("ttl", 30),
            status=data.get("status", "up"),
        )


@dataclass
class ServiceDiscoveryConfig:
    """Service discovery configuration."""

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    key_prefix: str = "mini_agent:services:"
    heartbeat_interval: int = 10  # seconds
    default_ttl: int = 30  # seconds


class ServiceRegistry:
    """Service registry with Redis backend."""

    def __init__(self, config: ServiceDiscoveryConfig | None = None) -> None:
        if not REDIS_AVAILABLE:
            raise ImportError("redis package required for ServiceRegistry")

        self.config = config or ServiceDiscoveryConfig()
        self._client: redis.Redis | None = None
        self._pool: redis.ConnectionPool | None = None
        self._registered_services: dict[str, ServiceInstance] = {}
        self._heartbeat_task: asyncio.Task | None = None
        self._running = False

    async def connect(self) -> None:
        """Connect to Redis."""
        if self._client is not None:
            return

        self._pool = redis.ConnectionPool(
            host=self.config.redis_host,
            port=self.config.redis_port,
            db=self.config.redis_db,
            password=self.config.redis_password,
            decode_responses=True,
        )
        self._client = redis.Redis(connection_pool=self._pool)

    async def disconnect(self) -> None:
        """Disconnect from Redis."""
        self._running = False
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        # Deregister all services
        for service in list(self._registered_services.values()):
            try:
                await self.deregister(service.service_name, service.instance_id)
            except Exception:
                pass

        if self._client:
            await self._client.close()
            self._client = None
        if self._pool:
            await self._pool.disconnect()
            self._pool = None

    def _make_service_key(self, service_name: str) -> str:
        """Create service key."""
        return f"{self.config.key_prefix}{service_name}"

    def _make_instance_key(self, service_name: str, instance_id: str) -> str:
        """Create instance key."""
        return f"{self.config.key_prefix}{service_name}:{instance_id}"

    async def register(
        self,
        service_name: str,
        host: str,
        port: int,
        *,
        instance_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> ServiceInstance:
        """Register a service instance."""
        if not self._client:
            await self.connect()

        effective_instance_id = instance_id or str(uuid.uuid4())[:8]
        effective_ttl = ttl or self.config.default_ttl
        now = _utc_iso(_utc_now()) or ""

        instance = ServiceInstance(
            service_name=service_name,
            instance_id=effective_instance_id,
            host=host,
            port=port,
            metadata=metadata or {},
            registered_at=now,
            last_heartbeat=now,
            ttl=effective_ttl,
            status="up",
        )

        # Store instance data
        instance_key = self._make_instance_key(service_name, effective_instance_id)
        await self._client.set(  # type: ignore
            instance_key,
            json.dumps(instance.to_dict()),
            ex=effective_ttl,
        )

        # Add to service set
        service_key = self._make_service_key(service_name)
        await self._client.sadd(service_key, effective_instance_id)  # type: ignore

        self._registered_services[f"{service_name}:{effective_instance_id}"] = instance

        # Start heartbeat if not running
        if not self._running:
            self._running = True
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        return instance

    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """Deregister a service instance."""
        if not self._client:
            await self.connect()

        # Remove instance data
        instance_key = self._make_instance_key(service_name, instance_id)
        await self._client.delete(instance_key)  # type: ignore

        # Remove from service set
        service_key = self._make_service_key(service_name)
        await self._client.srem(service_key, instance_id)  # type: ignore

        # Remove from local cache
        cache_key = f"{service_name}:{instance_id}"
        if cache_key in self._registered_services:
            del self._registered_services[cache_key]

        return True

    async def discover(self, service_name: str) -> list[ServiceInstance]:
        """Discover all instances of a service."""
        if not self._client:
            await self.connect()

        service_key = self._make_service_key(service_name)
        instance_ids = await self._client.smembers(service_key)  # type: ignore

        instances = []
        for instance_id in instance_ids:
            instance_key = self._make_instance_key(service_name, instance_id)
            data = await self._client.get(instance_key)  # type: ignore

            if data:
                try:
                    instance = ServiceInstance.from_dict(json.loads(data))
                    instances.append(instance)
                except (json.JSONDecodeError, KeyError):
                    # Invalid data, remove from set
                    await self._client.srem(service_key, instance_id)  # type: ignore

        return instances

    async def discover_one(self, service_name: str) -> ServiceInstance | None:
        """Discover one instance of a service (random selection)."""
        instances = await self.discover(service_name)
        if not instances:
            return None

        # Simple round-robin selection
        # In production, you might want weighted selection based on load
        import random
        return random.choice(instances)

    async def heartbeat(self, service_name: str, instance_id: str) -> bool:
        """Send heartbeat for a registered service."""
        if not self._client:
            await self.connect()

        cache_key = f"{service_name}:{instance_id}"
        instance = self._registered_services.get(cache_key)

        if not instance:
            return False

        # Update heartbeat time
        instance.last_heartbeat = _utc_iso(_utc_now()) or ""

        # Update in Redis with TTL
        instance_key = self._make_instance_key(service_name, instance_id)
        await self._client.set(  # type: ignore
            instance_key,
            json.dumps(instance.to_dict()),
            ex=instance.ttl,
        )

        return True

    async def _heartbeat_loop(self) -> None:
        """Periodic heartbeat for all registered services."""
        while self._running:
            await asyncio.sleep(self.config.heartbeat_interval)

            for cache_key, instance in list(self._registered_services.items()):
                try:
                    await self.heartbeat(instance.service_name, instance.instance_id)
                except Exception:
                    pass

    async def get_service_url(self, service_name: str) -> str | None:
        """Get URL for a service instance."""
        instance = await self.discover_one(service_name)
        if not instance:
            return None

        scheme = instance.metadata.get("scheme", "http")
        return f"{scheme}://{instance.host}:{instance.port}"

    async def list_services(self) -> list[str]:
        """List all registered service names."""
        if not self._client:
            await self.connect()

        pattern = f"{self.config.key_prefix}*"
        keys = []
        async for key in self._client.scan_iter(match=pattern):  # type: ignore
            # Extract service name from key
            key_str = str(key)
            if ":" in key_str and key_str.count(":") == 3:
                # This is an instance key, extract service name
                parts = key_str.split(":")
                if len(parts) >= 3:
                    keys.append(parts[2])

        return list(set(keys))


class LocalServiceRegistry:
    """Local service registry for single-instance deployments."""

    def __init__(self) -> None:
        self._services: dict[str, list[ServiceInstance]] = {}

    async def register(
        self,
        service_name: str,
        host: str,
        port: int,
        *,
        instance_id: str | None = None,
        metadata: dict[str, Any] | None = None,
        ttl: int | None = None,
    ) -> ServiceInstance:
        """Register a service instance."""
        effective_instance_id = instance_id or str(uuid.uuid4())[:8]
        now = _utc_iso(_utc_now()) or ""

        instance = ServiceInstance(
            service_name=service_name,
            instance_id=effective_instance_id,
            host=host,
            port=port,
            metadata=metadata or {},
            registered_at=now,
            last_heartbeat=now,
            ttl=ttl or 30,
            status="up",
        )

        if service_name not in self._services:
            self._services[service_name] = []
        self._services[service_name].append(instance)

        return instance

    async def deregister(self, service_name: str, instance_id: str) -> bool:
        """Deregister a service instance."""
        if service_name not in self._services:
            return False

        self._services[service_name] = [
            s for s in self._services[service_name]
            if s.instance_id != instance_id
        ]
        return True

    async def discover(self, service_name: str) -> list[ServiceInstance]:
        """Discover all instances of a service."""
        return self._services.get(service_name, [])

    async def discover_one(self, service_name: str) -> ServiceInstance | None:
        """Discover one instance of a service."""
        instances = await self.discover(service_name)
        if not instances:
            return None

        import random
        return random.choice(instances)

    async def get_service_url(self, service_name: str) -> str | None:
        """Get URL for a service instance."""
        instance = await self.discover_one(service_name)
        if not instance:
            return None

        scheme = instance.metadata.get("scheme", "http")
        return f"{scheme}://{instance.host}:{instance.port}"

    async def list_services(self) -> list[str]:
        """List all registered service names."""
        return list(self._services.keys())

    async def close(self) -> None:
        """Close the registry."""
        self._services.clear()
