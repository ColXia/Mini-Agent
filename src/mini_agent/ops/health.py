"""Health check endpoints for Kubernetes-style probes."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class HealthStatus(str, Enum):
    """Health check status."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    STARTING = "starting"
    STOPPING = "stopping"


@dataclass
class HealthCheckResult:
    """Result of a health check."""

    name: str
    status: HealthStatus
    message: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    timestamp: float = field(default_factory=time.time)


@dataclass
class HealthReport:
    """Overall health report."""

    status: HealthStatus
    checks: list[HealthCheckResult] = field(default_factory=list)
    version: str = "1.0.0"
    uptime_seconds: float = 0.0

    @property
    def is_healthy(self) -> bool:
        return self.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    @property
    def is_ready(self) -> bool:
        return self.status == HealthStatus.HEALTHY

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "is_healthy": self.is_healthy,
            "is_ready": self.is_ready,
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "details": c.details,
                    "latency_ms": c.latency_ms,
                    "timestamp": c.timestamp,
                }
                for c in self.checks
            ],
        }


HealthChecker = Callable[[], HealthCheckResult]


class HealthCheckRegistry:
    """Registry for health checkers."""

    def __init__(self, *, version: str = "1.0.0") -> None:
        self.version = version
        self._start_time = time.time()
        self._liveness_checkers: dict[str, HealthChecker] = {}
        self._readiness_checkers: dict[str, HealthChecker] = {}
        self._startup_checkers: dict[str, HealthChecker] = {}

    def register_liveness(self, name: str, checker: HealthChecker) -> None:
        """Register a liveness check.

        Liveness checks determine if the application is running.
        If failed, Kubernetes will restart the pod.
        """
        self._liveness_checkers[name] = checker

    def register_readiness(self, name: str, checker: HealthChecker) -> None:
        """Register a readiness check.

        Readiness checks determine if the application can serve traffic.
        If failed, Kubernetes will stop sending traffic.
        """
        self._readiness_checkers[name] = checker

    def register_startup(self, name: str, checker: HealthChecker) -> None:
        """Register a startup check.

        Startup checks determine if the application has started.
        Used for slow-starting containers.
        """
        self._startup_checkers[name] = checker

    def unregister(self, name: str) -> None:
        """Unregister a health check."""
        self._liveness_checkers.pop(name, None)
        self._readiness_checkers.pop(name, None)
        self._startup_checkers.pop(name, None)

    async def _run_check(self, checker: HealthChecker) -> HealthCheckResult:
        """Run a single health check."""
        start = time.time()
        try:
            if asyncio.iscoroutinefunction(checker):
                result = await checker()
            else:
                result = checker()

            result.latency_ms = (time.time() - start) * 1000
            return result
        except Exception as e:
            return HealthCheckResult(
                name="unknown",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=(time.time() - start) * 1000,
            )

    async def check_liveness(self) -> HealthReport:
        """Run liveness checks."""
        checks = []
        overall_status = HealthStatus.HEALTHY

        for name, checker in self._liveness_checkers.items():
            result = await self._run_check(checker)
            result.name = name
            checks.append(result)

            if result.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
            elif result.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED

        return HealthReport(
            status=overall_status,
            checks=checks,
            version=self.version,
            uptime_seconds=time.time() - self._start_time,
        )

    async def check_readiness(self) -> HealthReport:
        """Run readiness checks."""
        checks = []
        overall_status = HealthStatus.HEALTHY

        for name, checker in self._readiness_checkers.items():
            result = await self._run_check(checker)
            result.name = name
            checks.append(result)

            if result.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY
            elif result.status == HealthStatus.DEGRADED and overall_status == HealthStatus.HEALTHY:
                overall_status = HealthStatus.DEGRADED

        return HealthReport(
            status=overall_status,
            checks=checks,
            version=self.version,
            uptime_seconds=time.time() - self._start_time,
        )

    async def check_startup(self) -> HealthReport:
        """Run startup checks."""
        checks = []
        overall_status = HealthStatus.HEALTHY

        for name, checker in self._startup_checkers.items():
            result = await self._run_check(checker)
            result.name = name
            checks.append(result)

            if result.status == HealthStatus.UNHEALTHY:
                overall_status = HealthStatus.UNHEALTHY

        return HealthReport(
            status=overall_status,
            checks=checks,
            version=self.version,
            uptime_seconds=time.time() - self._start_time,
        )

    async def check_all(self) -> HealthReport:
        """Run all health checks."""
        all_checks = []

        # Run liveness checks
        liveness = await self.check_liveness()
        all_checks.extend(liveness.checks)

        # Run readiness checks
        readiness = await self.check_readiness()
        all_checks.extend(readiness.checks)

        # Determine overall status
        if liveness.status == HealthStatus.UNHEALTHY or readiness.status == HealthStatus.UNHEALTHY:
            overall_status = HealthStatus.UNHEALTHY
        elif liveness.status == HealthStatus.DEGRADED or readiness.status == HealthStatus.DEGRADED:
            overall_status = HealthStatus.DEGRADED
        else:
            overall_status = HealthStatus.HEALTHY

        return HealthReport(
            status=overall_status,
            checks=all_checks,
            version=self.version,
            uptime_seconds=time.time() - self._start_time,
        )


