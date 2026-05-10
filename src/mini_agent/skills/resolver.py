"""Skill resolver for three-layer skill resolution.

This module provides the SkillResolver for resolving skills across three layers:
- Internal Skills (core.*): Agent built-in, cannot be overridden
- Global Skills (global.*): System-level, shared across workspaces
- Workspace Skills (ws.*): Workspace-specific, local extensions

Resolution follows the assembly model, not override model:
- Internal skills are reserved and cannot be overridden
- Global skills are shared extensions
- Workspace skills are local extensions
- Final output is a ResolvedSkillSet
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from mini_agent.utils.text import safe_text


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_text(value: Any) -> str:
    return safe_text(value)


class SkillLayer(str, Enum):
    """Skill layer types for three-layer resolution."""

    INTERNAL = "internal"
    GLOBAL = "global"
    WORKSPACE = "workspace"


class SkillNamespace(str, Enum):
    """Skill namespace prefixes."""

    CORE = "core"
    GLOBAL = "global"
    WORKSPACE = "ws"


LAYER_NAMESPACE_MAP: dict[SkillLayer, SkillNamespace] = {
    SkillLayer.INTERNAL: SkillNamespace.CORE,
    SkillLayer.GLOBAL: SkillNamespace.GLOBAL,
    SkillLayer.WORKSPACE: SkillNamespace.WORKSPACE,
}


@dataclass(frozen=True, slots=True)
class SkillSpec:
    """Skill specification with layer metadata.

    This represents a skill definition at a specific layer.
    """

    skill_name: str
    layer: SkillLayer
    description: str = ""
    instructions: str = ""
    skill_file: Path | None = None
    requirements: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        normalized_name = _safe_text(self.skill_name)
        if not normalized_name:
            raise ValueError("skill_name is required")
        object.__setattr__(self, "skill_name", normalized_name)
        object.__setattr__(self, "description", _safe_text(self.description))
        object.__setattr__(self, "instructions", _safe_text(self.instructions))
        object.__setattr__(self, "requirements", dict(self.requirements) if self.requirements else {})
        object.__setattr__(self, "metadata", dict(self.metadata) if self.metadata else {})
        if self.created_at is None:
            object.__setattr__(self, "created_at", _utc_now())

    @property
    def full_name(self) -> str:
        """Return the fully qualified skill name."""
        namespace = LAYER_NAMESPACE_MAP[self.layer]
        return f"{namespace.value}.{self.skill_name}"

    @property
    def is_internal(self) -> bool:
        """Return True if this is an internal skill."""
        return self.layer == SkillLayer.INTERNAL


@dataclass(frozen=True, slots=True)
class ResolvedSkill:
    """A resolved skill with its source layer information."""

    skill_name: str
    full_name: str
    source_layer: SkillLayer
    description: str
    instructions: str
    skill_file: Path | None = None
    requirements: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_prompt(self) -> str:
        """Generate a prompt representation of this skill."""
        root = str(self.skill_file.parent) if self.skill_file else self.source_layer.value
        return (
            f"# Skill: {self.full_name}\n\n"
            f"{self.description}\n\n"
            f"**Source Layer:** {self.source_layer.value}\n"
            f"**Skill Root Directory:** `{root}`\n\n"
            "---\n\n"
            f"{self.instructions}"
        )


@dataclass(frozen=True, slots=True)
class ResolvedSkillSet:
    """A set of resolved skills for a run.

    This is the final output of skill resolution, containing all skills
    available to a run after three-layer assembly.
    """

    workspace_id: str
    session_id: str
    run_id: str
    skills: tuple[ResolvedSkill, ...] = ()
    internal_skill_names: tuple[str, ...] = ()
    global_skill_names: tuple[str, ...] = ()
    workspace_skill_names: tuple[str, ...] = ()
    resolution_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.resolution_timestamp is None:
            object.__setattr__(self, "resolution_timestamp", _utc_now())

    @property
    def skill_count(self) -> int:
        """Return the total number of skills."""
        return len(self.skills)

    def get_skill(self, skill_name: str) -> ResolvedSkill | None:
        """Get a skill by name (with or without namespace prefix)."""
        normalized = _safe_text(skill_name)
        for skill in self.skills:
            if skill.skill_name == normalized or skill.full_name == normalized:
                return skill
        return None

    def has_skill(self, skill_name: str) -> bool:
        """Check if a skill is available."""
        return self.get_skill(skill_name) is not None

    def list_skill_names(self) -> list[str]:
        """List all skill full names."""
        return [skill.full_name for skill in self.skills]


@dataclass(slots=True)
class InternalSkillRegistry:
    """Registry for internal (core) skills.

    Internal skills are built into the agent and cannot be overridden.
    They belong to the AgentProfile, not to any workspace.
    """

    _skills: dict[str, SkillSpec] = field(default_factory=dict)

    def register(self, spec: SkillSpec) -> SkillSpec:
        """Register an internal skill."""
        if spec.layer != SkillLayer.INTERNAL:
            raise ValueError("Only internal skills can be registered in InternalSkillRegistry")
        full_name = spec.full_name
        self._skills[full_name] = spec
        return spec

    def get(self, skill_name: str) -> SkillSpec | None:
        """Get an internal skill by name."""
        normalized = _safe_text(skill_name)
        if "." in normalized:
            return self._skills.get(normalized)
        return self._skills.get(f"core.{normalized}")

    def list_all(self) -> list[SkillSpec]:
        """List all internal skills."""
        return list(self._skills.values())


@dataclass(slots=True)
class GlobalSkillRegistry:
    """Registry for global skills.

    Global skills are installed at the system/user level and shared
    across all workspaces. They can be extended by workspace skills.
    """

    _skills: dict[str, SkillSpec] = field(default_factory=dict)

    def register(self, spec: SkillSpec) -> SkillSpec:
        """Register a global skill."""
        if spec.layer != SkillLayer.GLOBAL:
            raise ValueError("Only global skills can be registered in GlobalSkillRegistry")
        full_name = spec.full_name
        self._skills[full_name] = spec
        return spec

    def get(self, skill_name: str) -> SkillSpec | None:
        """Get a global skill by name."""
        normalized = _safe_text(skill_name)
        if "." in normalized:
            return self._skills.get(normalized)
        return self._skills.get(f"global.{normalized}")

    def list_all(self) -> list[SkillSpec]:
        """List all global skills."""
        return list(self._skills.values())


@dataclass(slots=True)
class WorkspaceSkillRegistry:
    """Registry for workspace-specific skills.

    Workspace skills are local to a specific workspace and do not
    propagate to other workspaces or the global registry.
    """

    workspace_id: str
    _skills: dict[str, SkillSpec] = field(default_factory=dict)

    def register(self, spec: SkillSpec) -> SkillSpec:
        """Register a workspace skill."""
        if spec.layer != SkillLayer.WORKSPACE:
            raise ValueError("Only workspace skills can be registered in WorkspaceSkillRegistry")
        full_name = spec.full_name
        self._skills[full_name] = spec
        return spec

    def get(self, skill_name: str) -> SkillSpec | None:
        """Get a workspace skill by name."""
        normalized = _safe_text(skill_name)
        if "." in normalized:
            return self._skills.get(normalized)
        return self._skills.get(f"ws.{normalized}")

    def list_all(self) -> list[SkillSpec]:
        """List all workspace skills."""
        return list(self._skills.values())


@dataclass(slots=True)
class SkillResolver:
    """Resolver for three-layer skill assembly.

    This resolver assembles skills from internal, global, and workspace
    layers following the assembly model:
    - Internal skills are reserved (cannot be overridden)
    - Global skills extend the internal set
    - Workspace skills extend the combined set
    """

    internal_registry: InternalSkillRegistry = field(default_factory=InternalSkillRegistry)
    global_registry: GlobalSkillRegistry = field(default_factory=GlobalSkillRegistry)
    workspace_registries: dict[str, WorkspaceSkillRegistry] = field(default_factory=dict)

    def get_or_create_workspace_registry(self, workspace_id: str) -> WorkspaceSkillRegistry:
        """Get or create a workspace skill registry."""
        normalized_workspace_id = _safe_text(workspace_id)
        if normalized_workspace_id not in self.workspace_registries:
            self.workspace_registries[normalized_workspace_id] = WorkspaceSkillRegistry(
                workspace_id=normalized_workspace_id
            )
        return self.workspace_registries[normalized_workspace_id]

    def resolve(
        self,
        workspace_id: str,
        session_id: str,
        run_id: str,
    ) -> ResolvedSkillSet:
        """Resolve skills for a specific run.

        Args:
            workspace_id: The workspace ID
            session_id: The session ID
            run_id: The run ID

        Returns:
            A ResolvedSkillSet containing all assembled skills
        """
        resolved_skills: list[ResolvedSkill] = []
        internal_names: list[str] = []
        global_names: list[str] = []
        workspace_names: list[str] = []

        for spec in self.internal_registry.list_all():
            resolved_skills.append(self._to_resolved_skill(spec))
            internal_names.append(spec.full_name)

        for spec in self.global_registry.list_all():
            if not self._is_internal_skill(spec.skill_name):
                resolved_skills.append(self._to_resolved_skill(spec))
                global_names.append(spec.full_name)

        workspace_registry = self.workspace_registries.get(_safe_text(workspace_id))
        if workspace_registry is not None:
            for spec in workspace_registry.list_all():
                if not self._is_internal_skill(spec.skill_name):
                    existing = self._find_skill(resolved_skills, spec.skill_name)
                    if existing is None:
                        resolved_skills.append(self._to_resolved_skill(spec))
                        workspace_names.append(spec.full_name)

        return ResolvedSkillSet(
            workspace_id=_safe_text(workspace_id),
            session_id=_safe_text(session_id),
            run_id=_safe_text(run_id),
            skills=tuple(resolved_skills),
            internal_skill_names=tuple(internal_names),
            global_skill_names=tuple(global_names),
            workspace_skill_names=tuple(workspace_names),
        )

    def _to_resolved_skill(self, spec: SkillSpec) -> ResolvedSkill:
        """Convert a SkillSpec to a ResolvedSkill."""
        return ResolvedSkill(
            skill_name=spec.skill_name,
            full_name=spec.full_name,
            source_layer=spec.layer,
            description=spec.description,
            instructions=spec.instructions,
            skill_file=spec.skill_file,
            requirements=spec.requirements,
            metadata=spec.metadata,
        )

    def _is_internal_skill(self, skill_name: str) -> bool:
        """Check if a skill name conflicts with an internal skill."""
        normalized = _safe_text(skill_name)
        return self.internal_registry.get(normalized) is not None

    def _find_skill(self, skills: list[ResolvedSkill], skill_name: str) -> ResolvedSkill | None:
        """Find a skill in a list by name."""
        normalized = _safe_text(skill_name)
        for skill in skills:
            if skill.skill_name == normalized:
                return skill
        return None

    def clear(self) -> None:
        """Clear all registries."""
        self.internal_registry._skills.clear()
        self.global_registry._skills.clear()
        self.workspace_registries.clear()


_SHARED_RESOLVER: SkillResolver | None = None


def shared_skill_resolver() -> SkillResolver:
    """Return the process-local shared skill resolver."""
    global _SHARED_RESOLVER
    if _SHARED_RESOLVER is None:
        _SHARED_RESOLVER = SkillResolver()
    return _SHARED_RESOLVER


def clear_shared_skill_resolver() -> None:
    """Clear the process-local shared skill resolver."""
    global _SHARED_RESOLVER
    if _SHARED_RESOLVER is not None:
        _SHARED_RESOLVER.clear()
    _SHARED_RESOLVER = None


__all__ = [
    "clear_shared_skill_resolver",
    "GlobalSkillRegistry",
    "InternalSkillRegistry",
    "ResolvedSkill",
    "ResolvedSkillSet",
    "shared_skill_resolver",
    "SkillLayer",
    "SkillNamespace",
    "SkillResolver",
    "SkillSpec",
    "WorkspaceSkillRegistry",
]