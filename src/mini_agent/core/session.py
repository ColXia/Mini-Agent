"""Canonical session state/store implementation for Mini-Agent runtime."""

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from mini_agent.memory.memory_files import resolve_workspace_memory_layout
from mini_agent.schema import Message
from mini_agent.session import SessionPersistence

logger = logging.getLogger(__name__)

@dataclass
class SessionState:
    """Session state for gateway/CLI shared session management."""

    session_id: str
    workspace_dir: Path
    agent: Any  # Agent runtime object
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self) -> None:
        """Update last activity timestamp."""
        self.updated_at = datetime.now(timezone.utc)


class SessionStore:
    """In-memory + persistent session store with TTL-based active cache."""

    _SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")

    def __init__(
        self,
        ttl_seconds: int = 7200,
        storage_dir: Path | None = None,
        max_age_seconds: int | None = None,
        max_count: int | None = None,
    ):
        self._sessions: dict[str, SessionState] = {}
        self._lock = asyncio.Lock()
        self._ttl_seconds = max(1, ttl_seconds)
        self._persistence = SessionPersistence(storage_dir)
        self._max_age_seconds = self._load_positive_int_from_env(
            "MINI_AGENT_SESSION_MAX_AGE_SECONDS",
            fallback=max_age_seconds,
        )
        self._max_count = self._load_positive_int_from_env(
            "MINI_AGENT_SESSION_MAX_COUNT",
            fallback=max_count,
        )

    @staticmethod
    def _load_positive_int_from_env(name: str, fallback: int | None = None) -> int | None:
        raw = os.getenv(name)
        if raw is None or not raw.strip():
            return fallback
        try:
            parsed = int(raw)
            if parsed > 0:
                return parsed
        except Exception:
            pass
        return fallback

    @classmethod
    def _validate_session_id(cls, session_id: str) -> str:
        if not cls._SESSION_ID_PATTERN.fullmatch(session_id or ""):
            raise ValueError("session_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}.")
        return session_id

    @staticmethod
    def _to_iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    @staticmethod
    def _from_iso(value: str | None, fallback: datetime) -> datetime:
        if not value:
            return fallback
        try:
            parsed = datetime.fromisoformat(value)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except Exception:
            return fallback

    @staticmethod
    def _message_dicts(messages: list[Any]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for msg in messages:
            if hasattr(msg, "model_dump"):
                payload = msg.model_dump()
            elif isinstance(msg, dict):
                payload = dict(msg)
            elif hasattr(msg, "__dict__"):
                payload = dict(vars(msg))
            else:
                payload = {"role": "assistant", "content": str(msg)}

            normalized.append(
                {
                    "role": payload.get("role", "assistant"),
                    "content": payload.get("content", ""),
                    "thinking": payload.get("thinking"),
                    "tool_calls": payload.get("tool_calls"),
                    "tool_call_id": payload.get("tool_call_id"),
                    "name": payload.get("name"),
                }
            )
        return normalized

    def _extract_messages(self, session: SessionState) -> list[dict[str, Any]]:
        messages = getattr(session.agent, "messages", [])
        if not isinstance(messages, list):
            return []
        return self._message_dicts(messages)

    @staticmethod
    def _normalize_optional_int(value: Any) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except Exception:
            return None

    @classmethod
    def _extract_execution_policy(cls, agent: Any) -> dict[str, int | None]:
        max_steps = cls._normalize_optional_int(getattr(agent, "max_steps", None))
        max_tool_calls_per_step = cls._normalize_optional_int(getattr(agent, "max_tool_calls_per_step", None))
        return {
            "max_steps": max_steps,
            "max_tool_calls_per_step": max_tool_calls_per_step,
        }

    @classmethod
    def _extract_configured_execution_policy(cls, agent: Any) -> dict[str, int | None]:
        configured_raw = getattr(agent, "execution_policy", None)
        if configured_raw is None:
            return cls._extract_execution_policy(agent)

        if hasattr(configured_raw, "max_steps") or hasattr(configured_raw, "max_tool_calls_per_step"):
            return {
                "max_steps": cls._normalize_optional_int(getattr(configured_raw, "max_steps", None)),
                "max_tool_calls_per_step": cls._normalize_optional_int(
                    getattr(configured_raw, "max_tool_calls_per_step", None)
                ),
            }

        if isinstance(configured_raw, dict):
            return {
                "max_steps": cls._normalize_optional_int(configured_raw.get("max_steps")),
                "max_tool_calls_per_step": cls._normalize_optional_int(
                    configured_raw.get("max_tool_calls_per_step")
                ),
            }

        return cls._extract_execution_policy(agent)

    @classmethod
    def _normalize_execution_policy(cls, value: Any) -> dict[str, int | None]:
        if not isinstance(value, dict):
            return {
                "max_steps": None,
                "max_tool_calls_per_step": None,
            }
        return {
            "max_steps": cls._normalize_optional_int(value.get("max_steps")),
            "max_tool_calls_per_step": cls._normalize_optional_int(value.get("max_tool_calls_per_step")),
        }

    @staticmethod
    def _policy_drift_fields(
        configured_policy: dict[str, int | None],
        runtime_policy: dict[str, int | None],
    ) -> list[str]:
        fields: list[str] = []
        for key in ("max_steps", "max_tool_calls_per_step"):
            if configured_policy.get(key) != runtime_policy.get(key):
                fields.append(key)
        return fields

    @classmethod
    def _build_policy_drift_diagnostics(
        cls,
        *,
        configured_policy: dict[str, int | None],
        runtime_policy: dict[str, int | None],
    ) -> dict[str, Any]:
        drift_fields = cls._policy_drift_fields(configured_policy, runtime_policy)
        return {
            "configured_max_steps": configured_policy.get("max_steps"),
            "configured_max_tool_calls_per_step": configured_policy.get("max_tool_calls_per_step"),
            "policy_drift": len(drift_fields) > 0,
            "policy_drift_fields": drift_fields,
        }

    @classmethod
    def _build_active_record(cls, session: SessionState) -> dict[str, Any]:
        runtime_policy = cls._extract_execution_policy(session.agent)
        configured_policy = cls._extract_configured_execution_policy(session.agent)
        diagnostics = cls._build_policy_drift_diagnostics(
            configured_policy=configured_policy,
            runtime_policy=runtime_policy,
        )
        return {
            "session_id": session.session_id,
            "workspace_dir": str(session.workspace_dir),
            "created_at": cls._to_iso(session.created_at),
            "updated_at": cls._to_iso(session.updated_at),
            "message_count": len(getattr(session.agent, "messages", []) or []),
            "active": True,
            "max_steps": runtime_policy["max_steps"],
            "max_tool_calls_per_step": runtime_policy["max_tool_calls_per_step"],
            **diagnostics,
        }

    @classmethod
    def _build_persisted_record(cls, persisted: dict[str, Any]) -> dict[str, Any]:
        runtime_policy = cls._normalize_execution_policy(persisted.get("execution_policy"))
        configured_policy = cls._normalize_execution_policy(
            persisted.get("configured_execution_policy")
        )
        if configured_policy["max_steps"] is None and configured_policy["max_tool_calls_per_step"] is None:
            configured_policy = dict(runtime_policy)
        diagnostics = cls._build_policy_drift_diagnostics(
            configured_policy=configured_policy,
            runtime_policy=runtime_policy,
        )
        return {
            "session_id": str(persisted.get("session_id", "")),
            "workspace_dir": str(persisted.get("workspace_dir", "")),
            "created_at": str(persisted.get("created_at", "")),
            "updated_at": str(persisted.get("updated_at", "")),
            "message_count": int(persisted.get("message_count", 0)),
            "active": False,
            "max_steps": runtime_policy["max_steps"],
            "max_tool_calls_per_step": runtime_policy["max_tool_calls_per_step"],
            **diagnostics,
        }

    def _persist_unlocked(self, session: SessionState) -> None:
        try:
            self._persistence.save_session(
                session_id=session.session_id,
                workspace_dir=str(session.workspace_dir),
                created_at=self._to_iso(session.created_at),
                updated_at=self._to_iso(session.updated_at),
                messages=self._extract_messages(session),
                execution_policy=self._extract_execution_policy(session.agent),
                configured_execution_policy=self._extract_configured_execution_policy(session.agent),
            )
        except Exception:
            logger.exception("Failed to persist session '%s'", session.session_id)

    def _apply_retention_unlocked(
        self,
        *,
        max_age_seconds: int | None = None,
        max_count: int | None = None,
    ) -> dict[str, Any]:
        max_age = self._max_age_seconds if max_age_seconds is None else max_age_seconds
        max_keep = self._max_count if max_count is None else max_count
        if max_age is None and max_keep is None:
            return {"deleted": 0, "remaining": len(self._persistence.list_sessions())}

        result = self._persistence.cleanup(
            max_age_seconds=max_age,
            max_count=max_keep,
        )
        deleted_ids = result.get("deleted_session_ids", [])
        if isinstance(deleted_ids, list):
            for session_id in deleted_ids:
                self._sessions.pop(str(session_id), None)
        return result

    def _cleanup_expired_unlocked(self) -> None:
        now = datetime.now(timezone.utc)
        expired = [
            sid
            for sid, session in self._sessions.items()
            if (now - session.updated_at).total_seconds() > self._ttl_seconds
        ]
        for sid in expired:
            del self._sessions[sid]

    async def get(self, session_id: str) -> Optional[SessionState]:
        session_id = self._validate_session_id(session_id)
        async with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return None

            age = (datetime.now(timezone.utc) - session.updated_at).total_seconds()
            if age > self._ttl_seconds:
                del self._sessions[session_id]
                return None

            session.touch()
            self._persist_unlocked(session)
            return session

    async def set(self, session: SessionState) -> None:
        session.session_id = self._validate_session_id(session.session_id)
        async with self._lock:
            self._sessions[session.session_id] = session
            self._persist_unlocked(session)
            self._apply_retention_unlocked()

    async def delete(self, session_id: str) -> bool:
        session_id = self._validate_session_id(session_id)
        async with self._lock:
            found = False
            if session_id in self._sessions:
                del self._sessions[session_id]
                found = True
            if self._persistence.delete_session(session_id):
                found = True
            return found

    async def restore(
        self,
        session_id: str,
        agent_builder: Callable[[Path], Awaitable[Any]],
        checkpoint_name: str | None = None,
    ) -> Optional[SessionState]:
        session_id = self._validate_session_id(session_id)
        existing = await self.get(session_id)
        if existing is not None:
            return existing

        if checkpoint_name:
            payloads = self._persistence.load_checkpoint(session_id, checkpoint_name)
            if payloads is None:
                return None
            session_record = self._persistence.load_session(session_id)
            if session_record is None:
                return None
            session_record = dict(session_record)
            session_record["messages"] = payloads
        else:
            session_record = self._persistence.load_session(session_id)
            if session_record is None:
                return None

        workspace_dir = Path(str(session_record.get("workspace_dir", "."))).expanduser().resolve()
        agent = await agent_builder(workspace_dir)

        raw_messages = session_record.get("messages", [])
        restored_messages: list[Message] = []
        if isinstance(raw_messages, list):
            for raw in raw_messages:
                if not isinstance(raw, dict):
                    continue
                try:
                    restored_messages.append(Message.model_validate(raw))
                except Exception:
                    continue

        if restored_messages:
            agent.messages = restored_messages

        persisted_policy = self._normalize_execution_policy(session_record.get("execution_policy"))
        persisted_max_steps = persisted_policy.get("max_steps")
        if persisted_max_steps is not None:
            try:
                agent.max_steps = persisted_max_steps
            except Exception:
                pass
        persisted_max_tools = persisted_policy.get("max_tool_calls_per_step")
        if hasattr(agent, "max_tool_calls_per_step"):
            try:
                setattr(agent, "max_tool_calls_per_step", persisted_max_tools)
            except Exception:
                pass

        now = datetime.now(timezone.utc)
        session = SessionState(
            session_id=session_id,
            workspace_dir=workspace_dir,
            agent=agent,
            created_at=self._from_iso(session_record.get("created_at"), now),
            updated_at=self._from_iso(session_record.get("updated_at"), now),
        )
        await self.set(session)
        return session

    async def list_all(self) -> list[SessionState]:
        async with self._lock:
            self._cleanup_expired_unlocked()
            return list(self._sessions.values())

    async def list_records(self, include_inactive: bool = False) -> list[dict[str, Any]]:
        async with self._lock:
            self._cleanup_expired_unlocked()
            active_records: dict[str, dict[str, Any]] = {}
            for session in self._sessions.values():
                active_records[session.session_id] = self._build_active_record(session)

        if not include_inactive:
            records = list(active_records.values())
            records.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
            return records

        merged = dict(active_records)
        for persisted in self._persistence.list_sessions():
            session_id = persisted.get("session_id")
            if not session_id or session_id in merged:
                continue
            merged[session_id] = self._build_persisted_record(persisted)

        records = list(merged.values())
        records.sort(key=lambda r: r.get("updated_at", ""), reverse=True)
        return records

    async def get_record(self, session_id: str, *, include_inactive: bool = True) -> dict[str, Any] | None:
        session_id = self._validate_session_id(session_id)
        async with self._lock:
            self._cleanup_expired_unlocked()
            session = self._sessions.get(session_id)
            if session is not None:
                age = (datetime.now(timezone.utc) - session.updated_at).total_seconds()
                if age > self._ttl_seconds:
                    del self._sessions[session_id]
                else:
                    return self._build_active_record(session)

        if not include_inactive:
            return None

        for persisted in self._persistence.list_sessions():
            if str(persisted.get("session_id")) == session_id:
                return self._build_persisted_record(persisted)
        return None

    async def get_history(
        self,
        session_id: str,
        *,
        limit: int | None = None,
        checkpoint_name: str | None = None,
    ) -> list[dict[str, Any]] | None:
        session_id = self._validate_session_id(session_id)
        if checkpoint_name:
            payloads = self._persistence.load_checkpoint(session_id, checkpoint_name)
            if payloads is None:
                return None
            if limit and limit > 0:
                return payloads[-limit:]
            return payloads

        session = await self.get(session_id)
        if session is not None:
            payloads = self._extract_messages(session)
            if limit and limit > 0:
                return payloads[-limit:]
            return payloads

        persisted = self._persistence.load_session(session_id)
        if persisted is None:
            return None
        payloads = persisted.get("messages", [])
        if not isinstance(payloads, list):
            return []
        if limit and limit > 0:
            return payloads[-limit:]
        return payloads

    async def save_checkpoint(self, session_id: str, checkpoint_name: str) -> dict[str, Any] | None:
        session_id = self._validate_session_id(session_id)
        session = await self.get(session_id)
        if session is not None:
            messages = self._extract_messages(session)
            return self._persistence.save_checkpoint(session_id, checkpoint_name, messages)

        persisted = self._persistence.load_session(session_id)
        if persisted is None:
            return None
        messages = persisted.get("messages", [])
        if not isinstance(messages, list):
            return None
        return self._persistence.save_checkpoint(session_id, checkpoint_name, messages)

    async def list_checkpoints(self, session_id: str) -> list[dict[str, Any]]:
        session_id = self._validate_session_id(session_id)
        return self._persistence.list_checkpoints(session_id)

    async def reset(self, session_id: str) -> bool:
        session_id = self._validate_session_id(session_id)
        session = await self.get(session_id)
        if session is None:
            return False

        async with session.lock:
            if session.agent.messages:
                session.agent.messages = [session.agent.messages[0]]
            session.touch()

        await self.set(session)
        return True

    async def cleanup_retention(
        self,
        *,
        max_age_seconds: int | None = None,
        max_count: int | None = None,
    ) -> dict[str, Any]:
        if max_age_seconds is not None and max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be > 0.")
        if max_count is not None and max_count <= 0:
            raise ValueError("max_count must be > 0.")

        async with self._lock:
            if max_age_seconds is not None:
                self._max_age_seconds = max_age_seconds
            if max_count is not None:
                self._max_count = max_count
            return self._apply_retention_unlocked()

    async def configure_retention(
        self,
        *,
        max_age_seconds: int | None = None,
        max_count: int | None = None,
    ) -> None:
        if max_age_seconds is not None and max_age_seconds <= 0:
            raise ValueError("max_age_seconds must be > 0.")
        if max_count is not None and max_count <= 0:
            raise ValueError("max_count must be > 0.")
        async with self._lock:
            self._max_age_seconds = max_age_seconds
            self._max_count = max_count

    async def set_storage_dir(self, storage_dir: Path, *, migrate_existing: bool = True) -> None:
        async with self._lock:
            sessions_snapshot = list(self._sessions.values()) if migrate_existing else []
            self._persistence = SessionPersistence(storage_dir)
            if migrate_existing:
                for session in sessions_snapshot:
                    self._persist_unlocked(session)
            self._apply_retention_unlocked()

    async def migrate_active_sessions(self) -> int:
        async with self._lock:
            count = 0
            for session in self._sessions.values():
                self._persist_unlocked(session)
                count += 1
            self._apply_retention_unlocked()
            return count

    async def retention_config(self) -> dict[str, int | None]:
        async with self._lock:
            return {
                "max_age_seconds": self._max_age_seconds,
                "max_count": self._max_count,
            }

    async def search_sessions(
        self,
        *,
        query: str,
        limit: int = 20,
        session_id: str | None = None,
        workspace_anchor_dir: str | None = None,
        exclude_session_id: str | None = None,
        include_inactive: bool = True,
    ) -> dict[str, Any]:
        active_ids: set[str]
        async with self._lock:
            self._cleanup_expired_unlocked()
            active_ids = set(self._sessions.keys())

        results = self._persistence.search_sessions(
            query=query,
            limit=limit,
            session_id=session_id,
            workspace_anchor_dir=workspace_anchor_dir,
            exclude_session_id=exclude_session_id,
        )
        if not include_inactive:
            results = [item for item in results if str(item.get("session_id", "")) in active_ids]
        max_limit = max(1, min(int(limit), 200))
        results = results[:max_limit]
        return {
            "hits": results,
            "active_session_count": len(active_ids),
            "returned": len(results),
        }

    async def search_relevant_memory(
        self,
        *,
        query: str,
        top_k: int = 5,
        session_id: str | None = None,
        workspace_dir: str | None = None,
        stale_after_days: int = 30,
    ) -> dict[str, Any]:
        resolved_workspace: Path | None = None

        normalized_session_id: str | None = None
        if session_id:
            normalized_session_id = self._validate_session_id(session_id)
            record = await self.get_record(normalized_session_id, include_inactive=True)
            if record is None:
                raise ValueError(f"Session not found: {normalized_session_id}")
            resolved_workspace = Path(str(record.get("workspace_dir", "."))).expanduser().resolve()

        if workspace_dir and workspace_dir.strip():
            resolved_workspace = Path(workspace_dir).expanduser().resolve()

        if resolved_workspace is None:
            resolved_workspace = Path.cwd().resolve()

        layout = resolve_workspace_memory_layout(resolved_workspace)
        memory_file = layout.memory_file or (layout.anchor_dir / "MEMORY.md")
        payload = self._persistence.search_relevant_memory(
            query=query,
            memory_file=memory_file,
            top_k=top_k,
            stale_after_days=stale_after_days,
        )
        return {
            **payload,
            "workspace_dir": str(resolved_workspace),
            "anchor_dir": str(layout.anchor_dir),
            "session_id": normalized_session_id,
        }

    async def session_search_stats(self) -> dict[str, Any]:
        stats = self._persistence.session_search_stats()
        active_count = 0
        async with self._lock:
            self._cleanup_expired_unlocked()
            active_count = len(self._sessions)
        return {
            **stats,
            "active_session_count": active_count,
        }

    async def clear(self) -> None:
        async with self._lock:
            self._sessions.clear()

    def __len__(self) -> int:
        return len(self._sessions)


session_store = SessionStore()

__all__ = ["SessionState", "SessionStore", "session_store"]
