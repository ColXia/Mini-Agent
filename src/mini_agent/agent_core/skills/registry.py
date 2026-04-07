"""Skill registry with source-priority resolution."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from mini_agent.agent_core.skills.eligibility import SkillEligibilityResult, SkillRequirements


class SkillSource(str, Enum):
    """Skill source types."""

    BUILTIN = "builtin"
    WORKSPACE = "workspace"
    PLUGIN = "plugin"
    REMOTE = "remote"


SOURCE_PRIORITY: dict[SkillSource, int] = {
    SkillSource.BUILTIN: 10,
    SkillSource.PLUGIN: 20,
    SkillSource.WORKSPACE: 30,
    SkillSource.REMOTE: 40,
}


@dataclass(frozen=True)
class AgentSkill:
    """Canonical skill record used by agent-core runtime."""

    name: str
    description: str
    instructions: str
    source: SkillSource
    frontmatter: dict[str, Any]
    requirements: SkillRequirements
    eligibility: SkillEligibilityResult
    skill_file: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def root_dir(self) -> Path | None:
        return self.skill_file.parent if self.skill_file else None

    def to_prompt(self) -> str:
        root = str(self.root_dir()) if self.root_dir() else self.source.value
        return (
            f"# Skill: {self.name}\n\n"
            f"{self.description}\n\n"
            f"**Skill Root Directory:** `{root}`\n\n"
            "All relative file references are resolved from this root.\n\n"
            "---\n\n"
            f"{self.instructions}"
        )


class SkillRegistry:
    """Registry resolving duplicate skills by source priority."""

    def __init__(self) -> None:
        self._skills: dict[str, AgentSkill] = {}

    def clear(self) -> None:
        self._skills.clear()

    def register(self, skill: AgentSkill) -> None:
        existing = self._skills.get(skill.name)
        if existing is None:
            self._skills[skill.name] = skill
            return

        existing_priority = SOURCE_PRIORITY.get(existing.source, 0)
        incoming_priority = SOURCE_PRIORITY.get(skill.source, 0)
        if incoming_priority >= existing_priority:
            self._skills[skill.name] = skill

    def get(self, name: str) -> AgentSkill | None:
        return self._skills.get(name)

    def list(self, *, eligible_only: bool = False) -> list[AgentSkill]:
        records = sorted(self._skills.values(), key=lambda item: item.name.lower())
        if not eligible_only:
            return records
        return [item for item in records if item.eligibility.eligible]

    def names(self, *, eligible_only: bool = False) -> list[str]:
        return [item.name for item in self.list(eligible_only=eligible_only)]
