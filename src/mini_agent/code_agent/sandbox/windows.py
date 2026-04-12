"""Windows restricted-token sandbox baseline for code-agent execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import os
from pathlib import Path
import re
import subprocess
from typing import Any

from mini_agent.code_agent.sandbox.network import NetworkDomainPolicy

try:  # pragma: no cover - importability varies by host platform
    import msvcrt
    import win32api
    import win32con
    import win32event
    import win32job
    import win32pipe
    import win32process
    import win32security
except Exception:  # pragma: no cover - non-Windows or missing optional dependency
    msvcrt = None
    win32api = None
    win32con = None
    win32event = None
    win32job = None
    win32pipe = None
    win32process = None
    win32security = None


_ELEVATION_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bstart-process\b[^\n]*\s-verb\s+runas\b", re.IGNORECASE), "runas_elevation"),
    (re.compile(r"\bset-executionpolicy\b", re.IGNORECASE), "execution_policy_mutation"),
    (re.compile(r"\breg(\.exe)?\s+add\s+HKLM\\", re.IGNORECASE), "hklm_registry_write"),
    (re.compile(r"\bsc(\.exe)?\s+", re.IGNORECASE), "service_control"),
    (re.compile(r"\bshutdown\b|\brestart-computer\b", re.IGNORECASE), "host_shutdown"),
)

_DEFAULT_DISABLED_WELL_KNOWN_SIDS: tuple[str, ...] = (
    "WinBuiltinAdministratorsSid",
    "WinBuiltinPowerUsersSid",
    "WinBuiltinBackupOperatorsSid",
    "WinBuiltinAccountOperatorsSid",
    "WinBuiltinSystemOperatorsSid",
    "WinBuiltinPrintOperatorsSid",
    "WinBuiltinNetworkConfigurationOperatorsSid",
)

_DEFAULT_UI_LIMITS: tuple[str, ...] = (
    "JOB_OBJECT_UILIMIT_DESKTOP",
    "JOB_OBJECT_UILIMIT_EXITWINDOWS",
    "JOB_OBJECT_UILIMIT_GLOBALATOMS",
    "JOB_OBJECT_UILIMIT_HANDLES",
    "JOB_OBJECT_UILIMIT_READCLIPBOARD",
    "JOB_OBJECT_UILIMIT_SYSTEMPARAMETERS",
    "JOB_OBJECT_UILIMIT_WRITECLIPBOARD",
)

_DEFAULT_MAX_PROCESSES = 32
_DEFAULT_MAX_PROCESS_MEMORY_MB = 2048


def expected_mandatory_policy_bits() -> int:
    if win32security is None:
        return 3
    return int(
        getattr(win32security, "TOKEN_MANDATORY_POLICY_NO_WRITE_UP", 1)
        | getattr(win32security, "TOKEN_MANDATORY_POLICY_NEW_PROCESS_MIN", 2)
    )


def _normalize_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except Exception:
        return False


def _native_windows_launch_supported() -> bool:
    return all(
        value is not None
        for value in (
            msvcrt,
            win32api,
            win32con,
            win32event,
            win32job,
            win32pipe,
            win32process,
            win32security,
        )
    )


def _normalize_optional_positive_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except Exception:
        return None
    return parsed if parsed > 0 else None


class _AsyncWindowsPipeReader:
    def __init__(self, file_obj):
        self._file_obj = file_obj

    async def readline(self) -> bytes:
        if self._file_obj is None:
            return b""
        return await asyncio.to_thread(self._file_obj.readline)


class WindowsSandboxedProcess:
    """Minimal process adapter compatible with BashTool expectations."""

    def __init__(
        self,
        *,
        process_handle,
        thread_handle,
        job_handle,
        stdout_file,
        stderr_file,
        pid: int,
    ) -> None:
        self._process_handle = process_handle
        self._thread_handle = thread_handle
        self._job_handle = job_handle
        self._stdout_file = stdout_file
        self._stderr_file = stderr_file
        self._closed_kernel_handles = False
        self._returncode: int | None = None
        self.pid = int(pid)
        self.stdout = _AsyncWindowsPipeReader(stdout_file) if stdout_file is not None else None
        self.stderr = _AsyncWindowsPipeReader(stderr_file) if stderr_file is not None else None

    @property
    def returncode(self) -> int | None:
        if self._returncode is not None:
            return self._returncode
        if self._process_handle is None:
            return None
        exit_code = win32process.GetExitCodeProcess(self._process_handle)
        if exit_code == win32con.STILL_ACTIVE:
            return None
        self._returncode = int(exit_code)
        return self._returncode

    def _close_kernel_handles(self) -> None:
        if self._closed_kernel_handles:
            return
        self._closed_kernel_handles = True
        for handle in (self._thread_handle, self._process_handle, self._job_handle):
            if handle is None:
                continue
            try:
                win32api.CloseHandle(handle)
            except Exception:
                pass
        self._thread_handle = None
        self._process_handle = None
        self._job_handle = None

    async def wait(self) -> int:
        if self.returncode is None:
            await asyncio.to_thread(
                win32event.WaitForSingleObject,
                self._process_handle,
                win32event.INFINITE,
            )
            _ = self.returncode
        self._close_kernel_handles()
        return self._returncode if self._returncode is not None else -1

    def terminate(self) -> None:
        if self.returncode is None and self._process_handle is not None:
            win32api.TerminateProcess(self._process_handle, 1)

    def kill(self) -> None:
        if self.returncode is None and self._process_handle is not None:
            win32api.TerminateProcess(self._process_handle, 9)

    async def communicate(self) -> tuple[bytes, bytes]:
        stdout_task = asyncio.create_task(asyncio.to_thread(self._read_remaining, self._stdout_file))
        stderr_task = asyncio.create_task(asyncio.to_thread(self._read_remaining, self._stderr_file))
        await self.wait()
        stdout = await stdout_task
        stderr = await stderr_task
        self._close_streams()
        return stdout, stderr

    def _read_remaining(self, file_obj) -> bytes:
        if file_obj is None:
            return b""
        try:
            return file_obj.read()
        except Exception:
            return b""

    def _close_streams(self) -> None:
        for attr in ("_stdout_file", "_stderr_file"):
            file_obj = getattr(self, attr, None)
            if file_obj is None:
                continue
            try:
                file_obj.close()
            except Exception:
                pass
            setattr(self, attr, None)


def _detach_pipe_to_file(handle):
    detached = int(handle.Detach())
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    fd = msvcrt.open_osfhandle(detached, flags)
    return os.fdopen(fd, "rb", closefd=True, buffering=0)


def _build_job_object(policy: "WindowsSandboxPolicy"):
    job = win32job.CreateJobObject(None, "")
    info = win32job.QueryInformationJobObject(
        job,
        win32job.JobObjectExtendedLimitInformation,
    )
    info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if policy.die_on_unhandled_exception:
        info["BasicLimitInformation"]["LimitFlags"] |= (
            win32job.JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION
        )
    if policy.max_processes is not None:
        info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_ACTIVE_PROCESS
        info["BasicLimitInformation"]["ActiveProcessLimit"] = int(policy.max_processes)
    if policy.max_process_memory_mb is not None:
        info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_PROCESS_MEMORY
        info["ProcessMemoryLimit"] = int(policy.max_process_memory_mb) * 1024 * 1024
    win32job.SetInformationJobObject(
        job,
        win32job.JobObjectExtendedLimitInformation,
        info,
    )
    if policy.restrict_ui:
        ui_flags = 0
        for name in _DEFAULT_UI_LIMITS:
            ui_flags |= int(getattr(win32job, name, 0))
        win32job.SetInformationJobObject(
            job,
            win32job.JobObjectBasicUIRestrictions,
            {"UIRestrictionsClass": ui_flags},
        )
    return job


def _build_disabled_sid_list() -> list[tuple[Any, int]]:
    disabled: list[tuple[Any, int]] = []
    for name in _DEFAULT_DISABLED_WELL_KNOWN_SIDS:
        sid_type = getattr(win32security, name, None)
        if sid_type is None:
            continue
        try:
            sid = win32security.CreateWellKnownSid(sid_type, None)
        except Exception:
            continue
        disabled.append((sid, 0))
    return disabled


def _apply_integrity_level(token, policy: "WindowsSandboxPolicy") -> None:
    if not policy.low_integrity:
        return
    low_sid = win32security.CreateWellKnownSid(win32security.WinLowLabelSid, None)
    win32security.SetTokenInformation(
        token,
        win32security.TokenIntegrityLevel,
        (
            low_sid,
            int(win32security.SE_GROUP_INTEGRITY | win32security.SE_GROUP_INTEGRITY_ENABLED),
        ),
    )


def _create_restricted_primary_token(policy: "WindowsSandboxPolicy"):
    current_token = win32security.OpenProcessToken(
        win32api.GetCurrentProcess(),
        win32con.TOKEN_DUPLICATE
        | win32con.TOKEN_ASSIGN_PRIMARY
        | win32con.TOKEN_QUERY
        | win32con.TOKEN_ADJUST_DEFAULT
        | win32con.TOKEN_ADJUST_PRIVILEGES,
    )
    try:
        disabled_sids = _build_disabled_sid_list() if policy.disable_admin_groups else []
        token = win32security.CreateRestrictedToken(
            current_token,
            win32security.DISABLE_MAX_PRIVILEGE,
            disabled_sids,
            [],
            [],
        )
        _apply_integrity_level(token, policy)
        return token
    finally:
        try:
            win32api.CloseHandle(current_token)
        except Exception:
            pass


def _build_inheritable_pipe_pair():
    security_attributes = win32security.SECURITY_ATTRIBUTES()
    security_attributes.bInheritHandle = True
    return win32pipe.CreatePipe(security_attributes, 0)


@dataclass(frozen=True)
class SandboxTransformResult:
    """Transformed command payload for sandbox-aware execution."""

    command: str
    cwd: str | None
    env_overrides: dict[str, str]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class WindowsSandboxPolicy:
    """Windows sandbox policy baseline."""

    workspace_root: str
    readable_roots: tuple[str, ...] = field(default_factory=tuple)
    writable_roots: tuple[str, ...] = field(default_factory=tuple)
    restricted_token: bool = True
    enforce_no_profile: bool = True
    deny_elevation: bool = True
    low_integrity: bool = True
    disable_admin_groups: bool = True
    die_on_unhandled_exception: bool = True
    restrict_ui: bool = True
    max_processes: int | None = _DEFAULT_MAX_PROCESSES
    max_process_memory_mb: int | None = _DEFAULT_MAX_PROCESS_MEMORY_MB
    network_policy: NetworkDomainPolicy = field(default_factory=NetworkDomainPolicy)

    @staticmethod
    def from_workspace(
        workspace_root: str | Path,
        *,
        network_policy: NetworkDomainPolicy | None = None,
        max_processes: int | None = _DEFAULT_MAX_PROCESSES,
        max_process_memory_mb: int | None = _DEFAULT_MAX_PROCESS_MEMORY_MB,
    ) -> "WindowsSandboxPolicy":
        root = _normalize_path(workspace_root)
        return WindowsSandboxPolicy(
            workspace_root=str(root),
            readable_roots=(str(root),),
            writable_roots=(str(root),),
            max_processes=max_processes,
            max_process_memory_mb=max_process_memory_mb,
            network_policy=(network_policy or NetworkDomainPolicy()).normalized(),
        )

    def normalized(self) -> "WindowsSandboxPolicy":
        workspace_root = str(_normalize_path(self.workspace_root))
        readable = {
            str(_normalize_path(value))
            for value in self.readable_roots
            if str(value).strip()
        }
        writable = {
            str(_normalize_path(value))
            for value in self.writable_roots
            if str(value).strip()
        }
        if not readable:
            readable = {workspace_root}
        if not writable:
            writable = {workspace_root}
        return WindowsSandboxPolicy(
            workspace_root=workspace_root,
            readable_roots=tuple(sorted(readable)),
            writable_roots=tuple(sorted(writable)),
            restricted_token=bool(self.restricted_token),
            enforce_no_profile=bool(self.enforce_no_profile),
            deny_elevation=bool(self.deny_elevation),
            low_integrity=bool(self.low_integrity),
            disable_admin_groups=bool(self.disable_admin_groups),
            die_on_unhandled_exception=bool(self.die_on_unhandled_exception),
            restrict_ui=bool(self.restrict_ui),
            max_processes=_normalize_optional_positive_int(self.max_processes),
            max_process_memory_mb=_normalize_optional_positive_int(self.max_process_memory_mb),
            network_policy=self.network_policy.normalized(),
        )


class WindowsRestrictedSandbox:
    """Windows command sandbox with lightweight policy validation."""

    def __init__(self, policy: WindowsSandboxPolicy):
        self.policy = policy.normalized()

    def select_initial(self) -> dict[str, Any]:
        return {
            "backend": "windows_restricted_token",
            "restricted_token": self.policy.restricted_token,
            "workspace_root": self.policy.workspace_root,
            "network_mode": self.policy.network_policy.mode.value,
            "low_integrity": self.policy.low_integrity,
            "mandatory_policy": expected_mandatory_policy_bits(),
            "disable_admin_groups": self.policy.disable_admin_groups,
            "restrict_ui": self.policy.restrict_ui,
            "die_on_unhandled_exception": self.policy.die_on_unhandled_exception,
            "max_processes": self.policy.max_processes,
            "max_process_memory_mb": self.policy.max_process_memory_mb,
        }

    def validate_cwd(self, cwd: str | Path | None) -> str | None:
        if cwd is None:
            return None
        normalized_cwd = _normalize_path(cwd)
        allowed_roots = [Path(value) for value in self.policy.writable_roots]
        if not any(_is_relative_to(normalized_cwd, root) for root in allowed_roots):
            raise PermissionError(
                f"cwd '{normalized_cwd}' is outside writable sandbox roots: {self.policy.writable_roots}"
            )
        return str(normalized_cwd)

    def _check_elevation(self, command: str) -> None:
        if not self.policy.deny_elevation:
            return
        for pattern, reason in _ELEVATION_PATTERNS:
            if pattern.search(command):
                raise PermissionError(f"Blocked by Windows sandbox elevated-command policy: {reason}")

    def _check_network(self, command: str) -> None:
        allowed, blocked = self.policy.network_policy.validate_command(command)
        if not allowed:
            raise PermissionError(
                f"Blocked by Windows sandbox network policy ({self.policy.network_policy.mode.value}): {blocked}"
            )

    def transform(
        self,
        command: str,
        *,
        cwd: str | Path | None = None,
    ) -> SandboxTransformResult:
        normalized_command = str(command or "").strip()
        if not normalized_command:
            raise ValueError("command must not be empty.")

        self._check_elevation(normalized_command)
        self._check_network(normalized_command)
        normalized_cwd = self.validate_cwd(cwd)

        prefix_parts = [
            "$ErrorActionPreference='Stop'",
            "$ProgressPreference='SilentlyContinue'",
        ]
        if self.policy.enforce_no_profile:
            prefix_parts.append("$env:MINI_AGENT_SANDBOX_PROFILE='no_profile'")
        wrapped = "; ".join(prefix_parts + [normalized_command])

        env_overrides = {
            "MINI_AGENT_SANDBOX_BACKEND": "windows_restricted_token",
            "MINI_AGENT_SANDBOX_RESTRICTED_TOKEN": "1" if self.policy.restricted_token else "0",
            "MINI_AGENT_SANDBOX_WORKSPACE": self.policy.workspace_root,
            "MINI_AGENT_SANDBOX_NETWORK_MODE": self.policy.network_policy.mode.value,
            "MINI_AGENT_SANDBOX_NATIVE_LAUNCH": "1",
            "MINI_AGENT_SANDBOX_INTEGRITY_LEVEL": "low" if self.policy.low_integrity else "default",
            "MINI_AGENT_SANDBOX_MANDATORY_POLICY": str(expected_mandatory_policy_bits()),
        }
        if self.policy.max_processes is not None:
            env_overrides["MINI_AGENT_SANDBOX_MAX_PROCESSES"] = str(self.policy.max_processes)
        if self.policy.max_process_memory_mb is not None:
            env_overrides["MINI_AGENT_SANDBOX_PROCESS_MEMORY_MB"] = str(self.policy.max_process_memory_mb)

        return SandboxTransformResult(
            command=wrapped,
            cwd=normalized_cwd,
            env_overrides=env_overrides,
            metadata={
                "backend": "windows_restricted_token",
                "restricted_token": self.policy.restricted_token,
                "readable_roots": list(self.policy.readable_roots),
                "writable_roots": list(self.policy.writable_roots),
                "network_mode": self.policy.network_policy.mode.value,
                "low_integrity": self.policy.low_integrity,
                "mandatory_policy": expected_mandatory_policy_bits(),
                "disable_admin_groups": self.policy.disable_admin_groups,
                "restrict_ui": self.policy.restrict_ui,
                "die_on_unhandled_exception": self.policy.die_on_unhandled_exception,
                "max_processes": self.policy.max_processes,
                "max_process_memory_mb": self.policy.max_process_memory_mb,
            },
        )

    def launch_process(
        self,
        argv: list[str],
        *,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        merge_stderr: bool = False,
    ) -> WindowsSandboxedProcess:
        if not _native_windows_launch_supported():
            raise RuntimeError(
                "Windows restricted sandbox native launch requires pywin32 on Windows."
            )

        if not argv:
            raise ValueError("argv must not be empty.")

        normalized_cwd = self.validate_cwd(cwd) or self.policy.workspace_root
        environment = {
            str(key): str(value)
            for key, value in os.environ.items()
        }
        environment.update(
            {
                str(key): str(value)
                for key, value in (env or {}).items()
            }
        )
        command_line = subprocess.list2cmdline([str(item) for item in argv])

        stdout_read = stdout_write = None
        stderr_read = stderr_write = None
        stdin_read = stdin_write = None
        restricted_token = None
        process_handle = None
        thread_handle = None
        job_handle = None

        try:
            stdout_read, stdout_write = _build_inheritable_pipe_pair()
            win32api.SetHandleInformation(stdout_read, win32con.HANDLE_FLAG_INHERIT, 0)

            if merge_stderr:
                stderr_target = stdout_write
            else:
                stderr_read, stderr_write = _build_inheritable_pipe_pair()
                win32api.SetHandleInformation(stderr_read, win32con.HANDLE_FLAG_INHERIT, 0)
                stderr_target = stderr_write

            stdin_read, stdin_write = _build_inheritable_pipe_pair()
            win32api.SetHandleInformation(stdin_write, win32con.HANDLE_FLAG_INHERIT, 0)

            startup = win32process.STARTUPINFO()
            startup.dwFlags |= win32con.STARTF_USESTDHANDLES | win32con.STARTF_USESHOWWINDOW
            startup.wShowWindow = win32con.SW_HIDE
            startup.hStdInput = stdin_read
            startup.hStdOutput = stdout_write
            startup.hStdError = stderr_target

            restricted_token = _create_restricted_primary_token(self.policy)
            job_handle = _build_job_object(self.policy)

            process_handle, thread_handle, pid, _thread_id = win32process.CreateProcessAsUser(
                restricted_token,
                None,
                command_line,
                None,
                None,
                True,
                win32con.CREATE_NO_WINDOW
                | win32con.CREATE_UNICODE_ENVIRONMENT
                | win32con.CREATE_SUSPENDED,
                environment,
                normalized_cwd,
                startup,
            )
            win32job.AssignProcessToJobObject(job_handle, process_handle)
            win32process.ResumeThread(thread_handle)

            stdout_file = _detach_pipe_to_file(stdout_read)
            stdout_read = None
            stderr_file = None
            if stderr_read is not None:
                stderr_file = _detach_pipe_to_file(stderr_read)
                stderr_read = None

            return WindowsSandboxedProcess(
                process_handle=process_handle,
                thread_handle=thread_handle,
                job_handle=job_handle,
                stdout_file=stdout_file,
                stderr_file=stderr_file,
                pid=pid,
            )
        finally:
            for handle in (
                stdout_write,
                stderr_write,
                stdin_read,
                stdin_write,
                restricted_token,
            ):
                if handle is None:
                    continue
                try:
                    win32api.CloseHandle(handle)
                except Exception:
                    pass

            for orphan in (stdout_read, stderr_read):
                if orphan is None:
                    continue
                try:
                    win32api.CloseHandle(orphan)
                except Exception:
                    pass
