"""Turn-context provider implementations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_agent.agent_core.context.turn_context_curation import (
    _normalize_text_relevance_score,
)
from mini_agent.agent_core.context.turn_context_types import (
    RuntimeTurnContext,
    TurnContextItem,
    _clean_text,
    _mcp_tool_label,
    _resolve_followup_query,
    _score_text_match,
    _session_search_query_candidates,
    _skill_match_haystack,
    _skill_metadata_match_bonus,
    _tokenize,
    _truncate_text,
)
from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime
from mini_agent.memory.promotion import has_workspace_shared_scope_signal
from mini_agent.memory.service import MemoryService


class RuntimeRecoveryTurnContextProvider:
    """Inject one lightweight recovery hint for the first post-restart turn."""

    name = "runtime_recovery"

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        _ = agent
        metadata = turn_context.metadata if isinstance(turn_context.metadata, dict) else {}
        recovery = metadata.get("recovery")
        if not isinstance(recovery, dict):
            return None

        state = _clean_text(recovery.get("state")) or "interrupted"
        summary = (
            _clean_text(recovery.get("summary"))
            or "previous shared-session task was interrupted"
        )
        last_activity = _clean_text(recovery.get("last_activity"))
        last_user = _clean_text(recovery.get("last_user_message"))
        last_assistant = _clean_text(recovery.get("last_assistant_message"))
        pending_approvals = recovery.get("pending_approvals")
        pending_items = pending_approvals if isinstance(pending_approvals, list) else []
        approval_labels = [
            f"{_clean_text(item.get('tool_name')) or 'tool'}[{_clean_text(item.get('token'))}]"
            for item in pending_items
            if isinstance(item, dict) and _clean_text(item.get("token"))
        ]

        lines = [
            "Previous shared-session work was interrupted before this turn.",
            f"Restart state: {state}",
            f"Restart summary: {summary}",
        ]
        if last_activity:
            lines.append(f"Last activity: {last_activity}")
        if last_user:
            lines.append(f"Last user message: {last_user}")
        if last_assistant:
            lines.append(f"Last assistant message: {last_assistant}")
        if approval_labels:
            lines.append(
                "Pending approvals were lost after restart and must be re-evaluated: "
                + ", ".join(approval_labels)
            )
        lines.append(
            "Continue from the restored session context and reassess any interrupted tool step safely."
        )

        return TurnContextItem(
            source="runtime",
            title="Shared-session recovery",
            content="\n".join(lines),
            metadata={
                "ranking_score": 1.0,
                "ranking_basis": "runtime_recovery",
                "recovery_state": state,
                "recovery_pending_approval_count": len(approval_labels),
            },
        )


class UserProfileTurnContextProvider:
    """Prepare relevant global user-profile facts for one turn."""

    name = "user_profile"

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        top_k: int = 3,
        max_fact_chars: int = 220,
        global_memory_root: str | Path | None = None,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.top_k = max(1, int(top_k))
        self.max_fact_chars = max(80, int(max_fact_chars))
        self.memory_service = MemoryService(
            self.workspace_dir,
            global_memory_root=global_memory_root,
        )

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = (turn_context, agent)
        profile = self.memory_service.profile()
        facts = list(profile.get("facts") or [])
        if not facts:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no global user-profile facts found",
            }
        return {
            "status": "ready",
            "available": True,
            "reason": f"{len(facts)} global profile fact(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        query = _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )
        if not query:
            return None

        hits = self.memory_service.search_profile(query=query, limit=self.top_k)
        if not hits:
            return None

        profile = self.memory_service.profile()
        lines: list[str] = []
        for index, hit in enumerate(hits, start=1):
            fact = _truncate_text(hit.get("fact"), limit=self.max_fact_chars)
            lines.append(f"{index}. {fact}")

        return TurnContextItem(
            source=self.name,
            title="Relevant user profile",
            content="\n".join(lines),
            metadata={
                "query": query,
                "returned": len(hits),
                "scope": _clean_text(profile.get("scope")) or "global",
                "user_file": _clean_text(profile.get("user_file")),
                "ranking_score": _normalize_text_relevance_score(hits[0].get("score")),
                "ranking_score_raw": round(float(hits[0].get("score") or 0.0), 6),
                "ranking_basis": "user_profile_match",
            },
        )


class WorkspaceMemoryContextProvider:
    """Prepare relevant workspace-memory snippets for one turn."""

    name = "workspace_memory"

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        top_k: int = 3,
        max_note_chars: int = 220,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.top_k = max(1, int(top_k))
        self.max_note_chars = max(80, int(max_note_chars))
        self.memory_service = MemoryService(self.workspace_dir)

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = (turn_context, agent)
        notes = self.memory_service.load_notes()
        if not notes:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no workspace memory notes found",
            }
        return {
            "status": "ready",
            "available": True,
            "reason": f"{len(notes)} note(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        notes = self.memory_service.load_notes()
        if not notes:
            return None

        query = self._resolve_query(turn_context=turn_context, agent=agent)
        if not query:
            return None

        ranked = self.memory_service.rank_workspace_notes(query=query)
        if not ranked:
            return None

        selected = ranked[: self.top_k]
        lines: list[str] = []
        for index, (note, _score) in enumerate(selected, start=1):
            source = self.memory_service.relative_path(note.path)
            note_text = _truncate_text(note.content, limit=self.max_note_chars)
            lines.append(f"{index}. [{note.category}] {note_text} (source: {source})")

        return TurnContextItem(
            source=self.name,
            title="Relevant workspace memory",
            content="\n".join(lines),
            metadata={
                "query": query,
                "returned": len(selected),
                "ranking_score": _normalize_text_relevance_score(selected[0][1]),
                "ranking_score_raw": round(float(selected[0][1]), 6),
                "ranking_basis": "workspace_memory_text_match",
            },
        )

    def _resolve_query(self, *, turn_context: RuntimeTurnContext, agent: Any) -> str:
        return _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )


class ConsolidatedMemoryTurnContextProvider:
    """Prepare relevant consolidated-memory hits for one turn."""

    name = "consolidated_memory"

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        memory_file: str | Path | None = None,
        session_store_dir: str | Path | None = None,
        top_k: int = 3,
        stale_after_days: int = 30,
        max_item_chars: int = 220,
        support_lookup: Any | None = None,
        auto_refresh: bool = True,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.memory_file = (
            Path(memory_file).expanduser().resolve()
            if memory_file is not None
            else None
        )
        self.session_store_dir = (
            Path(session_store_dir).expanduser().resolve()
            if session_store_dir is not None
            else None
        )
        self.top_k = max(1, int(top_k))
        self.stale_after_days = max(1, int(stale_after_days))
        self.max_item_chars = max(80, int(max_item_chars))
        self.support_lookup = support_lookup
        self.auto_refresh = bool(auto_refresh)
        self.memory_service = MemoryService(
            self.workspace_dir,
            session_store_dir=self.session_store_dir,
        )

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = agent
        refresh_status = self.memory_service.consolidated_refresh_status(
            memory_file=self.memory_file,
            exclude_session_id=turn_context.session_id,
        )
        if self.auto_refresh and bool(refresh_status.get("needs_refresh")):
            self.memory_service.refresh_consolidated_memory(
                memory_file=self.memory_file,
                exclude_session_id=turn_context.session_id,
            )
        snapshot = self.memory_service.consolidated_snapshot(memory_file=self.memory_file)
        if not snapshot.get("items"):
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no consolidated memory entries found",
            }
        return {
            "status": "ready",
            "available": True,
            "reason": f"{len(snapshot.get('items') or [])} consolidated item(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        query = _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )
        if not query:
            return None

        refresh_status = self.memory_service.consolidated_refresh_status(
            memory_file=self.memory_file,
            exclude_session_id=turn_context.session_id,
        )
        refresh_result: dict[str, Any] | None = None
        if self.auto_refresh and bool(refresh_status.get("needs_refresh")):
            refresh_result = self.memory_service.refresh_consolidated_memory(
                memory_file=self.memory_file,
                exclude_session_id=turn_context.session_id,
            )

        payload = self.memory_service.search_relevant_consolidated_memory(
            query=query,
            top_k=self.top_k,
            stale_after_days=self.stale_after_days,
            memory_file=self.memory_file,
            support_lookup=self.support_lookup,
        )
        hits = payload.get("hits") or []
        if not hits:
            return None

        drift_summary: dict[str, int] = {}
        lines: list[str] = []
        for index, hit in enumerate(hits, start=1):
            content = _truncate_text(hit.get("content"), limit=self.max_item_chars)
            drift_status = _clean_text(hit.get("drift_status")) or "unverified"
            drift_summary[drift_status] = drift_summary.get(drift_status, 0) + 1
            drift_suffix = drift_status.replace("_", " ")
            reason = _truncate_text(hit.get("drift_reason"), limit=90)
            if reason and drift_status != "aligned":
                drift_suffix = f"{drift_suffix}: {reason}"
            lines.append(f"{index}. {content} (drift: {drift_suffix})")

        return TurnContextItem(
            source=self.name,
            title="Relevant consolidated memory",
            content="\n".join(lines),
            metadata={
                "query": payload.get("query") or query,
                "returned": int(payload.get("returned") or 0),
                "memory_file": _clean_text(payload.get("memory_file"))
                or str(self.memory_file or self.memory_service.long_term_file),
                "memory_last_updated_utc": _clean_text(
                    payload.get("memory_last_updated_utc")
                ),
                "memory_file_mtime_utc": _clean_text(
                    payload.get("memory_file_mtime_utc")
                ),
                "drift_summary": drift_summary,
                "refresh_reason": _clean_text(refresh_status.get("reason")),
                "refresh_triggered": bool(
                    refresh_result and refresh_result.get("refreshed")
                ),
                "ranking_score": _normalize_text_relevance_score(hits[0].get("score")),
                "ranking_score_raw": round(float(hits[0].get("score") or 0.0), 6),
                "ranking_basis": "consolidated_memory_relevance",
            },
        )


class RuntimeTaskMemoryTurnContextProvider:
    """Prepare relevant persisted runtime task memory for one turn."""

    name = "runtime_task_memory"

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        state_root: str | Path | None = None,
        session_top_k: int = 2,
        shared_top_k: int = 1,
        max_item_chars: int = 220,
        include_workspace_shared: bool = True,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.session_top_k = max(1, int(session_top_k))
        self.shared_top_k = max(1, int(shared_top_k))
        self.max_item_chars = max(80, int(max_item_chars))
        self.include_workspace_shared = bool(include_workspace_shared)
        self.runtime = WorkspaceMemoriaRuntime(
            self.workspace_dir,
            state_root=state_root,
        )

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = agent
        session_id = _clean_text(turn_context.session_id)
        if not session_id:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "missing session id for runtime task memory",
            }

        stats = self.runtime.stats()
        namespaces = (
            stats.get("namespaces", {})
            if isinstance(stats.get("namespaces"), dict)
            else {}
        )
        session_namespace = self.runtime.session_namespace(session_id)
        session_stats = (
            namespaces.get(session_namespace, {})
            if isinstance(namespaces.get(session_namespace), dict)
            else {}
        )
        shared_namespace = self.runtime.shared_namespace()
        shared_stats = (
            namespaces.get(shared_namespace, {})
            if isinstance(namespaces.get(shared_namespace), dict)
            else {}
        )
        count = sum(int(value or 0) for value in session_stats.values()) + sum(
            int(value or 0)
            for value in shared_stats.values()
        )
        if count <= 0:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no persisted runtime task memory entries found",
            }
        return {
            "status": "ready",
            "available": True,
            "reason": f"{count} runtime task memory item(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        session_id = _clean_text(turn_context.session_id)
        if not session_id:
            return None

        query = _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )
        if not query:
            return None

        session_namespace = self.runtime.session_namespace(session_id)
        session_hits = [
            self.runtime._hit_to_dict(item)
            for item in self.runtime.retrieve(
                namespace=session_namespace,
                query=query,
                limit=self.session_top_k,
            )
        ]
        query_requests_workspace_shared = has_workspace_shared_scope_signal(query)
        include_shared_hits = bool(
            self.include_workspace_shared
            and (
                query_requests_workspace_shared
                or len(session_hits) < self.session_top_k
            )
        )
        shared_hits: list[dict[str, Any]] = []
        if include_shared_hits:
            shared_namespace = self.runtime.shared_namespace()
            shared_hits = [
                self.runtime._hit_to_dict(item)
                for item in self.runtime.retrieve(
                    namespace=shared_namespace,
                    query=query,
                    limit=self.shared_top_k,
                )
            ]
        if not session_hits and not shared_hits:
            return None

        lines: list[str] = []
        top_score = 0.0
        for index, hit in enumerate(session_hits, start=1):
            content = _truncate_text(hit.get("content"), limit=self.max_item_chars)
            lines.append(
                f"S{index}. {content} (layer: {_clean_text(hit.get('layer')) or 'working'})"
            )
            top_score = max(top_score, float(hit.get("score") or 0.0))
        for index, hit in enumerate(shared_hits, start=1):
            content = _truncate_text(hit.get("content"), limit=self.max_item_chars)
            lines.append(
                f"W{index}. {content} (layer: {_clean_text(hit.get('layer')) or 'working'})"
            )
            top_score = max(top_score, float(hit.get("score") or 0.0))

        return TurnContextItem(
            source=self.name,
            title="Relevant runtime task memory",
            content="\n".join(lines),
            metadata={
                "query": query,
                "session_namespace": session_namespace,
                "workspace_shared_namespace": self.runtime.shared_namespace(),
                "session_returned": len(session_hits),
                "shared_returned": len(shared_hits),
                "returned": len(session_hits) + len(shared_hits),
                "workspace_shared_requested": query_requests_workspace_shared,
                "workspace_shared_included": include_shared_hits,
                "workspace_shared_reason": (
                    "query_scope"
                    if query_requests_workspace_shared
                    else (
                        "session_fallback"
                        if include_shared_hits
                        else "suppressed_by_session_hits"
                    )
                ),
                "ranking_score": _normalize_text_relevance_score(top_score),
                "ranking_score_raw": round(top_score, 6),
                "ranking_basis": "runtime_task_memory_relevance",
            },
        )


class SessionSearchTurnContextProvider:
    """Prepare relevant same-workspace session-history hits for one turn."""

    name = "session_search"

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        session_store_dir: str | Path | None = None,
        top_k: int = 3,
        max_snippet_chars: int = 220,
        exclude_current_session: bool = True,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.session_store_dir = (
            Path(session_store_dir).expanduser().resolve()
            if session_store_dir is not None
            else None
        )
        self.top_k = max(1, int(top_k))
        self.max_snippet_chars = max(80, int(max_snippet_chars))
        self.exclude_current_session = bool(exclude_current_session)
        self.memory_service = MemoryService(
            self.workspace_dir,
            session_store_dir=self.session_store_dir,
        )

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = (turn_context, agent)
        stats = self.memory_service.session_search_stats()
        indexed_sessions = int(stats.get("indexed_sessions") or 0)
        if indexed_sessions <= 0:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no indexed session history found",
            }
        return {
            "status": "ready",
            "available": True,
            "reason": f"{indexed_sessions} indexed session(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        query = _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )
        if not query:
            return None

        excluded_session_id = (
            turn_context.session_id
            if self.exclude_current_session
            else None
        )
        lookup_query = query
        hits: list[dict[str, Any]] = []
        for candidate_query in _session_search_query_candidates(query):
            hits = self.memory_service.search_sessions(
                query=candidate_query,
                limit=max(self.top_k * 3, self.top_k),
                workspace_anchor_dir=str(self.memory_service.anchor_dir),
                exclude_session_id=excluded_session_id,
            )
            if hits:
                lookup_query = candidate_query
                break
        if not hits:
            return None

        selected = hits[: self.top_k]
        lines: list[str] = []
        session_ids: list[str] = []
        query_tokens = _tokenize(lookup_query)
        ranking_raw = 0.0
        for index, hit in enumerate(selected, start=1):
            session_id = _clean_text(hit.get("session_id")) or "session"
            role = _clean_text(hit.get("role")).lower() or "message"
            snippet = _truncate_text(
                hit.get("snippet") or hit.get("content"),
                limit=self.max_snippet_chars,
            )
            session_ids.append(session_id)
            if index == 1:
                ranking_raw = max(
                    _score_text_match(
                        query_text=lookup_query,
                        query_tokens=query_tokens,
                        haystack=_clean_text(hit.get("content")),
                    ),
                    0.5,
                )
            lines.append(f"{index}. [{session_id}/{role}] {snippet}")

        return TurnContextItem(
            source=self.name,
            title="Relevant workspace session history",
            content="\n".join(lines),
            metadata={
                "query": query,
                "lookup_query": lookup_query,
                "returned": len(selected),
                "workspace_anchor_dir": str(self.memory_service.anchor_dir),
                "excluded_session_id": excluded_session_id,
                "session_ids": session_ids,
                "ranking_score": _normalize_text_relevance_score(ranking_raw),
                "ranking_score_raw": round(float(ranking_raw), 6),
                "ranking_basis": "session_search_match",
            },
        )


class SkillCatalogTurnContextProvider:
    """Prepare lightweight relevant-skill hints for one turn."""

    name = "skill_catalog"

    def __init__(
        self,
        *,
        builtin_dir: str | Path,
        workspace_dir: str | Path | None = None,
        plugin_dirs: list[str | Path] | None = None,
        policy_store: Any | None = None,
        top_k: int = 3,
        max_description_chars: int = 180,
    ) -> None:
        self.builtin_dir = Path(builtin_dir).expanduser().resolve()
        self.workspace_dir = (
            Path(workspace_dir).expanduser().resolve()
            if workspace_dir is not None
            else None
        )
        self.plugin_dirs = [
            Path(path).expanduser().resolve()
            for path in (plugin_dirs or [])
        ]
        self.policy_store = policy_store
        self.top_k = max(1, int(top_k))
        self.max_description_chars = max(60, int(max_description_chars))
        self._loader: Any | None = None
        self._cached_entries: list[Any] | None = None

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = (turn_context, agent)
        entries = self._active_entries()
        if not entries:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no active skills discovered",
            }
        return {
            "status": "ready",
            "available": True,
            "reason": f"{len(entries)} skill(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        query = _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )
        if not query:
            return None

        entries = self._active_entries()
        if not entries:
            return None

        ranked = self._rank_entries(entries, query=query)
        if not ranked:
            return None

        selected = ranked[: self.top_k]
        primary_skill_name = (
            _clean_text(getattr(selected[0][0], "name", None))
            if selected
            else ""
        )
        lines: list[str] = [
            (
                f"Primary suggested skill for this request: `{primary_skill_name}`. "
                f"Call `get_skill(skill_name=\"{primary_skill_name}\")` before relying on it."
                if primary_skill_name
                else "If one of these skills is relevant, call `get_skill(skill_name)` before relying on it."
            ),
            "If one of these skills is relevant, call `get_skill(skill_name)` before relying on it.",
            "For clearly skill-shaped requests, `get_skill(...)` should usually come before `bash`, `read_file`, or other exploratory tools.",
            "If the task spans multiple domains, load multiple relevant skills instead of forcing one skill to cover everything.",
            "Do not merely mention a skill name from metadata; load the skill first.",
            "",
        ]
        skill_names: list[str] = []
        for index, (entry, _score) in enumerate(selected, start=1):
            skill_name = _clean_text(getattr(entry, "name", None))
            if skill_name:
                skill_names.append(skill_name)
            description = _truncate_text(
                getattr(entry, "description", ""),
                limit=self.max_description_chars,
            )
            source = _clean_text(
                getattr(getattr(entry, "source", None), "value", None)
                or getattr(entry, "source", None)
            )
            details: list[str] = []
            if source:
                details.append(source)
            if bool(getattr(entry, "always", False)):
                details.append("always")
            label = f" [{', '.join(details)}]" if details else ""
            lines.append(f"{index}. `{skill_name}`{label} {description}".rstrip())

        return TurnContextItem(
            source=self.name,
            title="Relevant skills",
            content="\n".join(lines),
            metadata={
                "query": query,
                "returned": len(selected),
                "skills": skill_names,
                "ranking_score": _normalize_text_relevance_score(selected[0][1]),
                "ranking_score_raw": round(float(selected[0][1]), 6),
                "ranking_basis": "skill_catalog_match",
            },
        )

    def _list_entries(self) -> list[Any]:
        if self._cached_entries is not None:
            return list(self._cached_entries)

        from mini_agent.agent_core.skills.loader import AgentSkillLoader

        self._loader = AgentSkillLoader(
            builtin_dir=self.builtin_dir,
            workspace_dir=self.workspace_dir,
            plugin_dirs=self.plugin_dirs,
        )
        try:
            self._cached_entries = list(self._loader.discover())
        except Exception:
            self._cached_entries = []
        return list(self._cached_entries)

    def _active_entries(self) -> list[Any]:
        from mini_agent.agent_core.skills.policy import (
            WorkspaceSkillPolicyStore,
            compute_active_skill_names,
        )

        entries = self._list_entries()
        if not entries:
            return []
        policy_store = self.policy_store
        if policy_store is None and self.workspace_dir is not None:
            policy_store = WorkspaceSkillPolicyStore(self.workspace_dir)
            self.policy_store = policy_store
        active_names = compute_active_skill_names(
            entries,
            policy_store.load() if policy_store is not None else None,
        )
        return [
            entry
            for entry in entries
            if _clean_text(getattr(entry, "name", None)) in active_names
        ]

    def _rank_entries(
        self,
        entries: list[Any],
        *,
        query: str,
    ) -> list[tuple[Any, float]]:
        query_text = _clean_text(query)
        query_tokens = _tokenize(query_text)
        if not query_text:
            return []

        is_catalog_query = any(
            token in {"skill", "skills", "workflow", "template", "reference"}
            for token in query_tokens
        )
        ranked: list[tuple[Any, float]] = []
        for entry in entries:
            haystack = _skill_match_haystack(entry)
            score = _score_text_match(
                query_text=query_text,
                query_tokens=query_tokens,
                haystack=haystack,
            )
            score += _skill_metadata_match_bonus(entry, query_text)
            if bool(getattr(entry, "always", False)):
                score += 0.25
            if score <= 0.0 and not is_catalog_query:
                continue
            ranked.append((entry, round(score, 6)))

        ranked.sort(
            key=lambda item: (
                -item[1],
                _clean_text(getattr(item[0], "name", None)).lower(),
            ),
        )
        return ranked


class MCPToolCatalogTurnContextProvider:
    """Prepare lightweight MCP capability hints for one turn."""

    name = "mcp_catalog"

    def __init__(
        self,
        *,
        top_k_servers: int = 2,
        top_k_tools: int = 4,
        max_tool_name_chars: int = 48,
    ) -> None:
        self.top_k_servers = max(1, int(top_k_servers))
        self.top_k_tools = max(1, int(top_k_tools))
        self.max_tool_name_chars = max(16, int(max_tool_name_chars))

    async def describe_readiness(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any]:
        _ = (turn_context, agent)
        from mini_agent.tools.mcp.lifecycle import get_registered_connections

        connections = [
            item
            for item in get_registered_connections()
            if getattr(item, "tools", None)
        ]
        if not connections:
            return {
                "status": "unavailable",
                "available": False,
                "reason": "no active MCP connections with exposed tools",
            }
        tool_count = sum(
            len(list(getattr(item, "tools", []) or []))
            for item in connections
        )
        return {
            "status": "ready",
            "available": True,
            "reason": f"{len(connections)} server(s), {tool_count} tool(s) available",
        }

    async def prepare(
        self,
        *,
        turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> TurnContextItem | None:
        from mini_agent.tools.mcp.lifecycle import get_registered_connections

        query = _resolve_followup_query(
            turn_context=turn_context,
            agent=agent,
            short_query_token_threshold=4,
        )
        if not query:
            return None

        connections = [
            item
            for item in get_registered_connections()
            if getattr(item, "tools", None)
        ]
        if not connections:
            return None

        ranked = self._rank_connections(connections, query=query)
        if not ranked:
            return None

        selected = ranked[: self.top_k_servers]
        lines: list[str] = []
        server_names: list[str] = []
        for index, (connection, matched_tools, _score) in enumerate(selected, start=1):
            server_name = _clean_text(getattr(connection, "name", None)) or f"server-{index}"
            server_names.append(server_name)
            connection_type = (
                _clean_text(getattr(connection, "connection_type", None)) or "stdio"
            )
            chosen_tools = matched_tools[: self.top_k_tools]
            if not chosen_tools:
                chosen_tools = list(getattr(connection, "tools", []) or [])[
                    : self.top_k_tools
                ]
            tool_names = [
                _truncate_text(
                    _mcp_tool_label(tool),
                    limit=self.max_tool_name_chars,
                )
                for tool in chosen_tools
                if _mcp_tool_label(tool)
            ]
            tool_label = ", ".join(tool_names) if tool_names else "no exposed tools"
            lines.append(f"{index}. `{server_name}` [{connection_type}] tools: {tool_label}")

        return TurnContextItem(
            source=self.name,
            title="Relevant MCP capabilities",
            content="\n".join(lines),
            metadata={
                "query": query,
                "returned": len(selected),
                "active_server_count": len(connections),
                "servers": server_names,
                "ranking_score": _normalize_text_relevance_score(selected[0][2]),
                "ranking_score_raw": round(float(selected[0][2]), 6),
                "ranking_basis": "mcp_catalog_match",
            },
        )

    def _rank_connections(
        self,
        connections: list[Any],
        *,
        query: str,
    ) -> list[tuple[Any, list[Any], float]]:
        query_text = _clean_text(query)
        query_tokens = _tokenize(query_text)
        if not query_text:
            return []

        is_catalog_query = any(
            token in {
                "mcp",
                "server",
                "servers",
                "tool",
                "tools",
                "resource",
                "resources",
                "capability",
                "capabilities",
            }
            for token in query_tokens
        )
        ranked: list[tuple[Any, list[Any], float]] = []
        for connection in connections:
            header = " ".join(
                [
                    _clean_text(getattr(connection, "name", None)),
                    _clean_text(getattr(connection, "connection_type", None)),
                ]
            )
            server_score = _score_text_match(
                query_text=query_text,
                query_tokens=query_tokens,
                haystack=header,
            )

            matched_tools: list[tuple[Any, float]] = []
            for tool in list(getattr(connection, "tools", []) or []):
                tool_score = _score_text_match(
                    query_text=query_text,
                    query_tokens=query_tokens,
                    haystack=" ".join(
                        [
                            _clean_text(getattr(tool, "name", None)),
                            _clean_text(
                                getattr(tool, "remote_name", None)
                                or getattr(tool, "raw_name", None)
                            ),
                            _clean_text(getattr(tool, "description", None)),
                        ]
                    ),
                )
                if tool_score > 0.0:
                    matched_tools.append((tool, tool_score))

            matched_tools.sort(
                key=lambda item: (
                    -item[1],
                    _clean_text(getattr(item[0], "name", None)).lower(),
                ),
            )
            top_tool_score = matched_tools[0][1] if matched_tools else 0.0
            total_score = round(server_score + (top_tool_score * 1.5), 6)
            if total_score <= 0.0 and not is_catalog_query:
                continue

            ranked.append(
                (
                    connection,
                    [item[0] for item in matched_tools],
                    total_score,
                )
            )

        ranked.sort(
            key=lambda item: (
                -item[2],
                _clean_text(getattr(item[0], "name", None)).lower(),
            ),
        )
        return ranked


__all__ = [
    "ConsolidatedMemoryTurnContextProvider",
    "MCPToolCatalogTurnContextProvider",
    "RuntimeRecoveryTurnContextProvider",
    "RuntimeTaskMemoryTurnContextProvider",
    "SessionSearchTurnContextProvider",
    "SkillCatalogTurnContextProvider",
    "UserProfileTurnContextProvider",
    "WorkspaceMemoryContextProvider",
]
