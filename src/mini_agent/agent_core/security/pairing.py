"""DM pairing store baseline with file persistence and TTL pruning."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import secrets
import time
from typing import Any, Iterator


PAIRING_CODE_LENGTH = 8
PAIRING_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
DEFAULT_PENDING_TTL_SECONDS = 3600
DEFAULT_MAX_PENDING = 3


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_channel(channel: str) -> str:
    text = str(channel).strip().lower()
    if not text:
        raise ValueError("pairing channel must not be empty.")
    safe = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in text)
    safe = safe.strip("._")
    if not safe:
        raise ValueError("pairing channel is invalid.")
    return safe


def _normalize_entry_id(entry_id: str | int) -> str:
    text = str(entry_id).strip()
    if not text:
        raise ValueError("pairing entry id must not be empty.")
    return text


def _normalize_code(code: str) -> str:
    text = str(code).strip().upper()
    if not text:
        raise ValueError("pairing code must not be empty.")
    return text


def _normalize_utc(value: datetime | None) -> datetime:
    return (value or _utc_now()).astimezone(timezone.utc)


def _parse_iso_utc(value: str) -> datetime | None:
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _to_iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _dedupe_strings(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for item in items:
        normalized = item.strip()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def _generate_pairing_code(existing: set[str]) -> str:
    for _ in range(512):
        code = "".join(secrets.choice(PAIRING_CODE_ALPHABET) for _ in range(PAIRING_CODE_LENGTH))
        if code not in existing:
            return code
    raise RuntimeError("failed to generate a unique pairing code.")


class PairingLimitError(RuntimeError):
    """Raised when pending pairing requests hit limit."""


@dataclass(frozen=True)
class PairingRequest:
    """One pending pairing challenge."""

    channel: str
    entry_id: str
    code: str
    created_utc: datetime
    last_seen_utc: datetime
    metadata: dict[str, Any] = field(default_factory=dict)

    def expired(self, *, ttl_seconds: int, now_utc: datetime | None = None) -> bool:
        now = _normalize_utc(now_utc)
        return now - self.created_utc.astimezone(timezone.utc) > timedelta(seconds=max(1, int(ttl_seconds)))


@dataclass(frozen=True)
class PairingChannelState:
    """Current pairing channel state."""

    channel: str
    pending: tuple[PairingRequest, ...] = ()
    allow_from: tuple[str, ...] = ()


@dataclass
class _CacheEntry:
    mtime_ns: int
    size: int
    payload: dict[str, Any]


class PairingStore:
    """File-backed pairing store with TTL pruning and pending cap."""

    def __init__(
        self,
        *,
        storage_dir: str | os.PathLike[str] | None = None,
        pending_ttl_seconds: int = DEFAULT_PENDING_TTL_SECONDS,
        max_pending: int = DEFAULT_MAX_PENDING,
        lock_timeout_seconds: float = 3.0,
    ) -> None:
        self.storage_dir = Path(storage_dir or ".mini_agent/pairing").resolve()
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self.pending_ttl_seconds = max(1, int(pending_ttl_seconds))
        self.max_pending = max(1, int(max_pending))
        self.lock_timeout_seconds = max(0.1, float(lock_timeout_seconds))
        self._cache: dict[Path, _CacheEntry] = {}

    def upsert_request(
        self,
        *,
        channel: str,
        entry_id: str | int,
        metadata: dict[str, Any] | None = None,
        now_utc: datetime | None = None,
    ) -> PairingRequest:
        normalized_channel = _normalize_channel(channel)
        normalized_entry = _normalize_entry_id(entry_id)
        now = _normalize_utc(now_utc)

        with self._channel_lock(normalized_channel):
            state = self._read_state(normalized_channel)
            state, _ = self._prune_state(state, now_utc=now)
            pending = list(state.pending)
            for idx, request in enumerate(pending):
                if request.entry_id != normalized_entry:
                    continue
                updated = PairingRequest(
                    channel=normalized_channel,
                    entry_id=request.entry_id,
                    code=request.code,
                    created_utc=request.created_utc,
                    last_seen_utc=now,
                    metadata=dict(metadata or request.metadata),
                )
                pending[idx] = updated
                next_state = PairingChannelState(
                    channel=normalized_channel,
                    pending=tuple(sorted(pending, key=lambda item: item.created_utc)),
                    allow_from=state.allow_from,
                )
                self._write_state(next_state)
                return updated

            if len(pending) >= self.max_pending:
                raise PairingLimitError(
                    f"pending pairing limit reached for channel '{normalized_channel}' (max={self.max_pending})."
                )
            existing_codes = {item.code for item in pending}
            request = PairingRequest(
                channel=normalized_channel,
                entry_id=normalized_entry,
                code=_generate_pairing_code(existing_codes),
                created_utc=now,
                last_seen_utc=now,
                metadata=dict(metadata or {}),
            )
            pending.append(request)
            next_state = PairingChannelState(
                channel=normalized_channel,
                pending=tuple(sorted(pending, key=lambda item: item.created_utc)),
                allow_from=state.allow_from,
            )
            self._write_state(next_state)
            return request

    def list_pending(self, *, channel: str, now_utc: datetime | None = None) -> tuple[PairingRequest, ...]:
        normalized_channel = _normalize_channel(channel)
        now = _normalize_utc(now_utc)
        with self._channel_lock(normalized_channel):
            state = self._read_state(normalized_channel)
            pruned, changed = self._prune_state(state, now_utc=now)
            if changed:
                self._write_state(pruned)
            return pruned.pending

    def list_allowed(self, *, channel: str) -> tuple[str, ...]:
        normalized_channel = _normalize_channel(channel)
        with self._channel_lock(normalized_channel):
            state = self._read_state(normalized_channel)
            return state.allow_from

    def is_allowed(self, *, channel: str, entry_id: str | int) -> bool:
        normalized_entry = _normalize_entry_id(entry_id)
        return normalized_entry in self.list_allowed(channel=channel)

    def add_allowed(self, *, channel: str, entry_id: str | int) -> tuple[str, ...]:
        normalized_channel = _normalize_channel(channel)
        normalized_entry = _normalize_entry_id(entry_id)
        with self._channel_lock(normalized_channel):
            state = self._read_state(normalized_channel)
            allow_from = _dedupe_strings([*state.allow_from, normalized_entry])
            next_state = PairingChannelState(
                channel=normalized_channel,
                pending=state.pending,
                allow_from=tuple(allow_from),
            )
            self._write_state(next_state)
            return next_state.allow_from

    def approve_code(
        self,
        *,
        channel: str,
        code: str,
        now_utc: datetime | None = None,
    ) -> PairingRequest | None:
        normalized_channel = _normalize_channel(channel)
        normalized_code = _normalize_code(code)
        now = _normalize_utc(now_utc)
        with self._channel_lock(normalized_channel):
            state = self._read_state(normalized_channel)
            state, changed = self._prune_state(state, now_utc=now)
            pending = list(state.pending)
            approved: PairingRequest | None = None
            for idx, request in enumerate(pending):
                if request.code != normalized_code:
                    continue
                approved = request
                del pending[idx]
                break

            if approved is None:
                if changed:
                    self._write_state(state)
                return None

            allow_from = _dedupe_strings([*state.allow_from, approved.entry_id])
            next_state = PairingChannelState(
                channel=normalized_channel,
                pending=tuple(pending),
                allow_from=tuple(allow_from),
            )
            self._write_state(next_state)
            return approved

    def snapshot(self, *, channel: str, now_utc: datetime | None = None) -> PairingChannelState:
        normalized_channel = _normalize_channel(channel)
        now = _normalize_utc(now_utc)
        with self._channel_lock(normalized_channel):
            state = self._read_state(normalized_channel)
            state, changed = self._prune_state(state, now_utc=now)
            if changed:
                self._write_state(state)
            return state

    def _prune_state(self, state: PairingChannelState, *, now_utc: datetime) -> tuple[PairingChannelState, bool]:
        kept = [
            request
            for request in state.pending
            if not request.expired(ttl_seconds=self.pending_ttl_seconds, now_utc=now_utc)
        ]
        kept = sorted(kept, key=lambda item: item.last_seen_utc)
        if len(kept) > self.max_pending:
            kept = kept[-self.max_pending :]
        changed = tuple(kept) != state.pending
        if changed:
            return (
                PairingChannelState(
                    channel=state.channel,
                    pending=tuple(kept),
                    allow_from=state.allow_from,
                ),
                True,
            )
        return state, False

    def _state_path(self, channel: str) -> Path:
        return self.storage_dir / f"{channel}-pairing.json"

    def _lock_path(self, channel: str) -> Path:
        return self.storage_dir / f"{channel}-pairing.lock"

    @contextmanager
    def _channel_lock(self, channel: str) -> Iterator[None]:
        lock_path = self._lock_path(channel)
        deadline = time.monotonic() + self.lock_timeout_seconds
        lock_fd: int | None = None
        while True:
            try:
                lock_fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
                os.write(lock_fd, str(os.getpid()).encode("utf-8"))
                break
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"pairing lock timeout for channel '{channel}'")
                time.sleep(0.05)
        try:
            yield
        finally:
            if lock_fd is not None:
                try:
                    os.close(lock_fd)
                except OSError:
                    pass
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _read_state(self, channel: str) -> PairingChannelState:
        path = self._state_path(channel)
        if not path.exists():
            return PairingChannelState(channel=channel)

        stat = path.stat()
        cache = self._cache.get(path)
        payload: dict[str, Any] | None = None
        if cache and cache.mtime_ns == stat.st_mtime_ns and cache.size == stat.st_size:
            payload = dict(cache.payload)
        else:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                payload = {"version": 1, "pending": [], "allow_from": []}
            self._cache[path] = _CacheEntry(
                mtime_ns=stat.st_mtime_ns,
                size=stat.st_size,
                payload=dict(payload),
            )
        return self._decode_state(channel, payload)

    def _write_state(self, state: PairingChannelState) -> None:
        path = self._state_path(state.channel)
        payload = self._encode_state(state)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)
        stat = path.stat()
        self._cache[path] = _CacheEntry(
            mtime_ns=stat.st_mtime_ns,
            size=stat.st_size,
            payload=dict(payload),
        )

    def _decode_state(self, channel: str, payload: dict[str, Any]) -> PairingChannelState:
        pending_records = payload.get("pending", [])
        pending: list[PairingRequest] = []
        if isinstance(pending_records, list):
            for item in pending_records:
                if not isinstance(item, dict):
                    continue
                entry_id_raw = item.get("entry_id")
                code_raw = item.get("code")
                created_raw = item.get("created_utc")
                last_seen_raw = item.get("last_seen_utc")
                if entry_id_raw is None or code_raw is None or created_raw is None or last_seen_raw is None:
                    continue
                created = _parse_iso_utc(str(created_raw))
                last_seen = _parse_iso_utc(str(last_seen_raw))
                if created is None or last_seen is None:
                    continue
                try:
                    entry_id = _normalize_entry_id(str(entry_id_raw))
                    code = _normalize_code(str(code_raw))
                except ValueError:
                    continue
                metadata_raw = item.get("metadata", {})
                metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
                pending.append(
                    PairingRequest(
                        channel=channel,
                        entry_id=entry_id,
                        code=code,
                        created_utc=created,
                        last_seen_utc=last_seen,
                        metadata=metadata,
                    )
                )
        allow_raw = payload.get("allow_from", [])
        allow_from: tuple[str, ...]
        if isinstance(allow_raw, list):
            allow_from = tuple(_dedupe_strings([str(item) for item in allow_raw]))
        else:
            allow_from = ()
        return PairingChannelState(
            channel=channel,
            pending=tuple(sorted(pending, key=lambda item: item.created_utc)),
            allow_from=allow_from,
        )

    @staticmethod
    def _encode_state(state: PairingChannelState) -> dict[str, Any]:
        return {
            "version": 1,
            "pending": [
                {
                    "entry_id": request.entry_id,
                    "code": request.code,
                    "created_utc": _to_iso_utc(request.created_utc),
                    "last_seen_utc": _to_iso_utc(request.last_seen_utc),
                    "metadata": dict(request.metadata),
                }
                for request in state.pending
            ],
            "allow_from": list(state.allow_from),
        }
