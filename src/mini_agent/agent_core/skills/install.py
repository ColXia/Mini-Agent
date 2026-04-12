from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
import requests
import re
import shutil
import tarfile
import tempfile
from typing import Any
from urllib.parse import urlparse
import zipfile

from mini_agent.agent_core.skills.loader import parse_skill_markdown
from mini_agent.agent_core.skills.policy import (
    WorkspaceSkillPolicy,
    WorkspaceSkillPolicyStore,
    normalize_skill_name,
)
from mini_agent.agent_core.skills.registry import SkillSource


def _slugify_skill_name(name: str) -> str:
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", str(name or "").strip().lower()).strip("-")
    return normalized or "skill"


def _discover_loader(candidate: Any | None) -> None:
    raw_loader = getattr(candidate, "loader", candidate)
    if raw_loader is not None and hasattr(raw_loader, "discover"):
        raw_loader.discover()


@dataclass(frozen=True)
class WorkspaceSkillInstallResult:
    skill_name: str
    description: str
    installed_path: str
    source_kind: str
    source_path: str | None
    activated: bool
    overwrite: bool
    policy: WorkspaceSkillPolicy
    ledger_path: str | None = None
    backup_path: str | None = None


@dataclass(frozen=True)
class WorkspaceSkillUninstallResult:
    skill_name: str
    removed_path: str
    backup_path: str | None
    source_kind: str | None
    source_path: str | None
    policy: WorkspaceSkillPolicy
    ledger_path: str | None = None


@dataclass(frozen=True)
class WorkspaceSkillRollbackResult:
    skill_name: str
    restored_path: str
    backup_path: str
    source_kind: str | None
    source_path: str | None
    policy: WorkspaceSkillPolicy
    ledger_path: str | None = None


@dataclass(frozen=True)
class _PreparedSkillSource:
    source_kind: str
    original_ref: str
    source_root: Path
    skill_file: Path
    temp_root: Path | None = None

    def cleanup(self) -> None:
        if self.temp_root is not None:
            shutil.rmtree(self.temp_root, ignore_errors=True)


class WorkspaceSkillSourceLedger:
    """Persist current workspace skill install sources and history."""

    def __init__(self, workspace_dir: str | Path) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()

    @property
    def path(self) -> Path:
        return self.workspace_dir / ".mini-agent" / "skill_sources.json"

    def load(self) -> dict[str, Any]:
        target = self.path
        if not target.exists():
            return {"skills": {}}
        try:
            raw = json.loads(target.read_text(encoding="utf-8-sig"))
        except Exception:
            return {"skills": {}}
        return self._normalize_payload(raw)

    def save(self, payload: dict[str, Any]) -> str:
        target = self.path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return str(target)

    def current_entry(self, skill_name: str) -> dict[str, Any] | None:
        slot = self.load().get("skills", {}).get(normalize_skill_name(skill_name))
        if not isinstance(slot, dict):
            return None
        current = slot.get("current")
        return dict(current) if isinstance(current, dict) else None

    def latest_backup_entry(self, skill_name: str) -> dict[str, Any] | None:
        slot = self.load().get("skills", {}).get(normalize_skill_name(skill_name))
        if not isinstance(slot, dict):
            return None
        history = slot.get("history")
        if not isinstance(history, list):
            return None
        for item in reversed(history):
            if not isinstance(item, dict):
                continue
            backup_path = str(item.get("backup_path") or "").strip()
            if backup_path and Path(backup_path).exists():
                return dict(item)
        return None

    def record_install(
        self,
        result: WorkspaceSkillInstallResult,
        *,
        policy_state: str,
        action: str = "install",
        backup_path: str | None = None,
    ) -> str:
        payload = self.load()
        skills = payload.setdefault("skills", {})
        if not isinstance(skills, dict):
            skills = {}
            payload["skills"] = skills

        timestamp = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        current = {
            "skill_name": result.skill_name,
            "description": result.description,
            "installed_path": result.installed_path,
            "source_kind": result.source_kind,
            "source_path": result.source_path,
            "activated": bool(result.activated),
            "overwrite": bool(result.overwrite),
            "policy_state": policy_state,
            "backup_path": backup_path,
            "updated_at_utc": timestamp,
        }
        slot = skills.setdefault(result.skill_name, {"current": None, "history": []})
        if not isinstance(slot, dict):
            slot = {"current": None, "history": []}
            skills[result.skill_name] = slot
        history = slot.setdefault("history", [])
        if not isinstance(history, list):
            history = []
            slot["history"] = history
        history.append({**current, "action": action})
        slot["current"] = dict(current)
        return self.save(payload)

    def record_uninstall(
        self,
        *,
        skill_name: str,
        description: str,
        removed_path: str,
        source_kind: str | None,
        source_path: str | None,
        policy_state: str,
        backup_path: str | None,
    ) -> str:
        payload = self.load()
        skills = payload.setdefault("skills", {})
        if not isinstance(skills, dict):
            skills = {}
            payload["skills"] = skills
        slot = skills.setdefault(skill_name, {"current": None, "history": []})
        if not isinstance(slot, dict):
            slot = {"current": None, "history": []}
            skills[skill_name] = slot
        history = slot.setdefault("history", [])
        if not isinstance(history, list):
            history = []
            slot["history"] = history
        history.append(
            {
                "action": "uninstall",
                "skill_name": skill_name,
                "description": description,
                "installed_path": removed_path,
                "source_kind": source_kind,
                "source_path": source_path,
                "policy_state": policy_state,
                "backup_path": backup_path,
                "updated_at_utc": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            }
        )
        slot["current"] = None
        return self.save(payload)

    @staticmethod
    def _normalize_payload(raw: Any) -> dict[str, Any]:
        if not isinstance(raw, dict):
            return {"skills": {}}
        skills = raw.get("skills")
        if not isinstance(skills, dict):
            return {"skills": {}}
        normalized: dict[str, Any] = {}
        for key, value in skills.items():
            skill_name = normalize_skill_name(key)
            if not skill_name:
                continue
            if isinstance(value, dict) and ("current" in value or "history" in value):
                current = value.get("current") if isinstance(value.get("current"), dict) else None
                history = [item for item in value.get("history", []) if isinstance(item, dict)]
            elif isinstance(value, dict):
                current = dict(value)
                history = []
            else:
                current = None
                history = []
            normalized[skill_name] = {"current": current, "history": history}
        return {"skills": normalized}


