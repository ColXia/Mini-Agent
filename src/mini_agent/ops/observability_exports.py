"""Filesystem retention utilities for observability export jobs."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TERMINAL_JOB_STATUSES = {"completed", "failed", "cancelled"}
_EXPORT_JOB_METADATA_VERSION = 1
_EXPORT_JOB_SNAPSHOT_VERSION = 1


@dataclass(frozen=True)
class _ExportJobRecord:
    """One persisted observability export-job metadata entry."""

    job_id: str
    metadata_file: Path
    payload: dict[str, Any]
    status: str
    completed_at: datetime | None
    updated_at: datetime


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _parse_iso_datetime(raw: Any) -> datetime | None:
    if not isinstance(raw, str):
        return None
    value = raw.strip()
    if not value:
        return None
    if value.endswith("Z"):
        value = f"{value[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(value)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_path_under(base_dir: Path, candidate: Path) -> Path | None:
    base = base_dir.resolve()
    try:
        resolved = candidate.resolve()
    except Exception:
        return None
    try:
        resolved.relative_to(base)
    except Exception:
        return None
    return resolved


def _export_job_metadata_dir(log_dir: Path) -> Path:
    return log_dir / "exports" / "jobs"


def _iter_export_job_metadata_files(log_dir: Path) -> list[Path]:
    metadata_dir = _export_job_metadata_dir(log_dir)
    if not metadata_dir.exists() or not metadata_dir.is_dir():
        return []
    return sorted(path for path in metadata_dir.glob("exp_*.json") if path.is_file())


def _load_export_job_records(log_dir: Path) -> list[_ExportJobRecord]:
    records: list[_ExportJobRecord] = []
    for metadata_file in _iter_export_job_metadata_files(log_dir):
        payload: dict[str, Any]
        try:
            loaded = json.loads(metadata_file.read_text(encoding="utf-8"))
            payload = loaded if isinstance(loaded, dict) else {}
        except Exception:
            payload = {}

        job_id = str(payload.get("job_id") or metadata_file.stem)
        status = str(payload.get("status") or "").strip().lower()
        completed_at = _parse_iso_datetime(payload.get("completed_at"))
        updated_at = _parse_iso_datetime(payload.get("updated_at"))
        if updated_at is None:
            updated_at = _parse_iso_datetime(payload.get("created_at"))
        if updated_at is None:
            updated_at = datetime.fromtimestamp(metadata_file.stat().st_mtime, timezone.utc)

        records.append(
            _ExportJobRecord(
                job_id=job_id,
                metadata_file=metadata_file,
                payload=payload,
                status=status,
                completed_at=completed_at,
                updated_at=updated_at,
            )
        )
    return records


def _resolve_artifact_file(log_dir: Path, payload: dict[str, Any]) -> Path | None:
    raw = payload.get("artifact_file")
    if not isinstance(raw, str) or not raw.strip():
        return None
    artifact = Path(raw.strip()).expanduser()
    if not artifact.is_absolute():
        artifact = log_dir / artifact
    return _safe_path_under(log_dir, artifact)


def _compute_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _write_snapshot(log_dir: Path, records: list[_ExportJobRecord]) -> None:
    metadata_dir = _export_job_metadata_dir(log_dir)
    metadata_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = metadata_dir / "snapshot.json"
    jobs: dict[str, dict[str, Any]] = {}
    for record in records:
        if not record.metadata_file.exists():
            continue
        updated_at = record.payload.get("updated_at")
        updated_at_str = (
            str(updated_at)
            if isinstance(updated_at, str) and updated_at.strip()
            else _to_utc_iso(record.updated_at)
        )
        jobs[record.job_id] = {
            "metadata_file": str(record.metadata_file.resolve()),
            "checksum_sha256": _compute_sha256(record.metadata_file),
            "status": record.status,
            "updated_at": updated_at_str,
        }

    snapshot_payload = {
        "snapshot_version": _EXPORT_JOB_SNAPSHOT_VERSION,
        "metadata_version": _EXPORT_JOB_METADATA_VERSION,
        "generated_at": _to_utc_iso(_utc_now()),
        "job_count": len(jobs),
        "jobs": jobs,
    }
    temp_path = snapshot_path.with_name(f"{snapshot_path.name}.tmp")
    temp_path.write_text(
        json.dumps(snapshot_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(snapshot_path)


def prune_observability_export_jobs(
    log_dir: str | Path,
    *,
    ttl_seconds: int | None = None,
    max_jobs: int | None = None,
) -> dict[str, int]:
    """Prune persisted observability export jobs and artifacts under one log dir."""
    resolved_log_dir = Path(log_dir).expanduser().resolve()
    now = _utc_now()
    resolved_ttl = (
        max(0, int(ttl_seconds))
        if ttl_seconds is not None
        else max(60, _env_int("MINI_AGENT_OBSERVABILITY_EXPORT_JOB_TTL_SECONDS", 3600))
    )
    resolved_max_jobs = (
        max(0, int(max_jobs))
        if max_jobs is not None
        else max(10, _env_int("MINI_AGENT_OBSERVABILITY_EXPORT_JOB_MAX", 200))
    )

    records = _load_export_job_records(resolved_log_dir)
    to_remove: dict[Path, _ExportJobRecord] = {}

    for record in records:
        if record.status not in _TERMINAL_JOB_STATUSES:
            continue
        if record.completed_at is None:
            continue
        if (now - record.completed_at).total_seconds() > resolved_ttl:
            to_remove[record.metadata_file] = record

    projected_remaining = len(records) - len(to_remove)
    if projected_remaining > resolved_max_jobs:
        removable_by_age = sorted(
            (
                record
                for record in records
                if record.status in _TERMINAL_JOB_STATUSES and record.metadata_file not in to_remove
            ),
            key=lambda item: item.updated_at,
        )
        for record in removable_by_age:
            if projected_remaining <= resolved_max_jobs:
                break
            to_remove[record.metadata_file] = record
            projected_remaining -= 1

    removed_jobs = 0
    removed_metadata_files = 0
    removed_artifact_files = 0

    for record in sorted(to_remove.values(), key=lambda item: item.updated_at):
        removed_jobs += 1

        artifact_file = _resolve_artifact_file(resolved_log_dir, record.payload)
        if artifact_file and artifact_file.exists() and artifact_file.is_file():
            try:
                artifact_file.unlink()
                removed_artifact_files += 1
            except Exception:
                pass

        if record.metadata_file.exists():
            try:
                record.metadata_file.unlink()
                removed_metadata_files += 1
            except Exception:
                pass

    remaining_records = _load_export_job_records(resolved_log_dir)
    try:
        _write_snapshot(resolved_log_dir, remaining_records)
    except Exception:
        pass

    return {
        "removed_jobs": removed_jobs,
        "removed_metadata_files": removed_metadata_files,
        "removed_artifact_files": removed_artifact_files,
        "remaining_jobs": len(remaining_records),
    }
