"""Operator-facing diagnostics for Mini-Agent memory layers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mini_agent.memory.knowledge_base_grounding import format_knowledge_base_grounding_lines
from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime
from mini_agent.memory.service import MemoryService


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _truncate_text(value: Any, *, limit: int) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 3)]}..."


def format_global_profile_details(
    profile: dict[str, Any] | None,
    *,
    query: str | None = None,
    matches: list[dict[str, Any]] | None = None,
    limit: int = 20,
) -> list[str]:
    payload = dict(profile or {})
    normalized_query = _clean_text(query)
    lines = ["Global Profile Memory"]
    lines.append(f"User file: {_clean_text(payload.get('user_file')) or 'n/a'}")
    lines.append(f"Fact count: {int(payload.get('fact_count') or 0)}")

    if normalized_query:
        normalized_matches = [dict(item) for item in (matches or []) if isinstance(item, dict)]
        lines.append(f"Query: {normalized_query}")
        lines.append(f"Matches: {len(normalized_matches)}")
        if normalized_matches:
            lines.append("")
            lines.append("Profile Matches")
            for index, item in enumerate(normalized_matches[: max(1, int(limit))], start=1):
                fact = _clean_text(item.get("fact"))
                score = float(item.get("score") or 0.0)
                fact_index = int(item.get("index") or 0) + 1
                lines.append(f"- {index}. [#{fact_index}] (score={score:.3f}) {fact}")
        else:
            lines.append("No matching profile facts found.")
        return lines

    facts = [
        _clean_text(item)
        for item in (payload.get("facts") or [])
        if _clean_text(item)
    ]
    if facts:
        lines.append("")
        lines.append("Facts")
        bounded = max(1, int(limit))
        for index, fact in enumerate(facts[:bounded], start=1):
            lines.append(f"- {index}. {fact}")
        remaining = len(facts) - bounded
        if remaining > 0:
            lines.append(f"- ... {remaining} more fact(s)")
    else:
        lines.append("No global profile facts stored.")
    return lines


def format_workspace_note_details(
    *,
    workspace_dir: str | Path,
    memory_root: str | Path,
    long_term_file: str | Path,
    daily_dir: str | Path,
    categories: list[str] | None = None,
    notes: list[dict[str, Any]] | None = None,
    query: str | None = None,
    total: int | None = None,
    limit: int = 10,
) -> list[str]:
    normalized_query = _clean_text(query)
    normalized_notes = [dict(item) for item in (notes or []) if isinstance(item, dict)]
    lines = ["Workspace Durable Notes"]
    lines.append(f"Workspace: {_clean_text(workspace_dir)}")
    lines.append(f"Memory root: {_clean_text(memory_root)}")
    lines.append(f"Long-term file: {_clean_text(long_term_file)}")
    lines.append(f"Daily dir: {_clean_text(daily_dir)}")
    if categories:
        values = [_clean_text(item) for item in categories if _clean_text(item)]
        if values:
            lines.append(f"Categories: {', '.join(values)}")

    if normalized_query:
        lines.append(f"Query: {normalized_query}")
        lines.append(f"Matches: {int(total or len(normalized_notes))}")
        if normalized_notes:
            lines.append("")
            lines.append("Note Matches")
            for index, item in enumerate(normalized_notes[: max(1, int(limit))], start=1):
                score = item.get("score")
                score_text = f"(score={float(score):.3f}) " if score is not None else ""
                lines.append(
                    f"- {index}. {score_text}[{_clean_text(item.get('timestamp'))}] "
                    f"[{_clean_text(item.get('category'))}] "
                    f"[{_clean_text(item.get('path'))}] "
                    f"{_truncate_text(item.get('content'), limit=140)}"
                )
        else:
            lines.append("No matching workspace notes found.")
        return lines

    lines.append(f"Recent notes: {int(total or len(normalized_notes))}")
    if normalized_notes:
        lines.append("")
        lines.append("Recent Workspace Notes")
        for index, item in enumerate(normalized_notes[: max(1, int(limit))], start=1):
            lines.append(
                f"- {index}. [{_clean_text(item.get('timestamp'))}] "
                f"[{_clean_text(item.get('category'))}] "
                f"[{_clean_text(item.get('path'))}] "
                f"{_truncate_text(item.get('content'), limit=140)}"
            )
    else:
        lines.append("No workspace durable notes stored.")
    return lines


def format_workspace_daily_details(
    *,
    workspace_dir: str | Path,
    day: str,
    path: str | Path,
    notes: list[dict[str, Any]] | None = None,
    note_count: int = 0,
    limit: int = 20,
) -> list[str]:
    normalized_notes = [dict(item) for item in (notes or []) if isinstance(item, dict)]
    lines = ["Workspace Daily Memory"]
    lines.append(f"Workspace: {_clean_text(workspace_dir)}")
    lines.append(f"Day: {_clean_text(day)}")
    lines.append(f"Path: {_clean_text(path)}")
    lines.append(f"Note count: {int(note_count)}")
    if normalized_notes:
        lines.append("")
        lines.append("Daily Notes")
        for index, item in enumerate(normalized_notes[: max(1, int(limit))], start=1):
            lines.append(
                f"- {index}. [{_clean_text(item.get('timestamp'))}] "
                f"[{_clean_text(item.get('category'))}] "
                f"{_truncate_text(item.get('content'), limit=160)}"
            )
    else:
        lines.append("No notes found in this daily memory file.")
    return lines


def format_consolidated_memory_details(
    snapshot: dict[str, Any] | None,
    *,
    refresh_status: dict[str, Any] | None = None,
    limit: int = 20,
) -> list[str]:
    payload = dict(snapshot or {})
    status = dict(refresh_status or {})
    items = [
        _clean_text(item)
        for item in (payload.get("items") or [])
        if _clean_text(item)
    ]
    lines = ["Consolidated Memory"]
    lines.append(f"Memory file: {_clean_text(payload.get('memory_file')) or 'n/a'}")
    if status:
        lines.append(
            "State: "
            + ("needs refresh" if bool(status.get("needs_refresh")) else "fresh")
            + f" | reason: {_clean_text(status.get('reason')) or 'unknown'}"
        )
    if _clean_text(payload.get("memory_last_updated_utc")):
        lines.append(f"Last updated: {_clean_text(payload.get('memory_last_updated_utc'))}")
    if _clean_text(payload.get("memory_file_mtime_utc")):
        lines.append(f"File mtime: {_clean_text(payload.get('memory_file_mtime_utc'))}")
    lines.append(f"Item count: {len(items)}")
    if items:
        lines.append("")
        lines.append("Items")
        bounded = max(1, int(limit))
        for index, item in enumerate(items[:bounded], start=1):
            lines.append(f"- {index}. {_truncate_text(item, limit=180)}")
        remaining = len(items) - bounded
        if remaining > 0:
            lines.append(f"- ... {remaining} more item(s)")
    else:
        lines.append("No consolidated memory items found.")
    return lines


def format_consolidated_memory_search_details(
    payload: dict[str, Any] | None,
    *,
    refresh_status: dict[str, Any] | None = None,
    limit: int = 10,
) -> list[str]:
    search = dict(payload or {})
    status = dict(refresh_status or {})
    hits = [dict(item) for item in (search.get("hits") or []) if isinstance(item, dict)]
    lines = ["Consolidated Memory Search"]
    lines.append(f"Query: {_clean_text(search.get('query')) or 'n/a'}")
    lines.append(f"Memory file: {_clean_text(search.get('memory_file')) or 'n/a'}")
    if status:
        lines.append(
            "State: "
            + ("needs refresh" if bool(status.get("needs_refresh")) else "fresh")
            + f" | reason: {_clean_text(status.get('reason')) or 'unknown'}"
        )
    lines.append(
        f"Returned: {int(search.get('returned') or 0)}"
        f" / {int(search.get('item_count') or 0)} item(s)"
    )
    if hits:
        lines.append("")
        lines.append("Hits")
        bounded = max(1, int(limit))
        for index, item in enumerate(hits[:bounded], start=1):
            lines.append(
                f"- {index}. (score={float(item.get('score') or 0.0):.3f}"
                f" | drift={_clean_text(item.get('drift_status')) or 'unknown'}) "
                f"{_truncate_text(item.get('content'), limit=180)}"
            )
            reason = _clean_text(item.get("drift_reason"))
            if reason:
                lines.append(f"  drift reason: {reason}")
        remaining = len(hits) - bounded
        if remaining > 0:
            lines.append(f"- ... {remaining} more hit(s)")
    else:
        lines.append("No consolidated memory matches found.")
    return lines


def build_memory_overview_payload(
    *,
    memory: MemoryService,
    diagnostics: dict[str, Any] | None = None,
    exclude_session_id: str | None = None,
    profile_limit: int = 5,
    note_limit: int = 5,
    consolidated_limit: int = 5,
) -> dict[str, Any]:
    summary = memory.summary()
    profile = memory.profile()
    facts = [
        _clean_text(item)
        for item in (profile.get("facts") or [])
        if _clean_text(item)
    ][: max(1, int(profile_limit))]
    recent_notes = [
        memory.note_to_dict(note)
        for note in memory.search_notes(query="", limit=max(1, int(note_limit)))
    ]
    refresh_status = memory.consolidated_refresh_status(exclude_session_id=exclude_session_id)
    consolidated_snapshot = memory.consolidated_snapshot()
    consolidated_snapshot["memory_file"] = refresh_status.get("memory_file")
    consolidated_items = [
        _clean_text(item)
        for item in (consolidated_snapshot.get("items") or [])
        if _clean_text(item)
    ][: max(1, int(consolidated_limit))]
    return {
        "diagnostics": dict(diagnostics or {}),
        "workspace_summary": {
            "workspace_dir": summary.workspace_dir,
            "memory_root": summary.memory_root,
            "long_term_file": summary.long_term_file,
            "daily_dir": summary.daily_dir,
            "daily_files": list(summary.daily_files),
            "notes_count": int(summary.notes_count),
            "categories": list(summary.categories),
        },
        "profile": {
            "user_file": profile.get("user_file"),
            "fact_count": int(profile.get("fact_count") or 0),
            "facts": facts,
        },
        "recent_notes": recent_notes,
        "consolidated": {
            "refresh_status": dict(refresh_status or {}),
            "snapshot": consolidated_snapshot,
            "items": consolidated_items,
        },
    }


def format_memory_overview_details(
    payload: dict[str, Any] | None,
    *,
    runtime_preview_limit: int = 3,
    note_preview_limit: int = 5,
    consolidated_preview_limit: int = 5,
) -> list[str]:
    overview = dict(payload or {})
    diagnostics = overview.get("diagnostics") if isinstance(overview.get("diagnostics"), dict) else {}
    workspace_summary = (
        overview.get("workspace_summary")
        if isinstance(overview.get("workspace_summary"), dict)
        else {}
    )
    profile = overview.get("profile") if isinstance(overview.get("profile"), dict) else {}
    recent_notes = [dict(item) for item in (overview.get("recent_notes") or []) if isinstance(item, dict)]
    consolidated = overview.get("consolidated") if isinstance(overview.get("consolidated"), dict) else {}
    refresh_status = (
        consolidated.get("refresh_status")
        if isinstance(consolidated.get("refresh_status"), dict)
        else {}
    )
    snapshot = consolidated.get("snapshot") if isinstance(consolidated.get("snapshot"), dict) else {}
    consolidated_items = [
        _clean_text(item)
        for item in (consolidated.get("items") or [])
        if _clean_text(item)
    ]
    runtime = diagnostics.get("runtime_task_memory") if isinstance(diagnostics.get("runtime_task_memory"), dict) else {}
    session_id = _clean_text(diagnostics.get("session_id"))
    workspace_anchor_dir = _clean_text(diagnostics.get("workspace_anchor_dir"))
    prepared_sources = diagnostics.get("prepared_context_sources") if isinstance(diagnostics.get("prepared_context_sources"), list) else []

    lines = ["Memory Overview"]
    lines.append(f"Workspace: {_clean_text(workspace_summary.get('workspace_dir')) or _clean_text(diagnostics.get('workspace_dir')) or 'n/a'}")
    lines.append(f"Memory root: {_clean_text(workspace_summary.get('memory_root')) or 'n/a'}")
    lines.append(f"Long-term file: {_clean_text(workspace_summary.get('long_term_file')) or 'n/a'}")
    lines.append(f"Daily dir: {_clean_text(workspace_summary.get('daily_dir')) or 'n/a'}")

    categories = [_clean_text(item) for item in (workspace_summary.get("categories") or []) if _clean_text(item)]
    if categories:
        lines.append(f"Categories: {', '.join(categories)}")

    lines.append("")
    lines.append("Session Context")
    lines.append(f"- session id: {session_id or 'n/a'}")
    lines.append(f"- workspace anchor: {workspace_anchor_dir or 'n/a'}")
    lines.append(
        f"- session namespace: {_clean_text(runtime.get('session_namespace')) or 'n/a'}"
        f" | shared namespace: {_clean_text(runtime.get('workspace_shared_namespace')) or 'n/a'}"
    )
    if prepared_sources:
        values = [_clean_text(item) for item in prepared_sources if _clean_text(item)]
        if values:
            lines.append(f"- prepared sources: {', '.join(values)}")

    lines.append("")
    lines.append("Runtime Task Memory")
    lines.append(
        f"- session entries: {int(runtime.get('session_count') or 0)}"
        f" | shared entries: {int(runtime.get('shared_count') or 0)}"
    )
    session_preview = runtime.get("session_preview") if isinstance(runtime.get("session_preview"), list) else []
    shared_preview = runtime.get("shared_preview") if isinstance(runtime.get("shared_preview"), list) else []
    if session_preview:
        lines.append("- session preview:")
        for line in format_runtime_memory_preview_lines(session_preview, limit=runtime_preview_limit):
            lines.append(f"  {line}")
    if shared_preview:
        lines.append("- shared preview:")
        for line in format_runtime_memory_preview_lines(shared_preview, limit=runtime_preview_limit):
            lines.append(f"  {line}")

    lines.append("")
    lines.append("Durable Memory")
    lines.append(
        f"- global profile facts: {int(profile.get('fact_count') or diagnostics.get('global_profile_fact_count') or 0)}"
        f" | workspace notes: {int(workspace_summary.get('notes_count') or diagnostics.get('workspace_note_count') or 0)}"
        f" | daily files: {len(workspace_summary.get('daily_files') or []) or int(diagnostics.get('workspace_daily_file_count') or 0)}"
    )
    profile_facts = [_clean_text(item) for item in (profile.get("facts") or []) if _clean_text(item)]
    if profile_facts:
        lines.append("- profile preview:")
        for index, fact in enumerate(profile_facts[: max(1, int(note_preview_limit))], start=1):
            lines.append(f"  - {index}. {fact}")
    if recent_notes:
        lines.append("- recent notes:")
        for index, item in enumerate(recent_notes[: max(1, int(note_preview_limit))], start=1):
            lines.append(
                "  - "
                + f"{index}. [{_clean_text(item.get('timestamp'))}] "
                + f"[{_clean_text(item.get('category'))}] "
                + _truncate_text(item.get("content"), limit=140)
            )

    lines.append("")
    lines.append("Consolidated Memory")
    lines.append(
        f"- state: {'needs refresh' if bool(refresh_status.get('needs_refresh')) else 'fresh'}"
        f" | items: {int(refresh_status.get('consolidated_item_count') or len(snapshot.get('items') or []))}"
        f" | pending sessions: {int(refresh_status.get('pending_session_count') or 0)}"
    )
    if _clean_text(refresh_status.get("reason")):
        lines.append(f"- reason: {_clean_text(refresh_status.get('reason'))}")
    if _clean_text(snapshot.get("memory_last_updated_utc")):
        lines.append(f"- last updated: {_clean_text(snapshot.get('memory_last_updated_utc'))}")
    if consolidated_items:
        lines.append("- consolidated preview:")
        for index, item in enumerate(consolidated_items[: max(1, int(consolidated_preview_limit))], start=1):
            lines.append(f"  - {index}. {_truncate_text(item, limit=160)}")

    last_memory_automation = diagnostics.get("last_memory_automation")
    if isinstance(last_memory_automation, dict) and last_memory_automation:
        lines.append("")
        lines.append("Last Durable Writeback")
        lines.append(
            f"- skipped_reason: {_clean_text(last_memory_automation.get('skipped_reason')) or 'none'}"
            f" | actions: {int(last_memory_automation.get('action_count') or 0)}"
        )

    last_runtime_task_memory = diagnostics.get("last_runtime_task_memory")
    if isinstance(last_runtime_task_memory, dict) and last_runtime_task_memory:
        lines.append("")
        lines.append("Last Runtime Task Writeback")
        lines.append(
            f"- stored: {'yes' if bool(last_runtime_task_memory.get('stored')) else 'no'}"
            f" | duplicate: {'yes' if bool(last_runtime_task_memory.get('duplicate')) else 'no'}"
            f" | shared candidate: {'yes' if bool(last_runtime_task_memory.get('workspace_shared_candidate')) else 'no'}"
        )
        if _clean_text(last_runtime_task_memory.get("skipped_reason")):
            lines.append(f"- skipped_reason: {_clean_text(last_runtime_task_memory.get('skipped_reason'))}")

    return lines


def format_memory_export_details(
    payload: dict[str, Any] | None,
    *,
    workspace_dir: str | Path,
    memory_root: str | Path,
    long_term_file: str | Path,
    daily_dir: str | Path,
) -> list[str]:
    export = dict(payload or {})
    content = str(export.get("content") or "").strip()
    lines = ["Memory Export"]
    lines.append(f"Workspace: {_clean_text(workspace_dir)}")
    lines.append(f"Memory root: {_clean_text(memory_root)}")
    lines.append(f"Long-term file: {_clean_text(long_term_file)}")
    lines.append(f"Daily dir: {_clean_text(daily_dir)}")
    lines.append(f"Format: {_clean_text(export.get('format')) or 'jsonl'}")
    lines.append(f"Item count: {int(export.get('item_count') or 0)}")
    lines.append("")
    lines.append("Content")
    lines.append(content or "(empty)")
    return lines


def build_memory_diagnostics(
    *,
    workspace_dir: str | Path,
    session_id: str | None = None,
    last_prepared_context: dict[str, Any] | None = None,
    last_memory_automation: dict[str, Any] | None = None,
    last_runtime_task_memory: dict[str, Any] | None = None,
    runtime_state_root: str | Path | None = None,
    preview_limit: int = 5,
) -> dict[str, Any]:
    resolved_workspace = Path(workspace_dir).expanduser().resolve()
    normalized_session_id = _clean_text(session_id) or None
    memory = MemoryService(resolved_workspace)
    runtime = WorkspaceMemoriaRuntime(resolved_workspace, state_root=runtime_state_root)

    summary = memory.summary()
    profile = memory.profile()
    consolidated = memory.consolidated_refresh_status(exclude_session_id=normalized_session_id)

    session_preview: list[dict[str, Any]] = []
    session_count = 0
    session_namespace = None
    if normalized_session_id:
        session_namespace = runtime.session_namespace(normalized_session_id)
        session_preview = runtime.list_namespace_entries(session_namespace, limit=preview_limit)
        session_count = sum(int(value or 0) for value in runtime.namespace_stats(session_namespace).values())

    shared_namespace = runtime.shared_namespace()
    shared_preview = runtime.list_namespace_entries(shared_namespace, limit=preview_limit)
    shared_count = sum(int(value or 0) for value in runtime.namespace_stats(shared_namespace).values())

    prepared_sources = []
    if isinstance(last_prepared_context, dict):
        raw_sources = last_prepared_context.get("sources")
        if isinstance(raw_sources, list):
            prepared_sources = [_clean_text(item).lower() for item in raw_sources if _clean_text(item)]

    return {
        "session_id": normalized_session_id,
        "workspace_dir": str(resolved_workspace),
        "workspace_anchor_dir": str(memory.anchor_dir),
        "global_profile_fact_count": int(profile.get("fact_count") or 0),
        "workspace_note_count": int(summary.notes_count),
        "workspace_daily_file_count": len(summary.daily_files),
        "prepared_context_sources": prepared_sources,
        "consolidated": {
            "needs_refresh": bool(consolidated.get("needs_refresh")),
            "reason": _clean_text(consolidated.get("reason")) or "unknown",
            "item_count": int(consolidated.get("consolidated_item_count") or 0),
            "pending_session_count": int(consolidated.get("pending_session_count") or 0),
            "memory_last_updated_utc": consolidated.get("memory_last_updated_utc"),
            "latest_workspace_session_updated_utc": consolidated.get("latest_workspace_session_updated_utc"),
        },
        "runtime_task_memory": {
            "session_namespace": session_namespace,
            "session_count": session_count,
            "session_preview": session_preview,
            "workspace_shared_namespace": shared_namespace,
            "shared_count": shared_count,
            "shared_preview": shared_preview,
        },
        "last_memory_automation": dict(last_memory_automation or {}),
        "last_runtime_task_memory": dict(last_runtime_task_memory or {}),
    }


def runtime_session_preview_entries(
    payload: dict[str, Any] | None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    diagnostics = payload if isinstance(payload, dict) else {}
    runtime = diagnostics.get("runtime_task_memory") if isinstance(diagnostics.get("runtime_task_memory"), dict) else {}
    raw_entries = runtime.get("session_preview") if isinstance(runtime.get("session_preview"), list) else []
    entries = [dict(item) for item in raw_entries if isinstance(item, dict)]
    if limit is None:
        return entries
    return entries[: max(0, int(limit))]


def runtime_shared_preview_entries(
    payload: dict[str, Any] | None,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    diagnostics = payload if isinstance(payload, dict) else {}
    runtime = diagnostics.get("runtime_task_memory") if isinstance(diagnostics.get("runtime_task_memory"), dict) else {}
    raw_entries = runtime.get("shared_preview") if isinstance(runtime.get("shared_preview"), list) else []
    entries = [dict(item) for item in raw_entries if isinstance(item, dict)]
    if limit is None:
        return entries
    return entries[: max(0, int(limit))]


def _runtime_entry_metadata(entry: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(entry, dict):
        return {}
    metadata = entry.get("metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _runtime_entry_badge_suffix(entry: dict[str, Any] | None) -> str:
    metadata = _runtime_entry_metadata(entry)
    badges: list[str] = []
    if bool(metadata.get("knowledge_base_grounded")):
        badges.append("KB")
    if bool(metadata.get("workspace_shared_candidate")):
        badges.append("shared-candidate")
    if not badges:
        return ""
    return f" [{' | '.join(badges)}]"


def format_runtime_memory_preview_lines(
    entries: list[dict[str, Any]] | None,
    *,
    limit: int = 5,
    include_latest_hint: bool = False,
    latest_hint_label: str = "entry",
) -> list[str]:
    normalized_entries = [dict(item) for item in (entries or []) if isinstance(item, dict)]
    lines: list[str] = []
    for index, item in enumerate(normalized_entries[: max(0, int(limit))], start=1):
        lines.append(
            f"- {index}. [{_clean_text(item.get('engram_id'))}]"
            f"{_runtime_entry_badge_suffix(item)} "
            f"{_truncate_text(item.get('content'), limit=120)}"
        )
        metadata = _runtime_entry_metadata(item)
        if bool(metadata.get("knowledge_base_grounded")):
            kb_id = _clean_text(metadata.get("knowledge_base_id")) or "default"
            hits = max(0, int(metadata.get("knowledge_base_hits") or 0))
            query = _clean_text(metadata.get("knowledge_base_query"))
            refs = [
                _clean_text(value)
                for value in (metadata.get("knowledge_base_refs") or [])
                if _clean_text(value)
            ]
            detail = f"  kb: {kb_id} | hits: {hits}"
            if query:
                detail += f" | query: {_truncate_text(query, limit=72)}"
            lines.append(detail)
            if refs:
                lines.append(f"  refs: {'; '.join(refs[:2])}")
    if include_latest_hint and normalized_entries:
        lines.append(f"- latest -> first {latest_hint_label} above")
    return lines


def format_runtime_memory_entry_details(entry: dict[str, Any] | None) -> list[str]:
    item = dict(entry or {})
    metadata = _runtime_entry_metadata(item)
    lines = [
        f"Engram: {_clean_text(item.get('engram_id'))}",
        f"Layer: {_clean_text(item.get('layer')) or 'working'}",
        f"Importance: {item.get('importance')}",
        f"Updated: {_clean_text(item.get('updated_at')) or 'n/a'}",
        f"Content: {_clean_text(item.get('content'))}",
    ]
    if bool(metadata.get("workspace_shared_candidate")):
        lines.append(
            "Shared Candidate: yes"
            + (
                f" | reason: {_clean_text(metadata.get('workspace_shared_candidate_reason'))}"
                if _clean_text(metadata.get("workspace_shared_candidate_reason"))
                else ""
            )
        )
        candidate_text = _clean_text(metadata.get("workspace_shared_candidate_text"))
        if candidate_text:
            lines.append(f"Shared Candidate Text: {candidate_text}")
    lines.extend(
        format_knowledge_base_grounding_lines(
            {
                "used": bool(metadata.get("knowledge_base_used") or metadata.get("knowledge_base_grounded")),
                "grounded": bool(metadata.get("knowledge_base_grounded")),
                "query": metadata.get("knowledge_base_query"),
                "knowledge_base_id": metadata.get("knowledge_base_id"),
                "hits": metadata.get("knowledge_base_hits"),
                "refs": metadata.get("knowledge_base_refs"),
            }
        )
    )
    extra_metadata = dict(metadata)
    for key in (
        "knowledge_base_used",
        "knowledge_base_grounded",
        "knowledge_base_query",
        "knowledge_base_id",
        "knowledge_base_hits",
        "knowledge_base_refs",
        "workspace_shared_candidate",
        "workspace_shared_candidate_reason",
        "workspace_shared_candidate_text",
    ):
        extra_metadata.pop(key, None)
    if extra_metadata:
        lines.append(f"Metadata: {json.dumps(extra_metadata, ensure_ascii=False, sort_keys=True)}")
    return lines


def format_runtime_session_selector_help(
    payload: dict[str, Any] | None,
    *,
    usage_command: str,
    limit: int = 5,
) -> str:
    entries = runtime_session_preview_entries(payload, limit=limit)
    if not entries:
        return "\n".join(
            [
                "No session runtime memory entries are available.",
                "Run /memory runtime after the session stores runtime task memory.",
                f"Usage: {usage_command}",
            ]
        ).strip()

    lines = [
        "Session runtime memory selectors:",
    ]
    lines.extend(
        format_runtime_memory_preview_lines(
            entries,
            limit=limit,
            include_latest_hint=True,
            latest_hint_label="session preview entry",
        )
    )
    lines.append(f"Usage: {usage_command}")
    return "\n".join(lines).strip()


def format_runtime_shared_selector_help(
    payload: dict[str, Any] | None,
    *,
    usage_command: str,
    limit: int = 5,
) -> str:
    entries = runtime_shared_preview_entries(payload, limit=limit)
    if not entries:
        return "\n".join(
            [
                "No workspace-shared runtime memory entries are available.",
                "Use /memory promote shared <selector> after a session entry becomes a shared candidate.",
                f"Usage: {usage_command}",
            ]
        ).strip()

    lines = [
        "Workspace-shared runtime memory selectors:",
    ]
    lines.extend(
        format_runtime_memory_preview_lines(
            entries,
            limit=limit,
            include_latest_hint=True,
            latest_hint_label="shared preview entry",
        )
    )
    lines.append(f"Usage: {usage_command}")
    return "\n".join(lines).strip()


def resolve_runtime_session_engram_selector(
    payload: dict[str, Any] | None,
    selector: str | None,
) -> str | None:
    normalized = _clean_text(selector)
    if not normalized:
        return None
    entries = runtime_session_preview_entries(payload)
    lowered = normalized.lower()
    if lowered == "latest":
        if not entries:
            return None
        return _clean_text(entries[0].get("engram_id")) or None
    if normalized.isdigit():
        index = int(normalized)
        if index <= 0 or index > len(entries):
            return None
        return _clean_text(entries[index - 1].get("engram_id")) or None
    for item in entries:
        if _clean_text(item.get("engram_id")) == normalized:
            return normalized
    return normalized


def resolve_runtime_shared_engram_selector(
    payload: dict[str, Any] | None,
    selector: str | None,
) -> str | None:
    normalized = _clean_text(selector)
    if not normalized:
        return None
    entries = runtime_shared_preview_entries(payload)
    lowered = normalized.lower()
    if lowered == "latest":
        if not entries:
            return None
        return _clean_text(entries[0].get("engram_id")) or None
    if normalized.isdigit():
        index = int(normalized)
        if index <= 0 or index > len(entries):
            return None
        return _clean_text(entries[index - 1].get("engram_id")) or None
    for item in entries:
        if _clean_text(item.get("engram_id")) == normalized:
            return normalized
    return normalized


def memory_diagnostics_summary_line(payload: dict[str, Any] | None) -> str:
    diagnostics = payload if isinstance(payload, dict) else {}
    consolidated = diagnostics.get("consolidated") if isinstance(diagnostics.get("consolidated"), dict) else {}
    runtime = diagnostics.get("runtime_task_memory") if isinstance(diagnostics.get("runtime_task_memory"), dict) else {}
    session_count = int(runtime.get("session_count") or 0)
    shared_count = int(runtime.get("shared_count") or 0)
    consolidated_state = "stale" if bool(consolidated.get("needs_refresh")) else "fresh"
    profile_count = int(diagnostics.get("global_profile_fact_count") or 0)
    return f"cons {consolidated_state} | rtm {session_count}+{shared_count} | profile {profile_count}"


def format_memory_diagnostics(
    payload: dict[str, Any] | None,
    *,
    include_header: bool = True,
    detail_mode: str = "full",
) -> str:
    diagnostics = payload if isinstance(payload, dict) else {}
    lines: list[str] = []
    if include_header:
        lines.append("Memory Diagnostics")
    lines.append(f"Summary: {memory_diagnostics_summary_line(diagnostics)}")
    lines.append(f"Workspace: {_clean_text(diagnostics.get('workspace_anchor_dir')) or _clean_text(diagnostics.get('workspace_dir'))}")

    consolidated = diagnostics.get("consolidated") if isinstance(diagnostics.get("consolidated"), dict) else {}
    lines.append("")
    lines.append("Consolidated")
    lines.append(
        f"- state: {'needs refresh' if bool(consolidated.get('needs_refresh')) else 'fresh'}"
        f" | items={int(consolidated.get('item_count') or 0)}"
        f" | pending_sessions={int(consolidated.get('pending_session_count') or 0)}"
    )
    if _clean_text(consolidated.get("reason")):
        lines.append(f"- reason: {_clean_text(consolidated.get('reason'))}")

    runtime = diagnostics.get("runtime_task_memory") if isinstance(diagnostics.get("runtime_task_memory"), dict) else {}
    lines.append("")
    lines.append("Runtime Task Memory")
    lines.append(
        f"- session: {int(runtime.get('session_count') or 0)}"
        f" | shared: {int(runtime.get('shared_count') or 0)}"
    )

    if detail_mode == "full":
        session_preview = runtime.get("session_preview") if isinstance(runtime.get("session_preview"), list) else []
        shared_preview = runtime.get("shared_preview") if isinstance(runtime.get("shared_preview"), list) else []
        if session_preview:
            lines.append("- session preview:")
            for line in format_runtime_memory_preview_lines(session_preview, limit=5):
                lines.append("  " + line)
        if shared_preview:
            lines.append("- shared preview:")
            for line in format_runtime_memory_preview_lines(shared_preview, limit=5):
                lines.append("  " + line)

    lines.append("")
    lines.append("Durable Memory")
    lines.append(
        f"- global profile facts: {int(diagnostics.get('global_profile_fact_count') or 0)}"
        f" | workspace notes: {int(diagnostics.get('workspace_note_count') or 0)}"
        f" | daily files: {int(diagnostics.get('workspace_daily_file_count') or 0)}"
    )

    prepared_sources = diagnostics.get("prepared_context_sources")
    if isinstance(prepared_sources, list) and prepared_sources:
        lines.append(f"- prepared sources: {', '.join(_clean_text(item) for item in prepared_sources if _clean_text(item))}")

    last_memory_automation = diagnostics.get("last_memory_automation")
    if isinstance(last_memory_automation, dict) and last_memory_automation:
        lines.append("")
        lines.append("Last Durable Writeback")
        lines.append(
            f"- skipped_reason: {_clean_text(last_memory_automation.get('skipped_reason')) or 'none'}"
            f" | actions={int(last_memory_automation.get('action_count') or 0)}"
        )

    last_runtime_task_memory = diagnostics.get("last_runtime_task_memory")
    if isinstance(last_runtime_task_memory, dict) and last_runtime_task_memory:
        lines.append("")
        lines.append("Last Runtime Task Writeback")
        lines.append(
            f"- stored: {'yes' if bool(last_runtime_task_memory.get('stored')) else 'no'}"
            f" | duplicate: {'yes' if bool(last_runtime_task_memory.get('duplicate')) else 'no'}"
            f" | skipped_reason: {_clean_text(last_runtime_task_memory.get('skipped_reason')) or 'none'}"
        )
        lines.append(
            f"- workspace_shared_candidate: {'yes' if bool(last_runtime_task_memory.get('workspace_shared_candidate')) else 'no'}"
            f" | reason: {_clean_text(last_runtime_task_memory.get('workspace_shared_candidate_reason')) or 'eligible'}"
        )
        if bool(last_runtime_task_memory.get("knowledge_base_grounded")):
            lines.extend(
                format_knowledge_base_grounding_lines(
                    {
                        "used": True,
                        "grounded": bool(last_runtime_task_memory.get("knowledge_base_grounded")),
                        "query": last_runtime_task_memory.get("knowledge_base_query"),
                        "knowledge_base_id": last_runtime_task_memory.get("knowledge_base_id"),
                        "hits": last_runtime_task_memory.get("knowledge_base_hits"),
                        "refs": last_runtime_task_memory.get("knowledge_base_refs"),
                    }
                )
            )
        if detail_mode == "full" and _clean_text(last_runtime_task_memory.get("content")):
            lines.append(f"- content: {_truncate_text(last_runtime_task_memory.get('content'), limit=140)}")
        if detail_mode == "full" and _clean_text(last_runtime_task_memory.get("workspace_shared_candidate_text")):
            lines.append(
                "- shared candidate: "
                + _truncate_text(last_runtime_task_memory.get("workspace_shared_candidate_text"), limit=140)
            )

    return "\n".join(line.rstrip() for line in lines if line is not None).strip()


__all__ = [
    "build_memory_overview_payload",
    "build_memory_diagnostics",
    "format_consolidated_memory_details",
    "format_consolidated_memory_search_details",
    "format_global_profile_details",
    "format_memory_diagnostics",
    "format_memory_export_details",
    "format_memory_overview_details",
    "format_runtime_memory_entry_details",
    "format_runtime_memory_preview_lines",
    "format_runtime_shared_selector_help",
    "format_runtime_session_selector_help",
    "format_workspace_daily_details",
    "format_workspace_note_details",
    "memory_diagnostics_summary_line",
    "resolve_runtime_shared_engram_selector",
    "resolve_runtime_session_engram_selector",
    "runtime_shared_preview_entries",
    "runtime_session_preview_entries",
]
