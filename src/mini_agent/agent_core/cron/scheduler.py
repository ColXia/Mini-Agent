"""Lean cron scheduler baseline with bounded queue and isolated execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import re
from typing import Any
from uuid import uuid4

from mini_agent.agent_core.cron.delivery import DeliveryConfig, DeliveryOutcome, DeliveryRouter
from mini_agent.agent_core.cron.isolated_run import IsolatedRunExecutor, IsolatedRunRequest, IsolatedRunResult


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ScheduleType(str, Enum):
    """Supported schedule types."""

    AT = "at"
    EVERY = "every"
    CRON = "cron"


@dataclass(frozen=True)
class CronJobSpec:
    """Cron job specification."""

    job_id: str
    schedule_type: ScheduleType
    message: str
    enabled: bool = True
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    delivery: DeliveryConfig = field(default_factory=DeliveryConfig.none)
    at_utc: datetime | None = None
    every_seconds: int | None = None
    start_at_utc: datetime | None = None
    cron_expr: str | None = None
    model_override: str | None = None
    tool_allowlist: tuple[str, ...] = ()
    timeout_seconds: int = 300

    def normalized(self) -> "CronJobSpec":
        job_id = self.job_id.strip() or f"job-{uuid4().hex[:10]}"
        message = self.message.strip()
        if not message:
            raise ValueError("Cron job message must not be empty.")

        at_utc = self.at_utc
        start_at_utc = self.start_at_utc
        if at_utc is not None and at_utc.tzinfo is None:
            at_utc = at_utc.replace(tzinfo=timezone.utc)
        if start_at_utc is not None and start_at_utc.tzinfo is None:
            start_at_utc = start_at_utc.replace(tzinfo=timezone.utc)

        every_seconds = self.every_seconds
        if every_seconds is not None:
            every_seconds = max(1, int(every_seconds))

        if self.schedule_type == ScheduleType.AT and at_utc is None:
            raise ValueError("ScheduleType.AT requires `at_utc`.")
        if self.schedule_type == ScheduleType.EVERY and every_seconds is None:
            raise ValueError("ScheduleType.EVERY requires `every_seconds`.")
        if self.schedule_type == ScheduleType.CRON and not str(self.cron_expr or "").strip():
            raise ValueError("ScheduleType.CRON requires `cron_expr`.")

        return CronJobSpec(
            job_id=job_id,
            schedule_type=self.schedule_type,
            message=message,
            enabled=bool(self.enabled),
            payload=dict(self.payload),
            metadata=dict(self.metadata),
            delivery=self.delivery,
            at_utc=at_utc,
            every_seconds=every_seconds,
            start_at_utc=start_at_utc,
            cron_expr=(str(self.cron_expr).strip() if self.cron_expr else None),
            model_override=(str(self.model_override).strip() or None) if self.model_override else None,
            tool_allowlist=tuple(self.tool_allowlist),
            timeout_seconds=max(1, int(self.timeout_seconds)),
        )


@dataclass
class CronJobState:
    """Mutable runtime state for one cron job."""

    next_run_utc: datetime | None
    last_run_utc: datetime | None = None
    run_count: int = 0
    queued_runs: int = 0
    dropped_runs: int = 0
    missed_runs: int = 0
    last_status: str | None = None
    last_error: str | None = None
    last_delivery: DeliveryOutcome | None = None


@dataclass
class CronJobRecord:
    """Job record combining spec and state."""

    spec: CronJobSpec
    state: CronJobState


@dataclass(frozen=True)
class QueuedRun:
    """Queued run payload."""

    job_id: str
    scheduled_for_utc: datetime
    enqueued_at_utc: datetime


@dataclass(frozen=True)
class TickSummary:
    """Tick operation summary."""

    due: int
    enqueued: int
    dropped: int
    missed: int
    queue_size: int


@dataclass(frozen=True)
class RunSummary:
    """Run operation summary."""

    executed: int
    succeeded: int
    failed: int
    deliveries_failed: int
    queue_size: int


def _normalize_weekday(value: int) -> int:
    if value in {0, 7}:
        return 6
    if 1 <= value <= 6:
        return value - 1
    return value


def _parse_field(field: str, minimum: int, maximum: int, *, is_weekday: bool = False) -> set[int]:
    tokens = [item.strip() for item in field.split(",") if item.strip()]
    if not tokens:
        raise ValueError("Invalid cron field: empty.")

    values: set[int] = set()
    for token in tokens:
        if token == "*":
            values.update(range(minimum, maximum + 1))
            continue

        step_match = re.match(r"^\*/(\d+)$", token)
        if step_match:
            step = int(step_match.group(1))
            if step <= 0:
                raise ValueError(f"Invalid step in cron field: {token}")
            values.update(range(minimum, maximum + 1, step))
            continue

        range_step_match = re.match(r"^(\d+)-(\d+)(?:/(\d+))?$", token)
        if range_step_match:
            start = int(range_step_match.group(1))
            end = int(range_step_match.group(2))
            step = int(range_step_match.group(3) or "1")
            if step <= 0:
                raise ValueError(f"Invalid range step in cron field: {token}")
            if start > end:
                raise ValueError(f"Invalid range in cron field: {token}")
            values.update(range(start, end + 1, step))
            continue

        if token.isdigit():
            values.add(int(token))
            continue

        raise ValueError(f"Unsupported cron token: {token}")

    normalized: set[int] = set()
    for value in values:
        if is_weekday:
            value = _normalize_weekday(value)
        if value < minimum or value > maximum:
            raise ValueError(f"Cron value {value} out of range [{minimum}, {maximum}]")
        normalized.add(value)
    return normalized


@dataclass(frozen=True)
class ParsedCronExpression:
    minutes: set[int]
    hours: set[int]
    days: set[int]
    months: set[int]
    weekdays: set[int]


def parse_cron_expression(expr: str) -> ParsedCronExpression:
    parts = [item.strip() for item in expr.split() if item.strip()]
    if len(parts) != 5:
        raise ValueError("Cron expression must have exactly five fields (m h dom mon dow).")
    return ParsedCronExpression(
        minutes=_parse_field(parts[0], 0, 59),
        hours=_parse_field(parts[1], 0, 23),
        days=_parse_field(parts[2], 1, 31),
        months=_parse_field(parts[3], 1, 12),
        weekdays=_parse_field(parts[4], 0, 6, is_weekday=True),
    )


def next_cron_time(expr: str, *, after_utc: datetime) -> datetime:
    parsed = parse_cron_expression(expr)
    probe = after_utc.astimezone(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
    horizon = probe + timedelta(days=400)
    while probe <= horizon:
        if (
            probe.minute in parsed.minutes
            and probe.hour in parsed.hours
            and probe.day in parsed.days
            and probe.month in parsed.months
            and probe.weekday() in parsed.weekdays
        ):
            return probe
        probe += timedelta(minutes=1)
    raise ValueError(f"Unable to find next run time for cron expression: {expr}")


class AgentCronScheduler:
    """Bounded cron scheduler with isolated execution."""

    def __init__(
        self,
        *,
        isolated_executor: IsolatedRunExecutor | None = None,
        delivery_router: DeliveryRouter | None = None,
        max_queue: int = 64,
        max_concurrent: int = 2,
        grace_seconds: int = 120,
    ) -> None:
        self.isolated_executor = isolated_executor or IsolatedRunExecutor()
        self.delivery_router = delivery_router or DeliveryRouter()
        self.max_queue = max(1, int(max_queue))
        self.max_concurrent = max(1, int(max_concurrent))
        self.grace_seconds = max(0, int(grace_seconds))

        self._jobs: dict[str, CronJobRecord] = {}
        self._queue: list[QueuedRun] = []
        self._lock = asyncio.Lock()

    def register_job(self, spec: CronJobSpec, *, now_utc: datetime | None = None) -> CronJobRecord:
        now = (now_utc or _utc_now()).astimezone(timezone.utc)
        normalized = spec.normalized()
        next_run = self._initial_next_run(normalized, now)
        record = CronJobRecord(spec=normalized, state=CronJobState(next_run_utc=next_run))
        self._jobs[normalized.job_id] = record
        return record

    def list_jobs(self) -> list[CronJobRecord]:
        return list(self._jobs.values())

    def get_job(self, job_id: str) -> CronJobRecord | None:
        return self._jobs.get(job_id)

    def remove_job(self, job_id: str) -> bool:
        removed = self._jobs.pop(job_id, None)
        if removed is None:
            return False
        self._queue = [item for item in self._queue if item.job_id != job_id]
        return True

    def _initial_next_run(self, spec: CronJobSpec, now: datetime) -> datetime | None:
        if not spec.enabled:
            return None
        if spec.schedule_type == ScheduleType.AT:
            assert spec.at_utc is not None
            return spec.at_utc.astimezone(timezone.utc)
        if spec.schedule_type == ScheduleType.EVERY:
            anchor = spec.start_at_utc.astimezone(timezone.utc) if spec.start_at_utc else now
            return anchor
        assert spec.cron_expr is not None
        return next_cron_time(spec.cron_expr, after_utc=now - timedelta(minutes=1))

    def _next_after(self, spec: CronJobSpec, previous: datetime, now: datetime) -> datetime | None:
        if spec.schedule_type == ScheduleType.AT:
            return None
        if spec.schedule_type == ScheduleType.EVERY:
            assert spec.every_seconds is not None
            interval = timedelta(seconds=spec.every_seconds)
            candidate = previous + interval
            if candidate > now:
                return candidate
            lag_seconds = (now - candidate).total_seconds()
            extra_steps = int(lag_seconds // spec.every_seconds) + 1
            return candidate + interval * extra_steps
        assert spec.cron_expr is not None
        return next_cron_time(spec.cron_expr, after_utc=max(previous, now - timedelta(minutes=1)))

    async def tick(self, *, now_utc: datetime | None = None) -> TickSummary:
        now = (now_utc or _utc_now()).astimezone(timezone.utc)
        due = 0
        enqueued = 0
        dropped = 0
        missed = 0

        async with self._lock:
            for record in self._jobs.values():
                next_run = record.state.next_run_utc
                if not record.spec.enabled or next_run is None or next_run > now:
                    continue

                due += 1
                lateness = (now - next_run).total_seconds()
                if lateness > self.grace_seconds:
                    missed += 1
                    record.state.missed_runs += 1
                    record.state.last_status = "missed_grace"
                    record.state.next_run_utc = self._next_after(record.spec, next_run, now)
                    continue

                if len(self._queue) >= self.max_queue:
                    dropped += 1
                    record.state.dropped_runs += 1
                    record.state.last_status = "dropped_queue_full"
                    record.state.next_run_utc = self._next_after(record.spec, next_run, now)
                    continue

                self._queue.append(
                    QueuedRun(
                        job_id=record.spec.job_id,
                        scheduled_for_utc=next_run,
                        enqueued_at_utc=now,
                    )
                )
                enqueued += 1
                record.state.queued_runs += 1
                record.state.last_status = "queued"
                record.state.next_run_utc = self._next_after(record.spec, next_run, now)

        return TickSummary(
            due=due,
            enqueued=enqueued,
            dropped=dropped,
            missed=missed,
            queue_size=len(self._queue),
        )

    async def _run_one(self, queued: QueuedRun, *, now_utc: datetime) -> tuple[IsolatedRunResult, DeliveryOutcome]:
        record = self._jobs[queued.job_id]
        request = IsolatedRunRequest(
            job_id=record.spec.job_id,
            message=record.spec.message,
            payload=dict(record.spec.payload),
            metadata=dict(record.spec.metadata),
            tool_allowlist=tuple(record.spec.tool_allowlist),
            model_override=record.spec.model_override,
            timeout_seconds=record.spec.timeout_seconds,
        )
        result = await self.isolated_executor.execute(request)
        delivery = await self.delivery_router.deliver(
            job_id=record.spec.job_id,
            message=record.spec.message,
            delivery=record.spec.delivery,
            run_result=result,
        )

        record.state.last_run_utc = now_utc
        record.state.run_count += 1
        record.state.queued_runs = max(0, record.state.queued_runs - 1)
        record.state.last_status = "succeeded" if result.success else "failed"
        record.state.last_error = result.error
        record.state.last_delivery = delivery
        return result, delivery

    async def run_pending(self, *, now_utc: datetime | None = None) -> RunSummary:
        now = (now_utc or _utc_now()).astimezone(timezone.utc)
        async with self._lock:
            queue = list(self._queue)
            self._queue.clear()

        if not queue:
            return RunSummary(executed=0, succeeded=0, failed=0, deliveries_failed=0, queue_size=0)

        semaphore = asyncio.Semaphore(self.max_concurrent)
        results: list[tuple[IsolatedRunResult, DeliveryOutcome]] = []

        async def _bounded(queued: QueuedRun):
            async with semaphore:
                results.append(await self._run_one(queued, now_utc=now))

        await asyncio.gather(*(_bounded(item) for item in queue))

        succeeded = len([item for item, _ in results if item.success])
        failed = len(results) - succeeded
        deliveries_failed = len([delivery for _, delivery in results if not delivery.delivered and not delivery.skipped])
        return RunSummary(
            executed=len(results),
            succeeded=succeeded,
            failed=failed,
            deliveries_failed=deliveries_failed,
            queue_size=len(self._queue),
        )

    async def tick_and_run(self, *, now_utc: datetime | None = None) -> tuple[TickSummary, RunSummary]:
        tick_summary = await self.tick(now_utc=now_utc)
        run_summary = await self.run_pending(now_utc=now_utc)
        return tick_summary, run_summary
