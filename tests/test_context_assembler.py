"""Tests for ContextAssembler service."""

from __future__ import annotations

import pytest

from mini_agent.agent_core.context.context_assembler import (
    AssembledContext,
    ContextAssembler,
    ContextAssemblerConfig,
    ContextSection,
    ContextSourceKind,
)


class TestContextSection:
    """Tests for ContextSection."""

    def test_context_section_creation(self) -> None:
        section = ContextSection(
            source_kind=ContextSourceKind.SYSTEM,
            source_id="system",
            title="System Instructions",
            content="You are a helpful assistant.",
            priority=100,
        )
        assert section.source_kind == ContextSourceKind.SYSTEM
        assert section.source_id == "system"
        assert section.title == "System Instructions"
        assert section.priority == 100

    def test_context_section_to_prompt(self) -> None:
        section = ContextSection(
            source_kind=ContextSourceKind.SKILL,
            source_id="skill:test",
            title="Test Skill",
            content="Skill instructions here.",
        )
        prompt = section.to_prompt()
        assert "## Test Skill" in prompt
        assert "Skill instructions here." in prompt

    def test_context_section_no_title(self) -> None:
        section = ContextSection(
            source_kind=ContextSourceKind.USER,
            source_id="user",
            title="",
            content="User input here.",
        )
        prompt = section.to_prompt()
        assert prompt == "User input here."


class TestAssembledContext:
    """Tests for AssembledContext."""

    def test_assembled_context_creation(self) -> None:
        sections = (
            ContextSection(
                source_kind=ContextSourceKind.SYSTEM,
                source_id="system",
                title="System",
                content="System prompt",
            ),
            ContextSection(
                source_kind=ContextSourceKind.SKILL,
                source_id="skill:test",
                title="Skill",
                content="Skill content",
            ),
        )
        context = AssembledContext(
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
            sections=sections,
            total_chars=100,
        )
        assert context.workspace_id == "ws-001"
        assert context.section_count == 2
        assert context.total_chars == 100

    def test_get_sections_by_kind(self) -> None:
        sections = (
            ContextSection(
                source_kind=ContextSourceKind.SYSTEM,
                source_id="system",
                title="System",
                content="System",
            ),
            ContextSection(
                source_kind=ContextSourceKind.SKILL,
                source_id="skill:1",
                title="Skill 1",
                content="Skill 1",
            ),
            ContextSection(
                source_kind=ContextSourceKind.SKILL,
                source_id="skill:2",
                title="Skill 2",
                content="Skill 2",
            ),
        )
        context = AssembledContext(
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
            sections=sections,
        )
        skill_sections = context.get_sections_by_kind(ContextSourceKind.SKILL)
        assert len(skill_sections) == 2

    def test_to_prompt(self) -> None:
        sections = (
            ContextSection(
                source_kind=ContextSourceKind.SYSTEM,
                source_id="system",
                title="System",
                content="System prompt",
            ),
            ContextSection(
                source_kind=ContextSourceKind.SKILL,
                source_id="skill:test",
                title="Test Skill",
                content="Skill content",
            ),
        )
        context = AssembledContext(
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
            sections=sections,
        )
        prompt = context.to_prompt()
        assert "## System" in prompt
        assert "## Test Skill" in prompt
        assert "---" in prompt

    def test_to_prompt_no_headers(self) -> None:
        sections = (
            ContextSection(
                source_kind=ContextSourceKind.SYSTEM,
                source_id="system",
                title="System",
                content="System prompt",
            ),
        )
        context = AssembledContext(
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
            sections=sections,
        )
        prompt = context.to_prompt(include_headers=False)
        assert "## System" not in prompt
        assert prompt == "System prompt"


class TestContextAssembler:
    """Tests for ContextAssembler."""

    def test_assembler_creation(self) -> None:
        assembler = ContextAssembler()
        assert len(assembler._sections) == 0

    def test_add_system_prompt(self) -> None:
        assembler = ContextAssembler()
        section = assembler.add_system_prompt("You are helpful.")
        assert section.source_kind == ContextSourceKind.SYSTEM
        assert section.priority == assembler.config.system_prompt_priority

    def test_add_skill_context(self) -> None:
        assembler = ContextAssembler()
        section = assembler.add_skill_context("test_skill", "Skill instructions")
        assert section.source_kind == ContextSourceKind.SKILL
        assert section.source_id == "skill:test_skill"
        assert "test_skill" in section.title

    def test_add_memory_context(self) -> None:
        assembler = ContextAssembler()
        section = assembler.add_memory_context(
            "Remember this.",
            source_id="session:memory",
            title="Session Memory",
        )
        assert section.source_kind == ContextSourceKind.MEMORY
        assert section.title == "Session Memory"

    def test_add_workspace_context(self) -> None:
        assembler = ContextAssembler()
        section = assembler.add_workspace_context("Workspace info")
        assert section.source_kind == ContextSourceKind.WORKSPACE

    def test_add_session_context(self) -> None:
        assembler = ContextAssembler()
        section = assembler.add_session_context("Session info")
        assert section.source_kind == ContextSourceKind.SESSION

    def test_add_user_context(self) -> None:
        assembler = ContextAssembler()
        section = assembler.add_user_context("User input")
        assert section.source_kind == ContextSourceKind.USER

    def test_assemble_priority_ordering(self) -> None:
        assembler = ContextAssembler()
        assembler.add_user_context("User input")  # priority 10
        assembler.add_system_prompt("System prompt")  # priority 100
        assembler.add_skill_context("skill", "Skill content")  # priority 50

        context = assembler.assemble(
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
        )

        # Should be ordered by priority (highest first)
        assert context.sections[0].source_kind == ContextSourceKind.SYSTEM
        assert context.sections[1].source_kind == ContextSourceKind.SKILL
        assert context.sections[2].source_kind == ContextSourceKind.USER

    def test_assemble_truncation(self) -> None:
        config = ContextAssemblerConfig(max_total_chars=100)
        assembler = ContextAssembler(config=config)

        # Add a large system prompt
        large_content = "x" * 200
        assembler.add_system_prompt(large_content)

        context = assembler.assemble(
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
        )

        # Should be truncated to fit within max_total_chars
        assert context.total_chars <= config.max_total_chars
        assert len(context.sections) == 1
        assert "[truncated]" in context.sections[0].content

    def test_clear(self) -> None:
        assembler = ContextAssembler()
        assembler.add_system_prompt("System")
        assembler.add_skill_context("skill", "Skill")
        assert len(assembler._sections) == 2

        assembler.clear()
        assert len(assembler._sections) == 0

    def test_full_assembly_flow(self) -> None:
        assembler = ContextAssembler()

        # Add all context types
        assembler.add_system_prompt("You are a helpful coding assistant.")
        assembler.add_skill_context("python", "Python best practices...")
        assembler.add_skill_context("testing", "Testing guidelines...")
        assembler.add_memory_context(
            "User prefers type hints.",
            source_id="session:memory",
            title="User Preferences",
        )
        assembler.add_workspace_context("Project: mini-agent")
        assembler.add_session_context("Current task: implement feature X")
        assembler.add_user_context("Please implement the feature.")

        context = assembler.assemble(
            workspace_id="ws-001",
            session_id="sess-001",
            run_id="run-001",
        )

        assert context.section_count == 7
        assert context.workspace_id == "ws-001"
        assert context.session_id == "sess-001"
        assert context.run_id == "run-001"

        # Verify prompt generation
        prompt = context.to_prompt()
        assert "System Instructions" in prompt
        assert "Python best practices" in prompt
        assert "User Preferences" in prompt
        assert "Project: mini-agent" in prompt
