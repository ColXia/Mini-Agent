"""Tests for P15 T3.3 cron baseline."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from mini_agent.agent_core.cron.delivery import DeliveryConfig, DeliveryMode, DeliveryRouter
from mini_agent.agent_core.cron.isolated_run import IsolatedRunExecutor, IsolatedRunRequest, IsolatedRunResult
from mini_agent.agent_core.cron.scheduler import (
    AgentCronScheduler,
    CronJobSpec,
    ScheduleType,
    next_cron_time,
    parse_cron_expression,
)


def _dt(year: int, month: int, day: int, hour: int, minute: int, second: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)


def test_parse_cron_expression_and_next_time():
    parsed = parse_cron_expression("*/15 9-18 * * 1-5")
    assert 0 in parsed.minutes
    assert 45 in parsed.minutes
    assert 9 in parsed.hours
    assert 18 in parsed.hours
    assert 0 in parsed.weekdays
    assert 4 in parsed.weekdays

    next_run = next_cron_time("*/15 * * * *", after_utc=_dt(2026, 1, 1, 0, 7))
    assert next_run == _dt(2026, 1, 1, 0, 15)


@pytest.mark.asyncio
async def test_scheduler_every_job_tick_and_run():
    executed: list[str] = []

    async def _handler(request: IsolatedRunRequest):
        executed.append(request.message)
        return IsolatedRunResult(job_id=request.job_id, success=True, output="ok")

    scheduler = AgentCronScheduler(
        isolated_executor=IsolatedRunExecutor(_handler),
        max_queue=8,
        max_concurrent=2,
        grace_seconds=120,
    )

    base = _dt(2026, 1, 1, 10, 0)
    scheduler.register_job(
        CronJobSpec(
            job_id="job-every",
            schedule_type=ScheduleType.EVERY,
            message="run-every",
            every_seconds=60,
            start_at_utc=base,
        ),
        now_utc=base,
    )

    tick = await scheduler.tick(now_utc=base)
    assert tick.due == 1
    assert tick.enqueued == 1
    run = await scheduler.run_pending(now_utc=base)
    assert run.executed == 1
    assert run.succeeded == 1
    assert executed == ["run-every"]

    record = scheduler.get_job("job-every")
    assert record is not None
    assert record.state.run_count == 1
    assert record.state.next_run_utc == base + timedelta(seconds=60)


@pytest.mark.asyncio
async def test_scheduler_at_job_runs_once():
    scheduler = AgentCronScheduler(max_queue=8, max_concurrent=1, grace_seconds=120)
    due_at = _dt(2026, 1, 1, 12, 30)
    scheduler.register_job(
        CronJobSpec(
            job_id="job-at",
            schedule_type=ScheduleType.AT,
            message="run-once",
            at_utc=due_at,
        ),
        now_utc=_dt(2026, 1, 1, 12, 0),
    )

    tick = await scheduler.tick(now_utc=due_at)
    assert tick.enqueued == 1
    run = await scheduler.run_pending(now_utc=due_at)
    assert run.executed == 1

    record = scheduler.get_job("job-at")
    assert record is not None
    assert record.state.next_run_utc is None
    assert record.state.run_count == 1

    tick_again = await scheduler.tick(now_utc=due_at + timedelta(minutes=5))
    assert tick_again.due == 0
    run_again = await scheduler.run_pending(now_utc=due_at + timedelta(minutes=5))
    assert run_again.executed == 0


@pytest.mark.asyncio
async def test_scheduler_queue_backpressure_drops_overflow():
    scheduler = AgentCronScheduler(max_queue=1, max_concurrent=1, grace_seconds=120)
    now = _dt(2026, 1, 1, 13, 0)
    scheduler.register_job(
        CronJobSpec(
            job_id="job-1",
            schedule_type=ScheduleType.EVERY,
            message="run-1",
            every_seconds=30,
            start_at_utc=now,
        ),
        now_utc=now,
    )
    scheduler.register_job(
        CronJobSpec(
            job_id="job-2",
            schedule_type=ScheduleType.EVERY,
            message="run-2",
            every_seconds=30,
            start_at_utc=now,
        ),
        now_utc=now,
    )

    tick = await scheduler.tick(now_utc=now)
    assert tick.due == 2
    assert tick.enqueued == 1
    assert tick.dropped == 1

    dropped_total = sum(item.state.dropped_runs for item in scheduler.list_jobs())
    assert dropped_total == 1


@pytest.mark.asyncio
async def test_scheduler_grace_window_miss_and_fast_forward():
    scheduler = AgentCronScheduler(max_queue=4, max_concurrent=1, grace_seconds=10)
    base = _dt(2026, 1, 1, 14, 0)
    scheduler.register_job(
        CronJobSpec(
            job_id="job-grace",
            schedule_type=ScheduleType.EVERY,
            message="run-grace",
            every_seconds=30,
            start_at_utc=base,
        ),
        now_utc=base,
    )

    late_now = base + timedelta(seconds=45)
    tick = await scheduler.tick(now_utc=late_now)
    assert tick.due == 1
    assert tick.missed == 1
    assert tick.enqueued == 0

    record = scheduler.get_job("job-grace")
    assert record is not None
    assert record.state.missed_runs == 1
    assert record.state.next_run_utc == base + timedelta(seconds=60)

    run = await scheduler.run_pending(now_utc=late_now)
    assert run.executed == 0


@pytest.mark.asyncio
async def test_scheduler_delivery_router_announce_mode():
    delivered_payloads: list[tuple[str | None, str]] = []

    async def _announce(payload):  # noqa: ANN001
        delivered_payloads.append((payload.target, payload.run_result.output))

    router = DeliveryRouter(announce_handler=_announce)
    scheduler = AgentCronScheduler(
        delivery_router=router,
        max_queue=4,
        max_concurrent=1,
        grace_seconds=120,
    )
    now = _dt(2026, 1, 1, 15, 0)
    scheduler.register_job(
        CronJobSpec(
            job_id="job-delivery",
            schedule_type=ScheduleType.EVERY,
            message="run-delivery",
            every_seconds=60,
            start_at_utc=now,
            delivery=DeliveryConfig(mode=DeliveryMode.ANNOUNCE, target="qq://group/1"),
        ),
        now_utc=now,
    )

    await scheduler.tick(now_utc=now)
    run = await scheduler.run_pending(now_utc=now)
    assert run.executed == 1
    assert run.deliveries_failed == 0
    assert delivered_payloads == [("qq://group/1", "[isolated-run] run-delivery")]
