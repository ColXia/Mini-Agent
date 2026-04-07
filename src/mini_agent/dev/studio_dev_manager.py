"""Studio dev process manager.

Provides one-command process management for:
1. Studio backend host (`uvicorn` gateway)
2. Studio frontend dev server (`vite`)
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_DEV_PROFILE = "single-main"


def _utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _is_windows() -> bool:
    return os.name == "nt"


def _tasklist_alive(pid: int) -> bool:
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
    )
    text = (result.stdout or "").strip()
    if not text:
        return False
    if "No tasks are running" in text:
        return False
    if "INFO:" in text and "No tasks are running" in text:
        return False
    return str(pid) in text


def is_process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if _is_windows():
        try:
            return _tasklist_alive(pid)
        except Exception:
            return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def is_port_listening(host: str, port: int, timeout: float = 0.35) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def is_port_free(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        try:
            sock.bind((host, port))
            return True
        except OSError:
            return False


def _resolve_npm_executable() -> str:
    return "npm.cmd" if _is_windows() else "npm"


def _read_json_file(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def _tail_lines(path: Path, lines: int) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="replace")
    chunks = text.splitlines()
    if lines <= 0:
        return text
    return "\n".join(chunks[-lines:])


def _to_bool(value: Any, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _to_int(value: Any, default: int, minimum: int) -> int:
    if value is None:
        return max(minimum, default)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _to_float(value: Any, default: float, minimum: float) -> float:
    if value is None:
        return max(minimum, default)
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _terminate_process(pid: int, *, force: bool, grace_seconds: float = 8.0) -> bool:
    if not is_process_alive(pid):
        return True

    if _is_windows():
        cmd = ["taskkill", "/PID", str(pid), "/T"]
        if force:
            cmd.append("/F")
        subprocess.run(cmd, capture_output=True, text=True, check=False)
        deadline = time.time() + max(1.0, grace_seconds)
        while time.time() < deadline:
            if not is_process_alive(pid):
                return True
            time.sleep(0.2)
        if not force:
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
            time.sleep(0.4)
        return not is_process_alive(pid)

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return True
    deadline = time.time() + max(1.0, grace_seconds)
    while time.time() < deadline:
        if not is_process_alive(pid):
            return True
        time.sleep(0.2)
    if force:
        try:
            os.kill(pid, signal.SIGKILL)
        except OSError:
            return True
        time.sleep(0.2)
    return not is_process_alive(pid)


@dataclass(slots=True)
class StudioDevStatus:
    running: bool
    backend_running: bool
    frontend_running: bool
    host: str
    gateway_port: int
    frontend_port: int
    backend_pid: int | None
    frontend_pid: int | None
    state_file: Path
    backend_log: Path
    frontend_log: Path
    profile_name: str | None = None
    profile_source: str | None = None
    message: str = ""


@dataclass(slots=True)
class StudioDevProfile:
    name: str
    description: str
    host: str
    gateway_port: int
    frontend_port: int
    backend_reload: bool
    startup_timeout: float
    backend_env: dict[str, str]
    frontend_env: dict[str, str]
    source: str


class StudioDevManager:
    """Manage one backend + one frontend dev process."""

    def __init__(self, repo_root: Path, state_root: Path | None = None) -> None:
        self.repo_root = repo_root.resolve()
        self.frontend_dir = (self.repo_root / "apps" / "agent_studio").resolve()
        if state_root is None:
            self.state_dir = Path.home() / ".mini-agent" / "studio-dev"
        else:
            self.state_dir = state_root.resolve()
        self.logs_dir = self.state_dir / "logs"
        self.profiles_dir = self.state_dir / "profiles"
        self.state_file = self.state_dir / "state.json"
        self.backend_log_file = self.logs_dir / "backend.log"
        self.frontend_log_file = self.logs_dir / "frontend.log"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        self.profiles_dir.mkdir(parents=True, exist_ok=True)

    def profile_path(self, name: str) -> Path:
        normalized = self._normalize_profile_name(name)
        return self.profiles_dir / f"{normalized}.json"

    def ensure_profile_template(self, name: str) -> Path:
        path = self.profile_path(name)
        if path.exists():
            return path
        payload = self._default_profile_payload(self._normalize_profile_name(name))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def list_profiles(self) -> list[str]:
        names = {
            "single-main",
            "team-reserved",
        }
        if self.profiles_dir.exists():
            for item in self.profiles_dir.glob("*.json"):
                names.add(item.stem)
        return sorted(names)

    def resolve_profile(
        self,
        *,
        profile_name: str,
        host: str | None,
        gateway_port: int | None,
        frontend_port: int | None,
        backend_reload: bool | None,
        startup_timeout: float | None,
        ensure_exists: bool = True,
    ) -> StudioDevProfile:
        normalized = self._normalize_profile_name(profile_name)
        path = self.profile_path(normalized)
        if ensure_exists:
            self.ensure_profile_template(normalized)

        base = self._default_profile_payload(normalized)
        if path.exists():
            payload = _read_json_file(path)
            if payload is None:
                raise RuntimeError(f"Invalid dev profile JSON: {path}")
            merged = self._merge_profile_payloads(base, payload)
            source = str(path)
        else:
            merged = base
            source = f"builtin:{normalized}"

        profile = self._profile_from_payload(merged, source=source)
        if host is not None and str(host).strip():
            profile.host = str(host).strip()
        if gateway_port is not None:
            profile.gateway_port = _to_int(gateway_port, profile.gateway_port, 1)
        if frontend_port is not None:
            profile.frontend_port = _to_int(frontend_port, profile.frontend_port, 1)
        if backend_reload is not None:
            profile.backend_reload = bool(backend_reload)
        if startup_timeout is not None:
            profile.startup_timeout = _to_float(startup_timeout, profile.startup_timeout, 3.0)

        profile.backend_env = self._expand_env_map(
            profile.backend_env,
            host=profile.host,
            gateway_port=profile.gateway_port,
            frontend_port=profile.frontend_port,
        )
        profile.frontend_env = self._expand_env_map(
            profile.frontend_env,
            host=profile.host,
            gateway_port=profile.gateway_port,
            frontend_port=profile.frontend_port,
        )
        profile.frontend_env.setdefault("VITE_API_BASE", f"http://{profile.host}:{profile.gateway_port}")
        return profile

    def profile_to_dict(self, profile: StudioDevProfile) -> dict[str, Any]:
        return {
            "name": profile.name,
            "description": profile.description,
            "host": profile.host,
            "gateway_port": profile.gateway_port,
            "frontend_port": profile.frontend_port,
            "backend_reload": profile.backend_reload,
            "startup_timeout": profile.startup_timeout,
            "backend_env": dict(profile.backend_env),
            "frontend_env": dict(profile.frontend_env),
            "source": profile.source,
        }

    def _normalize_profile_name(self, name: str | None) -> str:
        raw = str(name or "").strip().lower()
        return raw or DEFAULT_DEV_PROFILE

    def _default_profile_payload(self, name: str) -> dict[str, Any]:
        mode = "team" if name in {"team", "team-reserved"} else "single_main"
        description = (
            "Team-ready profile (multi-workspace reserved mode)."
            if mode == "team"
            else "Default single-main profile (one main workspace + one active main agent)."
        )
        return {
            "name": name,
            "description": description,
            "host": "127.0.0.1",
            "gateway_port": 8008,
            "frontend_port": 5174,
            "backend_reload": True,
            "startup_timeout": 40.0,
            "backend_env": {
                "MINI_AGENT_STUDIO_ENABLE_INSTANCE_LOCK": "1",
                "MINI_AGENT_RUNTIME_MODE": mode,
                "MINI_AGENT_MAIN_WORKSPACE": "{{repo_root}}",
                "MINI_AGENT_TEAM_MAX_AGENTS": "4",
                "MINI_AGENT_NOVEL_PROFILE_ID": "novel-default",
                "MINI_AGENT_NOVEL_API_HOST": "https://api.minimaxi.com",
                "MINI_AGENT_NOVEL_STYLE_TYPE": "anime",
                "MINI_AGENT_NOVEL_STYLE_WEIGHT": "1.0",
                "MINI_AGENT_NOVEL_COVER_ASPECT_RATIO": "1:1",
                "MINI_AGENT_NOVEL_ILLUSTRATION_ASPECT_RATIO": "16:9",
                "MINI_AGENT_NOVEL_MEMORY_NAMESPACE": "novel-main",
                "MINI_AGENT_NOVEL_TOOL_PROFILE_ID": "novel-default-tools",
                "MINI_AGENT_NOVEL_ENABLE_TEXT_TOOLS": "1",
                "MINI_AGENT_NOVEL_ENABLE_IMAGE_TOOLS": "1",
                "MINI_AGENT_NOVEL_ENABLE_AUDIO_TOOLS": "1",
            },
            "frontend_env": {
                "VITE_API_BASE": "http://{{host}}:{{gateway_port}}",
            },
        }

    def _merge_profile_payloads(self, base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
        merged = dict(base)
        for key, value in override.items():
            if key in {"backend_env", "frontend_env"}:
                baseline = self._normalize_env_map(base.get(key))
                patch = self._normalize_env_map(value, allow_null_delete=True)
                result = dict(baseline)
                for env_key, env_value in patch.items():
                    if env_value is None:
                        result.pop(env_key, None)
                    else:
                        result[env_key] = env_value
                merged[key] = result
                continue
            merged[key] = value
        return merged

    def _profile_from_payload(self, payload: dict[str, Any], *, source: str) -> StudioDevProfile:
        name = self._normalize_profile_name(payload.get("name"))
        description = str(payload.get("description") or "").strip() or f"Profile `{name}`"
        host = str(payload.get("host") or "127.0.0.1").strip() or "127.0.0.1"
        gateway_port = _to_int(payload.get("gateway_port"), 8008, 1)
        frontend_port = _to_int(payload.get("frontend_port"), 5174, 1)
        backend_reload = _to_bool(payload.get("backend_reload"), True)
        startup_timeout = _to_float(payload.get("startup_timeout"), 40.0, 3.0)
        backend_env = self._normalize_env_map(payload.get("backend_env"))
        frontend_env = self._normalize_env_map(payload.get("frontend_env"))
        return StudioDevProfile(
            name=name,
            description=description,
            host=host,
            gateway_port=gateway_port,
            frontend_port=frontend_port,
            backend_reload=backend_reload,
            startup_timeout=startup_timeout,
            backend_env=backend_env,
            frontend_env=frontend_env,
            source=source,
        )

    def _normalize_env_map(self, value: Any, *, allow_null_delete: bool = False) -> dict[str, Any]:
        if not isinstance(value, dict):
            return {}
        normalized: dict[str, Any] = {}
        for raw_key, raw_value in value.items():
            key = str(raw_key).strip()
            if not key:
                continue
            if raw_value is None:
                if allow_null_delete:
                    normalized[key] = None
                continue
            normalized[key] = str(raw_value)
        return normalized

    def _expand_env_map(
        self,
        env_map: dict[str, str],
        *,
        host: str,
        gateway_port: int,
        frontend_port: int,
    ) -> dict[str, str]:
        variables = {
            "repo_root": str(self.repo_root),
            "frontend_dir": str(self.frontend_dir),
            "host": host,
            "gateway_port": str(gateway_port),
            "frontend_port": str(frontend_port),
        }
        expanded: dict[str, str] = {}
        for key, value in env_map.items():
            text = str(value)
            for var_name, var_value in variables.items():
                text = text.replace(f"{{{{{var_name}}}}}", var_value)
                text = text.replace(f"${{{var_name}}}", var_value)
            expanded[str(key)] = text
        return expanded

    def up(
        self,
        *,
        profile_name: str,
        host: str | None,
        gateway_port: int | None,
        frontend_port: int | None,
        backend_reload: bool | None,
        frontend_install: bool,
        startup_timeout: float | None,
    ) -> StudioDevStatus:
        profile = self.resolve_profile(
            profile_name=profile_name,
            host=host,
            gateway_port=gateway_port,
            frontend_port=frontend_port,
            backend_reload=backend_reload,
            startup_timeout=startup_timeout,
            ensure_exists=True,
        )
        host = profile.host
        gateway_port = profile.gateway_port
        frontend_port = profile.frontend_port
        backend_reload = profile.backend_reload
        startup_timeout = profile.startup_timeout

        current = self.status()
        if current.running:
            raise RuntimeError(
                "Studio dev stack is already running. Use `mini-agent dev status` or `mini-agent dev down` first."
            )
        if not is_port_free(host, gateway_port):
            raise RuntimeError(
                f"Gateway port {gateway_port} is already in use; cannot start another backend host."
            )
        if not is_port_free(host, frontend_port):
            raise RuntimeError(
                f"Frontend port {frontend_port} is already in use; cannot start another frontend server."
            )

        python_executable = Path(sys.executable).resolve()
        if not python_executable.exists():
            raise RuntimeError(f"Python executable not found: {python_executable}")
        if not self.frontend_dir.exists():
            raise RuntimeError(f"Frontend directory not found: {self.frontend_dir}")

        backend_env = os.environ.copy()
        backend_env["PYTHONUTF8"] = "1"
        backend_env["PYTHONIOENCODING"] = "utf-8"
        backend_env["MINI_AGENT_STUDIO_HOST"] = host
        backend_env["MINI_AGENT_STUDIO_PORT"] = str(gateway_port)
        for key, value in profile.backend_env.items():
            backend_env[str(key)] = str(value)

        backend_cmd = [
            str(python_executable),
            "-m",
            "uvicorn",
            "apps.agent_studio_gateway.main:app",
            "--host",
            host,
            "--port",
            str(gateway_port),
        ]
        if backend_reload:
            backend_cmd.append("--reload")

        frontend_env = os.environ.copy()
        for key, value in profile.frontend_env.items():
            frontend_env[str(key)] = str(value)
        frontend_cmd: list[str] = [_resolve_npm_executable()]
        if frontend_install and not (self.frontend_dir / "node_modules").exists():
            install_cmd = [_resolve_npm_executable(), "install"]
            self._run_blocking_command(install_cmd, cwd=self.frontend_dir, env=frontend_env)
        frontend_cmd.extend(
            [
                "run",
                "dev",
                "--",
                "--host",
                host,
                "--port",
                str(frontend_port),
                "--strictPort",
            ]
        )

        self.backend_log_file.parent.mkdir(parents=True, exist_ok=True)
        backend_log = self.backend_log_file.open("a", encoding="utf-8")
        frontend_log = self.frontend_log_file.open("a", encoding="utf-8")
        backend_proc = None
        frontend_proc = None
        try:
            backend_proc = self._spawn(
                backend_cmd,
                cwd=self.repo_root,
                env=backend_env,
                stdout=backend_log,
            )
            frontend_proc = self._spawn(
                frontend_cmd,
                cwd=self.frontend_dir,
                env=frontend_env,
                stdout=frontend_log,
            )
            self._wait_until_ready(
                backend_pid=backend_proc.pid,
                frontend_pid=frontend_proc.pid,
                host=host,
                gateway_port=gateway_port,
                frontend_port=frontend_port,
                timeout_seconds=startup_timeout,
            )
            state = {
                "host": host,
                "gateway_port": gateway_port,
                "frontend_port": frontend_port,
                "backend_pid": backend_proc.pid,
                "frontend_pid": frontend_proc.pid,
                "backend_log": str(self.backend_log_file),
                "frontend_log": str(self.frontend_log_file),
                "backend_reload": bool(backend_reload),
                "profile_name": profile.name,
                "profile_source": profile.source,
                "started_at": _utc_now(),
                "repo_root": str(self.repo_root),
            }
            self.state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
            return self.status()
        except Exception:
            if frontend_proc is not None:
                _terminate_process(frontend_proc.pid, force=True)
            if backend_proc is not None:
                _terminate_process(backend_proc.pid, force=True)
            raise
        finally:
            backend_log.close()
            frontend_log.close()

    def down(self, *, force: bool) -> StudioDevStatus:
        current = self.status()
        state = _read_json_file(self.state_file) or {}
        backend_pid = int(state.get("backend_pid") or 0)
        frontend_pid = int(state.get("frontend_pid") or 0)
        if backend_pid > 0:
            _terminate_process(backend_pid, force=force)
        if frontend_pid > 0:
            _terminate_process(frontend_pid, force=force)
        try:
            if self.state_file.exists():
                self.state_file.unlink()
        except Exception:
            pass
        stopped = self.status()
        if not current.running:
            stopped.message = "Studio dev stack was not running."
        return stopped

    def status(self) -> StudioDevStatus:
        state = _read_json_file(self.state_file) or {}
        host = str(state.get("host") or "127.0.0.1")
        gateway_port = int(state.get("gateway_port") or 8008)
        frontend_port = int(state.get("frontend_port") or 5174)
        backend_pid = int(state.get("backend_pid") or 0) or None
        frontend_pid = int(state.get("frontend_pid") or 0) or None
        profile_name = str(state.get("profile_name") or "").strip() or None
        profile_source = str(state.get("profile_source") or "").strip() or None
        backend_running = bool(backend_pid and is_process_alive(backend_pid) and is_port_listening(host, gateway_port))
        frontend_running = bool(
            frontend_pid and is_process_alive(frontend_pid) and is_port_listening(host, frontend_port)
        )
        running = backend_running and frontend_running
        message = ""
        if self.state_file.exists() and not running:
            message = "State file exists but one or more managed processes are not healthy."
        return StudioDevStatus(
            running=running,
            backend_running=backend_running,
            frontend_running=frontend_running,
            host=host,
            gateway_port=gateway_port,
            frontend_port=frontend_port,
            backend_pid=backend_pid,
            frontend_pid=frontend_pid,
            state_file=self.state_file,
            backend_log=self.backend_log_file,
            frontend_log=self.frontend_log_file,
            profile_name=profile_name,
            profile_source=profile_source,
            message=message,
        )

    def read_logs(self, *, target: str, lines: int) -> dict[str, str]:
        output: dict[str, str] = {}
        normalized = target.strip().lower()
        if normalized in {"backend", "all"}:
            output["backend"] = _tail_lines(self.backend_log_file, lines)
        if normalized in {"frontend", "all"}:
            output["frontend"] = _tail_lines(self.frontend_log_file, lines)
        if normalized not in {"backend", "frontend", "all"}:
            raise RuntimeError("Invalid log target. Use backend, frontend, or all.")
        return output

    def follow_logs(self, *, target: str) -> None:
        normalized = target.strip().lower()
        files: list[tuple[str, Path]] = []
        if normalized in {"backend", "all"}:
            files.append(("backend", self.backend_log_file))
        if normalized in {"frontend", "all"}:
            files.append(("frontend", self.frontend_log_file))
        if not files:
            raise RuntimeError("Invalid log target. Use backend, frontend, or all.")

        offsets: dict[str, int] = {}
        for key, path in files:
            if path.exists():
                offsets[key] = path.stat().st_size
            else:
                offsets[key] = 0

        while True:
            for key, path in files:
                if not path.exists():
                    continue
                start = offsets.get(key, 0)
                current_size = path.stat().st_size
                if current_size < start:
                    start = 0
                if current_size == start:
                    continue
                with path.open("r", encoding="utf-8", errors="replace") as file_obj:
                    file_obj.seek(start)
                    chunk = file_obj.read()
                offsets[key] = current_size
                if chunk:
                    for line in chunk.splitlines():
                        print(f"[{key}] {line}")
            time.sleep(0.5)

    def _run_blocking_command(self, cmd: list[str], *, cwd: Path, env: dict[str, str]) -> None:
        result = subprocess.run(
            cmd,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
            raise RuntimeError(f"Command failed ({' '.join(cmd)}): {output}")

    def _spawn(
        self,
        cmd: list[str],
        *,
        cwd: Path,
        env: dict[str, str],
        stdout: Any,
    ) -> subprocess.Popen[Any]:
        kwargs: dict[str, Any] = {
            "cwd": str(cwd),
            "env": env,
            "stdout": stdout,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.DEVNULL,
        }
        if _is_windows():
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]
        return subprocess.Popen(cmd, **kwargs)  # noqa: S603

    def _wait_until_ready(
        self,
        *,
        backend_pid: int,
        frontend_pid: int,
        host: str,
        gateway_port: int,
        frontend_port: int,
        timeout_seconds: float,
    ) -> None:
        deadline = time.time() + max(3.0, timeout_seconds)
        backend_ok = False
        frontend_ok = False
        while time.time() < deadline:
            if not is_process_alive(backend_pid):
                raise RuntimeError(
                    f"Backend process exited early (PID {backend_pid}). Check log: {self.backend_log_file}"
                )
            if not is_process_alive(frontend_pid):
                raise RuntimeError(
                    f"Frontend process exited early (PID {frontend_pid}). Check log: {self.frontend_log_file}"
                )
            if not backend_ok:
                backend_ok = is_port_listening(host, gateway_port)
            if not frontend_ok:
                frontend_ok = is_port_listening(host, frontend_port)
            if backend_ok and frontend_ok:
                return
            time.sleep(0.3)
        raise RuntimeError(
            "Dev stack startup timed out before both ports became ready. "
            f"Backend log: {self.backend_log_file} | Frontend log: {self.frontend_log_file}"
        )
