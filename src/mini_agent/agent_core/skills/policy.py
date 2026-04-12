"""Workspace-scoped skill activation policy helpers."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Iterable


def normalize_skill_name(value: Any) -> str:
    return " ".join(str(value or "").split()).strip()


def _normalized_skill_key(value: Any) -> str:
    return normalize_skill_name(value).casefold()


def normalize_skill_policy_mode(value: Any) -> str:
    normalized = " ".join(str(value or "").split()).strip().lower().replace("-", "_")
    if normalized in {"", "all"}:
        return "all"
    if normalized in {"allowlist", "whitelist", "curated", "selected"}:
        return "allowlist"
    raise ValueError(f"Unsupported skill policy mode: {value}")


def _unique_skill_names(values: Iterable[Any]) -> tuple[str, ...]:
    seen: set[str] = set()
    ordered: list[str] = []
    for value in values:
        name = normalize_skill_name(value)
        if not name:
            continue
        key = _normalized_skill_key(name)
        if key in seen:
            continue
        seen.add(key)
        ordered.append(name)
    return tuple(ordered)


@dataclass(frozen=True)
class WorkspaceSkillPolicy:
    """Persisted workspace-level skill activation policy."""

    mode: str = "all"
    allowlist: tuple[str, ...] = ()
    denylist: tuple[str, ...] = ()

    @classmethod
    def from_raw(cls, raw: Any) -> "WorkspaceSkillPolicy":
        if not isinstance(raw, dict):
            return cls()
        try:
            mode = normalize_skill_policy_mode(raw.get("mode"))
        except ValueError:
            mode = "all"
        allowlist = _unique_skill_names(raw.get("allowlist") or [])
        denylist = _unique_skill_names(raw.get("denylist") or [])
        return cls(mode=mode, allowlist=allowlist, denylist=denylist)

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": normalize_skill_policy_mode(self.mode),
            "allowlist": list(_unique_skill_names(self.allowlist)),
            "denylist": list(_unique_skill_names(self.denylist)),
        }


def _entry_name(entry: Any) -> str:
    return normalize_skill_name(getattr(entry, "name", None))


def _entry_is_eligible(entry: Any) -> bool:
    return bool(getattr(entry, "eligible", False))


def describe_skill_activation(entry: Any, policy: WorkspaceSkillPolicy | None = None) -> tuple[bool, str]:
    active_policy = policy or WorkspaceSkillPolicy()
    name = _entry_name(entry)
    if not name:
        return False, "inactive"
    if not _entry_is_eligible(entry):
        return False, "blocked"
    key = _normalized_skill_key(name)
    denylist = {_normalized_skill_key(item) for item in active_policy.denylist}
    allowlist = {_normalized_skill_key(item) for item in active_policy.allowlist}
    if key in denylist:
        return False, "disabled"
    if normalize_skill_policy_mode(active_policy.mode) == "allowlist" and key not in allowlist:
        return False, "not-allowed"
    return True, "active"


def compute_active_skill_names(
    entries: Iterable[Any],
    policy: WorkspaceSkillPolicy | None = None,
) -> set[str]:
    active_policy = policy or WorkspaceSkillPolicy()
    names: set[str] = set()
    for entry in entries:
        name = _entry_name(entry)
        if not name:
            continue
        active, _reason = describe_skill_activation(entry, active_policy)
        if active:
            names.add(name)
    return names


class WorkspaceSkillPolicyStore:
    """Persist workspace-level skill policy under `.mini-agent/skill_policy.json`."""

    def __init__(self, workspace_dir: str | Path | None) -> None:
        self.workspace_dir = (
            Path(workspace_dir).expanduser().resolve()
            if workspace_dir is not None
            else None
        )

    @property
    def path(self) -> Path | None:
        if self.workspace_dir is None:
            return None
        return self.workspace_dir / ".mini-agent" / "skill_policy.json"

    def load(self) -> WorkspaceSkillPolicy:
        path = self.path
        if path is None or not path.exists():
            return WorkspaceSkillPolicy()
        try:
            raw = json.loads(path.read_text(encoding="utf-8-sig"))
        except Exception:
            return WorkspaceSkillPolicy()
        return WorkspaceSkillPolicy.from_raw(raw)

    def save(self, policy: WorkspaceSkillPolicy) -> WorkspaceSkillPolicy:
        path = self.path
        normalized = WorkspaceSkillPolicy.from_raw(policy.to_dict())
        if path is None:
            return normalized
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(normalized.to_dict(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return normalized

    def set_mode(self, mode: str) -> WorkspaceSkillPolicy:
        current = self.load()
        updated = WorkspaceSkillPolicy(
            mode=normalize_skill_policy_mode(mode),
            allowlist=current.allowlist,
            denylist=current.denylist,
        )
        return self.save(updated)

    def enable(self, names: Iterable[Any]) -> WorkspaceSkillPolicy:
        current = self.load()
        enabled_names = _unique_skill_names((*current.allowlist, *list(names)))
        disabled_keys = {_normalized_skill_key(item) for item in names}
        updated = WorkspaceSkillPolicy(
            mode=current.mode,
            allowlist=enabled_names,
            denylist=tuple(
                item for item in current.denylist if _normalized_skill_key(item) not in disabled_keys
            ),
        )
        return self.save(updated)

    def disable(self, names: Iterable[Any]) -> WorkspaceSkillPolicy:
        current = self.load()
        disabled_names = _unique_skill_names((*current.denylist, *list(names)))
        disabled_keys = {_normalized_skill_key(item) for item in names}
        updated = WorkspaceSkillPolicy(
            mode=current.mode,
            allowlist=tuple(
                item for item in current.allowlist if _normalized_skill_key(item) not in disabled_keys
            ),
            denylist=disabled_names,
        )
        return self.save(updated)

    def forget(self, names: Iterable[Any]) -> WorkspaceSkillPolicy:
        current = self.load()
        removed_keys = {_normalized_skill_key(item) for item in names}
        updated = WorkspaceSkillPolicy(
            mode=current.mode,
            allowlist=tuple(
                item for item in current.allowlist if _normalized_skill_key(item) not in removed_keys
            ),
            denylist=tuple(
                item for item in current.denylist if _normalized_skill_key(item) not in removed_keys
            ),
        )
        return self.save(updated)

    def reset(self) -> WorkspaceSkillPolicy:
        return self.save(WorkspaceSkillPolicy())

    def signature(self) -> str:
        path = self.path
        if path is None:
            return "none"
        resolved = path.expanduser().resolve()
        if not resolved.exists():
            return f"{resolved}|missing"
        try:
            mtime_ns = int(resolved.stat().st_mtime_ns)
        except Exception:
            mtime_ns = 0
        try:
            content = resolved.read_text(encoding="utf-8-sig")
        except Exception:
            content = ""
        return f"{resolved}|mtime={mtime_ns}|size={len(content)}"


class WorkspaceSkillRuntimeBridge:
    """Policy-aware runtime bridge over a raw `AgentSkillLoader`."""

    def __init__(
        self,
        loader: Any,
        *,
        workspace_dir: str | Path | None = None,
        eligible_only: bool = True,
        policy_store: WorkspaceSkillPolicyStore | None = None,
    ) -> None:
        self.loader = loader
        self.eligible_only = bool(eligible_only)
        self.policy_store = policy_store or WorkspaceSkillPolicyStore(workspace_dir)

    def _all_entries(self) -> list[Any]:
        if hasattr(self.loader, "list_tier1"):
            return list(self.loader.list_tier1(eligible_only=False))
        return []

    def _active_names(self) -> set[str]:
        return compute_active_skill_names(self._all_entries(), self.policy_store.load())

    def get_skill(self, name: str) -> Any | None:
        normalized_name = normalize_skill_name(name)
        if not normalized_name or normalized_name not in self._active_names():
            return None
        if hasattr(self.loader, "get_skill"):
            return self.loader.get_skill(normalized_name, eligible_only=self.eligible_only)
        return None

    def list_skills(self) -> list[str]:
        active_names = self._active_names()
        return sorted(active_names, key=str.casefold)

    def get_skills_metadata_prompt(self) -> str:
        active_names = self._active_names()
        if not active_names:
            return ""
        entries = [
            entry
            for entry in self._all_entries()
            if _entry_name(entry) in active_names
        ]
        if not entries:
            return ""
        lines = [
            "## Available Skills",
            "",
            "Skill metadata below is only a routing hint, not the full workflow.",
            "If a skill is relevant, call `get_skill(skill_name)` before relying on it, summarizing it, or claiming you will use it.",
            "If the task spans multiple domains, you may load more than one relevant skill.",
        ]
        for entry in entries:
            source = getattr(getattr(entry, "source", None), "value", None) or getattr(entry, "source", None)
            suffix = f" [{source}]" if source else ""
            lines.append(f"- `{_entry_name(entry)}`{suffix}: {normalize_skill_name(getattr(entry, 'description', ''))}")
        return "\n".join(lines)
