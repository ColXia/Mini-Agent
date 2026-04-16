"""Agent run logger with structured event journal and retention policy."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .schema import LLMCompletionResult, Message, ToolCall


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


EVENT_SCHEMA_VERSION = "1.0.0"


def _parse_semver(value: str) -> tuple[int, int, int] | None:
    parts = value.strip().split(".")
    if len(parts) != 3:
        return None
    try:
        major, minor, patch = (int(part) for part in parts)
    except Exception:
        return None
    if major < 0 or minor < 0 or patch < 0:
        return None
    return major, minor, patch


@dataclass(frozen=True)
class EventLogRetentionPolicy:
    """Retention policy for agent run logs."""

    enabled: bool = True
    prune_on_start: bool = True
    max_runs: int = 200
    max_age_days: int = 14
    max_total_size_mb: float = 512.0

    def normalized(self) -> "EventLogRetentionPolicy":
        return EventLogRetentionPolicy(
            enabled=bool(self.enabled),
            prune_on_start=bool(self.prune_on_start),
            max_runs=max(1, int(self.max_runs)),
            max_age_days=max(0, int(self.max_age_days)),
            max_total_size_mb=max(0.001, float(self.max_total_size_mb)),
        )


@dataclass
class _RunBundle:
    run_key: str
    files: list[Path]
    newest_mtime: float
    total_size: int


def build_retention_policy_from_config(config) -> EventLogRetentionPolicy:
    """Build retention policy from config with safe defaults."""
    observability = getattr(config, "observability", None)
    if observability is None:
        return EventLogRetentionPolicy()

    return EventLogRetentionPolicy(
        enabled=getattr(observability, "event_log_retention_enabled", True),
        prune_on_start=getattr(observability, "event_log_prune_on_start", True),
        max_runs=getattr(observability, "event_log_max_runs", 200),
        max_age_days=getattr(observability, "event_log_max_age_days", 14),
        max_total_size_mb=getattr(observability, "event_log_max_total_mb", 512.0),
    ).normalized()


def create_agent_logger(config) -> "AgentLogger":
    """Create an AgentLogger instance from runtime config."""
    observability = getattr(config, "observability", None)
    log_dir_raw = getattr(observability, "log_dir", "~/.mini-agent/log")
    log_dir = Path(str(log_dir_raw)).expanduser()
    policy = build_retention_policy_from_config(config)
    return AgentLogger(log_dir=log_dir, retention_policy=policy)


class AgentLogger:
    """Agent run logger.

    Emits two log files per run:
    - Human-readable trace (`.log`)
    - Structured replayable event journal (`.events.jsonl`)
    """

    def __init__(
        self,
        log_dir: str | Path | None = None,
        retention_policy: EventLogRetentionPolicy | None = None,
    ):
        self.log_dir = Path(log_dir) if log_dir else Path.home() / ".mini-agent" / "log"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.retention_policy = (retention_policy or EventLogRetentionPolicy()).normalized()
        self.log_file: Path | None = None
        self.event_file: Path | None = None
        self.log_index = 0
        self.event_index = 0
        self.run_id: str | None = None

    def start_new_run(self, workspace: str | Path | None = None) -> None:
        """Start a new run and initialize trace + event logs."""
        prune_summary: dict[str, Any] = {
            "removed_runs": 0,
            "removed_files": 0,
            "freed_bytes": 0,
            "remaining_runs": 0,
            "remaining_bytes": 0,
        }
        if self.retention_policy.enabled and self.retention_policy.prune_on_start:
            prune_summary = self.prune_logs()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        self.run_id = f"run_{timestamp}"
        self.log_file = self.log_dir / f"agent_run_{timestamp}.log"
        self.event_file = self.log_dir / f"agent_run_{timestamp}.events.jsonl"
        self.log_index = 0
        self.event_index = 0

        with open(self.log_file, "w", encoding="utf-8") as file:
            file.write("=" * 80 + "\n")
            file.write(f"Agent Run Log - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            file.write("=" * 80 + "\n\n")

        self.log_event(
            event_type="run.init",
            payload={
                "workspace": str(workspace) if workspace is not None else None,
                "log_file": str(self.log_file),
                "event_file": str(self.event_file),
                "retention": {
                    "max_runs": self.retention_policy.max_runs,
                    "max_age_days": self.retention_policy.max_age_days,
                    "max_total_size_mb": self.retention_policy.max_total_size_mb,
                    "prune_summary": prune_summary,
                },
            },
        )

    def prune_logs(self) -> dict[str, int]:
        """Prune old run logs according to retention policy."""
        policy = self.retention_policy.normalized()
        bundles = self._collect_run_bundles()
        if not bundles or not policy.enabled:
            return {
                "removed_runs": 0,
                "removed_files": 0,
                "freed_bytes": 0,
                "remaining_runs": len(bundles),
                "remaining_bytes": sum(bundle.total_size for bundle in bundles),
            }

        now_ts = datetime.now(timezone.utc).timestamp()
        to_remove: dict[str, _RunBundle] = {}

        # 1) Age policy
        if policy.max_age_days > 0:
            cutoff = now_ts - (policy.max_age_days * 86400)
            for bundle in bundles:
                if bundle.newest_mtime < cutoff:
                    to_remove[bundle.run_key] = bundle

        kept = [bundle for bundle in bundles if bundle.run_key not in to_remove]
        kept.sort(key=lambda bundle: bundle.newest_mtime)

        # 2) Max-run-count policy
        excess_runs = len(kept) - policy.max_runs
        if excess_runs > 0:
            for bundle in kept[:excess_runs]:
                to_remove[bundle.run_key] = bundle

        kept = [bundle for bundle in kept if bundle.run_key not in to_remove]
        kept.sort(key=lambda bundle: bundle.newest_mtime)

        # 3) Total-size policy
        limit_bytes = int(policy.max_total_size_mb * 1024 * 1024)
        total_bytes = sum(bundle.total_size for bundle in kept)
        if total_bytes > limit_bytes:
            for bundle in kept:
                if total_bytes <= limit_bytes:
                    break
                to_remove[bundle.run_key] = bundle
                total_bytes -= bundle.total_size

        removed_runs = 0
        removed_files = 0
        freed_bytes = 0
        for bundle in to_remove.values():
            removed_runs += 1
            for path in bundle.files:
                try:
                    size = path.stat().st_size
                except Exception:
                    size = 0
                try:
                    path.unlink(missing_ok=True)
                    removed_files += 1
                    freed_bytes += size
                except Exception:
                    continue

        remaining = self._collect_run_bundles()
        return {
            "removed_runs": removed_runs,
            "removed_files": removed_files,
            "freed_bytes": freed_bytes,
            "remaining_runs": len(remaining),
            "remaining_bytes": sum(bundle.total_size for bundle in remaining),
        }

    def _collect_run_bundles(self) -> list[_RunBundle]:
        bundles: dict[str, list[Path]] = {}
        for path in self.log_dir.glob("agent_run_*.log"):
            run_key = self._extract_run_key(path)
            if run_key:
                bundles.setdefault(run_key, []).append(path)
        for path in self.log_dir.glob("agent_run_*.events.jsonl"):
            run_key = self._extract_run_key(path)
            if run_key:
                bundles.setdefault(run_key, []).append(path)

        result: list[_RunBundle] = []
        for run_key, files in bundles.items():
            newest_mtime = 0.0
            total_size = 0
            for file_path in files:
                try:
                    stat = file_path.stat()
                    newest_mtime = max(newest_mtime, stat.st_mtime)
                    total_size += stat.st_size
                except Exception:
                    continue
            result.append(
                _RunBundle(
                    run_key=run_key,
                    files=sorted(files, key=lambda path: path.name),
                    newest_mtime=newest_mtime,
                    total_size=total_size,
                )
            )

        return sorted(result, key=lambda bundle: bundle.newest_mtime)

    def _extract_run_key(self, path: Path) -> str | None:
        name = path.name
        if name.endswith(".events.jsonl"):
            return name[: -len(".events.jsonl")]
        if name.endswith(".log"):
            return name[: -len(".log")]
        return None

    def log_event(
        self,
        event_type: str,
        payload: dict[str, Any] | None = None,
        level: str = "info",
    ) -> None:
        """Append one structured event to the JSONL event journal."""
        if self.event_file is None:
            return

        self.event_index += 1
        event = {
            "index": self.event_index,
            "run_id": self.run_id,
            "schema_version": EVENT_SCHEMA_VERSION,
            "timestamp": _utc_now_iso(),
            "type": event_type,
            "level": level,
            "payload": payload or {},
        }

        with open(self.event_file, "a", encoding="utf-8") as file:
            file.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    def log_request(self, messages: list[Message], tools: list[Any] | None = None) -> None:
        self.log_index += 1

        request_data = {
            "messages": [],
            "tools": [],
        }

        for message in messages:
            message_data = {
                "role": message.role,
                "content": message.content,
            }
            if message.thinking:
                message_data["thinking"] = message.thinking
            if message.tool_calls:
                message_data["tool_calls"] = [call.model_dump() for call in message.tool_calls]
            if message.tool_call_id:
                message_data["tool_call_id"] = message.tool_call_id
            if message.name:
                message_data["name"] = message.name

            request_data["messages"].append(message_data)

        if tools:
            request_data["tools"] = [tool.name for tool in tools]

        content = "LLM Request:\n\n"
        content += json.dumps(request_data, indent=2, ensure_ascii=False)
        self._write_log("REQUEST", content)

        self.log_event(
            event_type="llm.request",
            payload={
                "message_count": len(messages),
                "tool_count": len(tools or []),
                "tools": [tool.name for tool in tools] if tools else [],
            },
        )

    def log_completion(self, result: LLMCompletionResult) -> None:
        self.log_index += 1

        response_data: dict[str, Any] = {
            "content": result.content,
            "events": [event.model_dump() for event in result.events],
        }
        if result.thinking:
            response_data["thinking"] = result.thinking
        if result.tool_calls:
            response_data["tool_calls"] = [call.model_dump() for call in result.tool_calls]
        if result.finish_reason:
            response_data["finish_reason"] = result.finish_reason
        if result.usage is not None:
            response_data["usage"] = result.usage.model_dump()
        if result.error:
            response_data["error"] = result.error

        log_content = "LLM Response:\n\n"
        log_content += json.dumps(response_data, indent=2, ensure_ascii=False)
        self._write_log("RESPONSE", log_content)

        preview = result.content[:200] + ("..." if len(result.content) > 200 else "")
        self.log_event(
            event_type="llm.response",
            payload={
                "finish_reason": result.finish_reason,
                "tool_call_count": len(result.tool_calls or []),
                "event_count": len(result.events),
                "content_preview": preview,
                "error": result.error,
            },
        )

    def log_response(
        self,
        content: str,
        thinking: str | None = None,
        tool_calls: list[ToolCall] | None = None,
        finish_reason: str | None = None,
    ) -> None:
        """Backward-compatible wrapper over ``log_completion``."""

        self.log_completion(
            LLMCompletionResult(
                content=content,
                thinking=thinking,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
            )
        )

    def log_tool_result(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        result_success: bool,
        result_content: str | None = None,
        result_error: str | None = None,
    ) -> None:
        self.log_index += 1

        tool_result_data: dict[str, Any] = {
            "tool_name": tool_name,
            "arguments": arguments,
            "success": result_success,
        }

        if result_success:
            tool_result_data["result"] = result_content
        else:
            tool_result_data["error"] = result_error

        content = "Tool Execution:\n\n"
        content += json.dumps(tool_result_data, indent=2, ensure_ascii=False)
        self._write_log("TOOL_RESULT", content)

        self.log_event(
            event_type="tool.result",
            payload={
                "tool_name": tool_name,
                "success": result_success,
                "error": result_error if not result_success else None,
            },
            level="error" if not result_success else "info",
        )

    def _write_log(self, log_type: str, content: str) -> None:
        if self.log_file is None:
            return

        with open(self.log_file, "a", encoding="utf-8") as file:
            file.write("\n" + "-" * 80 + "\n")
            file.write(f"[{self.log_index}] {log_type}\n")
            file.write(f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}\n")
            file.write("-" * 80 + "\n")
            file.write(content + "\n")

    def get_log_file_path(self) -> Path | None:
        return self.log_file

    def get_event_file_path(self) -> Path | None:
        return self.event_file

    @staticmethod
    def read_events(event_file: str | Path) -> list[dict[str, Any]]:
        path = Path(event_file)
        if not path.exists():
            raise FileNotFoundError(f"Event log file not found: {path}")

        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            entry = line.strip()
            if not entry:
                continue
            events.append(json.loads(entry))
        return events

    @staticmethod
    def check_event_schema_compatibility(
        events: list[dict[str, Any]],
        expected_version: str | None = None,
    ) -> dict[str, Any]:
        detected_versions = sorted(
            {
                str(event.get("schema_version", "0.0.0")).strip() or "0.0.0"
                for event in events
            }
        )
        legacy_event_count = sum(1 for event in events if "schema_version" not in event)

        if expected_version is None:
            return {
                "compatible": True,
                "reason": "No expected schema version requested.",
                "current_schema_version": EVENT_SCHEMA_VERSION,
                "expected_schema_version": None,
                "detected_versions": detected_versions,
                "legacy_event_count": legacy_event_count,
            }

        parsed_expected = _parse_semver(expected_version)
        if parsed_expected is None:
            raise ValueError(
                f"Invalid expected schema version '{expected_version}'. Use semantic version format MAJOR.MINOR.PATCH."
            )

        expected_major = parsed_expected[0]
        incompatible_versions: list[str] = []
        for version in detected_versions:
            parsed = _parse_semver(version)
            if parsed is None:
                incompatible_versions.append(version)
                continue
            if parsed[0] != expected_major:
                incompatible_versions.append(version)

        if incompatible_versions:
            return {
                "compatible": False,
                "reason": (
                    "Detected schema major version mismatch. "
                    f"Expected major={expected_major}, incompatible versions={incompatible_versions}."
                ),
                "current_schema_version": EVENT_SCHEMA_VERSION,
                "expected_schema_version": expected_version,
                "detected_versions": detected_versions,
                "legacy_event_count": legacy_event_count,
            }

        return {
            "compatible": True,
            "reason": "Detected schema versions are compatible with requested major version.",
            "current_schema_version": EVENT_SCHEMA_VERSION,
            "expected_schema_version": expected_version,
            "detected_versions": detected_versions,
            "legacy_event_count": legacy_event_count,
        }

    @staticmethod
    def format_replay(events: list[dict[str, Any]], include_payload: bool = False) -> str:
        schema = AgentLogger.check_event_schema_compatibility(events, expected_version=None)
        lines = [
            "Run Event Replay",
            "================",
            (
                "Schema: "
                f"current={schema['current_schema_version']}, "
                f"detected={schema['detected_versions']}, "
                f"legacy_events={schema['legacy_event_count']}"
            ),
        ]
        for event in sorted(events, key=lambda item: int(item.get("index", 0))):
            timestamp = event.get("timestamp", "unknown")
            event_type = event.get("type", "unknown")
            level = str(event.get("level", "info")).upper()
            lines.append(f"[{event.get('index', '?')}] {timestamp} {level} {event_type}")
            if include_payload:
                payload = event.get("payload", {})
                lines.append("  " + json.dumps(payload, ensure_ascii=False))
        lines.append("")
        lines.append(f"Total events: {len(events)}")
        return "\n".join(lines)

    @staticmethod
    def list_event_log_files(path: str | Path, recursive: bool = True) -> list[Path]:
        """List event log files under one path or return the file itself if file path is provided."""
        target = Path(path).expanduser()
        if target.is_file():
            return [target.resolve()]
        if not target.exists():
            return []

        pattern = "agent_run_*.events.jsonl"
        iterator = target.rglob(pattern) if recursive else target.glob(pattern)
        return sorted(item.resolve() for item in iterator if item.is_file())

    @staticmethod
    def _next_backup_path(path: Path) -> Path:
        backup = path.with_name(f"{path.name}.bak")
        if not backup.exists():
            return backup

        index = 1
        while True:
            candidate = path.with_name(f"{path.name}.bak.{index}")
            if not candidate.exists():
                return candidate
            index += 1

    @staticmethod
    def migrate_event_schema_file(
        event_file: str | Path,
        *,
        target_version: str = EVENT_SCHEMA_VERSION,
        backup: bool = True,
        dry_run: bool = False,
    ) -> dict[str, Any]:
        """Backfill missing `schema_version` fields in one event log file."""
        if _parse_semver(target_version) is None:
            raise ValueError(
                f"Invalid target schema version '{target_version}'. Use MAJOR.MINOR.PATCH."
            )

        path = Path(event_file).expanduser()
        if not path.exists():
            raise FileNotFoundError(f"Event log file not found: {path}")
        if path.is_dir():
            raise IsADirectoryError(f"Event log path is a directory: {path}")

        resolved_path = path.resolve()
        temp_path = resolved_path.with_name(f"{resolved_path.name}.migrate.tmp")
        total_events = 0
        migrated_events = 0
        versioned_events = 0
        backup_path: Path | None = None
        writer = None

        try:
            if not dry_run:
                writer = temp_path.open("w", encoding="utf-8")

            with resolved_path.open("r", encoding="utf-8") as reader:
                for line_number, line in enumerate(reader, start=1):
                    raw = line.strip()
                    if not raw:
                        if writer is not None:
                            writer.write("\n")
                        continue

                    try:
                        event = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise ValueError(
                            f"Invalid JSON in '{resolved_path}' at line {line_number}: {exc}"
                        ) from exc
                    if not isinstance(event, dict):
                        raise ValueError(
                            f"Invalid event payload in '{resolved_path}' at line {line_number}: expected object."
                        )

                    total_events += 1
                    current_schema = str(event.get("schema_version", "")).strip()
                    if not current_schema:
                        event["schema_version"] = target_version
                        migrated_events += 1
                    else:
                        versioned_events += 1

                    if writer is not None:
                        writer.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

            if writer is not None:
                writer.close()
                writer = None

            changed = migrated_events > 0
            if not dry_run and changed:
                if backup:
                    backup_path = AgentLogger._next_backup_path(resolved_path)
                    resolved_path.replace(backup_path)
                    try:
                        temp_path.replace(resolved_path)
                    except Exception as exc:
                        backup_path.replace(resolved_path)
                        raise RuntimeError(
                            f"Failed to write migrated log for '{resolved_path}': {exc}"
                        ) from exc
                else:
                    temp_path.replace(resolved_path)
            elif not dry_run and temp_path.exists():
                temp_path.unlink(missing_ok=True)

            return {
                "file": str(resolved_path),
                "target_schema_version": target_version,
                "total_events": total_events,
                "migrated_events": migrated_events,
                "already_versioned_events": versioned_events,
                "changed": changed,
                "dry_run": dry_run,
                "backup_file": str(backup_path) if backup_path else None,
            }
        finally:
            if writer is not None:
                writer.close()
            if temp_path.exists():
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception:
                    pass
