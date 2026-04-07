"""Chrome lifecycle baseline for agent-core browser control."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import inspect
from typing import Any, Awaitable, Callable
from urllib.parse import urlsplit


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_profile_name(name: str) -> str:
    normalized = str(name).strip()
    if not normalized:
        raise ValueError("profile name must not be empty.")
    return normalized


def _normalize_cdp_url(raw: str) -> str:
    text = str(raw).strip()
    if not text:
        raise ValueError("cdp_url must not be empty.")
    parsed = urlsplit(text)
    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https", "ws", "wss"}:
        raise ValueError("cdp_url must use http/https/ws/wss scheme.")
    if not parsed.hostname:
        raise ValueError("cdp_url must include a hostname.")
    return text


def _profile_key(name: str) -> str:
    return _normalize_profile_name(name).lower()


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@dataclass(frozen=True)
class BrowserProfile:
    """One browser profile with isolated runtime options."""

    name: str
    cdp_url: str
    headless: bool = True
    user_data_dir: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _normalize_profile_name(self.name))
        object.__setattr__(self, "cdp_url", _normalize_cdp_url(self.cdp_url))
        if self.user_data_dir is not None:
            path = self.user_data_dir.strip()
            object.__setattr__(self, "user_data_dir", path or None)
        object.__setattr__(self, "metadata", dict(self.metadata))


@dataclass(frozen=True)
class BrowserLaunchResult:
    """Launch outcome metadata from start handler."""

    pid: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class BrowserProfileState:
    """Runtime state for one profile."""

    profile: BrowserProfile
    running: bool = False
    started_utc: datetime | None = None
    stopped_utc: datetime | None = None
    last_healthy_utc: datetime | None = None
    pid: int | None = None
    launch_metadata: dict[str, Any] = field(default_factory=dict)


BrowserStartHandler = Callable[
    [BrowserProfile],
    Awaitable[BrowserLaunchResult | dict[str, Any] | int | None]
    | BrowserLaunchResult
    | dict[str, Any]
    | int
    | None,
]
BrowserStopHandler = Callable[[BrowserProfileState], Awaitable[None] | None]
BrowserHealthHandler = Callable[[BrowserProfileState], Awaitable[bool] | bool]


class ChromeLifecycleManager:
    """Minimal profile lifecycle manager for browser control."""

    def __init__(
        self,
        *,
        start_handler: BrowserStartHandler | None = None,
        stop_handler: BrowserStopHandler | None = None,
        health_handler: BrowserHealthHandler | None = None,
    ) -> None:
        self._start_handler = start_handler
        self._stop_handler = stop_handler
        self._health_handler = health_handler
        self._states: dict[str, BrowserProfileState] = {}

    def register_profile(self, profile: BrowserProfile) -> BrowserProfileState:
        key = _profile_key(profile.name)
        current = self._states.get(key)
        if current is None:
            next_state = BrowserProfileState(profile=profile)
        else:
            next_state = replace(current, profile=profile)
        self._states[key] = next_state
        return next_state

    def get_profile(self, name: str) -> BrowserProfileState | None:
        return self._states.get(_profile_key(name))

    def list_profiles(self) -> tuple[BrowserProfileState, ...]:
        return tuple(self._states[key] for key in sorted(self._states))

    async def start(self, name: str) -> BrowserProfileState:
        state = self._require_state(name)
        if state.running:
            return state

        raw_launch = None
        if self._start_handler is not None:
            raw_launch = await _maybe_await(self._start_handler(state.profile))
        launch = self._coerce_launch_result(raw_launch)
        now = _utc_now()
        next_state = replace(
            state,
            running=True,
            started_utc=now,
            stopped_utc=None,
            pid=launch.pid,
            launch_metadata=dict(launch.metadata),
        )
        self._states[_profile_key(name)] = next_state
        return next_state

    async def stop(self, name: str) -> BrowserProfileState:
        state = self._require_state(name)
        if not state.running:
            return state

        if self._stop_handler is not None:
            await _maybe_await(self._stop_handler(state))

        next_state = replace(
            state,
            running=False,
            stopped_utc=_utc_now(),
            pid=None,
        )
        self._states[_profile_key(name)] = next_state
        return next_state

    async def ensure_running(self, name: str) -> BrowserProfileState:
        state = self._require_state(name)
        if state.running:
            return state
        return await self.start(name)

    async def health(self, name: str) -> bool:
        state = self._require_state(name)
        if not state.running:
            return False
        if self._health_handler is None:
            healthy = True
        else:
            healthy = bool(await _maybe_await(self._health_handler(state)))

        if healthy:
            updated = replace(state, last_healthy_utc=_utc_now())
            self._states[_profile_key(name)] = updated
        return healthy

    def _require_state(self, name: str) -> BrowserProfileState:
        state = self.get_profile(name)
        if state is None:
            raise KeyError(f"browser profile not found: {name}")
        return state

    @staticmethod
    def _coerce_launch_result(raw: BrowserLaunchResult | dict[str, Any] | int | None) -> BrowserLaunchResult:
        if raw is None:
            return BrowserLaunchResult()
        if isinstance(raw, BrowserLaunchResult):
            return raw
        if isinstance(raw, int):
            return BrowserLaunchResult(pid=raw)
        if isinstance(raw, dict):
            pid_raw = raw.get("pid")
            pid = int(pid_raw) if isinstance(pid_raw, int) else None
            metadata_raw = raw.get("metadata", {})
            metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
            return BrowserLaunchResult(pid=pid, metadata=metadata)
        raise TypeError("start_handler must return BrowserLaunchResult, dict, int, or None.")
