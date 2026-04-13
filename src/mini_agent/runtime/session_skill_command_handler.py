"""Session skill command routing extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Sequence

from fastapi import HTTPException

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

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


SUPPORTED_SKILL_ACTIONS = frozenset(
    {
        "list",
        "show",
        "search",
        "refresh",
        "active",
        "mode",
        "enable",
        "disable",
        "reset",
        "install",
        "uninstall",
        "rollback",
    }
)

MUTATING_SKILL_ACTIONS = frozenset(
    {
        "refresh",
        "mode",
        "enable",
        "disable",
        "reset",
        "install",
        "uninstall",
        "rollback",
    }
)


@dataclass(frozen=True, slots=True)
class RuntimeSessionSkillCommand:
    action: str
    skill_name: str | None = None
    path: str | None = None
    query: str | None = None
    mode: str | None = None


@dataclass(slots=True)
class RuntimeSessionSkillMutationPlan:
    action: str
    loader: Any
    updated_policy: Any
    reload_reason: str
    base_summary: str
    base_details: str
    command_name: str


@dataclass(slots=True)
class RuntimeSessionSkillPrepared:
    status: str
    result: dict[str, Any] | None = None
    mutation: RuntimeSessionSkillMutationPlan | None = None


@dataclass(slots=True)
class RuntimeSessionSkillCommandHandler:
    def validate_action(self, action: str) -> None:
        if action not in SUPPORTED_SKILL_ACTIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported session skill action: {action}")

    @staticmethod
    def is_mutating_action(action: str) -> bool:
        return action in MUTATING_SKILL_ACTIONS

    def prepare(
        self,
        session: "MainAgentSessionState",
        command: RuntimeSessionSkillCommand,
    ) -> RuntimeSessionSkillPrepared:
        action = command.action
        try:
            loader = resolve_skill_catalog_loader(
                workspace_dir=session.workspace_dir,
                agent=session.runtime.agent,
            )
        except Exception as exc:
            return RuntimeSessionSkillPrepared(
                status="unavailable",
                result={
                    "summary": "skill catalog unavailable",
                    "details": f"Skill catalog unavailable: {exc}",
                },
            )
        if loader is None:
            return RuntimeSessionSkillPrepared(
                status="disabled",
                result={
                    "summary": "skill support disabled",
                    "details": "Skill support is disabled in the active configuration.",
                },
            )

        policy_store = resolve_workspace_skill_policy_store(session.workspace_dir)
        policy = load_workspace_skill_policy(session.workspace_dir)
        if action == "list":
            entries = refresh_skill_catalog_loader(loader)
            counts = summarize_skill_entries(entries, policy)
            return RuntimeSessionSkillPrepared(
                status="ok",
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
        if action == "active":
            entries = refresh_skill_catalog_loader(loader)
            counts = summarize_skill_entries(entries, policy)
            return RuntimeSessionSkillPrepared(
                status="ok",
                result={
                    "summary": f"{counts['active']} active skill(s) | mode {policy.mode}",
                    "details": format_skill_policy_overview(policy, entries),
                    "counts": counts,
                    "policy": policy.to_dict(),
                },
            )
        if action == "show":
            if not command.skill_name:
                raise HTTPException(status_code=400, detail="Usage: /skill show <skill_name>")
            refresh_skill_catalog_loader(loader)
            entry, details = format_skill_detail(loader, command.skill_name)
            return RuntimeSessionSkillPrepared(
                status="ok" if entry is not None else "not_found",
                result={
                    "summary": f"showing {entry.name}" if entry is not None else "skill not found",
                    "details": details,
                    "skill_name": command.skill_name,
                    "found": entry is not None,
                    "active": bool(entry is not None and summarize_skill_entries([entry], policy)["active"] > 0),
                },
            )
        if action == "search":
            if not command.query:
                raise HTTPException(status_code=400, detail="Usage: /skill search <query>")
            refresh_skill_catalog_loader(loader)
            hits = search_skill_entries(loader, command.query)
            return RuntimeSessionSkillPrepared(
                status="ok",
                result={
                    "summary": f"{len(hits)} match(es)" if hits else "no matches",
                    "details": format_skill_search_results(command.query, hits, policy),
                    "query": command.query,
                    "match_count": len(hits),
                    "policy": policy.to_dict(),
                },
            )
        return RuntimeSessionSkillPrepared(
            status="ok",
            mutation=self._prepare_mutation(
                session,
                command=command,
                loader=loader,
                policy_store=policy_store,
                policy=policy,
            ),
        )

    async def complete_mutation(
        self,
        session: "MainAgentSessionState",
        mutation: RuntimeSessionSkillMutationPlan,
        *,
        queued_ids: Sequence[str],
        rebuild_session_agent: Callable[[tuple[str, str, str] | None], Awaitable[None]],
        selected_model_identity: tuple[str, str, str] | None,
    ) -> dict[str, Any]:
        entries = refresh_skill_catalog_loader(mutation.loader)
        effective_policy = (
            mutation.updated_policy
            if mutation.action != "refresh"
            else load_workspace_skill_policy(session.workspace_dir)
        )
        counts = summarize_skill_entries(entries, effective_policy)
        await rebuild_session_agent(selected_model_identity)
        if mutation.action == "refresh":
            result = {
                "summary": (
                    f"{counts['total']} skill(s) refreshed | {counts['active']} active | "
                    f"{counts['ready']} ready | {counts['blocked']} blocked"
                ),
                "details": format_skill_entries(entries, effective_policy),
                "counts": counts,
                "policy": effective_policy.to_dict(),
            }
        else:
            result = {
                "summary": mutation.base_summary,
                "details": mutation.base_details,
                "counts": counts,
                "policy": mutation.updated_policy.to_dict(),
            }
        return self._with_reload_queue_metadata(
            session_id=session.session_id,
            base_summary=str(result.get("summary") or ""),
            base_details=str(result.get("details") or ""),
            queued_ids=queued_ids,
            include_current_note=False,
            policy_payload=result.get("policy") if isinstance(result.get("policy"), dict) else None,
            counts_payload=result.get("counts") if isinstance(result.get("counts"), dict) else None,
        )

    def build_busy_result(
        self,
        session: "MainAgentSessionState",
        mutation: RuntimeSessionSkillMutationPlan,
        *,
        queued_ids: Sequence[str],
        include_current_note: bool,
    ) -> dict[str, Any]:
        return self._with_reload_queue_metadata(
            session_id=session.session_id,
            base_summary=mutation.base_summary,
            base_details=mutation.base_details,
            queued_ids=queued_ids,
            include_current_note=include_current_note,
            policy_payload=(
                mutation.updated_policy.to_dict()
                if mutation.action != "refresh"
                else None
            ),
        )

    def _prepare_mutation(
        self,
        session: "MainAgentSessionState",
        *,
        command: RuntimeSessionSkillCommand,
        loader: Any,
        policy_store: Any,
        policy: Any,
    ) -> RuntimeSessionSkillMutationPlan:
        action = command.action
        entries = refresh_skill_catalog_loader(loader)
        if action == "mode":
            requested_mode = command.mode or command.query or command.skill_name
            if not requested_mode:
                raise HTTPException(status_code=400, detail="Usage: /skill mode <all|allowlist>")
            try:
                updated_policy = policy_store.set_mode(requested_mode)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            base_summary = f"skill mode set to {updated_policy.mode}"
            base_details = format_skill_policy_overview(updated_policy, entries)
        elif action == "enable":
            if not command.skill_name:
                raise HTTPException(status_code=400, detail="Usage: /skill enable <skill_name>")
            entry = find_skill_entry(loader, command.skill_name)
            if entry is None:
                raise HTTPException(status_code=404, detail=f"Skill not found: {command.skill_name}")
            updated_policy = policy_store.enable([entry.name])
            base_summary = f"enabled {entry.name} in workspace policy"
            base_details = format_skill_policy_overview(updated_policy, entries)
        elif action == "disable":
            if not command.skill_name:
                raise HTTPException(status_code=400, detail="Usage: /skill disable <skill_name>")
            entry = find_skill_entry(loader, command.skill_name)
            if entry is None:
                raise HTTPException(status_code=404, detail=f"Skill not found: {command.skill_name}")
            updated_policy = policy_store.disable([entry.name])
            base_summary = f"disabled {entry.name} in workspace policy"
            base_details = format_skill_policy_overview(updated_policy, entries)
        elif action == "reset":
            updated_policy = policy_store.reset()
            base_summary = "workspace skill policy reset"
            base_details = format_skill_policy_overview(updated_policy, entries)
        elif action == "install":
            if not command.path:
                raise HTTPException(status_code=400, detail="Usage: /skill install <path>")
            try:
                install_result = install_workspace_skill_from_path(
                    workspace_dir=session.workspace_dir,
                    source_path=command.path,
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
            base_summary = f"installed {install_result.skill_name}"
            base_details = format_skill_install_result(install_result, entries, updated_policy)
        elif action == "uninstall":
            if not command.skill_name:
                raise HTTPException(status_code=400, detail="Usage: /skill uninstall <skill_name>")
            try:
                uninstall_result = uninstall_workspace_skill(
                    workspace_dir=session.workspace_dir,
                    skill_name=command.skill_name,
                    loader=loader,
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            entries = refresh_skill_catalog_loader(loader)
            updated_policy = uninstall_result.policy
            base_summary = f"uninstalled {uninstall_result.skill_name}"
            base_details = format_skill_uninstall_result(uninstall_result, entries, updated_policy)
        elif action == "rollback":
            if not command.skill_name:
                raise HTTPException(status_code=400, detail="Usage: /skill rollback <skill_name>")
            try:
                rollback_result = rollback_workspace_skill(
                    workspace_dir=session.workspace_dir,
                    skill_name=command.skill_name,
                    loader=loader,
                )
            except FileNotFoundError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            entries = refresh_skill_catalog_loader(loader)
            updated_policy = rollback_result.policy
            base_summary = f"rolled back {rollback_result.skill_name}"
            base_details = format_skill_rollback_result(rollback_result, entries, updated_policy)
        else:
            updated_policy = policy
            base_summary = "skill catalog refreshed"
            base_details = "Refreshed skill catalog."

        return RuntimeSessionSkillMutationPlan(
            action=action,
            loader=loader,
            updated_policy=updated_policy,
            reload_reason=self._reload_reason(action),
            base_summary=base_summary,
            base_details=base_details,
            command_name=self._command_name(command, updated_policy),
        )

    @staticmethod
    def _reload_reason(action: str) -> str:
        return {
            "mode": "workspace skill mode updated",
            "enable": "workspace skill policy updated",
            "disable": "workspace skill policy updated",
            "reset": "workspace skill policy reset",
            "install": "workspace skill installed",
            "uninstall": "workspace skill uninstalled",
            "rollback": "workspace skill rolled back",
            "refresh": "skill catalog refreshed",
        }.get(action, "workspace skill runtime changed")

    @staticmethod
    def _command_name(
        command: RuntimeSessionSkillCommand,
        updated_policy: Any,
    ) -> str:
        if command.action == "mode":
            return f"skill mode {updated_policy.mode}"
        if command.action == "install" and command.path:
            return f"skill install {command.path}"
        if command.action == "uninstall" and command.skill_name:
            return f"skill uninstall {command.skill_name}"
        if command.action == "rollback" and command.skill_name:
            return f"skill rollback {command.skill_name}"
        if command.action in {"enable", "disable"} and command.skill_name:
            return f"skill {command.action} {command.skill_name}".strip()
        return f"skill {command.action}"

    @staticmethod
    def _with_reload_queue_metadata(
        *,
        session_id: str,
        base_summary: str,
        base_details: str,
        queued_ids: Sequence[str],
        include_current_note: bool,
        policy_payload: dict[str, Any] | None = None,
        counts_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_ids = [item for item in (_safe_text(value) for value in queued_ids) if item]
        queued_current = session_id in normalized_ids
        queued_other_ids = [item for item in normalized_ids if item != session_id]
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


__all__ = [
    "MUTATING_SKILL_ACTIONS",
    "SUPPORTED_SKILL_ACTIONS",
    "RuntimeSessionSkillCommand",
    "RuntimeSessionSkillCommandHandler",
    "RuntimeSessionSkillMutationPlan",
    "RuntimeSessionSkillPrepared",
]
