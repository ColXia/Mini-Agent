"""Tests for skill tools."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mini_agent.tools.skill_loader import SkillLoader
from mini_agent.tools.skill_tool import GetSkillTool, create_skill_tools


def create_test_skill(skill_dir: Path, name: str, description: str, content: str) -> None:
    skill_file = skill_dir / "SKILL.md"
    skill_content = f"""---
name: {name}
description: {description}
---

{content}
"""
    skill_file.write_text(skill_content, encoding="utf-8")


@pytest.fixture
def skill_loader():
    with tempfile.TemporaryDirectory() as tmpdir:
        for i in range(2):
            skill_dir = Path(tmpdir) / f"test-skill-{i}"
            skill_dir.mkdir()
            create_test_skill(
                skill_dir,
                f"test-skill-{i}",
                f"Test skill {i} description",
                f"Test skill {i} content and instructions.",
            )

        loader = SkillLoader(tmpdir)
        loader.discover_skills()
        yield loader


@pytest.mark.asyncio
async def test_get_skill_tool(skill_loader):
    tool = GetSkillTool(skill_loader)

    result = await tool.execute(skill_name="test-skill-0")

    assert result.success
    assert "test-skill-0" in result.content
    assert "Test skill 0 description" in result.content
    assert "Test skill 0 content" in result.content


@pytest.mark.asyncio
async def test_get_skill_tool_nonexistent(skill_loader):
    tool = GetSkillTool(skill_loader)

    result = await tool.execute(skill_name="nonexistent-skill")

    assert result.success is False
    assert "not exist" in (result.error or "").lower()


def test_create_skill_tools_returns_single_tool_without_workspace_target():
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "test-skill"
        skill_dir.mkdir()
        create_test_skill(skill_dir, "test-skill", "Test skill", "Test content")

        tools, loader = create_skill_tools(tmpdir)

        assert len(tools) == 1
        assert isinstance(tools[0], GetSkillTool)
        assert loader is not None


def test_create_skill_tools_stays_silent_for_terminal_surfaces(capsys):
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "test-skill"
        skill_dir.mkdir()
        create_test_skill(skill_dir, "test-skill", "Test skill", "Test content")

        create_skill_tools(tmpdir)

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""


def test_tool_count_optimization_without_workspace_target():
    with tempfile.TemporaryDirectory() as tmpdir:
        skill_dir = Path(tmpdir) / "simple-skill"
        skill_dir.mkdir()
        create_test_skill(skill_dir, "simple-skill", "Simple test", "Content")

        tools, _ = create_skill_tools(tmpdir)

        assert len(tools) == 1
        assert tools[0].name == "get_skill"
        assert "load the full instructions" in tools[0].description.lower()


def test_get_skill_tool_description_requires_loading_before_relying(skill_loader):
    tool = GetSkillTool(skill_loader)

    assert "before relying on a skill" in tool.description
    assert "routing hint" in tool.description


@pytest.mark.asyncio
async def test_install_skill_tool_creates_workspace_skill(tmp_path: Path):
    builtin_dir = tmp_path / "builtin-skills"
    builtin_dir.mkdir()
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    tools, loader = create_skill_tools(
        str(builtin_dir),
        workspace_dir=str(workspace_dir),
    )
    install_tool = next(tool for tool in tools if tool.name == "install_skill")

    result = await install_tool.execute(
        skill_name="repo-helper",
        description="Workspace helper",
        instructions="Use this skill for repo-specific tasks.",
    )

    assert result.success is True
    installed_path = workspace_dir / ".mini-agent" / "skills" / "repo-helper" / "SKILL.md"
    assert installed_path.exists()
    assert "Installed skill: repo-helper" in result.content
    assert loader.get_skill("repo-helper") is not None
    ledger_path = workspace_dir / ".mini-agent" / "skill_sources.json"
    assert ledger_path.exists()
    assert "Ledger:" in result.content


@pytest.mark.asyncio
async def test_install_skill_from_path_tool_imports_existing_skill(tmp_path: Path):
    builtin_dir = tmp_path / "builtin-skills"
    builtin_dir.mkdir()
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()
    source_dir = tmp_path / "source-skill"
    source_dir.mkdir()
    create_test_skill(
        source_dir,
        "external-helper",
        "External helper",
        "Use this skill for imported workflow help.",
    )

    tools, loader = create_skill_tools(
        str(builtin_dir),
        workspace_dir=str(workspace_dir),
    )
    install_tool = next(tool for tool in tools if tool.name == "install_skill_from_path")

    result = await install_tool.execute(path=str(source_dir))

    assert result.success is True
    installed_path = workspace_dir / ".mini-agent" / "skills" / "external-helper" / "SKILL.md"
    assert installed_path.exists()
    assert "Installed skill: external-helper" in result.content
    assert "Source: directory" in result.content
    assert loader.get_skill("external-helper") is not None
    ledger_path = workspace_dir / ".mini-agent" / "skill_sources.json"
    assert ledger_path.exists()
    assert "external-helper" in ledger_path.read_text(encoding="utf-8")


def test_create_skill_tools_includes_install_tool_when_workspace_target_exists(tmp_path: Path):
    builtin_dir = tmp_path / "builtin-skills"
    builtin_dir.mkdir()
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    tools, loader = create_skill_tools(
        str(builtin_dir),
        workspace_dir=str(workspace_dir),
    )

    assert loader is not None
    assert [tool.name for tool in tools] == [
        "get_skill",
        "install_skill",
        "install_skill_from_path",
        "uninstall_skill",
        "rollback_skill",
    ]


@pytest.mark.asyncio
async def test_uninstall_skill_tool_removes_workspace_skill(tmp_path: Path):
    builtin_dir = tmp_path / "builtin-skills"
    builtin_dir.mkdir()
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    tools, loader = create_skill_tools(
        str(builtin_dir),
        workspace_dir=str(workspace_dir),
    )
    install_tool = next(tool for tool in tools if tool.name == "install_skill")
    uninstall_tool = next(tool for tool in tools if tool.name == "uninstall_skill")

    install_result = await install_tool.execute(
        skill_name="repo-helper",
        description="Workspace helper",
        instructions="Use this skill for repo-specific tasks.",
    )
    assert install_result.success is True

    uninstall_result = await uninstall_tool.execute(skill_name="repo-helper")

    assert uninstall_result.success is True
    assert "Uninstalled skill: repo-helper" in uninstall_result.content
    assert "Backup:" in uninstall_result.content
    assert loader.get_skill("repo-helper") is None
    installed_path = workspace_dir / ".mini-agent" / "skills" / "repo-helper"
    assert installed_path.exists() is False


@pytest.mark.asyncio
async def test_rollback_skill_tool_restores_latest_backup(tmp_path: Path):
    builtin_dir = tmp_path / "builtin-skills"
    builtin_dir.mkdir()
    workspace_dir = tmp_path / "workspace"
    workspace_dir.mkdir()

    tools, loader = create_skill_tools(
        str(builtin_dir),
        workspace_dir=str(workspace_dir),
    )
    install_tool = next(tool for tool in tools if tool.name == "install_skill")
    uninstall_tool = next(tool for tool in tools if tool.name == "uninstall_skill")
    rollback_tool = next(tool for tool in tools if tool.name == "rollback_skill")

    install_result = await install_tool.execute(
        skill_name="repo-helper",
        description="Workspace helper",
        instructions="Use this skill for repo-specific tasks.",
    )
    assert install_result.success is True

    uninstall_result = await uninstall_tool.execute(skill_name="repo-helper")
    assert uninstall_result.success is True
    assert loader.get_skill("repo-helper") is None

    rollback_result = await rollback_tool.execute(skill_name="repo-helper")

    assert rollback_result.success is True
    assert "Rolled back skill: repo-helper" in rollback_result.content
    assert "Backup:" in rollback_result.content
    restored_skill = loader.get_skill("repo-helper")
    assert restored_skill is not None
    assert "repo-specific tasks" in restored_skill.instructions
