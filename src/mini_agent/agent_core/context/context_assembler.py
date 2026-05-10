"""Context assembler for assembling agent context from multiple sources.

This module provides the ContextAssembler for assembling context from:
- Skills (resolved via SkillResolver)
- Memory (resolved via MemoryResolver)
- Workspace state
- Session state
- System prompts

The assembled context is used to build the agent's prompt for each turn.
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


class ContextSourceKind(str, Enum):
    """Kinds of context sources."""

    SYSTEM = "system"
    SKILL = "skill"
    MEMORY = "memory"
    WORKSPACE = "workspace"
    SESSION = "session"
    USER = "user"


@dataclass(frozen=True, slots=True)
class ContextSection:
    """A single section in the assembled context."""

    source_kind: ContextSourceKind
    source_id: str
    title: str
    content: str
    priority: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_id", _safe_text(self.source_id))
        object.__setattr__(self, "title", _safe_text(self.title))
        object.__setattr__(self, "content", _safe_text(self.content))
        object.__setattr__(self, "metadata", dict(self.metadata) if self.metadata else {})
        if self.created_at is None:
            object.__setattr__(self, "created_at", _utc_now())

    def to_prompt(self) -> str:
        """Generate prompt representation of this section."""
        if self.title:
            return f"## {self.title}\n\n{self.content}"
        return self.content


@dataclass(frozen=True, slots=True)
class AssembledContext:
    """Assembled context for agent prompt."""

    workspace_id: str
    session_id: str
    run_id: str
    sections: tuple[ContextSection, ...] = ()
    total_chars: int = 0
    assembly_timestamp: datetime | None = None

    def __post_init__(self) -> None:
        if self.assembly_timestamp is None:
            object.__setattr__(self, "assembly_timestamp", _utc_now())

    @property
    def section_count(self) -> int:
        """Return the number of sections."""
        return len(self.sections)

    def get_sections_by_kind(self, kind: ContextSourceKind) -> list[ContextSection]:
        """Get all sections of a specific kind."""
        return [s for s in self.sections if s.source_kind == kind]

    def get_sections_by_priority(self, min_priority: int = 0) -> list[ContextSection]:
        """Get all sections with priority >= min_priority."""
        return [s for s in self.sections if s.priority >= min_priority]

    def to_prompt(self, *, include_headers: bool = True) -> str:
        """Generate the full prompt from all sections.

        Args:
            include_headers: If True, include section headers

        Returns:
            The assembled prompt string
        """
        if not self.sections:
            return ""

        parts: list[str] = []
        for section in self.sections:
            if include_headers:
                parts.append(section.to_prompt())
            else:
                parts.append(section.content)

        return "\n\n---\n\n".join(parts)


@dataclass(slots=True)
class ContextAssemblerConfig:
    """Configuration for context assembly."""

    max_total_chars: int = 100000
    system_prompt_priority: int = 100
    skill_priority: int = 50
    memory_priority: int = 40
    workspace_priority: int = 30
    session_priority: int = 20
    user_priority: int = 10
    include_skill_instructions: bool = True
    include_memory_entries: bool = True
    include_workspace_state: bool = True
    include_session_state: bool = True


@dataclass(slots=True)
class ContextAssembler:
    """Assembler for agent context from multiple sources.

    This assembler combines context from:
    - System prompts (highest priority)
    - Resolved skills
    - Resolved memory
    - Workspace state
    - Session state
    - User input (lowest priority)

    The assembled context respects character limits and priority ordering.
    """

    config: ContextAssemblerConfig = field(default_factory=ContextAssemblerConfig)
    _sections: list[ContextSection] = field(default_factory=list)

    def add_system_prompt(self, content: str, *, source_id: str = "system") -> ContextSection:
        """Add system prompt section.

        Args:
            content: The system prompt content
            source_id: Optional source identifier

        Returns:
            The created ContextSection
        """
        section = ContextSection(
            source_kind=ContextSourceKind.SYSTEM,
            source_id=source_id,
            title="System Instructions",
            content=content,
            priority=self.config.system_prompt_priority,
        )
        self._sections.append(section)
        return section

    def add_skill_context(
        self,
        skill_name: str,
        instructions: str,
        *,
        source_id: str | None = None,
        priority: int | None = None,
    ) -> ContextSection:
        """Add skill context section.

        Args:
            skill_name: The skill name
            instructions: The skill instructions
            source_id: Optional source identifier
            priority: Optional priority override

        Returns:
            The created ContextSection
        """
        section = ContextSection(
            source_kind=ContextSourceKind.SKILL,
            source_id=source_id or f"skill:{skill_name}",
            title=f"Skill: {skill_name}",
            content=instructions,
            priority=priority if priority is not None else self.config.skill_priority,
        )
        self._sections.append(section)
        return section

    def add_memory_context(
        self,
        content: str,
        *,
        source_id: str,
        title: str = "Memory",
        priority: int | None = None,
    ) -> ContextSection:
        """Add memory context section.

        Args:
            content: The memory content
            source_id: Source identifier (e.g., "session:memory" or "workspace:memory")
            title: Section title
            priority: Optional priority override

        Returns:
            The created ContextSection
        """
        section = ContextSection(
            source_kind=ContextSourceKind.MEMORY,
            source_id=source_id,
            title=title,
            content=content,
            priority=priority if priority is not None else self.config.memory_priority,
        )
        self._sections.append(section)
        return section

    def add_workspace_context(
        self,
        content: str,
        *,
        source_id: str = "workspace",
        title: str = "Workspace Context",
        priority: int | None = None,
    ) -> ContextSection:
        """Add workspace context section.

        Args:
            content: The workspace context content
            source_id: Source identifier
            title: Section title
            priority: Optional priority override

        Returns:
            The created ContextSection
        """
        section = ContextSection(
            source_kind=ContextSourceKind.WORKSPACE,
            source_id=source_id,
            title=title,
            content=content,
            priority=priority if priority is not None else self.config.workspace_priority,
        )
        self._sections.append(section)
        return section

    def add_session_context(
        self,
        content: str,
        *,
        source_id: str = "session",
        title: str = "Session Context",
        priority: int | None = None,
    ) -> ContextSection:
        """Add session context section.

        Args:
            content: The session context content
            source_id: Source identifier
            title: Section title
            priority: Optional priority override

        Returns:
            The created ContextSection
        """
        section = ContextSection(
            source_kind=ContextSourceKind.SESSION,
            source_id=source_id,
            title=title,
            content=content,
            priority=priority if priority is not None else self.config.session_priority,
        )
        self._sections.append(section)
        return section

    def add_user_context(
        self,
        content: str,
        *,
        source_id: str = "user",
        title: str = "",
        priority: int | None = None,
    ) -> ContextSection:
        """Add user input section.

        Args:
            content: The user input content
            source_id: Source identifier
            title: Section title
            priority: Optional priority override

        Returns:
            The created ContextSection
        """
        section = ContextSection(
            source_kind=ContextSourceKind.USER,
            source_id=source_id,
            title=title,
            content=content,
            priority=priority if priority is not None else self.config.user_priority,
        )
        self._sections.append(section)
        return section

    def assemble(
        self,
        *,
        workspace_id: str,
        session_id: str,
        run_id: str,
    ) -> AssembledContext:
        """Assemble all sections into final context.

        This method:
        1. Sorts sections by priority (highest first)
        2. Truncates to fit within max_total_chars
        3. Returns the assembled context

        Args:
            workspace_id: The workspace ID
            session_id: The session ID
            run_id: The run ID

        Returns:
            An AssembledContext with all sections
        """
        # Sort by priority (highest first), then by source_kind for stability
        sorted_sections = sorted(
            self._sections,
            key=lambda s: (-s.priority, s.source_kind.value, s.source_id),
        )

        # Truncate to fit within max_total_chars
        total_chars = 0
        included: list[ContextSection] = []
        for section in sorted_sections:
            section_chars = len(section.content)
            if total_chars + section_chars <= self.config.max_total_chars:
                included.append(section)
                total_chars += section_chars
            elif total_chars < self.config.max_total_chars:
                # Partial inclusion with truncation
                remaining = self.config.max_total_chars - total_chars
                if remaining >= 50:  # Only include if meaningful (at least 50 chars)
                    truncated_content = section.content[:remaining] + "\n...[truncated]"
                    truncated_section = ContextSection(
                        source_kind=section.source_kind,
                        source_id=section.source_id,
                        title=section.title,
                        content=truncated_content,
                        priority=section.priority,
                        metadata={**section.metadata, "truncated": True},
                    )
                    included.append(truncated_section)
                    total_chars = self.config.max_total_chars
                break
            else:
                # No more room
                break

        return AssembledContext(
            workspace_id=workspace_id,
            session_id=session_id,
            run_id=run_id,
            sections=tuple(included),
            total_chars=total_chars,
        )

    def clear(self) -> None:
        """Clear all sections."""
        self._sections.clear()


__all__ = [
    "AssembledContext",
    "ContextAssembler",
    "ContextAssemblerConfig",
    "ContextSection",
    "ContextSourceKind",
]
