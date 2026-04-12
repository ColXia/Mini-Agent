"""Shared helpers for operator-facing `/skill` commands."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any

from mini_agent.agent_core.skills.install import (
    WorkspaceSkillInstallResult,
    WorkspaceSkillInstaller,
    WorkspaceSkillRollbackResult,
    WorkspaceSkillUninstallResult,
)
from mini_agent.agent_core.skills.loader import AgentSkillLoader, SkillTier1Metadata
from mini_agent.agent_core.skills.policy import (
    WorkspaceSkillPolicy,
    WorkspaceSkillPolicyStore,
    compute_active_skill_names,
    describe_skill_activation,
)
from mini_agent.config import Config
from mini_agent.runtime.tooling import (
    resolve_builtin_skills_dir,
    resolve_workspace_skills_dir,
)


@dataclass(frozen=True)
class SkillSearchHit:
    entry: SkillTier1Metadata
    score: float


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _source_name(value: Any) -> str:
    return _clean_text(getattr(value, "value", value))


def _status_text(entry: SkillTier1Metadata) -> str:
    if entry.eligible:
        return "ready"
    reason = _clean_text(entry.blocked_reason) or "blocked"
    return f"blocked ({reason})"


def resolve_workspace_skill_policy_store(workspace_dir: Path) -> WorkspaceSkillPolicyStore:
    return WorkspaceSkillPolicyStore(workspace_dir)


def load_workspace_skill_policy(workspace_dir: Path) -> WorkspaceSkillPolicy:
    return resolve_workspace_skill_policy_store(workspace_dir).load()


def resolve_workspace_skill_install_root(
    workspace_dir: Path,
    *,
    loader: Any | None = None,
) -> Path:
    raw_loader = _resolve_agent_skill_loader(loader)
    candidate = getattr(raw_loader, "workspace_dir", None)
    if candidate is not None:
        return Path(candidate).expanduser().resolve()
    return (workspace_dir / ".mini-agent" / "skills").resolve()


def install_workspace_skill_from_path(
    *,
    workspace_dir: Path,
    source_path: str | Path,
    loader: Any | None = None,
    activate: bool = True,
    overwrite: bool = False,
) -> WorkspaceSkillInstallResult:
    installer = WorkspaceSkillInstaller(
        workspace_dir,
        skills_root=resolve_workspace_skill_install_root(workspace_dir, loader=loader),
        policy_store=WorkspaceSkillPolicyStore(workspace_dir),
    )
    return installer.install_from_path(
        source_path,
        activate=activate,
        overwrite=overwrite,
        loader=loader,
    )


def uninstall_workspace_skill(
    *,
    workspace_dir: Path,
    skill_name: str,
    loader: Any | None = None,
) -> WorkspaceSkillUninstallResult:
    installer = WorkspaceSkillInstaller(
        workspace_dir,
        skills_root=resolve_workspace_skill_install_root(workspace_dir, loader=loader),
        policy_store=WorkspaceSkillPolicyStore(workspace_dir),
    )
    return installer.uninstall(skill_name, loader=loader)


def rollback_workspace_skill(
    *,
    workspace_dir: Path,
    skill_name: str,
    loader: Any | None = None,
) -> WorkspaceSkillRollbackResult:
    installer = WorkspaceSkillInstaller(
        workspace_dir,
        skills_root=resolve_workspace_skill_install_root(workspace_dir, loader=loader),
        policy_store=WorkspaceSkillPolicyStore(workspace_dir),
    )
    return installer.rollback(skill_name, loader=loader)


def _active_skill_names(
    entries: list[SkillTier1Metadata],
    policy: WorkspaceSkillPolicy | None = None,
) -> set[str]:
    return compute_active_skill_names(entries, policy)


def _activation_label(
    entry: SkillTier1Metadata,
    policy: WorkspaceSkillPolicy | None = None,
) -> str:
    active, reason = describe_skill_activation(entry, policy)
    if active:
        return "active"
    if reason == "disabled":
        return "inactive (disabled)"
    if reason == "not-allowed":
        return "inactive (not allowlisted)"
    return _status_text(entry)


def _resolve_agent_skill_loader(agent: Any | None) -> AgentSkillLoader | None:
    if agent is None:
        return None
    if isinstance(agent, AgentSkillLoader):
        return agent
    if (
        hasattr(agent, "list_tier1")
        and hasattr(agent, "get_skill")
        and hasattr(agent, "discover")
    ):
        return agent
    candidate = getattr(agent, "skill_catalog_loader", None)
    if candidate is None:
        runtime_candidate = getattr(agent, "skill_runtime", None)
        candidate = getattr(runtime_candidate, "loader", runtime_candidate)
    if isinstance(candidate, AgentSkillLoader):
        return candidate
    if (
        candidate is not None
        and hasattr(candidate, "list_tier1")
        and hasattr(candidate, "get_skill")
    ):
        return candidate
    return None


def resolve_skill_catalog_loader(
    *,
    workspace_dir: Path,
    agent: Any | None = None,
    config: Config | None = None,
) -> AgentSkillLoader | None:
    loader = _resolve_agent_skill_loader(agent)
    if loader is not None:
        return loader

    active_config = config or Config.load(allow_interactive_setup=False)
    if not getattr(active_config.tools, "enable_skills", False):
        return None

    workspace_skills_dir = resolve_workspace_skills_dir(workspace_dir)
    loader = AgentSkillLoader(
        builtin_dir=resolve_builtin_skills_dir(active_config),
        workspace_dir=workspace_skills_dir,
    )
    loader.discover()
    return loader


def list_skill_entries(
    loader: AgentSkillLoader,
    *,
    include_blocked: bool = True,
) -> list[SkillTier1Metadata]:
    return loader.list_tier1(eligible_only=not include_blocked)


def refresh_skill_catalog_loader(
    loader: AgentSkillLoader | None,
) -> list[SkillTier1Metadata]:
    if loader is None:
        return []
    if hasattr(loader, "discover"):
        loader.discover()
    return list_skill_entries(loader, include_blocked=True)


def _skill_dir_signature(root: Path | None) -> str:
    if root is None:
        return "none"
    resolved = root.expanduser().resolve()
    if not resolved.exists():
        return f"{resolved}|missing"
    skill_files = sorted(path for path in resolved.rglob("SKILL.md") if path.is_file())
    latest_mtime_ns = 0
    relative_paths: list[str] = []
    for skill_file in skill_files:
        relative_paths.append(skill_file.relative_to(resolved).as_posix())
        try:
            latest_mtime_ns = max(latest_mtime_ns, int(skill_file.stat().st_mtime_ns))
        except Exception:
            continue
    digest = hashlib.sha1("\n".join(relative_paths).encode("utf-8")).hexdigest()[:12]
    return f"{resolved}|count={len(skill_files)}|mtime={latest_mtime_ns}|paths={digest}"


def skill_catalog_signature(
    *,
    workspace_dir: Path,
    agent: Any | None = None,
    config: Config | None = None,
) -> tuple[str, str, str] | None:
    loader = _resolve_agent_skill_loader(agent)
    builtin_dir: Path | None = None
    workspace_skills_dir: Path | None = None
    if isinstance(loader, AgentSkillLoader):
        builtin_dir = loader.builtin_dir
        workspace_skills_dir = loader.workspace_dir
    else:
        active_config = config or Config.load(allow_interactive_setup=False)
        if not getattr(active_config.tools, "enable_skills", False):
            return None
        builtin_dir = resolve_builtin_skills_dir(active_config)
        workspace_skills_dir = resolve_workspace_skills_dir(workspace_dir)
    policy_store = WorkspaceSkillPolicyStore(workspace_dir)
    return (
        _skill_dir_signature(builtin_dir),
        _skill_dir_signature(workspace_skills_dir),
        policy_store.signature(),
    )


def summarize_skill_entries(
    entries: list[SkillTier1Metadata],
    policy: WorkspaceSkillPolicy | None = None,
) -> dict[str, Any]:
    total = len(entries)
    ready = sum(1 for entry in entries if entry.eligible)
    blocked = max(0, total - ready)
    workspace = sum(1 for entry in entries if _source_name(entry.source) == "workspace")
    active = len(_active_skill_names(entries, policy))
    summary: dict[str, Any] = {
        "total": total,
        "ready": ready,
        "blocked": blocked,
        "workspace": workspace,
        "active": active,
    }
    if policy is not None:
        summary["mode"] = policy.mode
    return summary


def format_skill_entries(
    entries: list[SkillTier1Metadata],
    policy: WorkspaceSkillPolicy | None = None,
) -> str:
    if not entries:
        return "No skills discovered."

    counts = summarize_skill_entries(entries, policy)
    policy_suffix = f" | active {counts['active']} | mode {counts['mode']}" if policy is not None else ""
    lines = [
        "Skills:",
        (
            f"- total {counts['total']} | ready {counts['ready']} | "
            f"blocked {counts['blocked']} | workspace {counts['workspace']}{policy_suffix}"
        ),
    ]
    for entry in entries:
        lines.append(
            f"- {entry.name} [{_source_name(entry.source)}] {_activation_label(entry, policy)}"
        )
        lines.append(f"  {entry.description}")
    return "\n".join(lines)


def find_skill_entry(
    loader: AgentSkillLoader,
    skill_name: str,
) -> SkillTier1Metadata | None:
    target = _clean_text(skill_name).lower()
    if not target:
        return None
    for entry in loader.list_tier1(eligible_only=False):
        if _clean_text(entry.name).lower() == target:
            return entry
    return None


def format_skill_detail(
    loader: AgentSkillLoader,
    skill_name: str,
) -> tuple[SkillTier1Metadata | None, str]:
    entry = find_skill_entry(loader, skill_name)
    if entry is None:
        available = ", ".join(item.name for item in loader.list_tier1(eligible_only=False))
        if available:
            return None, f"Skill not found: {skill_name}\nAvailable skills: {available}"
        return None, f"Skill not found: {skill_name}"

    skill = loader.get_skill(entry.name, eligible_only=False)
    if skill is None:
        return entry, f"Skill metadata exists but content could not be loaded: {entry.name}"

    lines = [
        f"Skill: {entry.name}",
        f"Source: {_source_name(entry.source)}",
        f"Status: {_status_text(entry)}",
        f"Skill Key: {entry.skill_key}",
    ]
    if entry.skill_file:
        lines.append(f"Path: {entry.skill_file}")
    lines.extend(
        [
            "",
            "Description:",
            entry.description,
            "",
            "Instructions:",
            skill.to_prompt(),
        ]
    )
    return entry, "\n".join(lines)


def search_skill_entries(
    loader: AgentSkillLoader,
    query: str,
    *,
    limit: int = 8,
) -> list[SkillSearchHit]:
    normalized_query = _clean_text(query).lower()
    if not normalized_query:
        return []
    tokens = [token for token in normalized_query.split(" ") if token]
    results: list[SkillSearchHit] = []
    for entry in loader.list_tier1(eligible_only=False):
        haystack = " ".join(
            [
                _clean_text(entry.name).lower(),
                _clean_text(entry.description).lower(),
                _clean_text(entry.skill_key).lower(),
            ]
        )
        score = 0.0
        if normalized_query == _clean_text(entry.name).lower():
            score += 8.0
        elif normalized_query in _clean_text(entry.name).lower():
            score += 6.0
        if normalized_query in _clean_text(entry.description).lower():
            score += 4.0
        if normalized_query in haystack:
            score += 2.0
        score += sum(1.25 for token in tokens if token in haystack)
        if entry.always and score > 0.0:
            score += 0.2
        if score <= 0.0:
            continue
        results.append(SkillSearchHit(entry=entry, score=round(score, 4)))
    results.sort(key=lambda item: (-item.score, item.entry.name.lower()))
    return results[: max(1, int(limit))]


def format_skill_search_results(
    query: str,
    hits: list[SkillSearchHit],
    policy: WorkspaceSkillPolicy | None = None,
) -> str:
    normalized_query = _clean_text(query)
    if not hits:
        return f'No skills matched "{normalized_query}".'
    lines = [f'Skill matches for "{normalized_query}":']
    for hit in hits:
        entry = hit.entry
        lines.append(
            f"- {entry.name} [{_source_name(entry.source)}] {_activation_label(entry, policy)}"
        )
        lines.append(f"  {entry.description}")
    return "\n".join(lines)


def format_skill_policy_overview(
    policy: WorkspaceSkillPolicy,
    entries: list[SkillTier1Metadata],
) -> str:
    counts = summarize_skill_entries(entries, policy)
    active_names = sorted(_active_skill_names(entries, policy), key=str.casefold)
    lines = [
        "Workspace Skill Policy:",
        f"- mode {policy.mode}",
        f"- active {counts['active']} / ready {counts['ready']}",
    ]
    if policy.allowlist:
        lines.append(f"- allowlist {', '.join(policy.allowlist)}")
    if policy.denylist:
        lines.append(f"- denylist {', '.join(policy.denylist)}")
    if active_names:
        lines.append(f"- active skills: {', '.join(active_names)}")
    else:
        lines.append("- active skills: (none)")
    return "\n".join(lines)


def format_skill_install_result(
    result: WorkspaceSkillInstallResult,
    entries: list[SkillTier1Metadata],
    policy: WorkspaceSkillPolicy,
) -> str:
    lines = [
        "Installed Skill:",
        f"- name {result.skill_name}",
        f"- description {result.description}",
        f"- source {result.source_kind}",
        f"- path {result.installed_path}",
        f"- activated {'yes' if result.activated else 'no'}",
    ]
    if result.source_path:
        lines.append(f"- from {result.source_path}")
    if result.ledger_path:
        lines.append(f"- ledger {result.ledger_path}")
    lines.extend(["", format_skill_policy_overview(policy, entries)])
    return "\n".join(lines)


def format_skill_uninstall_result(
    result: WorkspaceSkillUninstallResult,
    entries: list[SkillTier1Metadata],
    policy: WorkspaceSkillPolicy,
) -> str:
    lines = [
        "Uninstalled Skill:",
        f"- name {result.skill_name}",
        f"- removed {result.removed_path}",
    ]
    if result.source_kind:
        lines.append(f"- source {result.source_kind}")
    if result.source_path:
        lines.append(f"- from {result.source_path}")
    if result.backup_path:
        lines.append(f"- backup {result.backup_path}")
    if result.ledger_path:
        lines.append(f"- ledger {result.ledger_path}")
    lines.extend(["", format_skill_policy_overview(policy, entries)])
    return "\n".join(lines)


def format_skill_rollback_result(
    result: WorkspaceSkillRollbackResult,
    entries: list[SkillTier1Metadata],
    policy: WorkspaceSkillPolicy,
) -> str:
    lines = [
        "Rolled Back Skill:",
        f"- name {result.skill_name}",
        f"- restored {result.restored_path}",
        f"- backup {result.backup_path}",
    ]
    if result.source_kind:
        lines.append(f"- source {result.source_kind}")
    if result.source_path:
        lines.append(f"- from {result.source_path}")
    if result.ledger_path:
        lines.append(f"- ledger {result.ledger_path}")
    lines.extend(["", format_skill_policy_overview(policy, entries)])
    return "\n".join(lines)


__all__ = [
    "SkillSearchHit",
    "find_skill_entry",
    "format_skill_detail",
    "format_skill_entries",
    "format_skill_install_result",
    "format_skill_rollback_result",
    "format_skill_uninstall_result",
    "format_skill_policy_overview",
    "format_skill_search_results",
    "install_workspace_skill_from_path",
    "list_skill_entries",
    "load_workspace_skill_policy",
    "refresh_skill_catalog_loader",
    "resolve_skill_catalog_loader",
    "resolve_workspace_skill_install_root",
    "resolve_workspace_skill_policy_store",
    "rollback_workspace_skill",
    "search_skill_entries",
    "skill_catalog_signature",
    "summarize_skill_entries",
    "uninstall_workspace_skill",
]