# Common health checkers

def create_memory_checker(
    *,
    max_memory_percent: float = 90.0,
    name: str = "memory",
) -> HealthChecker:
    """Create a memory usage health checker."""
    import psutil

    def checker() -> HealthCheckResult:
        memory = psutil.virtual_memory()
        percent = memory.percent

        if percent >= max_memory_percent:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Memory usage too high: {percent:.1f}%",
                details={
                    "percent": percent,
                    "available_gb": memory.available / (1024**3),
                    "total_gb": memory.total / (1024**3),
                },
            )
        elif percent >= max_memory_percent * 0.8:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.DEGRADED,
                message=f"Memory usage high: {percent:.1f}%",
                details={
                    "percent": percent,
                    "available_gb": memory.available / (1024**3),
                    "total_gb": memory.total / (1024**3),
                },
            )

        return HealthCheckResult(
            name=name,
            status=HealthStatus.HEALTHY,
            details={
                "percent": percent,
                "available_gb": memory.available / (1024**3),
                "total_gb": memory.total / (1024**3),
            },
        )

    return checker


def create_database_checker(
    get_connection: Callable[[], Any],
    *,
    name: str = "database",
) -> HealthChecker:
    """Create a database connectivity health checker."""
    async def checker() -> HealthCheckResult:
        try:
            conn = get_connection()
            # Simple query to check connectivity
            if hasattr(conn, "execute"):
                await conn.execute("SELECT 1")
            return HealthCheckResult(
                name=name,
                status=HealthStatus.HEALTHY,
                message="Database connection OK",
            )
        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {e}",
            )

    return checker


def create_redis_checker(
    redis_client: Any,
    *,
    name: str = "redis",
) -> HealthChecker:
    """Create a Redis connectivity health checker."""
    async def checker() -> HealthCheckResult:
        try:
            result = await redis_client.ping()
            if result:
                return HealthCheckResult(
                    name=name,
                    status=HealthStatus.HEALTHY,
                    message="Redis connection OK",
                )
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message="Redis ping returned False",
            )
        except Exception as e:
            return HealthCheckResult(
                name=name,
                status=HealthStatus.UNHEALTHY,
                message=f"Redis connection failed: {e}",
            )

    return checker


def create_http_checker(
    url: str,
    *,
    timeout: float = 5.0,
    expected_status: int = 200,
    name: str | None = None,
) -> HealthChecker:
    """Create an HTTP endpoint health checker."""
    import aiohttp

    async def checker() -> HealthCheckResult:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                    if resp.status == expected_status:
                        return HealthCheckResult(
                            name=name or url,
                            status=HealthStatus.HEALTHY,
                            message=f"HTTP check OK: {resp.status}",
                        )
                    return HealthCheckResult(
                        name=name or url,
                        status=HealthStatus.UNHEALTHY,
                        message=f"Unexpected status: {resp.status}",
                        details={"expected": expected_status, "actual": resp.status},
                    )
        except asyncio.TimeoutError:
            return HealthCheckResult(
                name=name or url,
                status=HealthStatus.UNHEALTHY,
                message=f"HTTP check timeout after {timeout}s",
            )
        except Exception as e:
            return HealthCheckResult(
                name=name or url,
                status=HealthStatus.UNHEALTHY,
                message=f"HTTP check failed: {e}",
            )

    return checker


# Global health check registry
_registry: HealthCheckRegistry | None = None


def get_health_registry() -> HealthCheckRegistry:
    """Get the global health check registry."""
    global _registry
    if _registry is None:
        _registry = HealthCheckRegistry()
    return _registry