class WorkspaceSkillInstaller:
    """Install validated skills into one workspace-owned skill root."""

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        skills_root: str | Path | None = None,
        policy_store: WorkspaceSkillPolicyStore | None = None,
        source_ledger: WorkspaceSkillSourceLedger | None = None,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.skills_root = (
            Path(skills_root).expanduser().resolve()
            if skills_root is not None
            else (self.workspace_dir / ".mini-agent" / "skills").resolve()
        )
        self.backup_root = (self.workspace_dir / ".mini-agent" / "skill-backups").resolve()
        self.policy_store = policy_store or WorkspaceSkillPolicyStore(self.workspace_dir)
        self.source_ledger = source_ledger or WorkspaceSkillSourceLedger(self.workspace_dir)

    def install_from_path(
        self,
        source_path: str | Path,
        *,
        activate: bool = True,
        overwrite: bool = False,
        loader: Any | None = None,
    ) -> WorkspaceSkillInstallResult:
        prepared = self._prepare_source(source_path)
        try:
            raw = prepared.skill_file.read_text(encoding="utf-8")
            skill = parse_skill_markdown(
                raw,
                source=SkillSource.WORKSPACE,
                skill_file=prepared.skill_file,
            )
            if skill is None:
                raise ValueError(f"Invalid SKILL.md: {prepared.skill_file}")

            destination_dir = (self.skills_root / _slugify_skill_name(skill.name)).resolve()
            backup_path: str | None = None
            if prepared.source_root == destination_dir:
                destination_dir.mkdir(parents=True, exist_ok=True)
            else:
                if destination_dir.exists() and overwrite:
                    backup_path = self._backup_existing_skill(skill.name, destination_dir)
                self._prepare_destination(destination_dir, overwrite=overwrite)
                if prepared.skill_file.parent == prepared.source_root:
                    shutil.copytree(prepared.source_root, destination_dir)
                else:
                    destination_dir.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(prepared.skill_file, destination_dir / "SKILL.md")

            installed_skill_file = destination_dir / "SKILL.md"
            installed_raw = installed_skill_file.read_text(encoding="utf-8")
            installed_skill = parse_skill_markdown(
                installed_raw,
                source=SkillSource.WORKSPACE,
                skill_file=installed_skill_file,
            )
            if installed_skill is None:
                raise ValueError(f"Installed skill validation failed: {installed_skill_file}")

            policy = self.policy_store.enable([installed_skill.name]) if activate else self.policy_store.load()
            base_result = WorkspaceSkillInstallResult(
                skill_name=installed_skill.name,
                description=installed_skill.description,
                installed_path=str(destination_dir),
                source_kind=prepared.source_kind,
                source_path=prepared.original_ref,
                activated=bool(activate),
                overwrite=bool(overwrite),
                policy=policy,
                backup_path=backup_path,
            )
            ledger_path = self.source_ledger.record_install(
                base_result,
                policy_state=self._policy_state(installed_skill.name, policy),
                backup_path=backup_path,
            )
            _discover_loader(loader)
            return WorkspaceSkillInstallResult(**{**base_result.__dict__, "ledger_path": ledger_path})
        finally:
            prepared.cleanup()

    def install_inline(
        self,
        *,
        skill_name: str,
        description: str,
        instructions: str,
        activate: bool = True,
        overwrite: bool = False,
        loader: Any | None = None,
    ) -> WorkspaceSkillInstallResult:
        normalized_name = str(skill_name or "").strip()
        normalized_description = str(description or "").strip()
        normalized_instructions = str(instructions or "").strip()
        if not normalized_name or not normalized_description or not normalized_instructions:
            raise ValueError("Skill name, description, and instructions are required.")

        raw = self._render_skill_markdown(
            normalized_name,
            normalized_description,
            normalized_instructions,
        )
        parsed = parse_skill_markdown(raw, source=SkillSource.WORKSPACE)
        if parsed is None:
            raise ValueError("Inline skill content is invalid.")

        destination_dir = (self.skills_root / _slugify_skill_name(parsed.name)).resolve()
        backup_path: str | None = None
        if destination_dir.exists() and overwrite:
            backup_path = self._backup_existing_skill(parsed.name, destination_dir)
        self._prepare_destination(destination_dir, overwrite=overwrite)
        destination_dir.mkdir(parents=True, exist_ok=True)
        installed_skill_file = destination_dir / "SKILL.md"
        installed_skill_file.write_text(raw, encoding="utf-8")

        installed_skill = parse_skill_markdown(
            installed_skill_file.read_text(encoding="utf-8"),
            source=SkillSource.WORKSPACE,
            skill_file=installed_skill_file,
        )
        if installed_skill is None:
            raise ValueError(f"Installed skill validation failed: {installed_skill_file}")

        policy = self.policy_store.enable([installed_skill.name]) if activate else self.policy_store.load()
        base_result = WorkspaceSkillInstallResult(
            skill_name=installed_skill.name,
            description=installed_skill.description,
            installed_path=str(destination_dir),
            source_kind="inline",
            source_path=None,
            activated=bool(activate),
            overwrite=bool(overwrite),
            policy=policy,
            backup_path=backup_path,
        )
        ledger_path = self.source_ledger.record_install(
            base_result,
            policy_state=self._policy_state(installed_skill.name, policy),
            backup_path=backup_path,
        )
        _discover_loader(loader)
        return WorkspaceSkillInstallResult(**{**base_result.__dict__, "ledger_path": ledger_path})

    def uninstall(
        self,
        skill_name: str,
        *,
        loader: Any | None = None,
    ) -> WorkspaceSkillUninstallResult:
        normalized_name = normalize_skill_name(skill_name)
        if not normalized_name:
            raise ValueError("Skill name is required.")
        current = self.source_ledger.current_entry(normalized_name)
        destination_dir = (self.skills_root / _slugify_skill_name(normalized_name)).resolve()
        if current and str(current.get("installed_path") or "").strip():
            destination_dir = Path(str(current.get("installed_path"))).expanduser().resolve()
        if not destination_dir.exists():
            raise FileNotFoundError(f"Installed skill not found: {normalized_name}")
        backup_path = self._backup_existing_skill(normalized_name, destination_dir)
        shutil.rmtree(destination_dir)
        updated_policy = self.policy_store.forget([normalized_name])
        ledger_path = self.source_ledger.record_uninstall(
            skill_name=normalized_name,
            description=str((current or {}).get("description") or normalized_name),
            removed_path=str(destination_dir),
            source_kind=str((current or {}).get("source_kind") or "") or None,
            source_path=str((current or {}).get("source_path") or "") or None,
            policy_state=str((current or {}).get("policy_state") or "implicit"),
            backup_path=backup_path,
        )
        _discover_loader(loader)
        return WorkspaceSkillUninstallResult(
            skill_name=normalized_name,
            removed_path=str(destination_dir),
            backup_path=backup_path,
            source_kind=str((current or {}).get("source_kind") or "") or None,
            source_path=str((current or {}).get("source_path") or "") or None,
            policy=updated_policy,
            ledger_path=ledger_path,
        )

    def rollback(
        self,
        skill_name: str,
        *,
        loader: Any | None = None,
    ) -> WorkspaceSkillRollbackResult:
        normalized_name = normalize_skill_name(skill_name)
        if not normalized_name:
            raise ValueError("Skill name is required.")
        entry = self.source_ledger.latest_backup_entry(normalized_name)
        if entry is None:
            raise FileNotFoundError(f"No rollback backup found for skill: {normalized_name}")
        backup_path = Path(str(entry.get("backup_path") or "")).expanduser().resolve()
        if not backup_path.exists():
            raise FileNotFoundError(f"Rollback backup missing for skill: {normalized_name}")
        destination_dir = (self.skills_root / _slugify_skill_name(normalized_name)).resolve()
        if destination_dir.exists():
            shutil.rmtree(destination_dir)
        shutil.copytree(backup_path, destination_dir)

        policy_state = str(entry.get("policy_state") or "implicit").strip().lower()
        if policy_state == "denylist":
            updated_policy = self.policy_store.disable([normalized_name])
        elif policy_state == "allowlist":
            updated_policy = self.policy_store.enable([normalized_name])
        else:
            updated_policy = self.policy_store.forget([normalized_name])

        installed_skill_file = destination_dir / "SKILL.md"
        installed_raw = installed_skill_file.read_text(encoding="utf-8")
        installed_skill = parse_skill_markdown(
            installed_raw,
            source=SkillSource.WORKSPACE,
            skill_file=installed_skill_file,
        )
        if installed_skill is None:
            raise ValueError(f"Rollback validation failed: {installed_skill_file}")
        base_result = WorkspaceSkillInstallResult(
            skill_name=installed_skill.name,
            description=installed_skill.description,
            installed_path=str(destination_dir),
            source_kind=str(entry.get("source_kind") or "rollback"),
            source_path=str(entry.get("source_path") or "") or None,
            activated=policy_state != "denylist",
            overwrite=True,
            policy=updated_policy,
            backup_path=str(backup_path),
        )
        ledger_path = self.source_ledger.record_install(
            base_result,
            policy_state=self._policy_state(installed_skill.name, updated_policy),
            action="rollback",
            backup_path=str(backup_path),
        )
        _discover_loader(loader)
        return WorkspaceSkillRollbackResult(
            skill_name=installed_skill.name,
            restored_path=str(destination_dir),
            backup_path=str(backup_path),
            source_kind=str(entry.get("source_kind") or "rollback"),
            source_path=str(entry.get("source_path") or "") or None,
            policy=updated_policy,
            ledger_path=ledger_path,
        )

    @staticmethod
    def _render_skill_markdown(name: str, description: str, instructions: str) -> str:
        return (
            "---\n"
            f"name: {name}\n"
            f"description: {description}\n"
            "---\n\n"
            f"{instructions.strip()}\n"
        )

    def _prepare_destination(self, destination_dir: Path, *, overwrite: bool) -> None:
        self.skills_root.mkdir(parents=True, exist_ok=True)
        if not destination_dir.exists():
            return
        if not overwrite:
            raise FileExistsError(f"Skill already exists: {destination_dir.name}")
        try:
            destination_dir.relative_to(self.skills_root)
        except ValueError as exc:
            raise ValueError(f"Destination escapes workspace skill root: {destination_dir}") from exc
        shutil.rmtree(destination_dir)

    def _prepare_source(self, source_path: str | Path) -> _PreparedSkillSource:
        raw_source = str(source_path or "").strip()
        if not raw_source:
            raise ValueError("Skill source must not be empty.")
        if self._is_remote_url(raw_source):
            return self._prepare_remote_source(raw_source)
        return self._prepare_local_source(Path(raw_source).expanduser().resolve(), original_ref=raw_source)

    def _prepare_remote_source(self, source_url: str) -> _PreparedSkillSource:
        self.workspace_dir.mkdir(parents=True, exist_ok=True)
        temp_root = Path(tempfile.mkdtemp(prefix="mini-agent-skill-url-", dir=str(self.workspace_dir)))
        parsed = urlparse(source_url)
        filename = Path(parsed.path or "").name or "downloaded-skill"
        target = temp_root / filename
        response = requests.get(source_url, timeout=30)
        response.raise_for_status()
        target.write_bytes(response.content)
        try:
            return self._prepare_local_source(target, original_ref=source_url, remote=True, temp_root=temp_root)
        except Exception:
            shutil.rmtree(temp_root, ignore_errors=True)
            raise

    def _prepare_local_source(
        self,
        source_path: Path,
        *,
        original_ref: str,
        remote: bool = False,
        temp_root: Path | None = None,
    ) -> _PreparedSkillSource:
        if source_path.is_dir():
            skill_file = source_path / "SKILL.md"
            if not skill_file.exists():
                raise FileNotFoundError(f"Skill directory does not contain SKILL.md: {source_path}")
            return _PreparedSkillSource(
                source_kind="url_directory" if remote else "directory",
                original_ref=original_ref,
                source_root=source_path,
                skill_file=skill_file,
                temp_root=temp_root,
            )
        if source_path.is_file() and source_path.name.upper() == "SKILL.MD":
            return _PreparedSkillSource(
                source_kind="url_file" if remote else "file",
                original_ref=original_ref,
                source_root=source_path.parent,
                skill_file=source_path,
                temp_root=temp_root,
            )
        if source_path.is_file() and self._is_archive_path(source_path):
            self.workspace_dir.mkdir(parents=True, exist_ok=True)
            extract_root = temp_root or Path(tempfile.mkdtemp(prefix="mini-agent-skill-archive-", dir=str(self.workspace_dir)))
            unpack_dir = extract_root / "unpacked"
            unpack_dir.mkdir(parents=True, exist_ok=True)
            self._extract_archive(source_path, unpack_dir)
            skill_root, skill_file = self._find_skill_root_in_tree(unpack_dir)
            return _PreparedSkillSource(
                source_kind="url_archive" if remote else "archive",
                original_ref=original_ref,
                source_root=skill_root,
                skill_file=skill_file,
                temp_root=extract_root,
            )
        raise FileNotFoundError(f"Skill source not found: {source_path}")

    def _backup_existing_skill(self, skill_name: str, source_dir: Path) -> str:
        source_dir = source_dir.expanduser().resolve()
        try:
            source_dir.relative_to(self.skills_root)
        except Exception as exc:
            raise ValueError(f"Cannot back up skill outside workspace skill root: {source_dir}") from exc
        self.backup_root.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup_dir = (self.backup_root / _slugify_skill_name(skill_name) / stamp).resolve()
        backup_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_dir, backup_dir)
        return str(backup_dir)

    @staticmethod
    def _is_remote_url(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _is_archive_path(path: Path) -> bool:
        name = path.name.lower()
        return (
            name.endswith(".zip")
            or name.endswith(".tar")
            or name.endswith(".tgz")
            or name.endswith(".tar.gz")
            or name.endswith(".tar.bz2")
            or name.endswith(".tbz2")
            or name.endswith(".tar.xz")
            or name.endswith(".txz")
        )

    @staticmethod
    def _extract_archive(source_path: Path, destination_dir: Path) -> None:
        name = source_path.name.lower()
        if name.endswith(".zip"):
            with zipfile.ZipFile(source_path) as archive:
                for member in archive.infolist():
                    WorkspaceSkillInstaller._ensure_archive_member_within_destination(
                        member.filename,
                        destination_dir,
                    )
                archive.extractall(destination_dir)
            return
        if tarfile.is_tarfile(source_path):
            with tarfile.open(source_path) as archive:
                for member in archive.getmembers():
                    WorkspaceSkillInstaller._ensure_archive_member_within_destination(
                        member.name,
                        destination_dir,
                    )
                archive.extractall(destination_dir)
            return
        raise ValueError(f"Unsupported skill archive: {source_path}")

    @staticmethod
    def _ensure_archive_member_within_destination(member_name: str, destination_dir: Path) -> None:
        normalized = str(member_name or "").replace("\\", "/").strip()
        if not normalized:
            return
        target = (destination_dir / normalized).resolve()
        destination_root = destination_dir.resolve()
        try:
            target.relative_to(destination_root)
        except ValueError as exc:
            raise ValueError(f"Archive member escapes destination: {member_name}") from exc

    @staticmethod
    def _find_skill_root_in_tree(root: Path) -> tuple[Path, Path]:
        skill_files = sorted(path for path in root.rglob("SKILL.md") if path.is_file())
        if not skill_files:
            raise FileNotFoundError(f"No SKILL.md found in extracted archive: {root}")
        if len(skill_files) > 1:
            relative = ", ".join(path.relative_to(root).as_posix() for path in skill_files[:5])
            raise ValueError(
                "Archive contains multiple SKILL.md files; package one skill per archive. "
                f"Found: {relative}"
            )
        skill_file = skill_files[0]
        return skill_file.parent, skill_file

    @staticmethod
    def _policy_state(skill_name: str, policy: WorkspaceSkillPolicy) -> str:
        target = normalize_skill_name(skill_name).casefold()
        allowlist = {normalize_skill_name(item).casefold() for item in policy.allowlist}
        denylist = {normalize_skill_name(item).casefold() for item in policy.denylist}
        if target in denylist:
            return "denylist"
        if target in allowlist:
            return "allowlist"
        return "implicit"
