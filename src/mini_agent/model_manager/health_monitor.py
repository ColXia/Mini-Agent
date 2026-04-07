"""Provider health monitor baseline for model-manager runtime."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import RLock
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _normalize_provider_id(provider_id: str) -> str:
    normalized = provider_id.strip()
    return normalized or "provider"


@dataclass
class _ProviderHealthRecord:
    provider_id: str
    selected_count: int = 0
    total_successes: int = 0
    total_failures: int = 0
    consecutive_failures: int = 0
    last_selected_at: datetime | None = None
    last_success_at: datetime | None = None
    last_failure_at: datetime | None = None
    last_failure_reason: str | None = None
    mapping_mode_counts: dict[str, int] = field(default_factory=dict)

    @property
    def total_requests(self) -> int:
        return self.total_successes + self.total_failures

    @property
    def error_rate(self) -> float:
        total = self.total_requests
        if total <= 0:
            return 0.0
        return float(self.total_failures) / float(total)


class ProviderHealthMonitor:
    """In-memory provider health tracker for dashboard visibility."""

    def __init__(self, *, degraded_failure_threshold: int = 3):
        self._degraded_failure_threshold = max(1, int(degraded_failure_threshold))
        self._records: dict[str, _ProviderHealthRecord] = {}
        self._lock = RLock()

    def record_route(
        self,
        provider_id: str,
        *,
        mapping_mode: str | None = None,
        now: datetime | None = None,
    ) -> None:
        with self._lock:
            record = self._get_or_create_unlocked(provider_id)
            timestamp = now or _utc_now()
            record.selected_count += 1
            record.last_selected_at = timestamp
            if mapping_mode and mapping_mode.strip():
                mode = mapping_mode.strip().lower()
                record.mapping_mode_counts[mode] = record.mapping_mode_counts.get(mode, 0) + 1

    def record_success(self, provider_id: str, *, now: datetime | None = None) -> None:
        with self._lock:
            record = self._get_or_create_unlocked(provider_id)
            timestamp = now or _utc_now()
            record.total_successes += 1
            record.consecutive_failures = 0
            record.last_success_at = timestamp
            record.last_failure_reason = None

    def record_failure(
        self,
        provider_id: str,
        *,
        reason: str | None = None,
        now: datetime | None = None,
    ) -> None:
        with self._lock:
            record = self._get_or_create_unlocked(provider_id)
            timestamp = now or _utc_now()
            record.total_failures += 1
            record.consecutive_failures += 1
            record.last_failure_at = timestamp
            record.last_failure_reason = (reason or "").strip() or None

    def snapshot(
        self,
        provider_id: str,
        *,
        breaker_state: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            record = self._records.get(_normalize_provider_id(provider_id))
            if record is None:
                return self._empty_snapshot(provider_id, breaker_state=breaker_state)
            status = self._derive_status(record, breaker_state=breaker_state)
            return {
                "provider_id": record.provider_id,
                "status": status,
                "selected_count": record.selected_count,
                "total_requests": record.total_requests,
                "total_successes": record.total_successes,
                "total_failures": record.total_failures,
                "consecutive_failures": record.consecutive_failures,
                "error_rate": record.error_rate,
                "last_selected_at": _utc_iso(record.last_selected_at),
                "last_success_at": _utc_iso(record.last_success_at),
                "last_failure_at": _utc_iso(record.last_failure_at),
                "last_failure_reason": record.last_failure_reason,
                "mapping_mode_counts": dict(record.mapping_mode_counts),
                "breaker_state": breaker_state,
            }

    def stats(self, provider_id: str) -> dict[str, Any]:
        return self.snapshot(provider_id)

    def snapshots(self, *, breaker_states: dict[str, str] | None = None) -> list[dict[str, Any]]:
        with self._lock:
            provider_ids = sorted(self._records.keys())
        output: list[dict[str, Any]] = []
        for provider_id in provider_ids:
            breaker_state = None
            if breaker_states is not None:
                breaker_state = breaker_states.get(provider_id)
            output.append(self.snapshot(provider_id, breaker_state=breaker_state))
        return output

    def reset(self) -> None:
        with self._lock:
            self._records.clear()

    def _get_or_create_unlocked(self, provider_id: str) -> _ProviderHealthRecord:
        normalized = _normalize_provider_id(provider_id)
        existing = self._records.get(normalized)
        if existing is not None:
            return existing
        created = _ProviderHealthRecord(provider_id=normalized)
        self._records[normalized] = created
        return created

    def _derive_status(self, record: _ProviderHealthRecord, *, breaker_state: str | None) -> str:
        if breaker_state == "open":
            return "unhealthy"
        if record.total_requests <= 0 and record.selected_count <= 0:
            return "unknown"
        if record.consecutive_failures >= self._degraded_failure_threshold:
            return "degraded"
        return "healthy"

    def _empty_snapshot(self, provider_id: str, *, breaker_state: str | None) -> dict[str, Any]:
        status = "unhealthy" if breaker_state == "open" else "unknown"
        return {
            "provider_id": _normalize_provider_id(provider_id),
            "status": status,
            "selected_count": 0,
            "total_requests": 0,
            "total_successes": 0,
            "total_failures": 0,
            "consecutive_failures": 0,
            "error_rate": 0.0,
            "last_selected_at": None,
            "last_success_at": None,
            "last_failure_at": None,
            "last_failure_reason": None,
            "mapping_mode_counts": {},
            "breaker_state": breaker_state,
        }
