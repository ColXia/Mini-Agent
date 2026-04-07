"""Enhanced audit logging for security and compliance."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


class AuditEventType(str, Enum):
    """Types of audit events."""

    # Authentication events
    AUTH_LOGIN = "auth.login"
    AUTH_LOGOUT = "auth.logout"
    AUTH_FAILURE = "auth.failure"
    AUTH_TOKEN_REFRESH = "auth.token_refresh"

    # Access events
    ACCESS_GRANTED = "access.granted"
    ACCESS_DENIED = "access.denied"
    ACCESS_KEY_READ = "access.key_read"
    ACCESS_KEY_WRITE = "access.key_write"

    # Provider events
    PROVIDER_ADD = "provider.add"
    PROVIDER_REMOVE = "provider.remove"
    PROVIDER_ENABLE = "provider.enable"
    PROVIDER_DISABLE = "provider.disable"
    PROVIDER_CALL = "provider.call"
    PROVIDER_ERROR = "provider.error"

    # Skill events
    SKILL_LOAD = "skill.load"
    SKILL_EXECUTE = "skill.execute"
    SKILL_EVOLVE = "skill.evolve"

    # Configuration events
    CONFIG_CHANGE = "config.change"
    CONFIG_RELOAD = "config.reload"

    # Security events
    SECURITY_ALERT = "security.alert"
    SECURITY_KEY_ROTATE = "security.key_rotate"
    SECURITY_POLICY_CHANGE = "security.policy_change"

    # System events
    SYSTEM_START = "system.start"
    SYSTEM_STOP = "system.stop"
    SYSTEM_ERROR = "system.error"


class AuditSeverity(str, Enum):
    """Severity levels for audit events."""

    DEBUG = "debug"
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass
class AuditEvent:
    """A single audit event."""

    event_type: AuditEventType
    timestamp: str
    severity: AuditSeverity
    actor: str
    action: str
    resource: str | None = None
    result: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    event_id: str | None = None
    session_id: str | None = None
    ip_address: str | None = None
    user_agent: str | None = None

    def __post_init__(self) -> None:
        if self.event_id is None:
            self.event_id = self._generate_id()

    def _generate_id(self) -> str:
        """Generate a unique event ID."""
        data = f"{self.event_type}:{self.timestamp}:{self.actor}:{self.action}"
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "timestamp": self.timestamp,
            "severity": self.severity.value,
            "actor": self.actor,
            "action": self.action,
            "resource": self.resource,
            "result": self.result,
            "details": self.details,
            "metadata": self.metadata,
            "session_id": self.session_id,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditEvent":
        """Create from dictionary."""
        return cls(
            event_id=data.get("event_id"),
            event_type=AuditEventType(data.get("event_type", "system.error")),
            timestamp=data.get("timestamp", ""),
            severity=AuditSeverity(data.get("severity", "info")),
            actor=data.get("actor", "unknown"),
            action=data.get("action", ""),
            resource=data.get("resource"),
            result=data.get("result"),
            details=data.get("details", {}),
            metadata=data.get("metadata", {}),
            session_id=data.get("session_id"),
            ip_address=data.get("ip_address"),
            user_agent=data.get("user_agent"),
        )


class AuditLogWriter:
    """Writes audit events to log files."""

    def __init__(
        self,
        log_dir: Path,
        *,
        max_file_size_mb: float = 100.0,
        max_files: int = 30,
        compress_rotated: bool = True,
    ) -> None:
        self.log_dir = Path(log_dir).expanduser().resolve()
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.max_file_size = max(1.0, float(max_file_size_mb)) * 1024 * 1024
        self.max_files = max(1, int(max_files))
        self.compress_rotated = compress_rotated

        self._current_file: Path | None = None
        self._current_size: int = 0
        self._file_handle: Any = None

    def _get_log_file(self) -> Path:
        """Get current log file path."""
        today = _utc_now().strftime("%Y-%m-%d")
        return self.log_dir / f"audit-{today}.jsonl"

    def _rotate_if_needed(self) -> None:
        """Rotate log file if needed."""
        if self._current_file is None:
            return

        if self._current_size >= self.max_file_size:
            if self._file_handle:
                self._file_handle.close()
                self._file_handle = None

            # Rename with timestamp
            timestamp = _utc_now().strftime("%Y%m%d-%H%M%S")
            rotated = self._current_file.with_suffix(f".{timestamp}.jsonl")
            self._current_file.rename(rotated)

            if self.compress_rotated:
                import gzip
                with open(rotated, "rb") as f_in:
                    with gzip.open(f"{rotated}.gz", "wb") as f_out:
                        f_out.writelines(f_in)
                rotated.unlink()

            self._current_file = None
            self._current_size = 0

    def _cleanup_old_files(self) -> None:
        """Remove old log files beyond max_files."""
        files = sorted(self.log_dir.glob("audit-*.jsonl*"))
        while len(files) > self.max_files:
            files[0].unlink()
            files = files[1:]

    def write(self, event: AuditEvent) -> None:
        """Write an audit event to the log."""
        self._rotate_if_needed()

        log_file = self._get_log_file()
        if self._current_file != log_file:
            if self._file_handle:
                self._file_handle.close()
            self._current_file = log_file
            self._current_size = log_file.stat().st_size if log_file.exists() else 0
            self._file_handle = open(log_file, "a", encoding="utf-8")
            self._cleanup_old_files()

        line = json.dumps(event.to_dict(), ensure_ascii=False) + "\n"
        self._file_handle.write(line)
        self._file_handle.flush()
        self._current_size += len(line.encode("utf-8"))

    def close(self) -> None:
        """Close the log file."""
        if self._file_handle:
            self._file_handle.close()
            self._file_handle = None


class AuditLogger:
    """Central audit logging system."""

    def __init__(
        self,
        log_dir: Path = Path("~/.mini-agent/audit"),
        *,
        min_severity: AuditSeverity = AuditSeverity.INFO,
        enable_console: bool = False,
    ) -> None:
        self.writer = AuditLogWriter(log_dir)
        self.min_severity = min_severity
        self.enable_console = enable_console

        self._severity_order = {
            AuditSeverity.DEBUG: 0,
            AuditSeverity.INFO: 1,
            AuditSeverity.WARNING: 2,
            AuditSeverity.ERROR: 3,
            AuditSeverity.CRITICAL: 4,
        }

    def _should_log(self, severity: AuditSeverity) -> bool:
        """Check if severity meets minimum threshold."""
        return self._severity_order.get(severity, 0) >= self._severity_order.get(self.min_severity, 0)

    def log(
        self,
        event_type: AuditEventType,
        action: str,
        *,
        severity: AuditSeverity = AuditSeverity.INFO,
        actor: str = "system",
        resource: str | None = None,
        result: str | None = None,
        details: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> AuditEvent:
        """Log an audit event."""
        event = AuditEvent(
            event_type=event_type,
            timestamp=_utc_iso(_utc_now()) or "",
            severity=severity,
            actor=actor,
            action=action,
            resource=resource,
            result=result,
            details=details or {},
            metadata=metadata or {},
            session_id=session_id,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        if self._should_log(severity):
            self.writer.write(event)

            if self.enable_console:
                print(f"[AUDIT] {event.severity.value.upper()}: {event.event_type.value} - {event.action}")

        return event

    def log_auth(
        self,
        event_type: AuditEventType,
        actor: str,
        result: str,
        *,
        ip_address: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Log an authentication event."""
        severity = AuditSeverity.INFO if result == "success" else AuditSeverity.WARNING
        return self.log(
            event_type=event_type,
            action="authenticate",
            severity=severity,
            actor=actor,
            result=result,
            ip_address=ip_address,
            details=details,
        )

    def log_access(
        self,
        actor: str,
        resource: str,
        granted: bool,
        *,
        action: str = "access",
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Log an access event."""
        event_type = AuditEventType.ACCESS_GRANTED if granted else AuditEventType.ACCESS_DENIED
        severity = AuditSeverity.INFO if granted else AuditSeverity.WARNING
        return self.log(
            event_type=event_type,
            action=action,
            severity=severity,
            actor=actor,
            resource=resource,
            result="granted" if granted else "denied",
            details=details,
        )

    def log_provider(
        self,
        event_type: AuditEventType,
        provider: str,
        action: str,
        *,
        result: str = "success",
        severity: AuditSeverity = AuditSeverity.INFO,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Log a provider event."""
        return self.log(
            event_type=event_type,
            action=action,
            severity=severity,
            actor="system",
            resource=f"provider:{provider}",
            result=result,
            details=details,
        )

    def log_security_alert(
        self,
        alert_type: str,
        message: str,
        *,
        severity: AuditSeverity = AuditSeverity.WARNING,
        details: dict[str, Any] | None = None,
    ) -> AuditEvent:
        """Log a security alert."""
        return self.log(
            event_type=AuditEventType.SECURITY_ALERT,
            action=alert_type,
            severity=severity,
            actor="security",
            result=message,
            details=details,
        )

    def close(self) -> None:
        """Close the audit logger."""
        self.writer.close()


# Global audit logger instance
_audit_logger: AuditLogger | None = None


def get_audit_logger() -> AuditLogger:
    """Get the global audit logger instance."""
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger


def configure_audit_logger(
    log_dir: Path = Path("~/.mini-agent/audit"),
    min_severity: AuditSeverity = AuditSeverity.INFO,
    enable_console: bool = False,
) -> AuditLogger:
    """Configure the global audit logger."""
    global _audit_logger
    _audit_logger = AuditLogger(
        log_dir=log_dir,
        min_severity=min_severity,
        enable_console=enable_console,
    )
    return _audit_logger
