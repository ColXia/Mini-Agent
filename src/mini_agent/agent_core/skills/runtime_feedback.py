"""Shared runtime-reload feedback semantics for local skill mutations."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True, slots=True)
class SkillRuntimeReloadFeedback:
    """Shared surface-neutral feedback for local skill runtime reload flows."""

    reason: str
    busy_summary: str
    warm_prefix_base: str
    success_status: str
    cli_reload_success_base: str
    cli_reload_failure_base: str


def describe_skill_runtime_reload(payload: Mapping[str, Any] | None) -> SkillRuntimeReloadFeedback:
    """Describe how a successful local skill mutation should talk about runtime reload."""

    normalized_payload = payload or {}
    mutation = _safe_text(normalized_payload.get("mutation")).lower()
    skill_name = _safe_text(normalized_payload.get("skill_name"))
    mode = _safe_text(normalized_payload.get("mode"))
    reason = _safe_text(normalized_payload.get("reload_reason")) or "workspace skill runtime changed"
    summary = _safe_text(normalized_payload.get("summary")) or "skill command completed"

    if mutation == "install":
        return SkillRuntimeReloadFeedback(
            reason=reason,
            busy_summary=f"installed {skill_name}; runtime busy",
            warm_prefix_base="Workspace skill installed",
            success_status=f"Installed skill {skill_name}.",
            cli_reload_success_base=f"Installed {skill_name}",
            cli_reload_failure_base="Skill installed, but the current CLI agent did not reload",
        )
    if mutation == "uninstall":
        return SkillRuntimeReloadFeedback(
            reason=reason,
            busy_summary=f"uninstalled {skill_name}; runtime busy",
            warm_prefix_base="Workspace skill uninstalled",
            success_status=f"Uninstalled skill {skill_name}.",
            cli_reload_success_base=f"Uninstalled {skill_name}",
            cli_reload_failure_base="Skill uninstalled, but the current CLI agent did not reload",
        )
    if mutation == "rollback":
        return SkillRuntimeReloadFeedback(
            reason=reason,
            busy_summary=f"rolled back {skill_name}; runtime busy",
            warm_prefix_base="Workspace skill rolled back",
            success_status=f"Rolled back skill {skill_name}.",
            cli_reload_success_base=f"Rolled back {skill_name}",
            cli_reload_failure_base="Skill rolled back, but the current CLI agent did not reload",
        )
    if mutation == "mode":
        return SkillRuntimeReloadFeedback(
            reason=reason,
            busy_summary=f"skill mode set to {mode}; runtime busy",
            warm_prefix_base="Workspace skill mode updated",
            success_status="Workspace skill mode updated.",
            cli_reload_success_base=f"Skill mode set to {mode}",
            cli_reload_failure_base="Skill policy updated, but the current CLI agent did not reload",
        )
    if mutation in {"enable", "disable"}:
        return SkillRuntimeReloadFeedback(
            reason=reason,
            busy_summary=f"{mutation}d {skill_name}; runtime busy",
            warm_prefix_base="Workspace skill policy updated",
            success_status="Workspace skill policy updated.",
            cli_reload_success_base=f"Skill {mutation}d in workspace policy",
            cli_reload_failure_base="Workspace skill policy updated, but the current CLI agent did not reload",
        )
    if mutation == "reset":
        return SkillRuntimeReloadFeedback(
            reason=reason,
            busy_summary="workspace skill policy reset; runtime busy",
            warm_prefix_base="Workspace skill policy reset",
            success_status="Workspace skill policy reset.",
            cli_reload_success_base="Workspace skill policy reset",
            cli_reload_failure_base="Skill policy reset, but the current CLI agent did not reload",
        )
    if mutation == "refresh":
        return SkillRuntimeReloadFeedback(
            reason=reason,
            busy_summary="catalog refreshed; runtime busy",
            warm_prefix_base="Skill catalog refreshed",
            success_status="",
            cli_reload_success_base="Skill catalog refreshed",
            cli_reload_failure_base="Skill catalog refreshed, but the current CLI agent did not reload",
        )
    return SkillRuntimeReloadFeedback(
        reason=reason,
        busy_summary=f"{summary}; runtime busy",
        warm_prefix_base="Workspace skill updated",
        success_status="Skill command completed.",
        cli_reload_success_base=summary,
        cli_reload_failure_base=f"{summary} completed, but the current CLI agent did not reload",
    )


def format_cli_skill_reload_success(
    feedback: SkillRuntimeReloadFeedback,
    *,
    rebuilt: bool,
    active_model: str,
) -> str:
    """Format the CLI success note after a local skill runtime reload attempt."""

    model_label = _safe_text(active_model)
    if rebuilt and model_label:
        return f"{feedback.cli_reload_success_base}; current CLI agent reloaded on {model_label}"
    return feedback.cli_reload_success_base


def format_cli_skill_reload_failure(
    feedback: SkillRuntimeReloadFeedback,
    exc: Exception,
) -> str:
    """Format the CLI warning when skill mutation succeeds but reload fails."""

    return f"{feedback.cli_reload_failure_base}: {exc}"


__all__ = [
    "SkillRuntimeReloadFeedback",
    "describe_skill_runtime_reload",
    "format_cli_skill_reload_failure",
    "format_cli_skill_reload_success",
]
