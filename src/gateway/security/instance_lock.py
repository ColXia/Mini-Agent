"""Single-instance lock for gateway host:port bindings."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


class GatewayInstanceLockError(RuntimeError):
    """Raised when acquiring gateway instance lock fails."""


class GatewayInstanceLock:
    """Cross-process lock keyed by gateway host/port."""

    def __init__(self, host: str, port: int, lock_dir: str | Path | None = None):
        if not host:
            raise ValueError("host must not be empty.")
        if port <= 0:
            raise ValueError("port must be > 0.")

        if lock_dir is None:
            env_dir = os.getenv("MINI_AGENT_GATEWAY_LOCK_DIR")
            if env_dir:
                lock_dir = Path(env_dir)
            else:
                lock_dir = Path(tempfile.gettempdir()) / "mini-agent" / "gateway-locks"

        self.host = host
        self.port = port
        self.lock_dir = Path(lock_dir).expanduser().resolve()
        safe_host = host.replace(":", "_")
        self.path = self.lock_dir / f"{safe_host}_{port}.lock"
        self._handle = None

    @property
    def acquired(self) -> bool:
        return self._handle is not None

    def acquire(self) -> None:
        if self.acquired:
            return
        self.lock_dir.mkdir(parents=True, exist_ok=True)
        handle = open(self.path, "a+", encoding="utf-8")
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                handle.write("1")
                handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            handle.close()
            raise GatewayInstanceLockError(
                f"Gateway instance already running for {self.host}:{self.port}"
            ) from exc

        self._handle = handle

    def release(self) -> None:
        handle = self._handle
        if handle is None:
            return
        self._handle = None
        try:
            if os.name == "nt":
                import msvcrt

                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
        finally:
            handle.close()
