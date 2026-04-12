"""Agent-core skills loader with progressive disclosure tiers."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Iterable

import yaml

from mini_agent.agent_core.skills.eligibility import (
    SkillEligibilityChecker,
    SkillRequirements,
    parse_skill_requirements,
)
from mini_agent.agent_core.skills.registry import AgentSkill, SkillRegistry, SkillSource


@dataclass(frozen=True)
class SkillTier1Metadata:
    """Tier-1 skill metadata exposed in system prompts."""

    name: str
    description: str
    source: SkillSource
    eligible: bool
    blocked_reason: str | None
    skill_key: str
    always: bool
    skill_file: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


def parse_skill_markdown(
    raw: str,
    *,
    source: SkillSource,
    eligibility_checker: SkillEligibilityChecker | None = None,
    skill_file: Path | None = None,
) -> AgentSkill | None:
    """Parse raw skill markdown into a canonical `AgentSkill`."""

    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", raw, flags=re.DOTALL)
    if not match:
        return None

    try:
        frontmatter = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        return None

    if not isinstance(frontmatter, dict):
        return None

    name = str(frontmatter.get("name", "")).strip()
    description = str(frontmatter.get("description", "")).strip()
    if not name or not description:
        return None

    checker = eligibility_checker or SkillEligibilityChecker()
    instructions = match.group(2).strip()
    requirements = parse_skill_requirements(frontmatter)
    eligibility = checker.check(requirements)
    metadata = frontmatter.get("metadata") if isinstance(frontmatter.get("metadata"), dict) else {}

    return AgentSkill(
        name=name,
        description=description,
        instructions=instructions,
        source=source,
        frontmatter=frontmatter,
        requirements=requirements,
        eligibility=eligibility,
        skill_file=skill_file.resolve() if skill_file is not None else None,
        metadata=dict(metadata),
    )


class AgentSkillLoader:
    """Load skills from builtin/workspace/plugin/remote sources."""

    def __init__(
        self,
        *,
        builtin_dir: str | Path,
        workspace_dir: str | Path | None = None,
        plugin_dirs: Iterable[str | Path] | None = None,
        eligibility_checker: SkillEligibilityChecker | None = None,
    ) -> None:
        self.builtin_dir = Path(builtin_dir)
        self.workspace_dir = Path(workspace_dir) if workspace_dir else None
        self.plugin_dirs = [Path(path) for path in (plugin_dirs or [])]
        self.eligibility_checker = eligibility_checker or SkillEligibilityChecker()
        self.registry = SkillRegistry()
        self._remote_skills: dict[str, AgentSkill] = {}

    def _iter_skill_files(self, root: Path) -> list[Path]:
        if not root.exists():
            return []
        return sorted(root.rglob("SKILL.md"))

    def _parse_skill_file(self, skill_file: Path, source: SkillSource) -> AgentSkill | None:
        try:
            raw = skill_file.read_text(encoding="utf-8")
        except Exception:
            return None
        return parse_skill_markdown(
            raw,
            source=source,
            eligibility_checker=self.eligibility_checker,
            skill_file=skill_file,
        )

    def discover(self) -> list[SkillTier1Metadata]:
        """Discover all local skills and refresh registry."""
        self.registry.clear()

        for skill_file in self._iter_skill_files(self.builtin_dir):
            skill = self._parse_skill_file(skill_file, SkillSource.BUILTIN)
            if skill:
                self.registry.register(skill)

        if self.workspace_dir:
            for skill_file in self._iter_skill_files(self.workspace_dir):
                skill = self._parse_skill_file(skill_file, SkillSource.WORKSPACE)
                if skill:
                    self.registry.register(skill)

        for plugin_dir in self.plugin_dirs:
            for skill_file in self._iter_skill_files(plugin_dir):
                skill = self._parse_skill_file(skill_file, SkillSource.PLUGIN)
                if skill:
                    self.registry.register(skill)

        for skill in self._remote_skills.values():
            self.registry.register(skill)

        return self.list_tier1(eligible_only=False)

    def register_remote_skill(
        self,
        *,
        name: str,
        description: str,
        instructions: str,
        metadata: dict[str, Any] | None = None,
        requirements: SkillRequirements | None = None,
    ) -> None:
        """Register one remote skill entry for the current loader."""
        normalized_name = name.strip()
        normalized_description = description.strip()
        if not normalized_name or not normalized_description:
            raise ValueError("Remote skill name/description must not be empty.")

        req = requirements or SkillRequirements()
        eligibility = self.eligibility_checker.check(req)
        skill = AgentSkill(
            name=normalized_name,
            description=normalized_description,
            instructions=instructions.strip(),
            source=SkillSource.REMOTE,
            frontmatter={
                "name": normalized_name,
                "description": normalized_description,
            },
            requirements=req,
            eligibility=eligibility,
            skill_file=None,
            metadata=dict(metadata or {}),
        )
        self._remote_skills[normalized_name] = skill
        self.registry.register(skill)

    def get_skill(self, name: str, *, eligible_only: bool = False) -> AgentSkill | None:
        skill = self.registry.get(name)
        if skill is None:
            return None
        if eligible_only and not skill.eligibility.eligible:
            return None
        return skill

    def list_tier1(self, *, eligible_only: bool = True) -> list[SkillTier1Metadata]:
        records = self.registry.list(eligible_only=eligible_only)
        metadata: list[SkillTier1Metadata] = []
        for item in records:
            skill_key = str(item.frontmatter.get("skillKey", item.name.upper())).strip()
            always = bool(item.frontmatter.get("always", False))
            metadata.append(
                SkillTier1Metadata(
                    name=item.name,
                    description=item.description,
                    source=item.source,
                    eligible=item.eligibility.eligible,
                    blocked_reason=item.eligibility.blocked_reason(),
                    skill_key=skill_key,
                    always=always,
                    skill_file=str(item.skill_file) if item.skill_file else None,
                    metadata=dict(item.metadata or {}),
                )
            )
        return metadata

    def get_skills_metadata_prompt(self, *, eligible_only: bool = True) -> str:
        entries = self.list_tier1(eligible_only=eligible_only)
        if not entries:
            return ""

        lines = [
            "## Available Skills",
            "",
            "Skill metadata below is only a routing hint, not the full workflow.",
            "If a skill is relevant, call `get_skill(skill_name)` before relying on it, summarizing it, or claiming you will use it.",
            "If the task spans multiple domains, you may load more than one relevant skill.",
        ]
        for item in entries:
            suffix = f" [{item.source.value}]"
            lines.append(f"- `{item.name}`{suffix}: {item.description}")
        return "\n".join(lines)

    def load_tier2(self, name: str, *, eligible_only: bool = True) -> str | None:
        skill = self.get_skill(name, eligible_only=eligible_only)
        if skill is None:
            return None
        return skill.to_prompt()

    def list_tier3_files(
        self,
        name: str,
        *,
        directories: tuple[str, ...] = ("references", "templates", "scripts", "assets"),
        max_files: int = 200,
        eligible_only: bool = True,
    ) -> list[str]:
        skill = self.get_skill(name, eligible_only=eligible_only)
        if skill is None or skill.root_dir() is None:
            return []

        root = skill.root_dir()
        assert root is not None
        collected: list[str] = []
        for directory in directories:
            candidate = root / directory
            if not candidate.exists() or not candidate.is_dir():
                continue
            for item in sorted(candidate.rglob("*")):
                if not item.is_file():
                    continue
                relative = item.relative_to(root).as_posix()
                collected.append(relative)
                if len(collected) >= max_files:
                    return collected
        return collected

    def read_tier3_file(
        self,
        name: str,
        relative_path: str,
        *,
        max_chars: int = 20000,
        eligible_only: bool = True,
    ) -> str:
        skill = self.get_skill(name, eligible_only=eligible_only)
        if skill is None or skill.root_dir() is None:
            raise ValueError(f"Skill not found or unavailable: {name}")

        root = skill.root_dir()
        assert root is not None
        target = (root / relative_path).resolve()
        try:
            target.relative_to(root)
        except Exception as exc:
            raise ValueError(f"Path escapes skill root: {relative_path}") from exc

        if not target.exists() or not target.is_file():
            raise ValueError(f"Tier-3 file not found: {relative_path}")

        content = target.read_text(encoding="utf-8", errors="replace")
        if len(content) > max_chars:
            return content[:max_chars] + f"\n...[truncated to {max_chars} chars]"
        return content

    def build_runtime_bridge(self, *, eligible_only: bool = True) -> "AgentSkillRuntimeBridge":
        return AgentSkillRuntimeBridge(self, eligible_only=eligible_only)


class AgentSkillRuntimeBridge:
    """Bridge exposing SkillTool-compatible APIs over agent-core loader."""

    def __init__(self, loader: AgentSkillLoader, *, eligible_only: bool = True):
        self.loader = loader
        self.eligible_only = bool(eligible_only)

    def get_skill(self, name: str) -> AgentSkill | None:
        return self.loader.get_skill(name, eligible_only=self.eligible_only)

    def list_skills(self) -> list[str]:
        return self.loader.registry.names(eligible_only=self.eligible_only)

    def get_skills_metadata_prompt(self) -> str:
        return self.loader.get_skills_metadata_prompt(eligible_only=self.eligible_only)
