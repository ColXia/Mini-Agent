"""Runtime stack manager for gateway + the active QQ remote adapter."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
import signal
import shutil
import socket
import subprocess
import sys
import time
from typing import Any

def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _tail_lines(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    chunks = text.splitlines()
    if lines <= 0:
        return text
    return "\n".join(chunks[-lines:])


def _npm_executable() -> str:
    return "npm.cmd" if os.name == "nt" else "npm"


def _to_int(value: Any, default: int | None = None) -> int | None:
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def is_port_listening(host: str, port: int, *, timeout: float = 0.25) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_process_alive(pid: int | None) -> bool:
    if not pid or pid <= 0:
        return False
    if os.name == "nt":
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {int(pid)}", "/NH"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        stdout = (result.stdout or "").strip()
        if result.returncode != 0 or not stdout:
            return False
        lowered = stdout.lower()
        return str(pid) in stdout and "no tasks are running" not in lowered
    try:
        os.kill(int(pid), 0)
    except OSError:
        return False
    return True


def _terminate_process(pid: int | None, *, force: bool = False) -> bool:
    if not pid or pid <= 0:
        return False
    if not is_process_alive(pid):
        return True
    if os.name == "nt":
        command = ["taskkill", "/PID", str(int(pid)), "/T"]
        if force:
            command.append("/F")
        subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    else:
        sig = signal.SIGKILL if force else signal.SIGTERM
        try:
            os.kill(int(pid), sig)
        except OSError:
            return not is_process_alive(pid)
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if not is_process_alive(pid):
            return True
        time.sleep(0.1)
    return not is_process_alive(pid)


@dataclass(slots=True)
class RuntimeStackStatus:
    running: bool
    gateway_running: bool
    qqbot_running: bool
    host: str
    gateway_port: int
    workspace: Path
    gateway_pid: int | None
    qqbot_pid: int | None
    state_file: Path
    gateway_log: Path
    qqbot_log: Path
    qqbot_enabled: bool
    qqbot_configured: bool
    message: str = ""


class RuntimeStackManager:
    """Manage the local runtime stack used by TUI plus the active QQ remote adapter."""

    def __init__(
        self,
        *,
        source_root: Path,
        repo_root: Path | None = None,
        state_root: Path | None = None,
    ) -> None:
        self.source_root = source_root.resolve()
        self.repo_root = (repo_root or self.source_root.parent).resolve()
        self.qqbot_dir = (self.source_root / "apps" / "qqbot_channel").resolve()
        if state_root is None:
            self.state_dir = Path.home() / ".mini-agent" / "runtime-stack"
        else:
            self.state_dir = state_root.resolve()
        self.logs_dir = self.state_dir / "logs"
        self.state_file = self.state_dir / "state.json"
        self.gateway_log_file = self.logs_dir / "gateway.log"
        self.qqbot_log_file = self.logs_dir / "qqbot.log"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

    @property
    def qqbot_env_path(self) -> Path:
        return self.qqbot_dir / ".env"

    def _read_state(self) -> dict[str, Any] | None:
        if not self.state_file.exists():
            return None
        try:
            payload = json.loads(self.state_file.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _write_state(self, payload: dict[str, Any]) -> None:
        self.state_file.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _status_from_payload(self, payload: dict[str, Any] | None) -> RuntimeStackStatus:
        host = str((payload or {}).get("host") or "127.0.0.1")
        gateway_port = _to_int((payload or {}).get("gateway_port"), 8008) or 8008
        workspace_raw = (payload or {}).get("workspace")
        workspace = Path(workspace_raw).resolve() if workspace_raw else self.repo_root
        gateway_pid = _to_int((payload or {}).get("gateway_pid"))
        qqbot_pid = _to_int((payload or {}).get("qqbot_pid"))
        qqbot_enabled = bool((payload or {}).get("qqbot_enabled", False))
        qqbot_configured = self.qqbot_env_path.exists()

        gateway_running = bool(gateway_pid and is_process_alive(gateway_pid))
        qqbot_running = bool(qqbot_pid and is_process_alive(qqbot_pid))
        running = gateway_running or qqbot_running

        message = ""
        if payload and not running:
            message = "state exists but managed runtime processes are not running"
        elif payload and gateway_running and qqbot_enabled and not qqbot_running:
            message = "gateway is running but qqbot is not active"

        return RuntimeStackStatus(
            running=running,
            gateway_running=gateway_running,
            qqbot_running=qqbot_running,
            host=host,
            gateway_port=gateway_port,
            workspace=workspace,
            gateway_pid=gateway_pid if gateway_running else None,
            qqbot_pid=qqbot_pid if qqbot_running else None,
            state_file=self.state_file,
            gateway_log=self.gateway_log_file,
            qqbot_log=self.qqbot_log_file,
            qqbot_enabled=qqbot_enabled,
            qqbot_configured=qqbot_configured,
            message=message,
        )

    def status(self) -> RuntimeStackStatus:
        return self._status_from_payload(self._read_state())

    def _spawn_process(
        self,
        *,
        command: list[str],
        cwd: Path,
        env: dict[str, str],
        log_path: Path,
    ) -> int:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as handle:
            handle.write(f"\n[{_utc_now()}] start: {' '.join(command)}\n")
            handle.flush()
            creationflags = 0
            if os.name == "nt":
                creationflags = subprocess.CREATE_NEW_PROCESS_GROUP
            process = subprocess.Popen(
                command,
                cwd=str(cwd),
                env=env,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                creationflags=creationflags,
            )
        return int(process.pid)

    def _wait_for_gateway_ready(
        self,
        *,
        host: str,
        port: int,
        pid: int,
        timeout_seconds: float,
    ) -> None:
        deadline = time.time() + max(3.0, timeout_seconds)
        while time.time() < deadline:
            if is_port_listening(host, port):
                return
            if not is_process_alive(pid):
                tail = _tail_lines(self.gateway_log_file, 40)
                raise RuntimeError(
                    "Gateway failed to stay alive during startup.\n"
                    f"Last log lines:\n{tail or '(empty)'}"
                )
            time.sleep(0.25)
        raise RuntimeError(
            f"Gateway did not become ready at http://{host}:{port} within {timeout_seconds:.1f}s."
        )

    def _wait_for_process_stable(self, *, pid: int, label: str, log_path: Path) -> None:
        deadline = time.time() + 5.0
        while time.time() < deadline:
            if not is_process_alive(pid):
                tail = _tail_lines(log_path, 40)
                raise RuntimeError(
                    f"{label} exited during startup.\nLast log lines:\n{tail or '(empty)'}"
                )
            time.sleep(0.2)

    def _ensure_qqbot_prerequisites(self) -> str:
        if not self.qqbot_dir.exists():
            raise RuntimeError(f"QQ bot directory not found: {self.qqbot_dir}")
        if not self.qqbot_env_path.exists():
            raise RuntimeError(
                "QQ bot .env is missing. Copy `src/apps/qqbot_channel/.env.example` "
                "to `.env` and fill credentials first."
            )

        npm = shutil.which(_npm_executable()) or _npm_executable()
        if shutil.which(npm) is None and os.path.isabs(npm):
            raise RuntimeError("npm is not available in PATH.")

        node_modules_dir = self.qqbot_dir / "node_modules"
        if not node_modules_dir.exists():
            with self.qqbot_log_file.open("a", encoding="utf-8") as handle:
                handle.write(f"\n[{_utc_now()}] install: {npm} install\n")
                handle.flush()
                result = subprocess.run(
                    [npm, "install"],
                    cwd=str(self.qqbot_dir),
                    stdin=subprocess.DEVNULL,
                    stdout=handle,
                    stderr=subprocess.STDOUT,
                    check=False,
                )
            if result.returncode != 0:
                tail = _tail_lines(self.qqbot_log_file, 60)
                raise RuntimeError(
                    "QQ bot dependency install failed.\n"
                    f"Last log lines:\n{tail or '(empty)'}"
                )
        return npm

    def up(
        self,
        *,
        host: str,
        gateway_port: int,
        workspace: Path,
        qqbot: bool | None,
        approval_profile: str | None,
        access_level: str | None,
        startup_timeout: float = 20.0,
    ) -> RuntimeStackStatus:
        current = self.status()
        if current.running:
            raise RuntimeError(
                "Runtime stack is already running. Use `mini-agent stack status` "
                "or `mini-agent stack down` first."
            )

        if self.state_file.exists():
            self.state_file.unlink(missing_ok=True)

        if is_port_listening(host, gateway_port):
            raise RuntimeError(
                f"Gateway port {gateway_port} is already in use on {host}. "
                "Stop the existing process first."
            )

        workspace = workspace.resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        gateway_pid: int | None = None
        qqbot_pid: int | None = None
        qqbot_configured = self.qqbot_env_path.exists()
        if qqbot is None:
            qqbot_enabled = qqbot_configured
        else:
            qqbot_enabled = bool(qqbot)

        env = os.environ.copy()
        env.setdefault("PYTHONUTF8", "1")
        env.setdefault("PYTHONIOENCODING", "utf-8")
        if approval_profile:
            env["MINI_AGENT_APPROVAL_PROFILE"] = approval_profile
            env["MINI_AGENT_AGENT_MODE"] = approval_profile
        if access_level:
            env["MINI_AGENT_ACCESS_LEVEL"] = access_level

        try:
            gateway_command = [
                sys.executable,
                "-m",
                "mini_agent.cli",
                "serve",
                "--host",
                host,
                "--port",
                str(gateway_port),
                "--workspace",
                str(workspace),
            ]
            if approval_profile:
                gateway_command.extend(["--agent-mode", approval_profile])
            if access_level:
                gateway_command.extend(["--access-level", access_level])
            gateway_pid = self._spawn_process(
                command=gateway_command,
                cwd=self.repo_root,
                env=env,
                log_path=self.gateway_log_file,
            )
            self._wait_for_gateway_ready(
                host=host,
                port=gateway_port,
                pid=gateway_pid,
                timeout_seconds=startup_timeout,
            )

            if qqbot_enabled:
                npm = self._ensure_qqbot_prerequisites()
                qqbot_env = env.copy()
                qqbot_env["MINI_AGENT_GATEWAY_BASE"] = f"http://{host}:{gateway_port}"
                qqbot_pid = self._spawn_process(
                    command=[npm, "run", "start"],
                    cwd=self.qqbot_dir,
                    env=qqbot_env,
                    log_path=self.qqbot_log_file,
                )
                self._wait_for_process_stable(
                    pid=qqbot_pid,
                    label="QQ bot",
                    log_path=self.qqbot_log_file,
                )
        except Exception:
            if qqbot_pid:
                _terminate_process(qqbot_pid, force=True)
            if gateway_pid:
                _terminate_process(gateway_pid, force=True)
            raise

        payload = {
            "host": host,
            "gateway_port": gateway_port,
            "workspace": str(workspace),
            "gateway_pid": gateway_pid,
            "qqbot_pid": qqbot_pid,
            "qqbot_enabled": qqbot_enabled,
            "started_at": _utc_now(),
        }
        self._write_state(payload)

        status = self.status()
        if not qqbot_enabled and qqbot is None and not qqbot_configured:
            status.message = "qqbot .env not found, so QQ bot startup was skipped"
        elif not qqbot_enabled and qqbot is False:
            status.message = "qqbot startup disabled by flag"
        return status

    def down(self, *, force: bool = False) -> RuntimeStackStatus:
        payload = self._read_state()
        status = self._status_from_payload(payload)

        gateway_pid = _to_int((payload or {}).get("gateway_pid"))
        qqbot_pid = _to_int((payload or {}).get("qqbot_pid"))

        notes: list[str] = []
        if qqbot_pid:
            stopped = _terminate_process(qqbot_pid, force=force)
            notes.append("qqbot stopped" if stopped else "qqbot stop failed")
        if gateway_pid:
            stopped = _terminate_process(gateway_pid, force=force)
            notes.append("gateway stopped" if stopped else "gateway stop failed")

        self.state_file.unlink(missing_ok=True)

        return RuntimeStackStatus(
            running=False,
            gateway_running=False,
            qqbot_running=False,
            host=status.host,
            gateway_port=status.gateway_port,
            workspace=status.workspace,
            gateway_pid=None,
            qqbot_pid=None,
            state_file=self.state_file,
            gateway_log=self.gateway_log_file,
            qqbot_log=self.qqbot_log_file,
            qqbot_enabled=status.qqbot_enabled,
            qqbot_configured=status.qqbot_configured,
            message=", ".join(notes) if notes else "runtime stack already stopped",
        )

    def read_logs(self, *, target: str, lines: int = 120) -> dict[str, str]:
        payload: dict[str, str] = {}
        normalized = str(target or "all").strip().lower()
        if normalized in {"all", "gateway"}:
            payload["gateway"] = _tail_lines(self.gateway_log_file, lines)
        if normalized in {"all", "qqbot"}:
            payload["qqbot"] = _tail_lines(self.qqbot_log_file, lines)
        return payload
