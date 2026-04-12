"""Runtime manager for single-host main-agent session lifecycle."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import inspect
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Awaitable, Callable, Sequence
from uuid import uuid4

from fastapi import HTTPException

from mini_agent.agent import Agent
from mini_agent.agent_core.session import (
    AgentSessionKey,
    SessionLifecycleManager,
    SessionLifecyclePolicy,
    SessionLifecycleState,
)
from mini_agent.code_agent.context_compression import estimate_tokens
from mini_agent.commands.mcp_support import (
    collect_mcp_operator_snapshot,
    format_mcp_server_list,
    format_mcp_status,
)
from mini_agent.commands.skill_support import (
    find_skill_entry,
    format_skill_detail,
    format_skill_entries,
    format_skill_install_result,
    format_skill_policy_overview,
    format_skill_rollback_result,
    format_skill_search_results,
    format_skill_uninstall_result,
    install_workspace_skill_from_path,
    load_workspace_skill_policy,
    refresh_skill_catalog_loader,
    resolve_skill_catalog_loader,
    resolve_workspace_skill_policy_store,
    rollback_workspace_skill,
    search_skill_entries,
    summarize_skill_entries,
    uninstall_workspace_skill,
)
from mini_agent.config import Config
from mini_agent.interfaces import (
    MainAgentSessionApprovalResponse,
    MainAgentSessionContextResponse,
    MainAgentSessionControlResponse,
    MainAgentSessionDetail,
    MainAgentSessionMemoryResponse,
    MainAgentSessionMessage,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionPendingApproval,
    MainAgentSessionRecoverySnapshot,
    MainAgentSessionSkillResponse,
    MainAgentSessionSummary,
)
from mini_agent.memory.diagnostics import (
    build_memory_overview_payload,
    build_memory_diagnostics,
    format_consolidated_memory_details,
    format_consolidated_memory_search_details,
    format_global_profile_details,
    format_memory_diagnostics,
    format_memory_export_details,
    format_memory_overview_details,
    format_runtime_memory_entry_details,
    format_runtime_memory_preview_lines,
    format_runtime_shared_selector_help,
    format_runtime_session_selector_help,
    format_workspace_daily_details,
    format_workspace_note_details,
    memory_diagnostics_summary_line,
    resolve_runtime_shared_engram_selector,
    resolve_runtime_session_engram_selector,
)
from mini_agent.memory.knowledge_base_grounding import format_knowledge_base_grounding_lines
from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime
from mini_agent.memory.operator_actions import (
    save_operator_profile_fact,
    save_operator_workspace_note,
)
from mini_agent.memory.service import MemoryService
from mini_agent.runtime.session_snapshot import (
    RuntimeSessionImportMessage,
    RuntimeSessionSnapshot,
)
from mini_agent.runtime.sandbox_state import collect_sandbox_diagnostics, normalize_sandbox_diagnostics
from mini_agent.runtime.tooling import reconfigure_agent_runtime_policy
from mini_agent.schema import Message
from mini_agent.session import (
    SessionDetailProjection,
    SessionMessageProjection,
    SessionPendingApprovalProjection,
    SessionRecoveryProjection,
    SessionSummaryProjection,
)
from mini_agent.session.persistence import SessionPersistence
from mini_agent.tools.mcp_loader import cleanup_mcp_connections
from mini_agent.turn_context import (
    context_policy_summary_line,
    format_context_policy_details,
    resolve_turn_context_policy,
)


BuildAgentFn = Callable[[Path], Awaitable[Agent]]
BuildSelectedAgentFn = Callable[[Path, str | None, str | None, str | None], Awaitable[Agent]]
_RUNTIME_SESSION_KIND = "main-agent-runtime"


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


def _from_utc_iso(value: object, fallback: datetime) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        return fallback
    try:
        parsed = datetime.fromisoformat(raw)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return fallback


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


class _MainAgentRuntimePersistence:
    """Persistence wrapper for gateway-managed shared sessions."""

    def __init__(self, storage_dir: Path | None = None) -> None:
        if storage_dir is None:
            storage_dir = Path(tempfile.gettempdir()) / f"mini-agent-main-agent-runtime-{uuid4().hex}"
        self._session_store = SessionPersistence(storage_dir)
        self._shared_transcripts_dir = self._session_store.base_dir / "main_agent_runtime_transcripts"
        self._shared_transcripts_dir.mkdir(parents=True, exist_ok=True)

    def _read_metadata(self) -> dict[str, Any]:
        path = self._session_store.metadata_path
        if not path.exists():
            return {"sessions": {}}
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return {"sessions": {}}
        if not isinstance(raw, dict):
            return {"sessions": {}}
        sessions = raw.get("sessions")
        if not isinstance(sessions, dict):
            raw["sessions"] = {}
        return raw

    def _write_metadata(self, payload: dict[str, Any]) -> None:
        _atomic_write_text(
            self._session_store.metadata_path,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )

    def _shared_transcript_path(self, session_id: str) -> Path:
        normalized = "".join(
            char if char.isalnum() or char in "._-" else "_"
            for char in str(session_id or "")
        ).strip()
        safe_session_id = normalized or uuid4().hex
        return self._shared_transcripts_dir / f"{safe_session_id}.jsonl"

    @staticmethod
    def _serialize_transcript_entry(entry: "MainAgentSessionTranscriptEntry") -> dict[str, Any]:
        return {
            "index": int(entry.index),
            "role": _safe_text(entry.role).lower() or "assistant",
            "content": str(entry.content or ""),
            "surface": _safe_text(entry.surface).lower() or "api",
            "created_at": _to_utc_iso(entry.created_at),
            "channel_type": _safe_text(entry.channel_type) or None,
            "conversation_id": _safe_text(entry.conversation_id) or None,
            "sender_id": _safe_text(entry.sender_id) or None,
            "metadata": dict(entry.metadata) if isinstance(entry.metadata, dict) else {},
        }

    def _write_shared_transcript(
        self,
        session_id: str,
        entries: Sequence["MainAgentSessionTranscriptEntry"],
    ) -> Path:
        transcript_path = self._shared_transcript_path(session_id)
        content = "".join(
            json.dumps(self._serialize_transcript_entry(entry), ensure_ascii=False) + "\n"
            for entry in entries
        )
        _atomic_write_text(transcript_path, content)
        return transcript_path

    def _read_shared_transcript(self, session_id: str, record: dict[str, Any]) -> list[dict[str, Any]]:
        configured_path = str(record.get("shared_transcript_path") or "").strip()
        transcript_path = Path(configured_path) if configured_path else self._shared_transcript_path(session_id)
        if not transcript_path.exists():
            return []
        items: list[dict[str, Any]] = []
        for line in transcript_path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except Exception:
                continue
            if isinstance(parsed, dict):
                items.append(parsed)
        return items

    def save_session(
        self,
        session: "MainAgentSessionState",
        *,
        agent_messages: Sequence[Any] | None = None,
    ) -> None:
        messages = list(agent_messages) if agent_messages is not None else list(getattr(session.agent, "messages", []) or [])
        self._session_store.save_session(
            session_id=session.session_id,
            workspace_dir=str(session.workspace_dir),
            created_at=_to_utc_iso(session.created_at),
            updated_at=_to_utc_iso(session.updated_at),
            messages=messages,
        )

        transcript_path = self._write_shared_transcript(session.session_id, session.transcript)
        try:
            sandbox_diagnostics = collect_sandbox_diagnostics(agent=session.agent)
        except Exception:
            sandbox_diagnostics = session.sandbox_diagnostics
        sandbox_diagnostics = normalize_sandbox_diagnostics(sandbox_diagnostics)
        session.sandbox_diagnostics = dict(sandbox_diagnostics)
        metadata = self._read_metadata()
        sessions = metadata.setdefault("sessions", {})
        if not isinstance(sessions, dict):
            sessions = {}
            metadata["sessions"] = sessions
        record = sessions.get(session.session_id)
        if not isinstance(record, dict):
            record = {"session_id": session.session_id}
            sessions[session.session_id] = record
        record.update(
            {
                "session_id": session.session_id,
                "workspace_dir": str(session.workspace_dir),
                "created_at": _to_utc_iso(session.created_at),
                "updated_at": _to_utc_iso(session.updated_at),
                "message_count": len(session.transcript),
                "session_kind": _RUNTIME_SESSION_KIND,
                "title": _safe_text(session.title) or None,
                "origin_surface": _safe_text(session.origin_surface) or "api",
                "active_surface": _safe_text(session.active_surface or session.origin_surface) or "api",
                "reply_enabled": bool(session.reply_enabled),
                "busy": bool(session.busy),
                "running_state": _safe_text(session.running_state) or None,
                "channel_type": _safe_text(session.channel_type) or None,
                "conversation_id": _safe_text(session.conversation_id) or None,
                "sender_id": _safe_text(session.sender_id) or None,
                "token_usage": MainAgentRuntimeManager._session_token_usage(session),
                "token_limit": MainAgentRuntimeManager._session_token_limit(session),
                "shared": bool(session.shared),
                "knowledge_base_enabled": bool(session.knowledge_base_enabled),
                "selected_model_source": _safe_text(session.selected_model_source) or None,
                "selected_provider_id": _safe_text(session.selected_provider_id) or None,
                "selected_model_id": _safe_text(session.selected_model_id) or None,
                "pending_model_source": _safe_text(session.pending_model_source) or None,
                "pending_provider_id": _safe_text(session.pending_provider_id) or None,
                "pending_model_id": _safe_text(session.pending_model_id) or None,
                "pending_skill_reload": bool(session.pending_skill_reload),
                "pending_skill_reload_reason": _safe_text(session.pending_skill_reload_reason) or None,
                "shared_transcript_path": str(transcript_path),
                "shared_message_count": len(session.transcript),
                "next_transcript_index": int(session.next_transcript_index),
                "pending_approvals": [
                    self._serialize_pending_approval(item)
                    for item in session.pending_approvals
                    if isinstance(item, dict)
                ],
                "recovery_context_pending": bool(session.recovery_context_pending),
                "recovery_state": _safe_text(session.recovery_state) or None,
                "recovery_summary": _safe_text(session.recovery_summary) or None,
                "recovery_last_activity": _safe_text(session.recovery_last_activity) or None,
                "recovery_last_user_message": _safe_text(session.recovery_last_user_message) or None,
                "recovery_last_assistant_message": _safe_text(session.recovery_last_assistant_message) or None,
                "recovery_pending_approvals": [
                    self._serialize_pending_approval(item)
                    for item in session.recovery_pending_approvals
                    if isinstance(item, dict)
                ],
                "context_policy": (
                    dict(session.context_policy)
                    if isinstance(session.context_policy, dict)
                    else {}
                ),
                "last_prepared_context": (
                    dict(session.last_prepared_context)
                    if isinstance(session.last_prepared_context, dict)
                    else {}
                ),
                "prepared_context_diagnostics": (
                    dict(session.prepared_context_diagnostics)
                    if isinstance(session.prepared_context_diagnostics, dict)
                    else {}
                ),
                "memory_diagnostics": (
                    dict(session.memory_diagnostics)
                    if isinstance(session.memory_diagnostics, dict)
                    else {}
                ),
                "sandbox_diagnostics": (
                    dict(sandbox_diagnostics)
                    if isinstance(sandbox_diagnostics, dict)
                    else {}
                ),
                "last_memory_automation": (
                    dict(getattr(session.agent, "last_memory_automation", {}) or {})
                    if session.agent is not None
                    else {}
                ),
                "last_runtime_task_memory": (
                    dict(getattr(session.agent, "last_runtime_task_memory", {}) or {})
                    if session.agent is not None
                    else {}
                ),
            }
        )
        self._write_metadata(metadata)

    @staticmethod
    def _serialize_pending_approval(item: dict[str, Any]) -> dict[str, Any]:
        return {
            "token": _safe_text(item.get("token")) or None,
            "tool_name": _safe_text(item.get("tool_name")) or None,
            "arguments": dict(item.get("arguments")) if isinstance(item.get("arguments"), dict) else {},
            "kind": _safe_text(item.get("kind")) or None,
            "reason": _safe_text(item.get("reason")) or None,
            "cache_key": _safe_text(item.get("cache_key")) or None,
            "can_escalate": bool(item.get("can_escalate", False)),
            "step": int(item.get("step") or 0),
        }

    def list_session_records(self) -> list[dict[str, Any]]:
        records = []
        for record in self._session_store.list_sessions():
            if not isinstance(record, dict):
                continue
            if _safe_text(record.get("session_kind")) != _RUNTIME_SESSION_KIND:
                continue
            records.append(dict(record))
        records.sort(key=lambda item: str(item.get("updated_at", "")), reverse=True)
        return records

    def load_session_record(self, session_id: str) -> dict[str, Any] | None:
        record = self._session_store.load_session(session_id)
        if not isinstance(record, dict):
            return None
        if _safe_text(record.get("session_kind")) != _RUNTIME_SESSION_KIND:
            return None
        loaded = dict(record)
        loaded["shared_transcript"] = self._read_shared_transcript(session_id, loaded)
        return loaded

    def delete_session(self, session_id: str) -> bool:
        existed = self._session_store.delete_session(session_id)
        try:
            self._shared_transcript_path(session_id).unlink(missing_ok=True)
        except Exception:
            pass
        return existed


@dataclass
class MainAgentSessionState:
    session_id: str
    workspace_dir: Path
    agent: Agent
    lifecycle_state: SessionLifecycleState
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    title: str = ""
    origin_surface: str = ""
    active_surface: str = ""
    reply_enabled: bool = False
    busy: bool = False
    running_state: str = ""
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    shared: bool = False
    knowledge_base_enabled: bool = True
    selected_model_source: str | None = None
    selected_provider_id: str | None = None
    selected_model_id: str | None = None
    pending_model_source: str | None = None
    pending_provider_id: str | None = None
    pending_model_id: str | None = None
    pending_skill_reload: bool = False
    pending_skill_reload_reason: str = ""
    recovery_context_pending: bool = False
    recovery_state: str = ""
    recovery_summary: str = ""
    recovery_last_activity: str | None = None
    recovery_last_user_message: str | None = None
    recovery_last_assistant_message: str | None = None
    recovery_pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    context_policy: dict[str, Any] = field(default_factory=dict)
    last_prepared_context: dict[str, Any] = field(default_factory=dict)
    prepared_context_diagnostics: dict[str, Any] = field(default_factory=dict)
    memory_diagnostics: dict[str, Any] = field(default_factory=dict)
    sandbox_diagnostics: dict[str, Any] = field(default_factory=dict)
    transcript: list["MainAgentSessionTranscriptEntry"] = field(default_factory=list)
    next_transcript_index: int = 1
    current_turn_id: str | None = None
    cancel_event: asyncio.Event | None = None
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    pending_approval_waiters: dict[str, asyncio.Future[bool | None]] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def touch(self, *, now_utc: datetime | None = None) -> None:
        self.updated_at = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)


@dataclass
class MainAgentSessionTranscriptEntry:
    index: int
    role: str
    content: str
    surface: str
    created_at: datetime
    channel_type: str | None = None
    conversation_id: str | None = None
    sender_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


class MainAgentRuntimeMode(str, Enum):
    """Runtime policy modes for main-agent orchestration."""

    SINGLE_MAIN = "single_main"
    TEAM = "team"


@dataclass(frozen=True)
class MainAgentRuntimePolicy:
    """Policy for current single-main mode and future team expansion."""

    mode: MainAgentRuntimeMode = MainAgentRuntimeMode.SINGLE_MAIN
    main_workspace_dir: Path | None = None
    max_active_sessions: int = 1
    reserved_team_slots: int = 4
    workspace_application_required: bool = True
    session_lifecycle: SessionLifecyclePolicy = field(default_factory=SessionLifecyclePolicy)


@dataclass(frozen=True)
class MainAgentRuntimeDiagnostics:
    """Runtime diagnostics snapshot for system health and ops inspection."""

    mode: str
    active_sessions: int
    max_active_sessions: int
    available_session_slots: int
    reserved_team_slots: int
    workspace_application_required: bool
    team_saturation_rejections: int
    team_workspace_conflict_rejections: int
    lifecycle_auto_resets: int
    session_reset_mode: str
    session_idle_seconds: int
    main_workspace_dir: str | None = None


class MainAgentRuntimeManager:
    """In-process manager enforcing main-agent runtime/session policies."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        build_agent: BuildAgentFn,
        build_agent_with_selection: BuildSelectedAgentFn | None = None,
        policy: MainAgentRuntimePolicy | None = None,
        storage_dir: Path | None = None,
    ):
        self._ttl_seconds = int(ttl_seconds)
        self._build_agent = build_agent
        self._build_agent_with_selection = build_agent_with_selection
        self._policy = policy or MainAgentRuntimePolicy()
        self._sessions: dict[str, MainAgentSessionState] = {}
        self._store_lock = asyncio.Lock()
        self._team_saturation_rejections = 0
        self._team_workspace_conflict_rejections = 0
        self._lifecycle_auto_resets = 0
        self._lifecycle_manager = SessionLifecycleManager(self._policy.session_lifecycle)
        self._persistence = _MainAgentRuntimePersistence(storage_dir)

    async def clear(self) -> None:
        async with self._store_lock:
            self._sessions.clear()
            self._team_saturation_rejections = 0
            self._team_workspace_conflict_rejections = 0
            self._lifecycle_auto_resets = 0

    async def build_ephemeral_agent(self, workspace_dir: Path) -> Agent:
        """Build an isolated agent instance without attaching a managed session."""
        self._enforce_main_workspace_policy(workspace_dir)
        return await self._build_agent(workspace_dir)

    def validate_workspace(self, workspace_dir: Path) -> None:
        self._enforce_main_workspace_policy(workspace_dir)

    @staticmethod
    def _normalize_model_source(value: object) -> str | None:
        normalized = _safe_text(value).lower()
        return normalized or None

    @classmethod
    def _normalize_model_identity(
        cls,
        *,
        source: object,
        provider_id: object,
        model_id: object,
    ) -> tuple[str, str, str] | None:
        normalized_source = cls._normalize_model_source(source)
        normalized_provider_id = _safe_text(provider_id)
        normalized_model_id = _safe_text(model_id)
        if normalized_source and normalized_provider_id and normalized_model_id:
            return normalized_source, normalized_provider_id, normalized_model_id
        return None

    @classmethod
    def _route_model_identity(cls, agent: Agent | None) -> tuple[str, str, str] | None:
        route = getattr(agent, "runtime_route", None)
        if route is None:
            return None
        model_id = _safe_text(getattr(route, "model", ""))
        provider_id = _safe_text(getattr(route, "provider_id", ""))
        if not model_id:
            return None
        if provider_id.startswith("preset-"):
            return ("preset", provider_id.removeprefix("preset-"), model_id)
        if provider_id:
            return ("custom", provider_id, model_id)
        return ("config", "config", model_id)

    @classmethod
    def _selected_model_identity(cls, session: "MainAgentSessionState") -> tuple[str, str, str] | None:
        explicit = cls._normalize_model_identity(
            source=session.selected_model_source,
            provider_id=session.selected_provider_id,
            model_id=session.selected_model_id,
        )
        if explicit is not None:
            return explicit
        return cls._route_model_identity(session.agent)

    @classmethod
    def _pending_model_identity(cls, session: "MainAgentSessionState") -> tuple[str, str, str] | None:
        return cls._normalize_model_identity(
            source=session.pending_model_source,
            provider_id=session.pending_provider_id,
            model_id=session.pending_model_id,
        )

    @staticmethod
    def _set_selected_model_identity(
        session: "MainAgentSessionState",
        identity: tuple[str, str, str] | None,
    ) -> None:
        if identity is None:
            session.selected_model_source = None
            session.selected_provider_id = None
            session.selected_model_id = None
            return
        session.selected_model_source, session.selected_provider_id, session.selected_model_id = identity

    @staticmethod
    def _set_pending_model_identity(
        session: "MainAgentSessionState",
        identity: tuple[str, str, str] | None,
    ) -> None:
        if identity is None:
            session.pending_model_source = None
            session.pending_provider_id = None
            session.pending_model_id = None
            return
        session.pending_model_source, session.pending_provider_id, session.pending_model_id = identity

    @staticmethod
    def _clear_pending_skill_reload(session: "MainAgentSessionState") -> None:
        session.pending_skill_reload = False
        session.pending_skill_reload_reason = ""

    @staticmethod
    def _mark_pending_skill_reload(session: "MainAgentSessionState", *, reason: str) -> None:
        session.pending_skill_reload = True
        session.pending_skill_reload_reason = _safe_text(reason) or "workspace skill runtime changed"

    @staticmethod
    def _agent_knowledge_base_enabled(agent: Any) -> bool:
        checker = getattr(agent, "knowledge_base_enabled", None)
        if callable(checker):
            try:
                return bool(checker())
            except Exception:
                pass
        tools = getattr(agent, "tools", None)
        if isinstance(tools, dict):
            return "knowledge_base_query" in tools
        return True

    @classmethod
    def _apply_agent_knowledge_base_enabled(cls, agent: Any, enabled: bool) -> bool:
        setter = getattr(agent, "set_knowledge_base_enabled", None)
        if callable(setter):
            try:
                return bool(setter(enabled))
            except Exception:
                return cls._agent_knowledge_base_enabled(agent)
        return cls._agent_knowledge_base_enabled(agent)

    async def _build_agent_for_identity(
        self,
        workspace_dir: Path,
        identity: tuple[str, str, str] | None,
    ) -> Agent:
        if identity is None or self._build_agent_with_selection is None:
            return await self._build_agent(workspace_dir)
        source, provider_id, model_id = identity
        return await self._build_agent_with_selection(workspace_dir, source, provider_id, model_id)

    @staticmethod
    def _runtime_policy_overrides_from_diagnostics(
        value: Any,
    ) -> tuple[str | None, str | None]:
        diagnostics = normalize_sandbox_diagnostics(value)
        approval_profile = _safe_text(diagnostics.get("approval_profile")).lower() or None
        access_level = _safe_text(diagnostics.get("access_level")).lower() or None
        return approval_profile, access_level

    def _desired_runtime_policy_for_session(
        self,
        session: MainAgentSessionState,
    ) -> tuple[str | None, str | None]:
        return self._runtime_policy_overrides_from_diagnostics(session.sandbox_diagnostics)

    def _desired_runtime_policy_from_record(
        self,
        record: dict[str, Any],
    ) -> tuple[str | None, str | None]:
        return self._runtime_policy_overrides_from_diagnostics(record.get("sandbox_diagnostics"))

    @staticmethod
    def _effective_runtime_policy_for_agent(agent: Any) -> tuple[str, str]:
        policy = getattr(getattr(agent, "runtime_policy_engine", None), "policy", None)
        approval_profile = _safe_text(getattr(policy, "approval_profile", None)).lower() or "build"
        access_level = _safe_text(getattr(policy, "access_level", None)).lower() or "default"
        return approval_profile, access_level

    @staticmethod
    def _load_runtime_config() -> Config:
        return Config.load(allow_interactive_setup=False)

    def _reconfigure_session_agent_runtime_policy(
        self,
        session: MainAgentSessionState,
        *,
        approval_profile: str | None,
        access_level: str | None,
    ) -> dict[str, Any]:
        diagnostics = reconfigure_agent_runtime_policy(
            agent=session.agent,
            config=self._load_runtime_config(),
            workspace_dir=session.workspace_dir,
            approval_profile_override=approval_profile,
            access_level_override=access_level,
        )
        session.sandbox_diagnostics = normalize_sandbox_diagnostics(diagnostics)
        return session.sandbox_diagnostics

    async def get_or_create_session(
        self,
        session_id: str | None,
        workspace_dir: Path,
        *,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        session_title_hint: str | None = None,
    ) -> MainAgentSessionState:
        async with self._store_lock:
            now = datetime.now(timezone.utc)
            self._drop_expired_sessions_unlocked(now_utc=now)

            self._enforce_main_workspace_policy(workspace_dir)
            if self._policy.mode == MainAgentRuntimeMode.SINGLE_MAIN:
                for existing in self._sessions.values():
                    if not self._same_workspace(existing.workspace_dir, workspace_dir):
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                "Main-agent runtime is already active in another workspace. "
                                f"active_session_id={existing.session_id}"
                            ),
                        )
            normalized_surface = self._normalize_surface(surface)
            normalized_channel_type = _safe_text(channel_type) or None
            normalized_conversation_id = _safe_text(conversation_id) or None
            normalized_sender_id = _safe_text(sender_id) or None
            normalized_title_hint = _safe_text(session_title_hint)

            if session_id and session_id in self._sessions:
                session = self._sessions[session_id]
                if not self._same_workspace(session.workspace_dir, workspace_dir):
                    if self._policy.mode == MainAgentRuntimeMode.TEAM:
                        self._team_workspace_conflict_rejections += 1
                    raise HTTPException(status_code=400, detail="Session workspace mismatch.")
                self._refresh_session_lifecycle_unlocked(session, now_utc=now)
                session.touch(now_utc=now)
                self._persist_session_unlocked(session)
                return session

            # Team mode guardrail: if caller did not provide a session id and an
            # active session already exists for this workspace, reuse it to avoid
            # accidental workspace-local fan-out under retries.
            if self._policy.mode == MainAgentRuntimeMode.TEAM and not session_id:
                existing_workspace_session = self._find_latest_session_for_workspace(workspace_dir)
                if existing_workspace_session is not None:
                    self._refresh_session_lifecycle_unlocked(
                        existing_workspace_session,
                        now_utc=now,
                    )
                    existing_workspace_session.touch(now_utc=now)
                    self._persist_session_unlocked(existing_workspace_session)
                    return existing_workspace_session

            if session_id:
                persisted = self._persistence.load_session_record(session_id)
                if persisted is not None:
                    persisted_workspace = Path(str(persisted.get("workspace_dir", "."))).expanduser().resolve()
                    if not self._same_workspace(persisted_workspace, workspace_dir):
                        if self._policy.mode == MainAgentRuntimeMode.TEAM:
                            self._team_workspace_conflict_rejections += 1
                        raise HTTPException(status_code=400, detail="Session workspace mismatch.")
                    session = await self._restore_persisted_session_unlocked(persisted, now_utc=now)
                    self._refresh_session_lifecycle_unlocked(session, now_utc=now)
                    session.touch(now_utc=now)
                    self._persist_session_unlocked(session)
                    return session

            if not session_id:
                persisted_latest = self._find_latest_persisted_session_record_for_workspace(workspace_dir)
                if persisted_latest is not None:
                    session = await self._restore_persisted_session_unlocked(persisted_latest, now_utc=now)
                    if normalized_title_hint and not _safe_text(session.title):
                        session.title = self._allocate_session_title_unlocked(
                            normalized_title_hint,
                            workspace_dir=workspace_dir,
                        )
                    self._refresh_session_lifecycle_unlocked(session, now_utc=now)
                    session.touch(now_utc=now)
                    self._persist_session_unlocked(session)
                    return session

            if (
                self._policy.mode == MainAgentRuntimeMode.TEAM
                and len(self._sessions) >= max(1, int(self._policy.max_active_sessions))
            ):
                self._team_saturation_rejections += 1
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Agent-team runtime reached max_active_sessions. "
                        f"max_active_sessions={self._policy.max_active_sessions}"
                    ),
                )

            new_session_id = session_id or uuid4().hex
            agent = await self._build_agent_for_identity(workspace_dir, None)
            session_key = self._build_session_key(
                session_id=new_session_id,
                workspace_dir=workspace_dir,
            )
            lifecycle_state = self._lifecycle_manager.bootstrap(session_key, now_utc=now)
            session = MainAgentSessionState(
                session_id=new_session_id,
                workspace_dir=workspace_dir,
                agent=agent,
                lifecycle_state=lifecycle_state,
                created_at=now,
                updated_at=now,
                title=(
                    self._allocate_session_title_unlocked(
                        normalized_title_hint,
                        workspace_dir=workspace_dir,
                    )
                    if normalized_title_hint
                    else ""
                ),
                origin_surface=normalized_surface if surface is not None else "",
                active_surface=normalized_surface if surface is not None else "",
                channel_type=normalized_channel_type,
                conversation_id=normalized_conversation_id,
                sender_id=normalized_sender_id,
                shared=False,
                knowledge_base_enabled=self._agent_knowledge_base_enabled(agent),
                sandbox_diagnostics=collect_sandbox_diagnostics(agent=agent),
            )
            self._set_selected_model_identity(session, self._route_model_identity(agent))
            self._sessions[new_session_id] = session
            self._persist_session_unlocked(session)
            return session

    async def create_session(
        self,
        *,
        workspace_dir: Path,
        title: str | None = None,
        surface: str | None = None,
        shared: bool = False,
    ) -> MainAgentSessionState:
        async with self._store_lock:
            now = datetime.now(timezone.utc)
            self._drop_expired_sessions_unlocked(now_utc=now)
            self._enforce_main_workspace_policy(workspace_dir)
            if self._policy.mode == MainAgentRuntimeMode.SINGLE_MAIN:
                for existing in self._sessions.values():
                    if not self._same_workspace(existing.workspace_dir, workspace_dir):
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                "Main-agent runtime is already active in another workspace. "
                                f"active_session_id={existing.session_id}"
                            ),
                        )
            if len(self._sessions) >= max(1, int(self._policy.max_active_sessions)):
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Main-agent runtime reached max_active_sessions. "
                        f"max_active_sessions={self._policy.max_active_sessions}"
                    ),
                )

            normalized_title = self._allocate_session_title_unlocked(
                _safe_text(title) or "Session",
                workspace_dir=workspace_dir,
            )
            normalized_surface = self._normalize_surface(surface) or "tui"
            session_id = uuid4().hex
            agent = await self._build_agent_for_identity(workspace_dir, None)
            session_key = self._build_session_key(
                session_id=session_id,
                workspace_dir=workspace_dir,
            )
            lifecycle_state = self._lifecycle_manager.bootstrap(session_key, now_utc=now)
            session = MainAgentSessionState(
                session_id=session_id,
                workspace_dir=workspace_dir,
                agent=agent,
                lifecycle_state=lifecycle_state,
                created_at=now,
                updated_at=now,
                title=normalized_title,
                origin_surface=normalized_surface,
                active_surface=normalized_surface,
                shared=bool(shared),
                knowledge_base_enabled=self._agent_knowledge_base_enabled(agent),
                sandbox_diagnostics=collect_sandbox_diagnostics(agent=agent),
            )
            self._set_selected_model_identity(session, self._route_model_identity(agent))
            self._sessions[session_id] = session
            self._persist_session_unlocked(session)
            return session

    async def import_session_snapshot(
        self,
        *,
        session_id: str | None,
        workspace_dir: Path,
        title: str | None = None,
        origin_surface: str | None = None,
        active_surface: str | None = None,
        reply_enabled: bool = False,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        token_usage: int = 0,
        token_limit: int = 0,
        shared: bool = False,
        knowledge_base_enabled: bool | None = None,
        selected_model_source: str | None = None,
        selected_provider_id: str | None = None,
        selected_model_id: str | None = None,
        pending_model_source: str | None = None,
        pending_provider_id: str | None = None,
        pending_model_id: str | None = None,
        pending_skill_reload: bool = False,
        pending_skill_reload_reason: str | None = None,
        context_policy: dict[str, Any] | None = None,
        last_prepared_context: dict[str, Any] | None = None,
        prepared_context_diagnostics: dict[str, Any] | None = None,
        memory_diagnostics: dict[str, Any] | None = None,
        sandbox_diagnostics: dict[str, Any] | None = None,
        runtime_task_memory_payload: dict[str, Any] | None = None,
        workspace_shared_runtime_memory_payload: dict[str, Any] | None = None,
        agent_messages: Sequence[dict[str, Any]] | None = None,
        transcript: Sequence[dict[str, Any]] | None = None,
    ) -> MainAgentSessionState:
        async with self._store_lock:
            now = datetime.now(timezone.utc)
            self._drop_expired_sessions_unlocked(now_utc=now)
            self._enforce_main_workspace_policy(workspace_dir)
            if self._policy.mode == MainAgentRuntimeMode.SINGLE_MAIN:
                for existing in self._sessions.values():
                    if not self._same_workspace(existing.workspace_dir, workspace_dir):
                        raise HTTPException(
                            status_code=409,
                            detail=(
                                "Main-agent runtime is already active in another workspace. "
                                f"active_session_id={existing.session_id}"
                            ),
                        )

            if len(self._sessions) >= max(1, int(self._policy.max_active_sessions)):
                if self._policy.mode == MainAgentRuntimeMode.TEAM:
                    self._team_saturation_rejections += 1
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Main-agent runtime reached max_active_sessions. "
                        f"max_active_sessions={self._policy.max_active_sessions}"
                    ),
                )

            requested_session_id = _safe_text(session_id)
            if requested_session_id:
                if requested_session_id in self._sessions:
                    raise HTTPException(status_code=409, detail="Session already exists.")
                if self._persistence.load_session_record(requested_session_id) is not None:
                    raise HTTPException(status_code=409, detail="Session already exists.")
                new_session_id = requested_session_id
            else:
                new_session_id = self._allocate_new_session_id_unlocked()

            selected_identity = self._normalize_model_identity(
                source=selected_model_source,
                provider_id=selected_provider_id,
                model_id=selected_model_id,
            )
            pending_identity = self._normalize_model_identity(
                source=pending_model_source,
                provider_id=pending_provider_id,
                model_id=pending_model_id,
            )
            desired_approval_profile, desired_access_level = self._runtime_policy_overrides_from_diagnostics(
                sandbox_diagnostics
            )
            agent = await self._build_agent_for_identity(workspace_dir, selected_identity)
            if desired_approval_profile or desired_access_level:
                try:
                    reconfigure_agent_runtime_policy(
                        agent=agent,
                        config=self._load_runtime_config(),
                        workspace_dir=workspace_dir,
                        approval_profile_override=desired_approval_profile,
                        access_level_override=desired_access_level,
                    )
                except Exception:
                    pass
            self._restore_agent_messages_payload(agent_messages or [], agent)
            self._restore_agent_token_state(
                agent,
                token_usage=token_usage,
                token_limit=token_limit,
                raw_messages=agent_messages,
            )
            effective_knowledge_base_enabled = (
                bool(knowledge_base_enabled)
                if knowledge_base_enabled is not None
                else self._agent_knowledge_base_enabled(agent)
            )
            effective_knowledge_base_enabled = self._apply_agent_knowledge_base_enabled(
                agent,
                effective_knowledge_base_enabled,
            )
            session_key = self._build_session_key(
                session_id=new_session_id,
                workspace_dir=workspace_dir,
            )
            lifecycle_state = self._lifecycle_manager.bootstrap(session_key, now_utc=now)
            normalized_origin = self._normalize_surface(origin_surface or active_surface or "tui")
            normalized_active = self._normalize_surface(active_surface or origin_surface or normalized_origin)
            session = MainAgentSessionState(
                session_id=new_session_id,
                workspace_dir=workspace_dir,
                agent=agent,
                lifecycle_state=lifecycle_state,
                created_at=now,
                updated_at=now,
                title=_safe_text(title),
                origin_surface=normalized_origin,
                active_surface=normalized_active,
                reply_enabled=bool(reply_enabled),
                busy=False,
                running_state="",
                channel_type=_safe_text(channel_type) or None,
                conversation_id=_safe_text(conversation_id) or None,
                sender_id=_safe_text(sender_id) or None,
                shared=bool(shared),
                knowledge_base_enabled=effective_knowledge_base_enabled,
                selected_model_source=selected_identity[0] if selected_identity is not None else None,
                selected_provider_id=selected_identity[1] if selected_identity is not None else None,
                selected_model_id=selected_identity[2] if selected_identity is not None else None,
                pending_model_source=pending_identity[0] if pending_identity is not None else None,
                pending_provider_id=pending_identity[1] if pending_identity is not None else None,
                pending_model_id=pending_identity[2] if pending_identity is not None else None,
                pending_skill_reload=bool(pending_skill_reload),
                pending_skill_reload_reason=_safe_text(pending_skill_reload_reason),
                context_policy=self._normalize_context_policy_payload(context_policy),
                last_prepared_context=self._normalize_prepared_context_payload(last_prepared_context),
                prepared_context_diagnostics=self._normalize_prepared_context_diagnostics_payload(
                    prepared_context_diagnostics
                ),
                memory_diagnostics=self._normalize_memory_diagnostics_payload(memory_diagnostics),
                sandbox_diagnostics=self._normalize_sandbox_diagnostics_payload(sandbox_diagnostics),
                transcript=self._import_transcript_entries(
                    transcript,
                    default_surface=normalized_active,
                    now_utc=now,
                ),
            )
            session.next_transcript_index = max(
                [entry.index for entry in session.transcript] or [0]
            ) + 1
            if selected_identity is None:
                self._set_selected_model_identity(session, self._route_model_identity(agent))
            self._restore_session_runtime_task_memory_unlocked(
                workspace_dir=workspace_dir,
                session_id=new_session_id,
                payload=runtime_task_memory_payload,
            )
            self._restore_workspace_shared_runtime_task_memory_unlocked(
                workspace_dir=workspace_dir,
                payload=workspace_shared_runtime_memory_payload,
            )
            self.restore_agent_prepared_context_state(session)
            session.memory_diagnostics = self._build_memory_diagnostics_for_session(session)
            session.sandbox_diagnostics = self._build_sandbox_diagnostics_for_session(session)
            self._sessions[new_session_id] = session
            self._persist_session_unlocked(session, agent_messages=agent_messages)
            return session

    async def export_session_snapshot(self, session_id: str) -> RuntimeSessionSnapshot:
        async with self._store_lock:
            session = self._sessions.get(session_id)
            if session is not None:
                return self._build_session_snapshot(session)
            record = self._persistence.load_session_record(session_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Session not found.")
            return self._build_session_snapshot_from_record(record)

    async def get_runtime_diagnostics(self) -> MainAgentRuntimeDiagnostics:
        """Return a lock-consistent runtime diagnostics snapshot."""
        async with self._store_lock:
            max_active_sessions = max(1, int(self._policy.max_active_sessions))
            active_sessions = len(self._sessions)
            available_slots = max(0, max_active_sessions - active_sessions)
            main_workspace = (
                str(self._policy.main_workspace_dir.resolve())
                if self._policy.main_workspace_dir is not None
                else None
            )
            return MainAgentRuntimeDiagnostics(
                mode=self._policy.mode.value,
                active_sessions=active_sessions,
                max_active_sessions=max_active_sessions,
                available_session_slots=available_slots,
                reserved_team_slots=max(1, int(self._policy.reserved_team_slots)),
                workspace_application_required=bool(self._policy.workspace_application_required),
                team_saturation_rejections=max(0, int(self._team_saturation_rejections)),
                team_workspace_conflict_rejections=max(0, int(self._team_workspace_conflict_rejections)),
                lifecycle_auto_resets=max(0, int(self._lifecycle_auto_resets)),
                session_reset_mode=self._policy.session_lifecycle.mode.value,
                session_idle_seconds=max(1, int(self._policy.session_lifecycle.idle_seconds)),
                main_workspace_dir=main_workspace,
            )

    async def list_sessions(
        self,
        *,
        workspace_dir: Path | None = None,
        shared_only: bool = False,
    ) -> list[MainAgentSessionSummary]:
        async with self._store_lock:
            active_by_id = {
                session.session_id: self._build_session_summary(session)
                for session in self._sessions.values()
            }
            for record in self._persistence.list_session_records():
                session_id = _safe_text(record.get("session_id"))
                if not session_id or session_id in active_by_id:
                    continue
                active_by_id[session_id] = self._build_session_summary_from_record(record)
            sessions = list(active_by_id.values())
            if workspace_dir is not None:
                filtered: list[MainAgentSessionSummary] = []
                for item in sessions:
                    try:
                        item_workspace = Path(item.workspace_dir).expanduser().resolve()
                    except Exception:
                        continue
                    if self._same_workspace(item_workspace, workspace_dir):
                        filtered.append(item)
                sessions = filtered
            if shared_only:
                sessions = [item for item in sessions if bool(item.shared)]
            sessions.sort(key=lambda item: item.updated_at, reverse=True)
            return self._dedupe_session_summaries(sessions)

    async def rename_session(self, session_id: str, *, title: str) -> MainAgentSessionSummary:
        async with self._store_lock:
            session = await self._load_managed_session_unlocked(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found.")
        async with session.lock:
            session.title = _safe_text(title) or session.title or "Session"
            session.touch()
            self._persist_session_unlocked(session)
            return self._build_session_summary(session)

    async def set_session_shared(self, session_id: str, *, shared: bool) -> MainAgentSessionSummary:
        async with self._store_lock:
            session = await self._load_managed_session_unlocked(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found.")
        async with session.lock:
            session.shared = bool(shared)
            session.touch()
            self._persist_session_unlocked(session)
            return self._build_session_summary(session)

    async def get_session_detail(
        self,
        session_id: str,
        *,
        recent_limit: int = 50,
    ) -> MainAgentSessionDetail:
        async with self._store_lock:
            session = self._sessions.get(session_id)
            if session is not None:
                return self._build_session_detail(session, recent_limit=recent_limit)
            record = self._persistence.load_session_record(session_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Session not found.")
            return self._build_session_detail_from_record(record, recent_limit=recent_limit)

    async def get_recent_messages(
        self,
        session_id: str,
        *,
        limit: int = 10,
    ) -> list[MainAgentSessionMessage]:
        async with self._store_lock:
            session = self._sessions.get(session_id)
            normalized_limit = max(1, int(limit))
            if session is not None:
                entries = session.transcript[-normalized_limit:]
                return [self._build_session_message(entry) for entry in entries]
            record = self._persistence.load_session_record(session_id)
            if record is None:
                raise HTTPException(status_code=404, detail="Session not found.")
            transcript = self._transcript_entries_from_record(record)
            return [self._build_session_message(entry) for entry in transcript[-normalized_limit:]]

    async def delete_session(self, session_id: str) -> None:
        async with self._store_lock:
            found = False
            workspace_dir: Path | None = None
            if session_id in self._sessions:
                existing = self._sessions.pop(session_id, None)
                if existing is not None:
                    workspace_dir = existing.workspace_dir
                found = True
            if workspace_dir is None:
                record = self._persistence.load_session_record(session_id)
                if isinstance(record, dict):
                    workspace_dir = Path(str(record.get("workspace_dir", "."))).expanduser().resolve()
            if workspace_dir is not None:
                self._clear_runtime_task_memory_namespace(
                    workspace_dir=workspace_dir,
                    session_id=session_id,
                )
            if self._persistence.delete_session(session_id):
                found = True
            if not found:
                raise HTTPException(status_code=404, detail="Session not found.")

    async def reset_session(self, session_id: str) -> None:
        async with self._store_lock:
            session = await self._load_managed_session_unlocked(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found.")
        async with session.lock:
            self._reset_session_runtime_state_unlocked(
                session,
                clear_runtime_task_memory=True,
            )
            session.transcript.clear()
            session.next_transcript_index = 1
            session.lifecycle_state = self._lifecycle_manager.reset(session.lifecycle_state)
            session.lifecycle_state = self._lifecycle_manager.touch(session.lifecycle_state)
            session.touch()
            self._persist_session_unlocked(session)

    async def cancel_session_turn(
        self,
        session_id: str,
        *,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMutationResponse:
        async with self._store_lock:
            session = self._sessions.get(session_id)
            if session is None:
                if self._persistence.load_session_record(session_id) is None:
                    raise HTTPException(status_code=404, detail="Session not found.")
                raise HTTPException(status_code=409, detail="Session has no running turn to cancel.")

            if not session.busy:
                raise HTTPException(status_code=409, detail="Session has no running turn to cancel.")

            cancel_event = session.cancel_event
            if cancel_event is None:
                raise HTTPException(status_code=409, detail="Session turn is not cancellable.")

            if not cancel_event.is_set():
                cancel_event.set()
            for future in list(session.pending_approval_waiters.values()):
                if not future.done():
                    future.set_result(None)

            normalized_surface = self._normalize_surface(session.active_surface or session.origin_surface)
            session.running_state = "cancellation requested"
            self._append_transcript_unlocked(
                session,
                role="system",
                content=self._session_cancel_details(reason),
                surface=surface or normalized_surface,
                metadata={
                    "kind": "command",
                    "command": "cancel",
                    "summary": "cancellation requested",
                    "level": "info",
                },
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            session.touch()
            self._persist_session_unlocked(session)
            return MainAgentSessionMutationResponse(
                status="cancel_requested",
                session_id=session.session_id,
                active_surface=normalized_surface,
            )

    async def set_active_surface(self, session_id: str, *, surface: str) -> MainAgentSessionSummary:
        async with self._store_lock:
            session = await self._load_managed_session_unlocked(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found.")
        async with session.lock:
            now = datetime.now(timezone.utc)
            self._apply_surface_binding_unlocked(
                session,
                surface=surface,
                reply_enabled=False,
                now_utc=now,
            )
            session.touch(now_utc=now)
            self._persist_session_unlocked(session)
            return self._build_session_summary(session)

    async def control_session_context(
        self,
        session_id: str,
        *,
        action: str,
        reason: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionControlResponse:
        async with self._store_lock:
            session = await self._load_managed_session_unlocked(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found.")

        normalized_action = _safe_text(action).lower().replace("-", "_")
        if normalized_action not in {
            "compact",
            "drop_memories",
            "kb_on",
            "kb_off",
            "mcp_status",
            "mcp_list",
            "mcp_reload",
        }:
            raise HTTPException(status_code=400, detail=f"Unsupported session control action: {action}")

        async with session.lock:
            if session.busy and normalized_action not in {"mcp_status", "mcp_list"}:
                raise HTTPException(status_code=409, detail="Session is busy. Wait for the current turn to finish.")

            if normalized_action in {"mcp_status", "mcp_list", "mcp_reload"}:
                try:
                    config = Config.load(allow_interactive_setup=False)
                except Exception as exc:
                    raise HTTPException(
                        status_code=500,
                        detail=f"Failed to load config for MCP inspection: {exc}",
                    ) from exc

                if normalized_action == "mcp_reload":
                    try:
                        await cleanup_mcp_connections()
                        await self._rebuild_session_agent_with_identity(
                            session,
                            self._selected_model_identity(session),
                        )
                    except Exception as exc:
                        raise HTTPException(
                            status_code=500,
                            detail=f"MCP reload failed: {exc}",
                        ) from exc

                snapshot = collect_mcp_operator_snapshot(config)
                summary, details = self._session_mcp_control_output(
                    normalized_action,
                    snapshot=snapshot,
                )
                response = MainAgentSessionControlResponse(
                    status="controlled",
                    session_id=session.session_id,
                    action=normalized_action,
                    applied=normalized_action == "mcp_reload",
                    active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                    knowledge_base_enabled=bool(session.knowledge_base_enabled),
                    stats={
                        "summary": summary,
                        "details": details,
                        "configured_total": int(snapshot.configured_total),
                        "discoverable_total": int(snapshot.discoverable_total),
                        "disabled_total": int(snapshot.disabled_total),
                        "active_total": int(snapshot.active_total),
                        "tool_total": int(snapshot.tool_total),
                    },
                )
            elif normalized_action in {"kb_on", "kb_off"}:
                desired_enabled = normalized_action == "kb_on"
                previous_enabled = bool(session.knowledge_base_enabled)
                effective_enabled = self._apply_agent_knowledge_base_enabled(
                    session.agent,
                    desired_enabled,
                )
                session.knowledge_base_enabled = effective_enabled
                response = MainAgentSessionControlResponse(
                    status="controlled",
                    session_id=session.session_id,
                    action=normalized_action,
                    applied=(previous_enabled != effective_enabled),
                    active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                    reason=_safe_text(reason) or None,
                    knowledge_base_enabled=effective_enabled,
                )
            else:
                if normalized_action == "compact":
                    control_method = getattr(session.agent, "compact_context", None)
                else:
                    control_method = getattr(session.agent, "drop_memories", None)

                if control_method is None:
                    raise HTTPException(status_code=400, detail=f"Session control not supported: {normalized_action}")

                result = control_method(reason=reason)
                if inspect.isawaitable(result):
                    result = await result
                if not isinstance(result, dict):
                    result = {"applied": bool(result)}

                response = MainAgentSessionControlResponse(
                    status="controlled",
                    session_id=session.session_id,
                    action=normalized_action,
                    applied=bool(result.get("applied", False)),
                    active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                    reason=_safe_text(reason) or None,
                    message_count_before=max(0, int(result.get("message_count_before") or 0)),
                    message_count_after=max(0, int(result.get("message_count_after") or 0)),
                    token_count_before=max(0, int(result.get("token_count_before") or 0)),
                    token_count_after=max(0, int(result.get("token_count_after") or 0)),
                    knowledge_base_enabled=bool(session.knowledge_base_enabled),
                    stats=dict(result.get("stats")) if isinstance(result.get("stats"), dict) else None,
                )

            command_summary = self._session_control_summary(
                normalized_action,
                applied=response.applied,
                response=response,
            )
            command_details = self._session_control_details(response)
            self._append_transcript_unlocked(
                session,
                role="system",
                content=command_details,
                surface=surface or session.active_surface or session.origin_surface,
                metadata={
                    "kind": "command",
                    "command": self._session_control_command_name(normalized_action),
                    "summary": command_summary,
                    "level": "info",
                    **({"threads_visible": False} if normalized_action.startswith("mcp_") else {}),
                },
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            session.touch()
            self._persist_session_unlocked(session)
            return response

    async def update_session_context_policy(
        self,
        session_id: str,
        *,
        action: str,
        sources: Sequence[str] | None = None,
        max_items: int | None = None,
        max_total_chars: int | None = None,
        max_items_per_source: int | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionContextResponse:
        async with self._store_lock:
            session = await self._load_managed_session_unlocked(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found.")

        normalized_action = _safe_text(action).lower().replace("-", "_")
        if normalized_action not in {"include", "exclude", "budget", "reset"}:
            raise HTTPException(status_code=400, detail=f"Unsupported session context action: {action}")

        async with session.lock:
            if session.busy:
                raise HTTPException(status_code=409, detail="Session is busy. Wait for the current turn to finish.")

            normalized = self._normalize_context_policy_payload(session.context_policy)
            if normalized_action in {"include", "exclude"}:
                normalized_sources = [
                    item
                    for item in (_safe_text(value).lower() for value in list(sources or []))
                    if item
                ]
                if not normalized_sources:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Session context action requires sources: {normalized_action}",
                    )
                field_name = "include_sources" if normalized_action == "include" else "exclude_sources"
                normalized[field_name] = normalized_sources
                normalized = self._normalize_context_policy_payload(normalized)
            elif normalized_action == "budget":
                if max_items is None:
                    raise HTTPException(
                        status_code=400,
                        detail="Session context budget requires max_items.",
                    )
                normalized["max_items"] = max(1, int(max_items))
                if max_total_chars is not None:
                    normalized["max_total_chars"] = max(200, int(max_total_chars))
                if max_items_per_source is not None:
                    normalized["max_items_per_source"] = max(1, int(max_items_per_source))
                normalized = self._normalize_context_policy_payload(normalized)
            else:
                normalized = self._normalize_context_policy_payload({})

            session.context_policy = normalized
            command_name = f"context {normalized_action}"
            self._append_transcript_unlocked(
                session,
                role="system",
                content=format_context_policy_details(normalized, include_header=True),
                surface=surface or session.active_surface or session.origin_surface,
                metadata={
                    "kind": "command",
                    "command": command_name,
                    "summary": context_policy_summary_line(normalized, include_default=True),
                    "level": "info",
                    "threads_visible": False,
                },
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            session.touch()
            self._persist_session_unlocked(session)
            return MainAgentSessionContextResponse(
                status="updated",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                context_policy=dict(normalized),
            )

    async def manage_session_memory(
        self,
        session_id: str,
        *,
        action: str,
        engram_id: str | None = None,
        content: str | None = None,
        query: str | None = None,
        day: str | None = None,
        export_format: str | None = None,
        detail_mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionMemoryResponse:
        async with self._store_lock:
            session = await self._load_managed_session_unlocked(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found.")

        normalized_action = _safe_text(action).lower().replace("-", "_")
        normalized_engram_id = _safe_text(engram_id) or None
        normalized_content = _safe_text(content) or None
        normalized_query = _safe_text(query) or None
        normalized_day = _safe_text(day) or None
        normalized_export_format = _safe_text(export_format).lower() or None
        normalized_detail_mode = _safe_text(detail_mode).lower() or "full"
        if normalized_detail_mode not in {"brief", "full"}:
            raise HTTPException(status_code=400, detail="detail_mode must be brief or full.")

        if normalized_action not in {
            "status",
            "show",
            "session_show",
            "list",
            "overview",
            "export",
            "consolidated_show",
            "consolidated_search",
            "profile",
            "notes",
            "daily",
            "refresh",
            "runtime",
            "shared_list",
            "shared_show",
            "shared_clear",
            "promote_shared",
            "promote_note",
            "promote_profile",
            "save_note",
            "save_profile",
        }:
            raise HTTPException(status_code=400, detail=f"Unsupported session memory action: {action}")

        if normalized_action in {"status", "show", "runtime", "list", "shared_list"}:
            diagnostics = self._build_memory_diagnostics_for_session(session)
            result = self._session_memory_read_result(
                action=normalized_action,
                diagnostics=diagnostics,
                detail_mode=normalized_detail_mode,
            )
            self._persist_session_unlocked(session)
            return MainAgentSessionMemoryResponse(
                status="ok",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                memory_diagnostics=dict(diagnostics),
                result=result,
            )
        if normalized_action in {
            "overview",
            "export",
            "consolidated_show",
            "consolidated_search",
            "profile",
            "notes",
            "daily",
        }:
            diagnostics = self._build_memory_diagnostics_for_session(session)
            memory = MemoryService(session.workspace_dir)
            refresh_status = memory.consolidated_refresh_status(exclude_session_id=session.session_id)
            if normalized_action == "overview":
                overview = build_memory_overview_payload(
                    memory=memory,
                    diagnostics=diagnostics,
                    exclude_session_id=session.session_id,
                )
                result = {
                    "summary": "memory overview shown",
                    "details": "\n".join(format_memory_overview_details(overview)).strip(),
                    "overview": overview,
                }
            elif normalized_action == "export":
                try:
                    export_payload = memory.export_notes(format=normalized_export_format or "jsonl")
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                summary = memory.summary()
                result = {
                    "summary": "memory export prepared",
                    "details": "\n".join(
                        format_memory_export_details(
                            export_payload,
                            workspace_dir=summary.workspace_dir,
                            memory_root=summary.memory_root,
                            long_term_file=summary.long_term_file,
                            daily_dir=summary.daily_dir,
                        )
                    ).strip(),
                    "export": export_payload,
                }
            elif normalized_action == "consolidated_show":
                snapshot = memory.consolidated_snapshot()
                snapshot["memory_file"] = refresh_status.get("memory_file")
                result = {
                    "summary": "consolidated memory shown",
                    "details": "\n".join(
                        format_consolidated_memory_details(
                            snapshot,
                            refresh_status=refresh_status,
                            limit=20,
                        )
                    ).strip(),
                    "snapshot": snapshot,
                }
            elif normalized_action == "consolidated_search":
                if not normalized_query:
                    raise HTTPException(status_code=400, detail="Usage: /memory consolidated search <query>")
                payload = memory.search_relevant_consolidated_memory(
                    query=normalized_query,
                    top_k=10,
                )
                result = {
                    "summary": "consolidated memory matches shown",
                    "details": "\n".join(
                        format_consolidated_memory_search_details(
                            payload,
                            refresh_status=refresh_status,
                            limit=10,
                        )
                    ).strip(),
                    "query": normalized_query,
                    "search": payload,
                }
            elif normalized_action == "profile":
                profile = memory.profile()
                matches = memory.search_profile(query=normalized_query, limit=10) if normalized_query else None
                result = {
                    "summary": "global profile matches shown" if normalized_query else "global profile shown",
                    "details": "\n".join(
                        format_global_profile_details(
                            profile,
                            query=normalized_query,
                            matches=matches,
                            limit=20,
                        )
                    ).strip(),
                    "profile": profile,
                    "matches": matches or [],
                    "query": normalized_query,
                }
            elif normalized_action == "notes":
                summary = memory.summary()
                if normalized_query:
                    ranked = memory.rank_workspace_notes(query=normalized_query)[:10]
                    note_items = [
                        {
                            **memory.note_to_dict(note),
                            "score": score,
                        }
                        for note, score in ranked
                    ]
                    result = {
                        "summary": "workspace durable note matches shown",
                        "details": "\n".join(
                            format_workspace_note_details(
                                workspace_dir=summary.workspace_dir,
                                memory_root=summary.memory_root,
                                long_term_file=summary.long_term_file,
                                daily_dir=summary.daily_dir,
                                categories=summary.categories,
                                notes=note_items,
                                query=normalized_query,
                                total=len(note_items),
                            )
                        ).strip(),
                        "query": normalized_query,
                        "items": note_items,
                    }
                else:
                    recent_notes = [
                        memory.note_to_dict(note)
                        for note in memory.search_notes(query="", limit=10)
                    ]
                    result = {
                        "summary": "workspace durable notes shown",
                        "details": "\n".join(
                            format_workspace_note_details(
                                workspace_dir=summary.workspace_dir,
                                memory_root=summary.memory_root,
                                long_term_file=summary.long_term_file,
                                daily_dir=summary.daily_dir,
                                categories=summary.categories,
                                notes=recent_notes,
                                total=summary.notes_count,
                            )
                        ).strip(),
                        "items": recent_notes,
                    }
            else:
                if not normalized_day:
                    raise HTTPException(status_code=400, detail="Usage: /memory daily <YYYY-MM-DD>")
                try:
                    snapshot = memory.daily_snapshot(day=normalized_day)
                except FileNotFoundError as exc:
                    raise HTTPException(status_code=404, detail=str(exc)) from exc
                except ValueError as exc:
                    raise HTTPException(status_code=400, detail=str(exc)) from exc
                note_items = [memory.note_to_dict(note) for note in snapshot.notes]
                result = {
                    "summary": "workspace daily memory shown",
                    "details": "\n".join(
                        format_workspace_daily_details(
                            workspace_dir=snapshot.workspace_dir,
                            day=snapshot.day,
                            path=snapshot.path,
                            notes=note_items,
                            note_count=snapshot.note_count,
                        )
                    ).strip(),
                    "day": snapshot.day,
                    "items": note_items,
                }
            self._persist_session_unlocked(session)
            return MainAgentSessionMemoryResponse(
                status="ok",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                memory_diagnostics=dict(diagnostics),
                result=result,
            )
        if normalized_action == "session_show":
            diagnostics = self._build_memory_diagnostics_for_session(session)
            if not normalized_engram_id:
                raise HTTPException(
                    status_code=400,
                    detail=format_runtime_session_selector_help(
                        diagnostics,
                        usage_command="/memory show <selector>",
                    ),
                )
            resolved_engram_id = resolve_runtime_session_engram_selector(
                diagnostics,
                normalized_engram_id,
            )
            if not resolved_engram_id:
                raise HTTPException(
                    status_code=400,
                    detail=format_runtime_session_selector_help(
                        diagnostics,
                        usage_command="/memory show <selector>",
                    ),
                )
            runtime = WorkspaceMemoriaRuntime(session.workspace_dir)
            entry = runtime.get_namespace_entry(
                WorkspaceMemoriaRuntime.session_namespace(session.session_id),
                engram_id=resolved_engram_id,
            )
            if entry is None:
                raise HTTPException(
                    status_code=404,
                    detail=format_runtime_session_selector_help(
                        diagnostics,
                        usage_command="/memory show <selector>",
                    ),
                )
            details_lines = [
                "Session Runtime Memory",
                *format_runtime_memory_entry_details(entry),
            ]
            result = {
                "summary": "session runtime memory entry shown",
                "details": "\n".join(details_lines).strip(),
                "engram_id": resolved_engram_id,
                "entry": entry,
            }
            self._persist_session_unlocked(session)
            return MainAgentSessionMemoryResponse(
                status="ok",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                memory_diagnostics=dict(diagnostics),
                result=result,
            )
        if normalized_action == "shared_show":
            diagnostics = self._build_memory_diagnostics_for_session(session)
            if not normalized_engram_id:
                raise HTTPException(
                    status_code=400,
                    detail=format_runtime_shared_selector_help(
                        diagnostics,
                        usage_command="/memory shared show <selector>",
                    ),
                )
            resolved_engram_id = resolve_runtime_shared_engram_selector(
                diagnostics,
                normalized_engram_id,
            )
            if not resolved_engram_id:
                raise HTTPException(
                    status_code=400,
                    detail=format_runtime_shared_selector_help(
                        diagnostics,
                        usage_command="/memory shared show <selector>",
                    ),
                )
            runtime = WorkspaceMemoriaRuntime(session.workspace_dir)
            entry = runtime.get_workspace_shared_entry(engram_id=resolved_engram_id)
            if entry is None:
                raise HTTPException(
                    status_code=404,
                    detail=format_runtime_shared_selector_help(
                        diagnostics,
                        usage_command="/memory shared show <selector>",
                    ),
                )
            details_lines = [
                "Workspace-Shared Runtime Memory",
                *format_runtime_memory_entry_details(entry),
            ]
            result = {
                "summary": "workspace-shared runtime memory entry shown",
                "details": "\n".join(details_lines).strip(),
                "engram_id": resolved_engram_id,
                "entry": entry,
            }
            self._persist_session_unlocked(session)
            return MainAgentSessionMemoryResponse(
                status="ok",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                memory_diagnostics=dict(diagnostics),
                result=result,
            )

        async with session.lock:
            if session.busy:
                raise HTTPException(status_code=409, detail="Session is busy. Wait for the current turn to finish.")

            if normalized_action == "refresh":
                memory = MemoryService(session.workspace_dir)
                refresh = memory.refresh_consolidated_memory(exclude_session_id=session.session_id)
                session.memory_diagnostics = self._build_memory_diagnostics_for_session(session)
                details = format_memory_diagnostics(
                    session.memory_diagnostics,
                    include_header=True,
                    detail_mode=normalized_detail_mode,
                )
                summary = (
                    "memory refreshed"
                    if bool(refresh.get("refreshed"))
                    else f"memory {str(refresh.get('reason') or 'fresh').replace('_', ' ')}"
                )
                result = {
                    "summary": summary,
                    "details": details,
                    "refresh": refresh,
                }
            elif normalized_action == "shared_clear":
                runtime = WorkspaceMemoriaRuntime(session.workspace_dir)
                cleared = runtime.clear_workspace_shared_namespace()
                session.memory_diagnostics = self._build_memory_diagnostics_for_session(session)
                summary = (
                    "workspace-shared runtime memory cleared"
                    if cleared
                    else "workspace-shared runtime memory already empty"
                )
                details_lines = [
                    "Workspace-Shared Runtime Memory",
                    f"Action: {normalized_action}",
                    f"Cleared: {'yes' if cleared else 'no'}",
                    "",
                    format_memory_diagnostics(
                        session.memory_diagnostics,
                        include_header=True,
                        detail_mode=normalized_detail_mode,
                    ),
                ]
                result = {
                    "summary": summary,
                    "details": "\n".join(line for line in details_lines if line is not None).strip(),
                    "cleared": cleared,
                }
            else:
                session.memory_diagnostics = self._build_memory_diagnostics_for_session(session)
                if normalized_action in {"promote_shared", "promote_note", "promote_profile"}:
                    if not normalized_engram_id:
                        promote_target = (
                            "shared"
                            if normalized_action == "promote_shared"
                            else "note" if normalized_action == "promote_note" else "profile"
                        )
                        raise HTTPException(
                            status_code=400,
                            detail=format_runtime_session_selector_help(
                                session.memory_diagnostics,
                                usage_command=(
                                    f"/memory promote {promote_target} <selector>"
                                ),
                            ),
                        )
                    resolved_engram_id = resolve_runtime_session_engram_selector(
                        session.memory_diagnostics,
                        normalized_engram_id,
                    )
                    if not resolved_engram_id:
                        promote_target = (
                            "shared"
                            if normalized_action == "promote_shared"
                            else "note" if normalized_action == "promote_note" else "profile"
                        )
                        raise HTTPException(
                            status_code=400,
                            detail=format_runtime_session_selector_help(
                                session.memory_diagnostics,
                                usage_command=(
                                    f"/memory promote {promote_target} <selector>"
                                ),
                            ),
                        )
                    runtime = WorkspaceMemoriaRuntime(session.workspace_dir)
                    if normalized_action == "promote_shared":
                        promotion = runtime.promote_session_memory_to_workspace_shared(
                            session_id=session.session_id,
                            engram_id=resolved_engram_id,
                        )
                        summary = "runtime memory promoted to workspace-shared memory"
                    elif normalized_action == "promote_note":
                        promotion = runtime.promote_session_memory_to_workspace_note(
                            session_id=session.session_id,
                            engram_id=resolved_engram_id,
                        )
                        summary = "runtime memory promoted to workspace note"
                    else:
                        promotion = runtime.promote_session_memory_to_global_profile(
                            session_id=session.session_id,
                            engram_id=resolved_engram_id,
                        )
                        summary = "runtime memory promoted to global profile"
                    session.memory_diagnostics = self._build_memory_diagnostics_for_session(session)
                    details_lines = [
                        f"Action: {normalized_action}",
                    ]
                    if normalized_engram_id != resolved_engram_id:
                        details_lines.append(f"Selector: {normalized_engram_id}")
                    details_lines.append(f"Engram: {resolved_engram_id}")
                    if promotion.get("target"):
                        details_lines.append(f"Target: {promotion.get('target')}")
                    if promotion.get("category"):
                        details_lines.append(f"Category: {promotion.get('category')}")
                    if promotion.get("content"):
                        details_lines.append(f"Content: {promotion.get('content')}")
                    details_lines.extend(
                        format_knowledge_base_grounding_lines(
                            promotion.get("knowledge_base_grounding"),
                        )
                    )
                    details_lines.append("")
                    details_lines.append(
                        format_memory_diagnostics(
                            session.memory_diagnostics,
                            include_header=True,
                            detail_mode=normalized_detail_mode,
                        )
                    )
                    result = {
                        "summary": summary,
                        "details": "\n".join(line for line in details_lines if line is not None).strip(),
                        "promotion": promotion,
                        "engram_id": resolved_engram_id,
                        "selector": normalized_engram_id,
                    }
                else:
                    if not normalized_content:
                        raise HTTPException(
                            status_code=400,
                            detail=(
                                "Usage: /memory save "
                                f"{'note' if normalized_action == 'save_note' else 'profile'} <text>"
                            ),
                        )
                    prepared_sources = []
                    if isinstance(session.memory_diagnostics.get("prepared_context_sources"), list):
                        prepared_sources = [
                            _safe_text(item).lower()
                            for item in session.memory_diagnostics.get("prepared_context_sources", [])
                            if _safe_text(item)
                        ]
                    if normalized_action == "save_note":
                        save_result = save_operator_workspace_note(
                            workspace_dir=session.workspace_dir,
                            content=normalized_content,
                            prepared_context_sources=prepared_sources,
                            prepared_context=session.last_prepared_context,
                        )
                        summary = "operator note saved to workspace memory"
                    else:
                        save_result = save_operator_profile_fact(
                            workspace_dir=session.workspace_dir,
                            content=normalized_content,
                        )
                        summary = (
                            "operator profile fact saved"
                            if bool(save_result.get("saved"))
                            else "operator profile fact already present"
                        )
                    session.memory_diagnostics = self._build_memory_diagnostics_for_session(session)
                    details_lines = [
                        f"Action: {normalized_action}",
                        f"Target: {save_result.get('target')}",
                    ]
                    if save_result.get("category"):
                        details_lines.append(f"Category: {save_result.get('category')}")
                    if save_result.get("content"):
                        details_lines.append(f"Content: {save_result.get('content')}")
                    details_lines.extend(
                        format_knowledge_base_grounding_lines(
                            save_result.get("knowledge_base_grounding"),
                        )
                    )
                    details_lines.append("")
                    details_lines.append(
                        format_memory_diagnostics(
                            session.memory_diagnostics,
                            include_header=True,
                            detail_mode=normalized_detail_mode,
                        )
                    )
                    result = {
                        "summary": summary,
                        "details": "\n".join(line for line in details_lines if line is not None).strip(),
                        "saved": save_result,
                    }

            self._append_transcript_unlocked(
                session,
                role="system",
                content=str(result.get("details") or ""),
                surface=surface or session.active_surface or session.origin_surface,
                metadata={
                    "kind": "command",
                    "command": f"memory {normalized_action}",
                    "summary": str(result.get("summary") or "memory command"),
                    "level": "info",
                    "threads_visible": False,
                    **({"engram_id": str(result.get("engram_id") or normalized_engram_id)} if (result.get("engram_id") or normalized_engram_id) else {}),
                },
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            session.touch()
            self._persist_session_unlocked(session)
            return MainAgentSessionMemoryResponse(
                status="ok",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                memory_diagnostics=dict(session.memory_diagnostics),
                result=result,
            )

    async def manage_session_skills(
        self,
        session_id: str,
        *,
        action: str,
        skill_name: str | None = None,
        path: str | None = None,
        query: str | None = None,
        mode: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionSkillResponse:
        async with self._store_lock:
            session = await self._load_managed_session_unlocked(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found.")

        normalized_action = _safe_text(action).lower().replace("-", "_")
        normalized_skill_name = _safe_text(skill_name) or None
        normalized_path = _safe_text(path) or None
        normalized_query = _safe_text(query) or None
        normalized_mode = _safe_text(mode) or None
        if normalized_action not in {"list", "show", "search", "refresh", "active", "mode", "enable", "disable", "reset", "install"}:
            raise HTTPException(status_code=400, detail=f"Unsupported session skill action: {action}")

        try:
            loader = resolve_skill_catalog_loader(
                workspace_dir=session.workspace_dir,
                agent=session.agent,
            )
        except Exception as exc:
            return MainAgentSessionSkillResponse(
                status="unavailable",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                result={
                    "summary": "skill catalog unavailable",
                    "details": f"Skill catalog unavailable: {exc}",
                },
            )

        if loader is None:
            return MainAgentSessionSkillResponse(
                status="disabled",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                result={
                    "summary": "skill support disabled",
                    "details": "Skill support is disabled in the active configuration.",
                },
            )

        policy_store = resolve_workspace_skill_policy_store(session.workspace_dir)
        policy = load_workspace_skill_policy(session.workspace_dir)

        if normalized_action == "list":
            entries = refresh_skill_catalog_loader(loader)
            counts = summarize_skill_entries(entries, policy)
            return MainAgentSessionSkillResponse(
                status="ok",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                result={
                    "summary": (
                        f"{counts['total']} skill(s) | {counts['active']} active | "
                        f"{counts['ready']} ready | {counts['blocked']} blocked | mode {policy.mode}"
                    ),
                    "details": format_skill_entries(entries, policy),
                    "counts": counts,
                    "policy": policy.to_dict(),
                },
            )
        if normalized_action == "active":
            entries = refresh_skill_catalog_loader(loader)
            counts = summarize_skill_entries(entries, policy)
            return MainAgentSessionSkillResponse(
                status="ok",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                result={
                    "summary": f"{counts['active']} active skill(s) | mode {policy.mode}",
                    "details": format_skill_policy_overview(policy, entries),
                    "counts": counts,
                    "policy": policy.to_dict(),
                },
            )
        if normalized_action == "show":
            if not normalized_skill_name:
                raise HTTPException(status_code=400, detail="Usage: /skill show <skill_name>")
            refresh_skill_catalog_loader(loader)
            entry, details = format_skill_detail(loader, normalized_skill_name)
            return MainAgentSessionSkillResponse(
                status="ok" if entry is not None else "not_found",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                result={
                    "summary": f"showing {entry.name}" if entry is not None else "skill not found",
                    "details": details,
                    "skill_name": normalized_skill_name,
                    "found": entry is not None,
                    "active": bool(entry is not None and summarize_skill_entries([entry], policy)["active"] > 0),
                },
            )
        if normalized_action == "search":
            if not normalized_query:
                raise HTTPException(status_code=400, detail="Usage: /skill search <query>")
            refresh_skill_catalog_loader(loader)
            hits = search_skill_entries(loader, normalized_query)
            return MainAgentSessionSkillResponse(
                status="ok",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                result={
                    "summary": f"{len(hits)} match(es)" if hits else "no matches",
                    "details": format_skill_search_results(normalized_query, hits, policy),
                    "query": normalized_query,
                    "match_count": len(hits),
                    "policy": policy.to_dict(),
                },
            )

        entries = refresh_skill_catalog_loader(loader)
        if normalized_action == "mode":
            requested_mode = normalized_mode or normalized_query or normalized_skill_name
            if not requested_mode:
                raise HTTPException(status_code=400, detail="Usage: /skill mode <all|allowlist>")
            try:
                updated_policy = policy_store.set_mode(requested_mode)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            summary = f"skill mode set to {updated_policy.mode}"
            details = format_skill_policy_overview(updated_policy, entries)
        elif normalized_action == "enable":
            if not normalized_skill_name:
                raise HTTPException(status_code=400, detail="Usage: /skill enable <skill_name>")
            entry = find_skill_entry(loader, normalized_skill_name)
            if entry is None:
                raise HTTPException(status_code=404, detail=f"Skill not found: {normalized_skill_name}")
            updated_policy = policy_store.enable([entry.name])
            summary = f"enabled {entry.name} in workspace policy"
            details = format_skill_policy_overview(updated_policy, entries)
        elif normalized_action == "disable":
            if not normalized_skill_name:
                raise HTTPException(status_code=400, detail="Usage: /skill disable <skill_name>")
            entry = find_skill_entry(loader, normalized_skill_name)
            if entry is None:
                raise HTTPException(status_code=404, detail=f"Skill not found: {normalized_skill_name}")
            updated_policy = policy_store.disable([entry.name])
            summary = f"disabled {entry.name} in workspace policy"
            details = format_skill_policy_overview(updated_policy, entries)
        elif normalized_action == "reset":
            updated_policy = policy_store.reset()
            summary = "workspace skill policy reset"
            details = format_skill_policy_overview(updated_policy, entries)
        elif normalized_action == "install":
            if not normalized_path:
                raise HTTPException(status_code=400, detail="Usage: /skill install <path>")
            try:
                install_result = install_workspace_skill_from_path(
                    workspace_dir=session.workspace_dir,
                    source_path=normalized_path,
                    loader=loader,
                    activate=True,
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except FileExistsError as exc:
                raise HTTPException(status_code=409, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            entries = refresh_skill_catalog_loader(loader)
            updated_policy = install_result.policy
            summary = f"installed {install_result.skill_name}"
            details = format_skill_install_result(install_result, entries, updated_policy)
        elif normalized_action == "uninstall":
            if not normalized_skill_name:
                raise HTTPException(status_code=400, detail="Usage: /skill uninstall <skill_name>")
            try:
                uninstall_result = uninstall_workspace_skill(
                    workspace_dir=session.workspace_dir,
                    skill_name=normalized_skill_name,
                    loader=loader,
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            entries = refresh_skill_catalog_loader(loader)
            updated_policy = uninstall_result.policy
            summary = f"uninstalled {uninstall_result.skill_name}"
            details = format_skill_uninstall_result(uninstall_result, entries, updated_policy)
        elif normalized_action == "rollback":
            if not normalized_skill_name:
                raise HTTPException(status_code=400, detail="Usage: /skill rollback <skill_name>")
            try:
                rollback_result = rollback_workspace_skill(
                    workspace_dir=session.workspace_dir,
                    skill_name=normalized_skill_name,
                    loader=loader,
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            entries = refresh_skill_catalog_loader(loader)
            updated_policy = rollback_result.policy
            summary = f"rolled back {rollback_result.skill_name}"
            details = format_skill_rollback_result(rollback_result, entries, updated_policy)
        else:
            updated_policy = policy
            summary = ""
            details = ""

        reload_reason = {
            "mode": "workspace skill mode updated",
            "enable": "workspace skill policy updated",
            "disable": "workspace skill policy updated",
            "reset": "workspace skill policy reset",
            "install": "workspace skill installed",
            "uninstall": "workspace skill uninstalled",
            "rollback": "workspace skill rolled back",
            "refresh": "skill catalog refreshed",
        }.get(normalized_action, "workspace skill runtime changed")

        def _with_reload_queue_metadata(
            *,
            base_summary: str,
            base_details: str,
            queued_ids: Sequence[str],
            include_current_note: bool,
            policy_payload: dict[str, Any] | None = None,
            counts_payload: dict[str, Any] | None = None,
        ) -> dict[str, Any]:
            normalized_ids = [item for item in (_safe_text(value) for value in queued_ids) if item]
            queued_current = session.session_id in normalized_ids
            queued_other_ids = [item for item in normalized_ids if item != session.session_id]
            detail_lines: list[str] = []
            if include_current_note and queued_current:
                detail_lines.append(
                    "Current session skill reload is queued and will apply automatically after the current turn finishes."
                )
            if queued_other_ids:
                noun = "session" if len(queued_other_ids) == 1 else "sessions"
                detail_lines.append(
                    f"Queued skill runtime reload for {len(queued_other_ids)} other workspace {noun}: "
                    f"{', '.join(queued_other_ids)}."
                )
            detail_text = str(base_details or "").strip()
            if detail_lines:
                detail_text = (
                    f"{detail_text}\n\n" + "\n".join(detail_lines)
                    if detail_text
                    else "\n".join(detail_lines)
                )
            summary_text = _safe_text(base_summary)
            if include_current_note and queued_current:
                summary_text = f"{summary_text}; reload queued" if summary_text else "reload queued"
            elif queued_other_ids:
                summary_text = (
                    f"{summary_text}; {len(queued_other_ids)} other session(s) pending reload"
                    if summary_text
                    else f"{len(queued_other_ids)} other session(s) pending reload"
                )
            payload: dict[str, Any] = {
                "summary": summary_text,
                "details": detail_text,
                "reload_pending": queued_current,
                "reload_queued_session_ids": normalized_ids,
                "reload_queued_current_session": queued_current,
                "reload_queued_other_sessions": len(queued_other_ids),
            }
            if policy_payload is not None:
                payload["policy"] = dict(policy_payload)
            if counts_payload is not None:
                payload["counts"] = dict(counts_payload)
            return payload

        if normalized_action != "refresh" and session.busy:
            queued_ids = await self.queue_workspace_skill_reload(
                session.workspace_dir,
                current_session_id=session.session_id,
                reason=reload_reason,
                include_current=True,
            )
            return MainAgentSessionSkillResponse(
                status="busy",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                result=_with_reload_queue_metadata(
                    base_summary=summary,
                    base_details=details,
                    queued_ids=queued_ids,
                    include_current_note=True,
                    policy_payload=updated_policy.to_dict(),
                ),
            )

        if normalized_action == "refresh" and session.busy:
            queued_ids = await self.queue_workspace_skill_reload(
                session.workspace_dir,
                current_session_id=session.session_id,
                reason=reload_reason,
                include_current=True,
            )
            return MainAgentSessionSkillResponse(
                status="busy",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                result=_with_reload_queue_metadata(
                    base_summary="skill catalog refreshed",
                    base_details="Refreshed skill catalog.",
                    queued_ids=queued_ids,
                    include_current_note=True,
                ),
            )

        queued_other_ids = await self.queue_workspace_skill_reload(
            session.workspace_dir,
            current_session_id=session.session_id,
            reason=reload_reason,
            include_current=False,
        )

        async with session.lock:
            if normalized_action != "refresh" and session.busy:
                queued_ids = await self.queue_workspace_skill_reload(
                    session.workspace_dir,
                    current_session_id=session.session_id,
                    reason=reload_reason,
                    include_current=True,
                )
                return MainAgentSessionSkillResponse(
                    status="busy",
                    session_id=session.session_id,
                    action=normalized_action,
                    active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                    result=_with_reload_queue_metadata(
                        base_summary=summary,
                        base_details=details,
                        queued_ids=queued_ids,
                        include_current_note=True,
                        policy_payload=updated_policy.to_dict(),
                    ),
                )

            if normalized_action == "refresh" and session.busy:
                queued_ids = await self.queue_workspace_skill_reload(
                    session.workspace_dir,
                    current_session_id=session.session_id,
                    reason=reload_reason,
                    include_current=True,
                )
                return MainAgentSessionSkillResponse(
                    status="busy",
                    session_id=session.session_id,
                    action=normalized_action,
                    active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                    result=_with_reload_queue_metadata(
                        base_summary="skill catalog refreshed",
                        base_details="Refreshed skill catalog.",
                        queued_ids=queued_ids,
                        include_current_note=True,
                    ),
                )

            entries = refresh_skill_catalog_loader(loader)
            counts = summarize_skill_entries(
                entries,
                updated_policy if normalized_action != "refresh" else load_workspace_skill_policy(session.workspace_dir),
            )
            active_identity = self._selected_model_identity(session)
            await self._rebuild_session_agent_with_identity(session, active_identity)
            if normalized_action == "refresh":
                result = {
                    "summary": (
                        f"{counts['total']} skill(s) refreshed | {counts['active']} active | "
                        f"{counts['ready']} ready | {counts['blocked']} blocked"
                    ),
                    "details": format_skill_entries(entries, load_workspace_skill_policy(session.workspace_dir)),
                    "counts": counts,
                    "policy": load_workspace_skill_policy(session.workspace_dir).to_dict(),
                }
            else:
                result = {
                    "summary": summary,
                    "details": details,
                    "counts": counts,
                    "policy": updated_policy.to_dict(),
                }
            result = _with_reload_queue_metadata(
                base_summary=str(result.get("summary") or ""),
                base_details=str(result.get("details") or ""),
                queued_ids=queued_other_ids,
                include_current_note=False,
                policy_payload=result.get("policy") if isinstance(result.get("policy"), dict) else None,
                counts_payload=result.get("counts") if isinstance(result.get("counts"), dict) else None,
            )
            self._append_transcript_unlocked(
                session,
                role="system",
                content=str(result.get("details") or ""),
                surface=surface or session.active_surface or session.origin_surface,
                metadata={
                    "kind": "command",
                    "command": (
                        f"skill mode {updated_policy.mode}"
                        if normalized_action == "mode"
                        else (
                            f"skill install {normalized_path}"
                            if normalized_action == "install" and normalized_path
                            else (
                            f"skill uninstall {normalized_skill_name}"
                            if normalized_action == "uninstall" and normalized_skill_name
                            else (
                            f"skill rollback {normalized_skill_name}"
                            if normalized_action == "rollback" and normalized_skill_name
                            else (
                              f"skill {normalized_action} {normalized_skill_name}".strip()
                              if normalized_action in {"enable", "disable"} and normalized_skill_name
                              else f"skill {normalized_action}"
                              )))
                          )
                      ),
                    "summary": str(result.get("summary") or "skill command completed"),
                    "level": "info",
                    "threads_visible": False,
                },
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            session.touch()
            self._persist_session_unlocked(session)
            return MainAgentSessionSkillResponse(
                status="ok",
                session_id=session.session_id,
                action=normalized_action,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                result=result,
            )

    async def update_session_model_selection(
        self,
        session_id: str,
        *,
        provider_source: str,
        provider_id: str,
        model_id: str,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionModelSelectionResponse:
        async with self._store_lock:
            session = await self._load_managed_session_unlocked(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found.")

        requested_identity = self._normalize_model_identity(
            source=provider_source,
            provider_id=provider_id,
            model_id=model_id,
        )
        if requested_identity is None:
            raise HTTPException(status_code=400, detail="Invalid model selection payload.")

        async with session.lock:
            current_identity = self._selected_model_identity(session)
            pending_identity = self._pending_model_identity(session)

            if session.busy:
                if current_identity == requested_identity and pending_identity is None:
                    active_surface = self._normalize_surface(session.active_surface or session.origin_surface or surface)
                    return MainAgentSessionModelSelectionResponse(
                        status="selected",
                        session_id=session.session_id,
                        active_surface=active_surface,
                        applied=True,
                        queued=False,
                        selected_model_source=requested_identity[0],
                        selected_provider_id=requested_identity[1],
                        selected_model_id=requested_identity[2],
                    )
                if pending_identity != requested_identity:
                    self._set_pending_model_identity(session, requested_identity)
                    self.bind_session_surface(
                        session,
                        surface=surface,
                        channel_type=channel_type,
                        conversation_id=conversation_id,
                        sender_id=sender_id,
                    )
                    session.touch()
                    self._persist_session_unlocked(session)
                active_surface = self._normalize_surface(session.active_surface or session.origin_surface or surface)
                return MainAgentSessionModelSelectionResponse(
                    status="queued",
                    session_id=session.session_id,
                    active_surface=active_surface,
                    applied=False,
                    queued=True,
                    selected_model_source=current_identity[0] if current_identity is not None else None,
                    selected_provider_id=current_identity[1] if current_identity is not None else None,
                    selected_model_id=current_identity[2] if current_identity is not None else None,
                    pending_model_source=requested_identity[0],
                    pending_provider_id=requested_identity[1],
                    pending_model_id=requested_identity[2],
                )

            if current_identity == requested_identity and session.agent is not None:
                self._set_pending_model_identity(session, None)
                self.bind_session_surface(
                    session,
                    surface=surface,
                    channel_type=channel_type,
                    conversation_id=conversation_id,
                    sender_id=sender_id,
                )
                session.touch()
                self._persist_session_unlocked(session)
                active_surface = self._normalize_surface(session.active_surface or session.origin_surface or surface)
                return MainAgentSessionModelSelectionResponse(
                    status="selected",
                    session_id=session.session_id,
                    active_surface=active_surface,
                    applied=True,
                    queued=False,
                    selected_model_source=requested_identity[0],
                    selected_provider_id=requested_identity[1],
                    selected_model_id=requested_identity[2],
                )

            await self._rebuild_session_agent_with_identity(session, requested_identity)
            self.bind_session_surface(
                session,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            session.touch()
            self._persist_session_unlocked(session)
            active_surface = self._normalize_surface(session.active_surface or session.origin_surface or surface)
            return MainAgentSessionModelSelectionResponse(
                status="selected",
                session_id=session.session_id,
                active_surface=active_surface,
                applied=True,
                queued=False,
                selected_model_source=requested_identity[0],
                selected_provider_id=requested_identity[1],
                selected_model_id=requested_identity[2],
            )

    async def apply_pending_session_model_selection(
        self,
        session: MainAgentSessionState,
    ) -> bool:
        pending_identity = self._pending_model_identity(session)
        if pending_identity is None or session.busy:
            return False
        await self._rebuild_session_agent_with_identity(session, pending_identity)
        session.touch()
        self._persist_session_unlocked(session)
        return True

    async def update_session_runtime_policy(
        self,
        session_id: str,
        *,
        approval_profile: str | None = None,
        access_level: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ):
        from mini_agent.interfaces import MainAgentSessionRuntimePolicyResponse

        async with self._store_lock:
            session = await self._load_managed_session_unlocked(session_id)
            if session is None:
                raise HTTPException(status_code=404, detail="Session not found.")

            current_profile, current_access = self._desired_runtime_policy_for_session(session)
            if session.agent is not None:
                current_profile, current_access = self._effective_runtime_policy_for_agent(session.agent)
            resolved_profile = _safe_text(approval_profile).lower() or current_profile or "build"
            resolved_access = _safe_text(access_level).lower() or current_access or "default"

            if session.busy and not session.pending_approvals:
                raise HTTPException(
                    status_code=409,
                    detail="Session is busy. Runtime mode can only change while idle or waiting on approval.",
                )

            if session.agent is not None:
                diagnostics = self._reconfigure_session_agent_runtime_policy(
                    session,
                    approval_profile=resolved_profile,
                    access_level=resolved_access,
                )
            else:
                diagnostics = normalize_sandbox_diagnostics(
                    {
                        **dict(session.sandbox_diagnostics or {}),
                        "approval_profile": resolved_profile,
                        "access_level": resolved_access,
                        "sandbox_mode": "unrestricted" if resolved_access == "full-access" else "workspace",
                    }
                )
                session.sandbox_diagnostics = dict(diagnostics)

            self.bind_session_surface(
                session,
                surface=surface,
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            self._append_transcript_unlocked(
                session,
                role="system",
                content=(
                    "Runtime Policy Updated\n"
                    f"- execution: {resolved_profile}\n"
                    f"- access: {resolved_access}"
                ),
                surface=surface or session.active_surface or session.origin_surface,
                metadata={
                    "kind": "command",
                    "command": "policy",
                    "summary": f"{resolved_profile} / {resolved_access}",
                    "level": "info",
                },
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            session.touch()
            self._persist_session_unlocked(session)
            return MainAgentSessionRuntimePolicyResponse(
                status="updated",
                session_id=session.session_id,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
                applied=True,
                approval_profile=resolved_profile,
                access_level=resolved_access,
                sandbox_diagnostics=dict(diagnostics),
            )

    async def queue_workspace_skill_reload(
        self,
        workspace_dir: Path,
        *,
        current_session_id: str | None,
        reason: str,
        include_current: bool,
    ) -> tuple[str, ...]:
        normalized_reason = _safe_text(reason) or "workspace skill runtime changed"
        async with self._store_lock:
            queued_ids: list[str] = []
            for candidate in self._sessions.values():
                if not self._same_workspace(candidate.workspace_dir, workspace_dir):
                    continue
                if (
                    current_session_id
                    and candidate.session_id == current_session_id
                    and not include_current
                ):
                    continue
                if candidate.agent is None and self._pending_model_identity(candidate) is None:
                    continue
                self._mark_pending_skill_reload(candidate, reason=normalized_reason)
                candidate.touch()
                self._persist_session_unlocked(candidate)
                queued_ids.append(candidate.session_id)
            return tuple(queued_ids)

    async def apply_pending_session_skill_reload(
        self,
        session: MainAgentSessionState,
    ) -> bool:
        if session.busy or not bool(session.pending_skill_reload):
            return False
        if self._pending_model_identity(session) is not None:
            return False
        identity = self._selected_model_identity(session)
        if identity is None:
            return False
        await self._rebuild_session_agent_with_identity(session, identity)
        session.touch()
        self._persist_session_unlocked(session)
        return True

    def mark_turn_started(
        self,
        session: MainAgentSessionState,
        *,
        surface: str | None,
        detail: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        normalized_surface = self._normalize_surface(surface)
        session.busy = True
        session.current_turn_id = uuid4().hex
        session.cancel_event = asyncio.Event()
        session.pending_approvals = []
        session.pending_approval_waiters.clear()
        session.running_state = _safe_text(detail) or f"{normalized_surface} request running"
        session.touch(now_utc=now_utc)
        self._persist_session_unlocked(session)

    def mark_turn_finished(
        self,
        session: MainAgentSessionState,
        *,
        now_utc: datetime | None = None,
    ) -> None:
        session.busy = False
        session.running_state = ""
        session.current_turn_id = None
        session.cancel_event = None
        session.pending_approvals = []
        session.pending_approval_waiters.clear()
        session.touch(now_utc=now_utc)
        self._persist_session_unlocked(session)

    def bind_session_surface(
        self,
        session: MainAgentSessionState,
        *,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self._apply_surface_binding_unlocked(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )
        self._persist_session_unlocked(session)

    def record_message(
        self,
        session: MainAgentSessionState,
        *,
        role: str,
        content: str,
        surface: str | None,
        metadata: dict[str, Any] | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        self._apply_surface_binding_unlocked(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now,
        )
        self._append_transcript_unlocked(
            session,
            role=role,
            content=content,
            surface=self._normalize_surface(surface),
            metadata=metadata,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now,
        )
        session.touch(now_utc=now)
        self._persist_session_unlocked(session)

    @staticmethod
    def _session_control_command_name(action: str) -> str:
        normalized = _safe_text(action).lower().replace("-", "_")
        if normalized.startswith("mcp_"):
            return normalized.replace("_", " ")
        return normalized

    @staticmethod
    def _session_control_summary(
        action: str,
        *,
        applied: bool,
        response: MainAgentSessionControlResponse | None = None,
    ) -> str:
        normalized = _safe_text(action).lower().replace("-", "_")
        if normalized in {"mcp_status", "mcp_list", "mcp_reload"}:
            stats = response.stats if response is not None and isinstance(response.stats, dict) else {}
            summary = str(stats.get("summary") or "").strip()
            if summary:
                return summary
            if normalized == "mcp_reload":
                return "reloaded MCP bindings"
            return "MCP status shown" if normalized == "mcp_status" else "MCP server list shown"
        if normalized == "compact":
            return "context compacted" if applied else "context already compact"
        if normalized == "kb_on":
            return "knowledge base enabled" if applied else "knowledge base already enabled"
        if normalized == "kb_off":
            return "knowledge base disabled" if applied else "knowledge base already disabled"
        return "older memories dropped" if applied else "no older memories to drop"

    @staticmethod
    def _session_control_details(response: MainAgentSessionControlResponse) -> str:
        normalized = _safe_text(response.action).lower().replace("-", "_")
        if normalized in {"mcp_status", "mcp_list", "mcp_reload"}:
            stats = response.stats if isinstance(response.stats, dict) else {}
            details = str(stats.get("details") or "").strip()
            if details:
                return details
            return f"Action: {response.action}"
        if normalized in {"kb_on", "kb_off"}:
            lines = [
                f"Action: {response.action}",
                f"Knowledge Base: {'enabled' if bool(response.knowledge_base_enabled) else 'disabled'}",
            ]
            if response.reason:
                lines.append(f"Reason: {response.reason}")
            return "\n".join(lines)
        lines = [
            f"Action: {response.action}",
            f"Messages: {response.message_count_before} -> {response.message_count_after}",
            f"Tokens: {response.token_count_before} -> {response.token_count_after}",
        ]
        if response.reason:
            lines.append(f"Reason: {response.reason}")
        if isinstance(response.stats, dict):
            lines.append(
                "Stats: "
                f"masked={int(response.stats.get('masked_messages') or 0)}, "
                f"snipped={int(response.stats.get('snipped_messages') or 0)}, "
                f"merged={int(response.stats.get('merged_messages') or 0)}"
            )
        return "\n".join(lines)

    @staticmethod
    def _session_mcp_control_output(action: str, *, snapshot: Any) -> tuple[str, str]:
        normalized = _safe_text(action).lower().replace("-", "_")
        if normalized == "mcp_status":
            return (
                f"{int(getattr(snapshot, 'active_total', 0) or 0)} active server(s) | "
                f"{int(getattr(snapshot, 'tool_total', 0) or 0)} tool(s)",
                format_mcp_status(snapshot),
            )
        details = f"{format_mcp_status(snapshot)}\n\n{format_mcp_server_list(snapshot)}"
        if normalized == "mcp_list":
            return (
                f"{int(getattr(snapshot, 'configured_total', 0) or 0)} configured server(s) | "
                f"{int(getattr(snapshot, 'active_total', 0) or 0)} active",
                details,
            )
        return (
            f"reloaded MCP | {int(getattr(snapshot, 'active_total', 0) or 0)} active server(s) | "
            f"{int(getattr(snapshot, 'tool_total', 0) or 0)} tool(s)",
            details,
        )

    @staticmethod
    def _session_cancel_details(reason: str | None) -> str:
        lines = [
            "Action: cancel",
            "State: cancellation requested",
        ]
        normalized_reason = _safe_text(reason)
        if normalized_reason:
            lines.append(f"Reason: {normalized_reason}")
        return "\n".join(lines)

    @staticmethod
    def _session_approval_details(
        *,
        command: str,
        token: str,
        tool_name: str,
    ) -> str:
        lines = [
            f"Action: {command}",
            f"Token: {token}",
            f"Tool: {tool_name}",
        ]
        return "\n".join(lines)

    def record_turn(
        self,
        session: MainAgentSessionState,
        *,
        user_message: str,
        assistant_reply: str,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self.record_message(
            session,
            role="user",
            content=user_message,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )
        self.record_message(
            session,
            role="assistant",
            content=assistant_reply,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )

    def record_activity(
        self,
        session: MainAgentSessionState,
        *,
        label: str,
        detail: str,
        surface: str | None,
        activity_id: str | None = None,
        preview: str = "",
        output_text: str = "",
        state: str = "",
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        normalized_surface = self._normalize_surface(surface)
        self._apply_surface_binding_unlocked(
            session,
            surface=surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now,
        )
        entry = self._ensure_activity_transcript_entry_unlocked(
            session,
            surface=normalized_surface,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now,
        )
        metadata = entry.metadata
        items = metadata.get("activity_items")
        if not isinstance(items, list):
            items = []
            metadata["activity_items"] = items
        metadata["kind"] = "activity"
        metadata["threads_visible"] = True
        if session.current_turn_id:
            metadata["turn_id"] = session.current_turn_id

        normalized_label = self._activity_label(label)
        normalized_detail = self._activity_detail(normalized_label, detail)
        normalized_preview = _safe_text(preview)
        normalized_output = str(output_text or "").strip()
        normalized_state = _safe_text(state).lower()
        item_key = _safe_text(activity_id)

        target: dict[str, Any] | None = None
        if item_key:
            for item in items:
                if _safe_text(item.get("id")) == item_key:
                    target = item
                    break
        if target is None:
            target = {
                "id": item_key or f"activity-{len(items) + 1}",
                "label": normalized_label,
                "detail": normalized_detail,
                "preview": normalized_preview,
                "output_text": normalized_output,
                "output_summary": self._activity_output_summary(normalized_output),
                "state": normalized_state,
            }
            items.append(target)
        else:
            target["label"] = normalized_label
            target["detail"] = normalized_detail
            if normalized_preview:
                target["preview"] = normalized_preview
            if normalized_output:
                target["output_text"] = normalized_output
                target["output_summary"] = self._activity_output_summary(normalized_output)
            if normalized_state:
                target["state"] = normalized_state

        entry.created_at = now
        entry.surface = normalized_surface
        if channel_type:
            entry.channel_type = channel_type
        if conversation_id:
            entry.conversation_id = conversation_id
        if sender_id:
            entry.sender_id = sender_id
        session.touch(now_utc=now)
        self._persist_session_unlocked(session)
        return dict(target)

    def record_pending_approval(
        self,
        session: MainAgentSessionState,
        *,
        payload: dict[str, Any],
        future: asyncio.Future[bool | None],
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        normalized = self._normalize_pending_approval(payload)
        if normalized is None:
            raise HTTPException(status_code=400, detail="Invalid pending approval payload.")
        token = normalized["token"]
        existing_index = next(
            (index for index, item in enumerate(session.pending_approvals) if _safe_text(item.get("token")) == token),
            None,
        )
        if existing_index is None:
            session.pending_approvals.append(normalized)
        else:
            session.pending_approvals[existing_index] = normalized
        session.pending_approval_waiters[token] = future
        session.touch(now_utc=now_utc)
        self._persist_session_unlocked(session)
        return dict(normalized)

    def clear_pending_approval(
        self,
        session: MainAgentSessionState,
        *,
        token: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        normalized_token = _safe_text(token)
        if not normalized_token:
            session.pending_approvals = []
            session.pending_approval_waiters.clear()
            session.touch(now_utc=now_utc)
            self._persist_session_unlocked(session)
            return
        session.pending_approvals = [
            item
            for item in session.pending_approvals
            if _safe_text(item.get("token")) != normalized_token
        ]
        session.pending_approval_waiters.pop(normalized_token, None)
        session.touch(now_utc=now_utc)
        self._persist_session_unlocked(session)

    async def resolve_pending_approval(
        self,
        session_id: str,
        *,
        approved: bool,
        token: str | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
    ) -> MainAgentSessionApprovalResponse:
        async with self._store_lock:
            session = self._sessions.get(session_id)
            if session is None:
                if self._persistence.load_session_record(session_id) is None:
                    raise HTTPException(status_code=404, detail="Session not found.")
                raise HTTPException(
                    status_code=409,
                    detail=(
                        "Pending approval was interrupted after restart and cannot be resumed directly. "
                        "Send a new message to continue with recovery context."
                    ),
                )

            pending = self._pending_approvals_from_raw(session.pending_approvals)
            if not pending:
                if session.recovery_context_pending and session.recovery_pending_approvals:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Pending approval was interrupted after restart and cannot be resumed directly. "
                            "Send a new message to continue with recovery context."
                        ),
                    )
                raise HTTPException(status_code=409, detail="Session has no pending approval.")

            normalized_token = _safe_text(token)
            if normalized_token:
                target = next((item for item in pending if item["token"] == normalized_token), None)
                if target is None:
                    raise HTTPException(status_code=404, detail=f"Pending approval not found: {normalized_token}")
            elif len(pending) == 1:
                target = pending[0]
                normalized_token = target["token"]
            else:
                available = ", ".join(item["token"] for item in pending)
                raise HTTPException(
                    status_code=409,
                    detail=f"Multiple approvals pending. Specify a token: {available}",
                )

            future = session.pending_approval_waiters.get(normalized_token)
            if future is None or future.done():
                raise HTTPException(
                    status_code=409,
                    detail="Pending approval is no longer waiting for input.",
                )

            command = "approve" if approved else "deny"
            decision = "approved" if approved else "denied"
            self._append_transcript_unlocked(
                session,
                role="system",
                content=self._session_approval_details(
                    command=command,
                    token=normalized_token,
                    tool_name=target["tool_name"],
                ),
                surface=surface or session.active_surface or session.origin_surface,
                metadata={
                    "kind": "command",
                    "command": command,
                    "summary": f"{decision} {target['tool_name']}",
                    "level": "info",
                    "token": normalized_token,
                    "tool_name": target["tool_name"],
                },
                channel_type=channel_type,
                conversation_id=conversation_id,
                sender_id=sender_id,
            )
            future.set_result(bool(approved))
            session.touch()
            self._persist_session_unlocked(session)
            return MainAgentSessionApprovalResponse(
                status="resolved",
                session_id=session.session_id,
                token=normalized_token,
                tool_name=target["tool_name"],
                decision=decision,
                active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
            )

    def build_recovery_turn_context(
        self,
        session: MainAgentSessionState,
    ) -> dict[str, Any] | None:
        snapshot = self._stored_recovery_snapshot_from_session(session)
        if snapshot is None:
            return None
        payload = snapshot.model_dump()
        payload["resume_strategy"] = "next_message"
        payload["continue_hint"] = "Continue from the interrupted shared-session task using restored context."
        if payload.get("pending_approvals"):
            payload["approval_hint"] = "Pending approvals from before restart were lost and must be re-evaluated."
        return payload

    def clear_recovery_context(
        self,
        session: MainAgentSessionState,
        *,
        now_utc: datetime | None = None,
    ) -> None:
        self._clear_recovery_context_unlocked(session)
        session.touch(now_utc=now_utc)
        self._persist_session_unlocked(session)

    @staticmethod
    def _clear_recovery_context_unlocked(session: MainAgentSessionState) -> None:
        session.recovery_context_pending = False
        session.recovery_state = ""
        session.recovery_summary = ""
        session.recovery_last_activity = None
        session.recovery_last_user_message = None
        session.recovery_last_assistant_message = None
        session.recovery_pending_approvals = []

    def _drop_expired_sessions_unlocked(self, *, now_utc: datetime | None = None) -> None:
        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        expired_ids = [
            sid
            for sid, session in self._sessions.items()
            if (now - session.updated_at).total_seconds() > self._ttl_seconds
        ]
        for sid in expired_ids:
            self._sessions.pop(sid, None)

    def _persist_session_unlocked(
        self,
        session: MainAgentSessionState,
        *,
        agent_messages: Sequence[Any] | None = None,
    ) -> None:
        try:
            self._persistence.save_session(session, agent_messages=agent_messages)
        except Exception:
            return

    def _allocate_new_session_id_unlocked(self) -> str:
        while True:
            candidate = uuid4().hex
            if candidate in self._sessions:
                continue
            if self._persistence.load_session_record(candidate) is not None:
                continue
            return candidate

    async def _load_managed_session_unlocked(self, session_id: str) -> MainAgentSessionState | None:
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing
        record = self._persistence.load_session_record(session_id)
        if record is None:
            return None
        return await self._restore_persisted_session_unlocked(record)

    async def _restore_persisted_session_unlocked(
        self,
        record: dict[str, Any],
        *,
        now_utc: datetime | None = None,
    ) -> MainAgentSessionState:
        session_id = _safe_text(record.get("session_id")) or uuid4().hex
        existing = self._sessions.get(session_id)
        if existing is not None:
            return existing

        now = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        workspace_dir = Path(str(record.get("workspace_dir", "."))).expanduser().resolve()
        selected_identity = self._normalize_model_identity(
            source=record.get("selected_model_source"),
            provider_id=record.get("selected_provider_id"),
            model_id=record.get("selected_model_id"),
        )
        pending_identity = self._normalize_model_identity(
            source=record.get("pending_model_source"),
            provider_id=record.get("pending_provider_id"),
            model_id=record.get("pending_model_id"),
        )
        desired_approval_profile, desired_access_level = self._desired_runtime_policy_from_record(record)
        agent = await self._build_agent_for_identity(workspace_dir, selected_identity)
        if desired_approval_profile or desired_access_level:
            try:
                reconfigure_agent_runtime_policy(
                    agent=agent,
                    config=self._load_runtime_config(),
                    workspace_dir=workspace_dir,
                    approval_profile_override=desired_approval_profile,
                    access_level_override=desired_access_level,
                )
            except Exception:
                pass
        self._restore_agent_messages_payload(record.get("messages") or [], agent)
        self._restore_agent_token_state(
            agent,
            token_usage=record.get("token_usage"),
            token_limit=record.get("token_limit"),
            raw_messages=record.get("messages"),
        )
        restored_knowledge_base_enabled = record.get("knowledge_base_enabled")
        effective_knowledge_base_enabled = (
            bool(restored_knowledge_base_enabled)
            if restored_knowledge_base_enabled is not None
            else self._agent_knowledge_base_enabled(agent)
        )
        effective_knowledge_base_enabled = self._apply_agent_knowledge_base_enabled(
            agent,
            effective_knowledge_base_enabled,
        )
        transcript = self._transcript_entries_from_record(record)
        session_key = self._build_session_key(
            session_id=session_id,
            workspace_dir=workspace_dir,
        )
        lifecycle_state = self._lifecycle_manager.bootstrap(session_key, now_utc=now)
        session = MainAgentSessionState(
            session_id=session_id,
            workspace_dir=workspace_dir,
            agent=agent,
            lifecycle_state=lifecycle_state,
            created_at=_from_utc_iso(record.get("created_at"), now),
            updated_at=_from_utc_iso(record.get("updated_at"), now),
            title=_safe_text(record.get("title")),
            origin_surface=self._normalize_surface(record.get("origin_surface")),
            active_surface=self._normalize_surface(record.get("active_surface") or record.get("origin_surface")),
            reply_enabled=bool(record.get("reply_enabled", False)),
            busy=False,
            running_state="",
            channel_type=_safe_text(record.get("channel_type")) or None,
            conversation_id=_safe_text(record.get("conversation_id")) or None,
            sender_id=_safe_text(record.get("sender_id")) or None,
            shared=bool(record.get("shared", False)),
            knowledge_base_enabled=effective_knowledge_base_enabled,
            selected_model_source=selected_identity[0] if selected_identity is not None else None,
            selected_provider_id=selected_identity[1] if selected_identity is not None else None,
            selected_model_id=selected_identity[2] if selected_identity is not None else None,
            pending_model_source=pending_identity[0] if pending_identity is not None else None,
            pending_provider_id=pending_identity[1] if pending_identity is not None else None,
            pending_model_id=pending_identity[2] if pending_identity is not None else None,
            pending_skill_reload=bool(record.get("pending_skill_reload", False)),
            pending_skill_reload_reason=_safe_text(record.get("pending_skill_reload_reason")),
            context_policy=self._normalize_context_policy_payload(record.get("context_policy")),
            last_prepared_context=self._normalize_prepared_context_payload(record.get("last_prepared_context")),
            prepared_context_diagnostics=self._normalize_prepared_context_diagnostics_payload(
                record.get("prepared_context_diagnostics")
            ),
            memory_diagnostics=self._build_memory_diagnostics_from_record(record),
            sandbox_diagnostics=self._build_sandbox_diagnostics_from_record(record),
            pending_approvals=[],
            transcript=transcript,
            next_transcript_index=max([entry.index for entry in transcript] or [0]) + 1,
        )
        stored_recovery = self._stored_recovery_snapshot_from_record(record, transcript=transcript)
        if stored_recovery is not None:
            session.recovery_context_pending = True
            session.recovery_state = _safe_text(stored_recovery.state)
            session.recovery_summary = _safe_text(stored_recovery.summary)
            session.recovery_last_activity = _safe_text(stored_recovery.last_activity) or None
            session.recovery_last_user_message = _safe_text(stored_recovery.last_user_message) or None
            session.recovery_last_assistant_message = _safe_text(stored_recovery.last_assistant_message) or None
            session.recovery_pending_approvals = [
                item.model_dump() for item in list(stored_recovery.pending_approvals or [])
            ]
        if selected_identity is None:
            self._set_selected_model_identity(session, self._route_model_identity(agent))
        self.restore_agent_prepared_context_state(session)
        session.sandbox_diagnostics = self._build_sandbox_diagnostics_for_session(session)
        self._sessions[session_id] = session
        return session

    @staticmethod
    def _restore_agent_messages_payload(
        raw_messages: Sequence[Any],
        agent: Agent,
    ) -> None:
        restored: list[Message] = []
        for raw in raw_messages or []:
            if not isinstance(raw, dict):
                continue
            try:
                restored.append(Message.model_validate(raw))
            except Exception:
                continue
        if not restored:
            return
        if restored[0].role != "system":
            base_messages = getattr(agent, "messages", None)
            if isinstance(base_messages, list) and base_messages:
                try:
                    base_system = base_messages[0]
                    if hasattr(base_system, "model_dump"):
                        restored.insert(0, Message.model_validate(base_system.model_dump()))
                    elif isinstance(base_system, dict):
                        restored.insert(0, Message.model_validate(base_system))
                    else:
                        restored.insert(
                            0,
                            Message(
                                role=str(getattr(base_system, "role", "system") or "system"),
                                content=str(getattr(base_system, "content", "")),
                            ),
                        )
                except Exception:
                    pass
        agent.messages = restored

    def _import_transcript_entries(
        self,
        items: Sequence[dict[str, Any]] | None,
        *,
        default_surface: str,
        now_utc: datetime,
    ) -> list[MainAgentSessionTranscriptEntry]:
        entries: list[MainAgentSessionTranscriptEntry] = []
        for fallback_index, item in enumerate(items or [], start=1):
            if not isinstance(item, dict):
                continue
            try:
                index = int(item.get("index", fallback_index) or fallback_index)
            except Exception:
                index = fallback_index
            entries.append(
                MainAgentSessionTranscriptEntry(
                    index=max(1, index),
                    role=_safe_text(item.get("role")).lower() or "assistant",
                    content=str(item.get("content", "")),
                    surface=self._normalize_surface(item.get("surface") or default_surface),
                    created_at=_from_utc_iso(item.get("created_at"), now_utc),
                    channel_type=_safe_text(item.get("channel_type")) or None,
                    conversation_id=_safe_text(item.get("conversation_id")) or None,
                    sender_id=_safe_text(item.get("sender_id")) or None,
                    metadata=dict(item.get("metadata")) if isinstance(item.get("metadata"), dict) else {},
                )
            )
        entries.sort(key=lambda item: (item.index, item.created_at))
        for normalized_index, entry in enumerate(entries, start=1):
            entry.index = normalized_index
        return entries

    def _transcript_entries_from_record(self, record: dict[str, Any]) -> list[MainAgentSessionTranscriptEntry]:
        updated_at = _from_utc_iso(record.get("updated_at"), datetime.now(timezone.utc))
        default_surface = _safe_text(record.get("active_surface") or record.get("origin_surface")) or "api"
        raw_transcript = record.get("shared_transcript")
        items = raw_transcript if isinstance(raw_transcript, list) else []
        return self._import_transcript_entries(items, default_surface=default_surface, now_utc=updated_at)

    @staticmethod
    def _normalize_pending_approval(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        token = _safe_text(item.get("token"))
        tool_name = _safe_text(item.get("tool_name")) or "tool"
        if not token:
            return None
        return {
            "token": token,
            "tool_name": tool_name,
            "arguments": dict(item.get("arguments")) if isinstance(item.get("arguments"), dict) else {},
            "kind": _safe_text(item.get("kind")) or None,
            "reason": _safe_text(item.get("reason")) or None,
            "cache_key": _safe_text(item.get("cache_key")) or None,
            "can_escalate": bool(item.get("can_escalate", False)),
            "step": max(0, int(item.get("step") or 0)),
        }

    @classmethod
    def _pending_approvals_from_raw(cls, raw_items: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_items, list):
            return []
        approvals: list[dict[str, Any]] = []
        for item in raw_items:
            normalized = cls._normalize_pending_approval(item)
            if normalized is not None:
                approvals.append(normalized)
        return approvals

    @staticmethod
    def _normalize_context_policy_payload(value: Any) -> dict[str, Any]:
        return resolve_turn_context_policy(value or {})

    @staticmethod
    def _normalize_prepared_context_payload(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _normalize_prepared_context_diagnostics_payload(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _normalize_memory_diagnostics_payload(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _normalize_sandbox_diagnostics_payload(value: Any) -> dict[str, Any]:
        return normalize_sandbox_diagnostics(value)

    def _build_memory_diagnostics_for_session(
        self,
        session: MainAgentSessionState,
        *,
        preview_limit: int = 5,
    ) -> dict[str, Any]:
        try:
            diagnostics = build_memory_diagnostics(
                workspace_dir=session.workspace_dir,
                session_id=session.session_id,
                last_prepared_context=session.last_prepared_context,
                last_memory_automation=getattr(session.agent, "last_memory_automation", {}),
                last_runtime_task_memory=getattr(session.agent, "last_runtime_task_memory", {}),
                preview_limit=preview_limit,
            )
        except Exception:
            diagnostics = self._normalize_memory_diagnostics_payload(session.memory_diagnostics)
        session.memory_diagnostics = self._normalize_memory_diagnostics_payload(diagnostics)
        return session.memory_diagnostics

    def _build_memory_diagnostics_from_record(
        self,
        record: dict[str, Any],
        *,
        preview_limit: int = 5,
    ) -> dict[str, Any]:
        workspace_dir = _safe_text(record.get("workspace_dir"))
        if not workspace_dir:
            return self._normalize_memory_diagnostics_payload(record.get("memory_diagnostics"))
        try:
            diagnostics = build_memory_diagnostics(
                workspace_dir=workspace_dir,
                session_id=_safe_text(record.get("session_id")) or None,
                last_prepared_context=self._normalize_prepared_context_payload(record.get("last_prepared_context")),
                last_memory_automation=record.get("last_memory_automation"),
                last_runtime_task_memory=record.get("last_runtime_task_memory"),
                preview_limit=preview_limit,
            )
        except Exception:
            diagnostics = record.get("memory_diagnostics")
        return self._normalize_memory_diagnostics_payload(diagnostics)

    def _build_sandbox_diagnostics_for_session(
        self,
        session: MainAgentSessionState,
    ) -> dict[str, Any]:
        try:
            diagnostics = collect_sandbox_diagnostics(agent=session.agent)
        except Exception:
            diagnostics = session.sandbox_diagnostics
        session.sandbox_diagnostics = self._normalize_sandbox_diagnostics_payload(diagnostics)
        return session.sandbox_diagnostics

    def _build_sandbox_diagnostics_from_record(
        self,
        record: dict[str, Any],
    ) -> dict[str, Any]:
        return self._normalize_sandbox_diagnostics_payload(record.get("sandbox_diagnostics"))

    def restore_agent_prepared_context_state(self, session: MainAgentSessionState) -> None:
        agent = session.agent
        if hasattr(agent, "last_prepared_turn_context"):
            try:
                agent.last_prepared_turn_context = dict(session.last_prepared_context)
            except Exception:
                agent.last_prepared_turn_context = None
        if hasattr(agent, "prepared_context_diagnostics"):
            try:
                agent.prepared_context_diagnostics = dict(session.prepared_context_diagnostics)
            except Exception:
                agent.prepared_context_diagnostics = {}

    def capture_agent_prepared_context_state(self, session: MainAgentSessionState) -> None:
        session.knowledge_base_enabled = self._agent_knowledge_base_enabled(session.agent)
        last_prepared = getattr(session.agent, "last_prepared_turn_context", None)
        diagnostics = getattr(session.agent, "prepared_context_diagnostics", None)
        session.last_prepared_context = self._normalize_prepared_context_payload(last_prepared)
        session.prepared_context_diagnostics = self._normalize_prepared_context_diagnostics_payload(diagnostics)
        session.memory_diagnostics = self._build_memory_diagnostics_for_session(session)
        session.sandbox_diagnostics = self._build_sandbox_diagnostics_for_session(session)
        self._persist_session_unlocked(session)

    async def _rebuild_session_agent_with_identity(
        self,
        session: MainAgentSessionState,
        identity: tuple[str, str, str] | None,
    ) -> None:
        self.capture_agent_prepared_context_state(session)
        serialized_messages = self._serialize_agent_messages(getattr(session.agent, "messages", []) or [])
        rebuilt = await self._build_agent_for_identity(session.workspace_dir, identity)
        desired_approval_profile, desired_access_level = self._desired_runtime_policy_for_session(session)
        if desired_approval_profile or desired_access_level:
            try:
                reconfigure_agent_runtime_policy(
                    agent=rebuilt,
                    config=self._load_runtime_config(),
                    workspace_dir=session.workspace_dir,
                    approval_profile_override=desired_approval_profile,
                    access_level_override=desired_access_level,
                )
            except Exception:
                pass
        self._restore_agent_messages_payload(serialized_messages, rebuilt)
        session.knowledge_base_enabled = self._apply_agent_knowledge_base_enabled(
            rebuilt,
            bool(session.knowledge_base_enabled),
        )
        session.agent = rebuilt
        effective_identity = self._route_model_identity(rebuilt) or identity
        self._set_selected_model_identity(session, effective_identity)
        self._set_pending_model_identity(session, None)
        self._clear_pending_skill_reload(session)
        self.restore_agent_prepared_context_state(session)
        session.sandbox_diagnostics = self._build_sandbox_diagnostics_for_session(session)

    @classmethod
    def _build_pending_approval_models(
        cls,
        raw_items: Sequence[dict[str, Any]] | None,
    ) -> list[MainAgentSessionPendingApproval]:
        return [item.to_transport() for item in cls._build_pending_approval_projections(raw_items)]

    @classmethod
    def _build_pending_approval_projections(
        cls,
        raw_items: Sequence[dict[str, Any]] | None,
    ) -> list[SessionPendingApprovalProjection]:
        approvals: list[SessionPendingApprovalProjection] = []
        for item in cls._pending_approvals_from_raw(list(raw_items or [])):
            approvals.append(
                SessionPendingApprovalProjection(
                    token=item["token"],
                    tool_name=item["tool_name"],
                    arguments=dict(item.get("arguments") or {}),
                    kind=item.get("kind"),
                    reason=item.get("reason"),
                    cache_key=item.get("cache_key"),
                    can_escalate=bool(item.get("can_escalate", False)),
                    step=int(item.get("step") or 0),
                )
            )
        return approvals

    @classmethod
    def _stored_recovery_snapshot_from_record(
        cls,
        record: dict[str, Any],
        *,
        transcript: Sequence["MainAgentSessionTranscriptEntry"],
    ) -> MainAgentSessionRecoverySnapshot | None:
        pending = cls._pending_approvals_from_raw(record.get("recovery_pending_approvals"))
        state = _safe_text(record.get("recovery_state"))
        summary = _safe_text(record.get("recovery_summary"))
        last_activity = _safe_text(record.get("recovery_last_activity")) or None
        last_user_message = _safe_text(record.get("recovery_last_user_message")) or None
        last_assistant_message = _safe_text(record.get("recovery_last_assistant_message")) or None
        context_pending = bool(record.get("recovery_context_pending"))

        if not context_pending and not state and not summary and not pending:
            busy = bool(record.get("busy", False))
            running_state = _safe_text(record.get("running_state")) or None
            fallback_pending = cls._pending_approvals_from_raw(record.get("pending_approvals"))
            fallback = cls._build_session_recovery_projection(
                transcript=transcript,
                origin_surface=record.get("origin_surface"),
                active_surface=record.get("active_surface") or record.get("origin_surface"),
                reply_enabled=bool(record.get("reply_enabled", False)),
                channel_type=_safe_text(record.get("channel_type")) or None,
                busy=busy,
                running_state=running_state,
                pending_approvals=fallback_pending,
                persisted_record=True,
            )
            if _safe_text(fallback.state).lower() != "interrupted":
                return None
            return fallback.to_transport()

        normalized_state = state or "interrupted"
        normalized_summary = summary or "interrupted after restart"
        return SessionRecoveryProjection(
            state=normalized_state,
            summary=normalized_summary,
            last_activity=last_activity or cls._last_activity_summary(transcript),
            last_user_message=last_user_message or cls._last_role_preview(transcript, role="user"),
            last_assistant_message=last_assistant_message or cls._last_role_preview(transcript, role="assistant"),
            pending_approvals=tuple(cls._build_pending_approval_projections(pending)),
        ).to_transport()

    @classmethod
    def _stored_recovery_snapshot_from_session(
        cls,
        session: MainAgentSessionState,
    ) -> MainAgentSessionRecoverySnapshot | None:
        if not bool(session.recovery_context_pending):
            return None
        pending = cls._pending_approvals_from_raw(session.recovery_pending_approvals)
        state = _safe_text(session.recovery_state) or "interrupted"
        summary = _safe_text(session.recovery_summary) or "interrupted after restart"
        return SessionRecoveryProjection(
            state=state,
            summary=summary,
            last_activity=_safe_text(session.recovery_last_activity) or cls._last_activity_summary(session.transcript),
            last_user_message=_safe_text(session.recovery_last_user_message)
            or cls._last_role_preview(session.transcript, role="user"),
            last_assistant_message=_safe_text(session.recovery_last_assistant_message)
            or cls._last_role_preview(session.transcript, role="assistant"),
            pending_approvals=tuple(cls._build_pending_approval_projections(pending)),
        ).to_transport()

    @staticmethod
    def _serialize_agent_messages(messages: Sequence[Any]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for item in messages or []:
            if hasattr(item, "model_dump"):
                payload = item.model_dump()
            elif isinstance(item, dict):
                payload = dict(item)
            elif hasattr(item, "__dict__"):
                payload = dict(vars(item))
            else:
                payload = {"role": "assistant", "content": str(item)}
            serialized.append(
                {
                    "role": payload.get("role", "assistant"),
                    "content": payload.get("content", ""),
                    "thinking": payload.get("thinking"),
                    "tool_calls": payload.get("tool_calls"),
                    "tool_call_id": payload.get("tool_call_id"),
                    "name": payload.get("name"),
                }
            )
        return serialized

    def _enforce_main_workspace_policy(self, workspace_dir: Path) -> None:
        if self._policy.mode != MainAgentRuntimeMode.SINGLE_MAIN:
            return
        if self._policy.main_workspace_dir is None:
            return
        main_workspace = self._policy.main_workspace_dir.resolve()
        if self._same_workspace(workspace_dir, main_workspace):
            return
        raise HTTPException(
            status_code=409,
            detail=(
                "Main-agent single-main mode requires the main workspace. "
                f"requested_workspace={workspace_dir.resolve()} "
                f"main_workspace={main_workspace} "
                "agent_team_mode=reserved"
            ),
        )

    @staticmethod
    def _path_key(path: Path) -> str:
        resolved = str(path.resolve())
        return resolved.lower() if os.name == "nt" else resolved

    @classmethod
    def _same_workspace(cls, left: Path, right: Path) -> bool:
        return cls._path_key(left) == cls._path_key(right)

    def _find_latest_session_for_workspace(self, workspace_dir: Path) -> MainAgentSessionState | None:
        candidates = [
            session
            for session in self._sessions.values()
            if self._same_workspace(session.workspace_dir, workspace_dir)
        ]
        if not candidates:
            return None
        return max(candidates, key=lambda item: item.updated_at)

    def _find_latest_persisted_session_record_for_workspace(
        self,
        workspace_dir: Path,
    ) -> dict[str, Any] | None:
        candidates: list[dict[str, Any]] = []
        for record in self._persistence.list_session_records():
            record_workspace = _safe_text(record.get("workspace_dir"))
            if not record_workspace:
                continue
            try:
                resolved_workspace = Path(record_workspace).expanduser().resolve()
            except Exception:
                continue
            if self._same_workspace(resolved_workspace, workspace_dir):
                candidates.append(record)
        if not candidates:
            return None
        candidates.sort(key=lambda item: _safe_text(item.get("updated_at")), reverse=True)
        return dict(candidates[0])

    def _allocate_session_title_unlocked(
        self,
        base_title: str,
        *,
        workspace_dir: Path,
    ) -> str:
        normalized_base = _safe_text(base_title)
        if not normalized_base:
            return ""
        exact_taken = False
        numbered_suffixes: set[int] = set()

        def _observe_title(raw_title: object, raw_workspace: Path | None) -> None:
            nonlocal exact_taken
            title = _safe_text(raw_title)
            if not title:
                return
            if raw_workspace is not None and not self._same_workspace(raw_workspace, workspace_dir):
                return
            if title == normalized_base:
                exact_taken = True
                return
            prefix = f"{normalized_base} "
            if not title.startswith(prefix):
                return
            suffix = title[len(prefix) :].strip()
            if suffix.isdigit():
                numbered_suffixes.add(max(1, int(suffix)))

        for session in self._sessions.values():
            _observe_title(session.title, session.workspace_dir)
        for record in self._persistence.list_session_records():
            record_workspace = _safe_text(record.get("workspace_dir"))
            if not record_workspace:
                continue
            try:
                resolved_workspace = Path(record_workspace).expanduser().resolve()
            except Exception:
                continue
            _observe_title(record.get("title"), resolved_workspace)

        if not exact_taken:
            return normalized_base

        suffix = 1
        while suffix in numbered_suffixes:
            suffix += 1
        return f"{normalized_base} {suffix}"

    @classmethod
    def _session_summary_dedup_key(
        cls,
        summary: MainAgentSessionSummary,
    ) -> tuple[str, str, str, str, str] | None:
        channel = _safe_text(summary.channel_type).lower()
        conversation = _safe_text(summary.conversation_id)
        if not channel or not conversation:
            return None
        workspace_dir = _safe_text(summary.workspace_dir)
        try:
            workspace_key = cls._path_key(Path(workspace_dir).expanduser().resolve())
        except Exception:
            workspace_key = workspace_dir.lower()
        title = _safe_text(summary.title) or "<untitled>"
        origin = cls._normalize_surface(summary.origin_surface)
        return workspace_key, channel, conversation, origin, title

    @classmethod
    def _session_summary_conversation_key(
        cls,
        summary: MainAgentSessionSummary,
    ) -> tuple[str, str, str] | None:
        channel = _safe_text(summary.channel_type).lower()
        conversation = _safe_text(summary.conversation_id)
        if not channel or not conversation:
            return None
        workspace_dir = _safe_text(summary.workspace_dir)
        try:
            workspace_key = cls._path_key(Path(workspace_dir).expanduser().resolve())
        except Exception:
            workspace_key = workspace_dir.lower()
        return workspace_key, channel, conversation

    @classmethod
    def _is_channel_stub_summary(cls, summary: MainAgentSessionSummary) -> bool:
        channel = _safe_text(summary.channel_type).lower()
        if not channel:
            return False
        title = _safe_text(summary.title)
        origin = cls._normalize_surface(summary.origin_surface)
        return not title and origin == channel

    @classmethod
    def _is_interactive_shared_summary(cls, summary: MainAgentSessionSummary) -> bool:
        channel = _safe_text(summary.channel_type).lower()
        if not channel:
            return False
        title = _safe_text(summary.title)
        origin = cls._normalize_surface(summary.origin_surface)
        return bool(title) and origin not in {"", channel}

    @classmethod
    def _dedupe_session_summaries(
        cls,
        sessions: Sequence[MainAgentSessionSummary],
    ) -> list[MainAgentSessionSummary]:
        deduped: list[MainAgentSessionSummary] = []
        seen_keys: set[tuple[str, str, str, str, str]] = set()
        for summary in sessions:
            key = cls._session_summary_dedup_key(summary)
            if key is not None:
                if key in seen_keys:
                    continue
                seen_keys.add(key)
            deduped.append(summary)
        grouped: dict[tuple[str, str, str], list[MainAgentSessionSummary]] = {}
        for summary in deduped:
            key = cls._session_summary_conversation_key(summary)
            if key is None:
                continue
            grouped.setdefault(key, []).append(summary)

        filtered: list[MainAgentSessionSummary] = []
        for summary in deduped:
            key = cls._session_summary_conversation_key(summary)
            if key is None:
                filtered.append(summary)
                continue
            siblings = grouped.get(key, [])
            if cls._is_channel_stub_summary(summary) and any(
                cls._is_interactive_shared_summary(candidate)
                for candidate in siblings
                if candidate.session_id != summary.session_id
            ):
                continue
            filtered.append(summary)
        return filtered

    @staticmethod
    def _reset_agent_messages(agent: Agent | None) -> None:
        if agent is None:
            return
        messages = getattr(agent, "messages", None)
        if isinstance(messages, list) and messages:
            agent.messages = [messages[0]]
        if hasattr(agent, "api_total_tokens"):
            agent.api_total_tokens = 0
        reset_runtime_state = getattr(agent, "reset_ephemeral_runtime_state", None)
        if callable(reset_runtime_state):
            reset_runtime_state()
            return
        if hasattr(agent, "last_prepared_turn_context"):
            agent.last_prepared_turn_context = None
        if hasattr(agent, "prepared_context_diagnostics"):
            agent.prepared_context_diagnostics = {}
        if hasattr(agent, "last_memory_automation"):
            agent.last_memory_automation = {}
        if hasattr(agent, "last_runtime_task_memory"):
            agent.last_runtime_task_memory = {}

    @staticmethod
    def _clear_runtime_task_memory_namespace(
        *,
        workspace_dir: Path,
        session_id: str,
    ) -> bool:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).clear_session_namespace(session_id)
        except Exception:
            return False

    @staticmethod
    def _snapshot_runtime_task_memory_payload(
        *,
        workspace_dir: Path,
        session_id: str,
    ) -> dict[str, Any]:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).snapshot_session_namespace_payload(session_id)
        except Exception:
            return {}

    @staticmethod
    def _snapshot_workspace_shared_runtime_task_memory_payload(
        *,
        workspace_dir: Path,
    ) -> dict[str, Any]:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).snapshot_workspace_shared_namespace_payload()
        except Exception:
            return {}

    @staticmethod
    def _restore_session_runtime_task_memory_unlocked(
        *,
        workspace_dir: Path,
        session_id: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).restore_session_namespace_payload(
                session_id,
                payload,
                replace=True,
            )
        except Exception:
            return {
                "restored": False,
                "namespace": WorkspaceMemoriaRuntime.session_namespace(session_id),
                "entry_count": 0,
                "stats": {},
            }

    @staticmethod
    def _restore_workspace_shared_runtime_task_memory_unlocked(
        *,
        workspace_dir: Path,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        try:
            return WorkspaceMemoriaRuntime(workspace_dir).restore_workspace_shared_namespace_payload(
                payload,
                replace=False,
            )
        except Exception:
            return {
                "restored": False,
                "namespace": WorkspaceMemoriaRuntime.shared_namespace(),
                "entry_count": 0,
                "stats": {},
                "merged": True,
            }

    def _reset_session_runtime_state_unlocked(
        self,
        session: MainAgentSessionState,
        *,
        clear_runtime_task_memory: bool,
    ) -> None:
        self._reset_agent_messages(session.agent)
        if clear_runtime_task_memory:
            self._clear_runtime_task_memory_namespace(
                workspace_dir=session.workspace_dir,
                session_id=session.session_id,
            )
        session.current_turn_id = None
        session.cancel_event = None
        session.pending_approvals = []
        for future in list(session.pending_approval_waiters.values()):
            if not future.done():
                future.set_result(None)
        session.pending_approval_waiters.clear()
        self._clear_recovery_context_unlocked(session)
        session.last_prepared_context = {}
        session.prepared_context_diagnostics = {}
        session.busy = False
        session.running_state = ""
        session.knowledge_base_enabled = self._agent_knowledge_base_enabled(session.agent)
        session.memory_diagnostics = self._build_memory_diagnostics_for_session(session)

    @staticmethod
    def _normalize_surface(surface: str | None) -> str:
        normalized = str(surface or "").strip().lower()
        return normalized or "api"

    @staticmethod
    def _normalize_nonnegative_int(value: Any, *, default: int = 0) -> int:
        try:
            parsed = int(value or 0)
        except Exception:
            return max(0, int(default))
        return max(0, parsed)

    @classmethod
    def _estimate_raw_message_tokens(cls, raw_messages: Sequence[Any] | None) -> int:
        restored: list[Message] = []
        for raw in raw_messages or []:
            if not isinstance(raw, dict):
                continue
            try:
                restored.append(Message.model_validate(raw))
            except Exception:
                continue
        if not restored:
            return 0
        try:
            return cls._normalize_nonnegative_int(estimate_tokens(restored))
        except Exception:
            return 0

    @classmethod
    def _session_token_usage(cls, session: MainAgentSessionState) -> int:
        live = cls._normalize_nonnegative_int(getattr(session.agent, "api_total_tokens", 0))
        if live > 0:
            return live
        messages = getattr(session.agent, "messages", None)
        if isinstance(messages, list):
            try:
                return cls._normalize_nonnegative_int(estimate_tokens(messages))
            except Exception:
                return 0
        return 0

    @classmethod
    def _session_token_limit(cls, session: MainAgentSessionState) -> int:
        return cls._normalize_nonnegative_int(getattr(session.agent, "token_limit", 0))

    @classmethod
    def _record_token_usage(cls, record: dict[str, Any]) -> int:
        explicit = cls._normalize_nonnegative_int(record.get("token_usage"))
        if explicit > 0:
            return explicit
        raw_messages = record.get("messages")
        if isinstance(raw_messages, list):
            return cls._estimate_raw_message_tokens(raw_messages)
        return 0

    @classmethod
    def _record_token_limit(cls, record: dict[str, Any]) -> int:
        return cls._normalize_nonnegative_int(record.get("token_limit"))

    @classmethod
    def _restore_agent_token_state(
        cls,
        agent: Agent,
        *,
        token_usage: Any = None,
        token_limit: Any = None,
        raw_messages: Sequence[Any] | None = None,
    ) -> None:
        usage = cls._normalize_nonnegative_int(token_usage)
        if usage <= 0:
            usage = cls._estimate_raw_message_tokens(raw_messages)
        if hasattr(agent, "api_total_tokens"):
            agent.api_total_tokens = usage

        limit = cls._normalize_nonnegative_int(token_limit)
        if limit > 0:
            setattr(agent, "token_limit", limit)

    def _build_session_summary_projection(
        self,
        session: MainAgentSessionState,
    ) -> SessionSummaryProjection:
        memory_diagnostics = self._build_memory_diagnostics_for_session(session)
        sandbox_diagnostics = self._build_sandbox_diagnostics_for_session(session)
        pending_approvals = tuple(self._build_pending_approval_projections(session.pending_approvals))
        recovery = self._build_session_recovery_projection(
            transcript=session.transcript,
            origin_surface=session.origin_surface,
            active_surface=session.active_surface,
            reply_enabled=session.reply_enabled,
            channel_type=session.channel_type,
            busy=session.busy,
            running_state=session.running_state,
            pending_approvals=session.pending_approvals,
            persisted_record=False,
        )
        stored_recovery = self._stored_recovery_snapshot_from_session(session)
        if stored_recovery is not None and not session.busy and not pending_approvals:
            recovery = SessionRecoveryProjection.from_payload(stored_recovery)
        return SessionSummaryProjection(
            session_id=session.session_id,
            workspace_dir=str(session.workspace_dir),
            created_at=_to_utc_iso(session.created_at),
            updated_at=_to_utc_iso(session.updated_at),
            title=_safe_text(session.title) or None,
            message_count=len(session.transcript),
            origin_surface=self._normalize_surface(session.origin_surface),
            active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
            reply_enabled=bool(session.reply_enabled),
            busy=bool(session.busy),
            running_state=_safe_text(session.running_state) or None,
            channel_type=session.channel_type,
            conversation_id=session.conversation_id,
            sender_id=session.sender_id,
            token_usage=self._session_token_usage(session),
            token_limit=self._session_token_limit(session),
            shared=bool(session.shared),
            knowledge_base_enabled=bool(session.knowledge_base_enabled),
            selected_model_source=session.selected_model_source,
            selected_provider_id=session.selected_provider_id,
            selected_model_id=session.selected_model_id,
            pending_model_source=session.pending_model_source,
            pending_provider_id=session.pending_provider_id,
            pending_model_id=session.pending_model_id,
            pending_skill_reload=bool(session.pending_skill_reload),
            pending_skill_reload_reason=_safe_text(session.pending_skill_reload_reason) or None,
            pending_approvals=pending_approvals,
            recovery=recovery,
            memory_diagnostics=dict(memory_diagnostics),
            sandbox_diagnostics=dict(sandbox_diagnostics),
        )

    def _build_session_summary(self, session: MainAgentSessionState) -> MainAgentSessionSummary:
        return self._build_session_summary_projection(session).to_transport()

    def _build_session_detail(
        self,
        session: MainAgentSessionState,
        *,
        recent_limit: int,
    ) -> MainAgentSessionDetail:
        normalized_limit = max(1, int(recent_limit))
        summary = self._build_session_summary_projection(session)
        return SessionDetailProjection(
            **summary.__dict__,
            context_policy=self._normalize_context_policy_payload(session.context_policy),
            last_prepared_context=self._normalize_prepared_context_payload(session.last_prepared_context),
            prepared_context_diagnostics=self._normalize_prepared_context_diagnostics_payload(
                session.prepared_context_diagnostics
            ),
            recent_messages=tuple(
                self._build_session_message_projection(entry)
                for entry in session.transcript[-normalized_limit:]
            ),
        ).to_transport()

    def _build_session_summary_projection_from_record(
        self,
        record: dict[str, Any],
    ) -> SessionSummaryProjection:
        memory_diagnostics = self._build_memory_diagnostics_from_record(record)
        sandbox_diagnostics = self._build_sandbox_diagnostics_from_record(record)
        transcript = self._transcript_entries_from_record(record)
        pending_approvals = tuple(self._build_pending_approval_projections(record.get("pending_approvals")))
        recovery = self._build_session_recovery_projection(
            transcript=transcript,
            origin_surface=record.get("origin_surface"),
            active_surface=record.get("active_surface") or record.get("origin_surface"),
            reply_enabled=bool(record.get("reply_enabled", False)),
            channel_type=_safe_text(record.get("channel_type")) or None,
            busy=bool(record.get("busy", False)),
            running_state=_safe_text(record.get("running_state")) or None,
            pending_approvals=record.get("pending_approvals"),
            persisted_record=True,
        )
        stored_recovery = self._stored_recovery_snapshot_from_record(record, transcript=transcript)
        if stored_recovery is not None and not bool(record.get("busy", False)) and not pending_approvals:
            recovery = SessionRecoveryProjection.from_payload(stored_recovery)
        return SessionSummaryProjection(
            session_id=_safe_text(record.get("session_id")) or uuid4().hex,
            workspace_dir=str(record.get("workspace_dir", "")),
            created_at=str(record.get("created_at", "")),
            updated_at=str(record.get("updated_at", "")),
            title=_safe_text(record.get("title")) or None,
            message_count=max(0, int(record.get("shared_message_count") or record.get("message_count") or 0)),
            origin_surface=self._normalize_surface(record.get("origin_surface")),
            active_surface=self._normalize_surface(record.get("active_surface") or record.get("origin_surface")),
            reply_enabled=bool(record.get("reply_enabled", False)),
            busy=False,
            running_state=None,
            channel_type=_safe_text(record.get("channel_type")) or None,
            conversation_id=_safe_text(record.get("conversation_id")) or None,
            sender_id=_safe_text(record.get("sender_id")) or None,
            token_usage=self._record_token_usage(record),
            token_limit=self._record_token_limit(record),
            shared=bool(record.get("shared", False)),
            knowledge_base_enabled=bool(record.get("knowledge_base_enabled", True)),
            selected_model_source=self._normalize_model_source(record.get("selected_model_source")),
            selected_provider_id=_safe_text(record.get("selected_provider_id")) or None,
            selected_model_id=_safe_text(record.get("selected_model_id")) or None,
            pending_model_source=self._normalize_model_source(record.get("pending_model_source")),
            pending_provider_id=_safe_text(record.get("pending_provider_id")) or None,
            pending_model_id=_safe_text(record.get("pending_model_id")) or None,
            pending_skill_reload=bool(record.get("pending_skill_reload", False)),
            pending_skill_reload_reason=_safe_text(record.get("pending_skill_reload_reason")) or None,
            pending_approvals=tuple(),
            recovery=recovery,
            memory_diagnostics=dict(memory_diagnostics),
            sandbox_diagnostics=dict(sandbox_diagnostics),
        )

    def _build_session_summary_from_record(self, record: dict[str, Any]) -> MainAgentSessionSummary:
        return self._build_session_summary_projection_from_record(record).to_transport()

    def _build_session_detail_from_record(
        self,
        record: dict[str, Any],
        *,
        recent_limit: int,
    ) -> MainAgentSessionDetail:
        normalized_limit = max(1, int(recent_limit))
        summary = self._build_session_summary_projection_from_record(record)
        transcript = self._transcript_entries_from_record(record)
        return SessionDetailProjection(
            **summary.__dict__,
            context_policy=self._normalize_context_policy_payload(record.get("context_policy")),
            last_prepared_context=self._normalize_prepared_context_payload(record.get("last_prepared_context")),
            prepared_context_diagnostics=self._normalize_prepared_context_diagnostics_payload(
                record.get("prepared_context_diagnostics")
            ),
            recent_messages=tuple(
                self._build_session_message_projection(entry)
                for entry in transcript[-normalized_limit:]
            ),
        ).to_transport()

    def _build_session_snapshot(self, session: MainAgentSessionState) -> RuntimeSessionSnapshot:
        memory_diagnostics = self._build_memory_diagnostics_for_session(session)
        sandbox_diagnostics = self._build_sandbox_diagnostics_for_session(session)
        return RuntimeSessionSnapshot(
            session_id=session.session_id,
            workspace_dir=str(session.workspace_dir),
            title=_safe_text(session.title) or None,
            origin_surface=self._normalize_surface(session.origin_surface),
            active_surface=self._normalize_surface(session.active_surface or session.origin_surface),
            reply_enabled=bool(session.reply_enabled),
            channel_type=session.channel_type,
            conversation_id=session.conversation_id,
            sender_id=session.sender_id,
            token_usage=self._session_token_usage(session),
            token_limit=self._session_token_limit(session),
            shared=bool(session.shared),
            knowledge_base_enabled=bool(session.knowledge_base_enabled),
            selected_model_source=session.selected_model_source,
            selected_provider_id=session.selected_provider_id,
            selected_model_id=session.selected_model_id,
            pending_model_source=session.pending_model_source,
            pending_provider_id=session.pending_provider_id,
            pending_model_id=session.pending_model_id,
            pending_skill_reload=bool(session.pending_skill_reload),
            pending_skill_reload_reason=_safe_text(session.pending_skill_reload_reason) or None,
            context_policy=self._normalize_context_policy_payload(session.context_policy),
            last_prepared_context=self._normalize_prepared_context_payload(session.last_prepared_context),
            prepared_context_diagnostics=self._normalize_prepared_context_diagnostics_payload(
                session.prepared_context_diagnostics
            ),
            memory_diagnostics=dict(memory_diagnostics),
            sandbox_diagnostics=dict(sandbox_diagnostics),
            runtime_task_memory_payload=self._snapshot_runtime_task_memory_payload(
                workspace_dir=session.workspace_dir,
                session_id=session.session_id,
            ),
            workspace_shared_runtime_memory_payload=self._snapshot_workspace_shared_runtime_task_memory_payload(
                workspace_dir=session.workspace_dir,
            ),
            agent_messages=self._serialize_agent_messages(getattr(session.agent, "messages", []) or []),
            transcript=[
                RuntimeSessionImportMessage(
                    role=entry.role,
                    content=entry.content,
                    surface=entry.surface,
                    created_at=_to_utc_iso(entry.created_at),
                    channel_type=entry.channel_type,
                    conversation_id=entry.conversation_id,
                    sender_id=entry.sender_id,
                    metadata=dict(entry.metadata) if entry.metadata else None,
                )
                for entry in session.transcript
            ],
        )

    def _build_session_snapshot_from_record(self, record: dict[str, Any]) -> RuntimeSessionSnapshot:
        transcript = self._transcript_entries_from_record(record)
        raw_messages = record.get("messages")
        agent_messages = raw_messages if isinstance(raw_messages, list) else []
        workspace_dir = Path(str(record.get("workspace_dir", "."))).expanduser().resolve()
        session_id = _safe_text(record.get("session_id")) or None
        return RuntimeSessionSnapshot(
            session_id=session_id,
            workspace_dir=str(record.get("workspace_dir", "")),
            title=_safe_text(record.get("title")) or None,
            origin_surface=self._normalize_surface(record.get("origin_surface")),
            active_surface=self._normalize_surface(record.get("active_surface") or record.get("origin_surface")),
            reply_enabled=bool(record.get("reply_enabled", False)),
            channel_type=_safe_text(record.get("channel_type")) or None,
            conversation_id=_safe_text(record.get("conversation_id")) or None,
            sender_id=_safe_text(record.get("sender_id")) or None,
            token_usage=self._record_token_usage(record),
            token_limit=self._record_token_limit(record),
            shared=bool(record.get("shared", False)),
            knowledge_base_enabled=bool(record.get("knowledge_base_enabled", True)),
            selected_model_source=self._normalize_model_source(record.get("selected_model_source")),
            selected_provider_id=_safe_text(record.get("selected_provider_id")) or None,
            selected_model_id=_safe_text(record.get("selected_model_id")) or None,
            pending_model_source=self._normalize_model_source(record.get("pending_model_source")),
            pending_provider_id=_safe_text(record.get("pending_provider_id")) or None,
            pending_model_id=_safe_text(record.get("pending_model_id")) or None,
            pending_skill_reload=bool(record.get("pending_skill_reload", False)),
            pending_skill_reload_reason=_safe_text(record.get("pending_skill_reload_reason")) or None,
            context_policy=self._normalize_context_policy_payload(record.get("context_policy")),
            last_prepared_context=self._normalize_prepared_context_payload(record.get("last_prepared_context")),
            prepared_context_diagnostics=self._normalize_prepared_context_diagnostics_payload(
                record.get("prepared_context_diagnostics")
            ),
            memory_diagnostics=self._build_memory_diagnostics_from_record(record),
            sandbox_diagnostics=self._build_sandbox_diagnostics_from_record(record),
            runtime_task_memory_payload=(
                self._snapshot_runtime_task_memory_payload(
                    workspace_dir=workspace_dir,
                    session_id=session_id,
                )
                if session_id
                else {}
            ),
            workspace_shared_runtime_memory_payload=self._snapshot_workspace_shared_runtime_task_memory_payload(
                workspace_dir=workspace_dir,
            ),
            agent_messages=self._serialize_agent_messages(agent_messages),
            transcript=[
                RuntimeSessionImportMessage(
                    role=entry.role,
                    content=entry.content,
                    surface=entry.surface,
                    created_at=_to_utc_iso(entry.created_at),
                    channel_type=entry.channel_type,
                    conversation_id=entry.conversation_id,
                    sender_id=entry.sender_id,
                    metadata=dict(entry.metadata) if entry.metadata else None,
                )
                for entry in transcript
            ],
        )

    @staticmethod
    def _build_session_message_projection(entry: MainAgentSessionTranscriptEntry) -> SessionMessageProjection:
        return SessionMessageProjection(
            index=entry.index,
            role=entry.role,
            content=entry.content,
            surface=entry.surface,
            created_at=_to_utc_iso(entry.created_at),
            channel_type=entry.channel_type,
            conversation_id=entry.conversation_id,
            sender_id=entry.sender_id,
            metadata=dict(entry.metadata) if entry.metadata else None,
        )

    @staticmethod
    def _build_session_message(entry: MainAgentSessionTranscriptEntry) -> MainAgentSessionMessage:
        return MainAgentRuntimeManager._build_session_message_projection(entry).to_transport()

    @classmethod
    def _build_session_recovery_projection(
        cls,
        *,
        transcript: Sequence[MainAgentSessionTranscriptEntry],
        origin_surface: str | None,
        active_surface: str | None,
        reply_enabled: bool,
        channel_type: str | None,
        busy: bool,
        running_state: str | None,
        pending_approvals: Sequence[dict[str, Any]] | None,
        persisted_record: bool,
    ) -> SessionRecoveryProjection:
        normalized_origin = cls._normalize_surface(origin_surface)
        normalized_active = cls._normalize_surface(active_surface or origin_surface)
        normalized_running_state = _safe_text(running_state)
        normalized_pending = cls._pending_approvals_from_raw(list(pending_approvals or []))

        state = "idle"
        summary = "idle"
        if persisted_record and normalized_pending:
            state = "interrupted"
            if len(normalized_pending) == 1:
                summary = f"interrupted after restart: approval pending for {normalized_pending[0]['tool_name']}"
            else:
                summary = f"interrupted after restart: {len(normalized_pending)} approvals pending"
        elif persisted_record and (busy or normalized_running_state):
            state = "interrupted"
            summary = (
                f"interrupted after restart: {normalized_running_state}"
                if normalized_running_state
                else "interrupted after restart"
            )
        elif busy:
            state = "running"
            summary = normalized_running_state or f"{normalized_active} request running"
        elif normalized_active != normalized_origin:
            state = "handoff"
            summary = f"active on {normalized_active}; origin {normalized_origin}"
        elif reply_enabled and _safe_text(channel_type):
            state = "reply_enabled"
            summary = f"replying via {_safe_text(channel_type).lower()}"

        return SessionRecoveryProjection(
            state=state,
            summary=summary,
            last_activity=cls._last_activity_summary(transcript),
            last_user_message=cls._last_role_preview(transcript, role="user"),
            last_assistant_message=cls._last_role_preview(transcript, role="assistant"),
            pending_approvals=tuple(cls._build_pending_approval_projections(normalized_pending if persisted_record else [])),
        )

    @staticmethod
    def _session_memory_read_result(
        *,
        action: str,
        diagnostics: dict[str, Any],
        detail_mode: str,
    ) -> dict[str, Any]:
        normalized_action = _safe_text(action).lower().replace("-", "_")
        summary = memory_diagnostics_summary_line(diagnostics)
        if normalized_action == "status":
            details = (
                f"Memory status: {summary}\n"
                f"Workspace: {_safe_text(diagnostics.get('workspace_anchor_dir')) or _safe_text(diagnostics.get('workspace_dir'))}"
            )
        elif normalized_action in {"runtime", "list"}:
            runtime = diagnostics.get("runtime_task_memory") if isinstance(diagnostics.get("runtime_task_memory"), dict) else {}
            details_lines = [
                "Session Runtime Memory" if normalized_action == "list" else "Runtime Task Memory",
                f"Session namespace: {_safe_text(runtime.get('session_namespace')) or 'n/a'}",
                f"Session entries: {int(runtime.get('session_count') or 0)}",
                f"Shared namespace: {_safe_text(runtime.get('workspace_shared_namespace')) or 'n/a'}",
                f"Shared entries: {int(runtime.get('shared_count') or 0)}",
            ]
            session_preview = runtime.get("session_preview") if isinstance(runtime.get("session_preview"), list) else []
            shared_preview = runtime.get("shared_preview") if isinstance(runtime.get("shared_preview"), list) else []
            if session_preview:
                details_lines.append("")
                details_lines.append("Session Preview")
                details_lines.extend(
                    format_runtime_memory_preview_lines(
                        session_preview,
                        limit=5,
                        include_latest_hint=True,
                        latest_hint_label="session preview entry",
                    )
                )
            if shared_preview:
                details_lines.append("")
                details_lines.append("Shared Preview")
                details_lines.extend(format_runtime_memory_preview_lines(shared_preview, limit=5))
            details = "\n".join(details_lines).strip()
        elif normalized_action == "shared_list":
            runtime = diagnostics.get("runtime_task_memory") if isinstance(diagnostics.get("runtime_task_memory"), dict) else {}
            details_lines = [
                "Workspace-Shared Runtime Memory",
                f"Shared namespace: {_safe_text(runtime.get('workspace_shared_namespace')) or 'n/a'}",
                f"Shared entries: {int(runtime.get('shared_count') or 0)}",
            ]
            shared_preview = runtime.get("shared_preview") if isinstance(runtime.get("shared_preview"), list) else []
            if shared_preview:
                details_lines.append("")
                details_lines.append("Shared Preview")
                details_lines.extend(
                    format_runtime_memory_preview_lines(
                        shared_preview,
                        limit=5,
                        include_latest_hint=True,
                        latest_hint_label="shared preview entry",
                    )
                )
            details = "\n".join(details_lines).strip()
        else:
            details = format_memory_diagnostics(
                diagnostics,
                include_header=True,
                detail_mode=detail_mode,
            )
        return {
            "summary": summary,
            "details": details,
        }

    @classmethod
    def _build_session_recovery_snapshot(
        cls,
        *,
        transcript: Sequence[MainAgentSessionTranscriptEntry],
        origin_surface: str | None,
        active_surface: str | None,
        reply_enabled: bool,
        channel_type: str | None,
        busy: bool,
        running_state: str | None,
        pending_approvals: Sequence[dict[str, Any]] | None,
        persisted_record: bool,
    ) -> MainAgentSessionRecoverySnapshot:
        return cls._build_session_recovery_projection(
            transcript=transcript,
            origin_surface=origin_surface,
            active_surface=active_surface,
            reply_enabled=reply_enabled,
            channel_type=channel_type,
            busy=busy,
            running_state=running_state,
            pending_approvals=pending_approvals,
            persisted_record=persisted_record,
        ).to_transport()

    @classmethod
    def _last_activity_summary(cls, transcript: Sequence[MainAgentSessionTranscriptEntry]) -> str | None:
        for entry in reversed(list(transcript or [])):
            metadata = dict(entry.metadata) if isinstance(entry.metadata, dict) else {}
            if entry.role == "tool" and metadata.get("kind") == "activity":
                items = metadata.get("activity_items")
                if isinstance(items, list) and items:
                    item = items[-1]
                    label = cls._activity_label(item.get("label", "activity"))
                    detail = _safe_text(item.get("detail")) or "running"
                    preview = _safe_text(item.get("preview"))
                    output_summary = _safe_text(item.get("output_summary"))
                    parts = [f"{label} {detail}"]
                    if preview:
                        parts.append(preview)
                    if output_summary and label == "shell":
                        parts.append(output_summary)
                    return " | ".join(part for part in parts if part).strip() or None
                text = _safe_text(entry.content)
                if text:
                    return text
            if metadata.get("kind") == "command":
                command = _safe_text(metadata.get("command")) or "command"
                command_summary = _safe_text(metadata.get("summary")) or _safe_text(entry.content) or "applied"
                return f"{command} | {command_summary}"
        return None

    @staticmethod
    def _last_role_preview(
        transcript: Sequence[MainAgentSessionTranscriptEntry],
        *,
        role: str,
        limit: int = 160,
    ) -> str | None:
        normalized_role = _safe_text(role).lower()
        for entry in reversed(list(transcript or [])):
            if _safe_text(entry.role).lower() != normalized_role:
                continue
            text = _safe_text(entry.content)
            if not text:
                continue
            if len(text) <= limit:
                return text
            return text[: limit - 3] + "..."
        return None

    def _apply_surface_binding_unlocked(
        self,
        session: MainAgentSessionState,
        *,
        surface: str | None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        reply_enabled: bool | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        normalized_surface = self._normalize_surface(surface)
        if not str(session.origin_surface or "").strip():
            session.origin_surface = normalized_surface
        session.active_surface = normalized_surface
        if channel_type:
            session.channel_type = str(channel_type).strip() or session.channel_type
        if conversation_id:
            session.conversation_id = str(conversation_id).strip() or session.conversation_id
        if sender_id:
            session.sender_id = str(sender_id).strip() or session.sender_id
        if reply_enabled is not None:
            session.reply_enabled = bool(reply_enabled)
        else:
            session.reply_enabled = bool(session.channel_type and session.conversation_id and normalized_surface == session.channel_type)
        session.touch(now_utc=now_utc)

    def _append_transcript_unlocked(
        self,
        session: MainAgentSessionState,
        *,
        role: str,
        content: str,
        surface: str,
        metadata: dict[str, Any] | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> MainAgentSessionTranscriptEntry | None:
        text = str(content or "")
        normalized_metadata = dict(metadata) if isinstance(metadata, dict) else {}
        if not text.strip() and not normalized_metadata:
            return None
        created_at = (now_utc or datetime.now(timezone.utc)).astimezone(timezone.utc)
        entry = MainAgentSessionTranscriptEntry(
            index=session.next_transcript_index,
            role=str(role or "").strip().lower() or "assistant",
            content=text,
            surface=self._normalize_surface(surface),
            created_at=created_at,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            metadata=normalized_metadata,
        )
        session.transcript.append(entry)
        session.next_transcript_index += 1
        return entry

    def _ensure_activity_transcript_entry_unlocked(
        self,
        session: MainAgentSessionState,
        *,
        surface: str,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        now_utc: datetime | None = None,
    ) -> MainAgentSessionTranscriptEntry:
        current_turn_id = _safe_text(session.current_turn_id)
        if current_turn_id:
            for entry in reversed(session.transcript):
                if entry.role != "tool":
                    continue
                metadata = entry.metadata if isinstance(entry.metadata, dict) else {}
                if metadata.get("kind") != "activity":
                    continue
                if _safe_text(metadata.get("turn_id")) == current_turn_id:
                    return entry
        entry = self._append_transcript_unlocked(
            session,
            role="tool",
            content="",
            surface=surface,
            metadata={
                "kind": "activity",
                "activity_items": [],
                "threads_visible": True,
                **({"turn_id": current_turn_id} if current_turn_id else {}),
            },
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
            now_utc=now_utc,
        )
        if entry is None:  # pragma: no cover - defensive
            raise RuntimeError("Failed to create activity transcript entry.")
        return entry

    @staticmethod
    def _activity_label(value: str) -> str:
        normalized = _safe_text(value).lower().replace("_", "-")
        if normalized in {"bash", "powershell", "shell", "shell-command"}:
            return "shell"
        if normalized.startswith("bash-"):
            return normalized.replace("bash-", "shell-", 1)
        return normalized or "activity"

    @staticmethod
    def _activity_detail(label: str, detail: str) -> str:
        normalized_detail = _safe_text(detail)
        if label != "thinking":
            return normalized_detail or "running"
        lowered = normalized_detail.lower()
        if not lowered:
            return "thinking"
        if lowered == "starting run":
            return "starting"
        if "planned" in lowered:
            return "planning"
        if "preparing final response" in lowered:
            return "drafting"
        if lowered == "response ready":
            return "ready"
        if lowered == "agent unavailable":
            return "agent unavailable"
        if lowered == "turn limit reached":
            return "turn limit"
        if lowered == "cancelled":
            return "cancelled"
        if lowered in {"run failed", "exception raised"}:
            return "failed"
        return lowered

    @staticmethod
    def _activity_output_summary(output_text: str) -> str:
        normalized = str(output_text or "").strip()
        if not normalized:
            return ""
        non_empty = [line.strip() for line in normalized.splitlines() if line.strip()]
        if not non_empty:
            return ""
        summary_lines = [
            line
            for line in non_empty
            if not (line.startswith("[") and "]" in line[:20])
        ] or non_empty
        first = summary_lines[0]
        if len(first) > 68:
            first = f"{first[:65]}..."
        remaining = len(summary_lines) - 1
        if remaining > 0:
            return f"{first} (+{remaining} more line(s))"
        return first

    @classmethod
    def _build_session_key(cls, *, session_id: str, workspace_dir: Path) -> AgentSessionKey:
        return AgentSessionKey(
            agent_id="main-agent",
            channel="gateway",
            peer_kind="workspace",
            peer_id=cls._path_key(workspace_dir),
            thread_id=session_id,
        )

    def _refresh_session_lifecycle_unlocked(
        self,
        session: MainAgentSessionState,
        *,
        now_utc: datetime | None = None,
    ) -> bool:
        result = self._lifecycle_manager.ensure_active(session.lifecycle_state, now_utc=now_utc)
        session.lifecycle_state = result.state
        if result.reset:
            self._reset_session_runtime_state_unlocked(
                session,
                clear_runtime_task_memory=True,
            )
            self._lifecycle_auto_resets += 1
        session.lifecycle_state = self._lifecycle_manager.touch(session.lifecycle_state, now_utc=now_utc)
        return result.reset
