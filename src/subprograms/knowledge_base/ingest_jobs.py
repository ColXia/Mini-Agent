"""Minimal in-memory ingest job queue for knowledge-base ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from threading import Lock
from typing import Any, Callable
from uuid import uuid4


def _utc_iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


Runner = Callable[[], dict[str, Any]]


@dataclass
class IngestJob:
    """Single ingest job record."""

    job_id: str
    kind: str
    payload: dict[str, Any]
    status: str = "queued"
    attempts: int = 0
    max_retries: int = 0
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str = field(default_factory=_utc_iso_now)
    updated_at: str = field(default_factory=_utc_iso_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "kind": self.kind,
            "status": self.status,
            "attempts": self.attempts,
            "max_retries": self.max_retries,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
            "result": self.result,
            "payload": self.payload,
        }


class IngestJobQueue:
    """Thread-safe minimal ingest queue with status tracking."""

    def __init__(self, max_jobs: int = 500) -> None:
        self._max_jobs = max(1, int(max_jobs))
        self._jobs: dict[str, IngestJob] = {}
        self._order: list[str] = []
        self._lock = Lock()

    def create_job(
        self, *, kind: str, payload: dict[str, Any], max_retries: int = 0
    ) -> IngestJob:
        with self._lock:
            job = IngestJob(
                job_id=f"ij_{uuid4().hex[:16]}",
                kind=str(kind),
                payload=dict(payload),
                max_retries=max(0, int(max_retries)),
            )
            self._jobs[job.job_id] = job
            self._order.append(job.job_id)
            self._trim_if_needed()
            return job

    def get_job(self, job_id: str) -> IngestJob | None:
        with self._lock:
            return self._jobs.get(str(job_id))

    def run_job(self, *, job_id: str, runner: Runner) -> IngestJob:
        with self._lock:
            job = self._jobs.get(str(job_id))
            if job is None:
                raise KeyError(f"job not found: {job_id}")
            job.status = "running"
            job.updated_at = _utc_iso_now()

        while True:
            with self._lock:
                job = self._jobs[str(job_id)]
                job.attempts += 1
                job.updated_at = _utc_iso_now()

            try:
                result = runner()
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    job = self._jobs[str(job_id)]
                    job.error = f"{type(exc).__name__}: {exc}"
                    job.result = None
                    if job.attempts <= job.max_retries:
                        job.status = "queued"
                        job.updated_at = _utc_iso_now()
                        continue
                    job.status = "failed"
                    job.updated_at = _utc_iso_now()
                return job

            with self._lock:
                job = self._jobs[str(job_id)]
                job.status = "succeeded"
                job.result = dict(result)
                job.error = None
                job.updated_at = _utc_iso_now()
                return job

    def retry_failed_job(self, *, job_id: str, runner: Runner) -> IngestJob:
        with self._lock:
            job = self._jobs.get(str(job_id))
            if job is None:
                raise KeyError(f"job not found: {job_id}")
            if job.status != "failed":
                raise ValueError("only failed jobs can be retried")
            job.status = "queued"
            job.error = None
            job.result = None
            job.updated_at = _utc_iso_now()
        return self.run_job(job_id=job_id, runner=runner)

    def summary(self) -> dict[str, Any]:
        with self._lock:
            counts: dict[str, int] = {}
            for job in self._jobs.values():
                counts[job.status] = counts.get(job.status, 0) + 1
            return {
                "total": len(self._jobs),
                "counts": counts,
            }

    def _trim_if_needed(self) -> None:
        while len(self._order) > self._max_jobs:
            oldest = self._order.pop(0)
            self._jobs.pop(oldest, None)
