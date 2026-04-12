"""Two-phase consolidation scheduler with lease/backoff baseline."""

from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from mini_agent.memory.consolidation_phase1 import Phase1ArtifactStore, Phase1Extractor
from mini_agent.memory.consolidation_phase2 import Phase2Consolidator, Phase2Result
from mini_agent.memory.memory_files import resolve_workspace_root
from mini_agent.session.persistence import SessionPersistence


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_utc(value: str | None) -> datetime:
    if not value:
        return datetime.fromtimestamp(0, tz=timezone.utc)
    normalized = value
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return datetime.fromtimestamp(0, tz=timezone.utc)


@dataclass(frozen=True)
class Phase1RunSummary:
    leased: int
    processed: int
    failed: int
    artifact_ids: list[str]
    errors: list[str]


class ConsolidationJobStore:
    """SQLite-backed job store for lease/retry control."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir.expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_dir / "consolidation" / "scheduler.sqlite3"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS jobs (
                    session_id TEXT PRIMARY KEY,
                    session_updated_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    leased_until TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    next_retry_at TEXT,
                    last_error TEXT,
                    last_artifact_id TEXT,
                    updated_at TEXT NOT NULL
                )
                """
            )
            conn.commit()

    def upsert_session_jobs(self, sessions: list[dict[str, Any]]) -> None:
        now_iso = _utc_iso(_utc_now())
        with self._connect() as conn:
            for session in sessions:
                session_id = str(session.get("session_id", "")).strip()
                updated_at = str(session.get("updated_at", "")).strip()
                if not session_id or not updated_at:
                    continue
                existing = conn.execute(
                    "SELECT session_updated_at FROM jobs WHERE session_id = ?",
                    (session_id,),
                ).fetchone()
                if existing is None:
                    conn.execute(
                        """
                        INSERT INTO jobs (
                            session_id, session_updated_at, status, leased_until,
                            attempts, next_retry_at, last_error, last_artifact_id, updated_at
                        ) VALUES (?, ?, 'pending', NULL, 0, NULL, NULL, NULL, ?)
                        """,
                        (session_id, updated_at, now_iso),
                    )
                    continue
                if str(existing["session_updated_at"]) != updated_at:
                    conn.execute(
                        """
                        UPDATE jobs
                        SET session_updated_at = ?, status = 'pending', leased_until = NULL,
                            next_retry_at = NULL, last_error = NULL, updated_at = ?
                        WHERE session_id = ?
                        """,
                        (updated_at, now_iso, session_id),
                    )
            conn.commit()

    def lease_jobs(
        self,
        *,
        max_jobs: int = 8,
        lease_seconds: int = 3600,
        now_utc: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = now_utc or _utc_now()
        now_iso = _utc_iso(now)
        lease_until_iso = _utc_iso(now + timedelta(seconds=max(1, int(lease_seconds))))
        leased: list[dict[str, Any]] = []
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT session_id, session_updated_at, status, leased_until, attempts, next_retry_at
                FROM jobs
                WHERE status IN ('pending', 'retry')
                ORDER BY session_updated_at DESC
                """
            ).fetchall()

            for row in rows:
                if len(leased) >= max(1, int(max_jobs)):
                    break
                leased_until = _parse_utc(str(row["leased_until"]) if row["leased_until"] else None)
                retry_at = _parse_utc(str(row["next_retry_at"]) if row["next_retry_at"] else None)
                if row["leased_until"] and leased_until > now:
                    continue
                if row["next_retry_at"] and retry_at > now:
                    continue
                session_id = str(row["session_id"])
                conn.execute(
                    """
                    UPDATE jobs
                    SET status = 'leased', leased_until = ?, updated_at = ?
                    WHERE session_id = ?
                    """,
                    (lease_until_iso, now_iso, session_id),
                )
                leased.append(
                    {
                        "session_id": session_id,
                        "session_updated_at": str(row["session_updated_at"]),
                    }
                )
            conn.commit()
        return leased

    def heartbeat(self, session_id: str, *, heartbeat_seconds: int = 90, now_utc: datetime | None = None) -> None:
        now = now_utc or _utc_now()
        lease_until_iso = _utc_iso(now + timedelta(seconds=max(1, int(heartbeat_seconds))))
        with self._connect() as conn:
            conn.execute(
                "UPDATE jobs SET leased_until = ?, updated_at = ? WHERE session_id = ?",
                (lease_until_iso, _utc_iso(now), session_id),
            )
            conn.commit()

    def mark_success(self, session_id: str, *, artifact_id: str | None = None, now_utc: datetime | None = None) -> None:
        now = now_utc or _utc_now()
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'done', leased_until = NULL, next_retry_at = NULL, last_error = NULL,
                    last_artifact_id = ?, updated_at = ?
                WHERE session_id = ?
                """,
                (artifact_id, _utc_iso(now), session_id),
            )
            conn.commit()

    def mark_failure(
        self,
        session_id: str,
        *,
        error: str,
        retry_seconds: int = 3600,
        now_utc: datetime | None = None,
    ) -> None:
        now = now_utc or _utc_now()
        retry_at = _utc_iso(now + timedelta(seconds=max(1, int(retry_seconds))))
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE jobs
                SET status = 'retry', leased_until = NULL,
                    attempts = attempts + 1,
                    next_retry_at = ?,
                    last_error = ?,
                    updated_at = ?
                WHERE session_id = ?
                """,
                (retry_at, error[:400], _utc_iso(now), session_id),
            )
            conn.commit()

    def stats(self) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(1) AS n FROM jobs GROUP BY status"
            ).fetchall()
        stats = {"pending": 0, "leased": 0, "retry": 0, "done": 0}
        for row in rows:
            status = str(row["status"])
            if status in stats:
                stats[status] = int(row["n"])
        return stats


class ConsolidationScheduler:
    """Bounded scheduler for phase1/phase2 consolidation."""

    def __init__(
        self,
        *,
        session_persistence: SessionPersistence,
        base_dir: Path,
        memory_file: Path,
        workspace_anchor_dir: Path | str | None = None,
    ):
        self.session_persistence = session_persistence
        self.job_store = ConsolidationJobStore(base_dir)
        self.phase1_store = Phase1ArtifactStore(base_dir)
        self.phase1_extractor = Phase1Extractor()
        self.phase2 = Phase2Consolidator(base_dir, memory_file)
        self.workspace_anchor_dir = (
            Path(workspace_anchor_dir).expanduser().resolve()
            if workspace_anchor_dir is not None
            else None
        )

    def _matches_workspace_anchor(self, workspace_dir: Any) -> bool:
        if self.workspace_anchor_dir is None:
            return True
        try:
            resolved_workspace_dir = resolve_workspace_root(str(workspace_dir or ""))
        except Exception:
            return False
        return resolved_workspace_dir == self.workspace_anchor_dir

    def _list_workspace_sessions(
        self,
        *,
        exclude_session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_excluded = str(exclude_session_id or "").strip()
        sessions: list[dict[str, Any]] = []
        for session in self.session_persistence.list_sessions():
            session_id = str(session.get("session_id", "")).strip()
            if not session_id:
                continue
            if normalized_excluded and session_id == normalized_excluded:
                continue
            if not self._matches_workspace_anchor(session.get("workspace_dir")):
                continue
            sessions.append(session)
        return sessions

    def run_phase1(
        self,
        *,
        max_jobs: int = 8,
        lease_seconds: int = 3600,
        retry_seconds: int = 3600,
        exclude_session_id: str | None = None,
    ) -> Phase1RunSummary:
        sessions = self._list_workspace_sessions(exclude_session_id=exclude_session_id)
        self.job_store.upsert_session_jobs(sessions)
        leased_jobs = self.job_store.lease_jobs(max_jobs=max_jobs, lease_seconds=lease_seconds)

        artifact_ids: list[str] = []
        errors: list[str] = []
        processed = 0
        failed = 0

        for job in leased_jobs:
            session_id = str(job["session_id"])
            try:
                record = self.session_persistence.load_session(session_id)
                if record is None:
                    raise ValueError(f"Session not found while consolidating: {session_id}")
                if not self._matches_workspace_anchor(record.get("workspace_dir")):
                    self.job_store.mark_success(session_id, artifact_id=None)
                    continue

                messages = record.get("messages", [])
                if not isinstance(messages, list):
                    messages = []
                artifact = self.phase1_extractor.extract(
                    session_id=session_id,
                    workspace_dir=str(record.get("workspace_dir", "")),
                    session_updated_at=str(record.get("updated_at", "")),
                    messages=messages,
                )
                self.phase1_store.save(artifact)
                self.job_store.mark_success(session_id, artifact_id=artifact.artifact_id)
                artifact_ids.append(artifact.artifact_id)
                processed += 1
            except Exception as exc:
                self.job_store.mark_failure(session_id, error=str(exc), retry_seconds=retry_seconds)
                errors.append(f"{session_id}: {exc}")
                failed += 1

        return Phase1RunSummary(
            leased=len(leased_jobs),
            processed=processed,
            failed=failed,
            artifact_ids=artifact_ids,
            errors=errors,
        )

    def run_phase2(self, *, top_n: int = 40) -> Phase2Result:
        artifacts = self.phase1_store.list_artifacts()
        return self.phase2.consolidate(artifacts, top_n=top_n)

    def run_all(
        self,
        *,
        max_jobs: int = 8,
        lease_seconds: int = 3600,
        retry_seconds: int = 3600,
        top_n: int = 40,
        exclude_session_id: str | None = None,
    ) -> dict[str, Any]:
        phase1 = self.run_phase1(
            max_jobs=max_jobs,
            lease_seconds=lease_seconds,
            retry_seconds=retry_seconds,
            exclude_session_id=exclude_session_id,
        )
        phase2 = self.run_phase2(top_n=top_n)
        return {
            "phase1": asdict(phase1),
            "phase2": asdict(phase2),
            "job_stats": self.job_store.stats(),
        }
