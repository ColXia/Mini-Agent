"""Tests for P15 T3.2 skills-platform baseline."""

from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.agent_core import AgentSkillLoader, SkillRequirements, SkillSource


def _write_skill(
    skill_dir: Path,
    *,
    name: str,
    description: str,
    body: str,
    extra_frontmatter: str = "",
) -> Path:
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    frontmatter_lines = [
        "---",
        f"name: {name}",
        f"description: {description}",
    ]
    if extra_frontmatter.strip():
        frontmatter_lines.extend(extra_frontmatter.strip().splitlines())
    frontmatter_lines.extend(["---", "", body.strip(), ""])
    skill_file.write_text("\n".join(frontmatter_lines), encoding="utf-8")
    return skill_file


def test_skill_loader_resolves_source_priority_workspace_over_builtin(tmp_path: Path):
    builtin_root = tmp_path / "builtin"
    workspace_root = tmp_path / "workspace"

    _write_skill(
        builtin_root / "shared",
        name="shared-skill",
        description="builtin description",
        body="builtin instructions",
    )
    _write_skill(
        workspace_root / "shared",
        name="shared-skill",
        description="workspace description",
        body="workspace instructions",
    )

    loader = AgentSkillLoader(
        builtin_dir=builtin_root,
        workspace_dir=workspace_root,
    )
    loader.discover()
    skill = loader.get_skill("shared-skill", eligible_only=False)

    assert skill is not None
    assert skill.source == SkillSource.WORKSPACE
    assert "workspace instructions" in skill.instructions


def test_skill_loader_tier2_and_tier3_access(tmp_path: Path):
    builtin_root = tmp_path / "builtin"
    skill_file = _write_skill(
        builtin_root / "demo",
        name="demo-skill",
        description="demo skill",
        body="Use this skill to run demo flow.",
    )
    scripts_dir = skill_file.parent / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)
    (scripts_dir / "run.sh").write_text("echo demo", encoding="utf-8")

    loader = AgentSkillLoader(builtin_dir=builtin_root)
    loader.discover()

    tier2 = loader.load_tier2("demo-skill")
    assert tier2 is not None
    assert "Use this skill to run demo flow." in tier2
    assert "Skill Root Directory" in tier2

    tier3_files = loader.list_tier3_files("demo-skill")
    assert "scripts/run.sh" in tier3_files

    script_content = loader.read_tier3_file("demo-skill", "scripts/run.sh")
    assert script_content == "echo demo"

    with pytest.raises(ValueError, match="escapes skill root"):
        loader.read_tier3_file("demo-skill", "../outside.txt")


def test_skill_loader_eligibility_filtering(tmp_path: Path):
    builtin_root = tmp_path / "builtin"
    _write_skill(
        builtin_root / "blocked",
        name="blocked-skill",
        description="requires unavailable env",
        body="blocked",
        extra_frontmatter="""
requires:
  env: [UNIT_TEST_MISSING_ENV]
""",
    )

    loader = AgentSkillLoader(
        builtin_dir=builtin_root,
        eligibility_checker=None,
    )
    loader.discover()

    visible = loader.list_tier1(eligible_only=False)
    assert len(visible) == 1
    assert visible[0].eligible is False
    assert "missing_env" in (visible[0].blocked_reason or "")

    hidden = loader.list_tier1(eligible_only=True)
    assert hidden == []


def test_skill_loader_runtime_bridge_compatible_interface(tmp_path: Path):
    builtin_root = tmp_path / "builtin"
    _write_skill(
        builtin_root / "bridge",
        name="bridge-skill",
        description="bridge description",
        body="bridge instructions",
    )

    loader = AgentSkillLoader(builtin_dir=builtin_root)
    loader.discover()
    bridge = loader.build_runtime_bridge()

    names = bridge.list_skills()
    assert names == ["bridge-skill"]

    metadata_prompt = bridge.get_skills_metadata_prompt()
    assert "bridge-skill" in metadata_prompt
    assert "bridge description" in metadata_prompt

    skill = bridge.get_skill("bridge-skill")
    assert skill is not None
    assert "bridge instructions" in skill.to_prompt()


def test_remote_skill_registration_and_override(tmp_path: Path):
    builtin_root = tmp_path / "builtin"
    _write_skill(
        builtin_root / "remote",
        name="remote-skill",
        description="builtin variant",
        body="builtin instructions",
    )

    loader = AgentSkillLoader(builtin_dir=builtin_root)
    loader.discover()
    loader.register_remote_skill(
        name="remote-skill",
        description="remote variant",
        instructions="remote instructions",
        requirements=SkillRequirements(),
    )

    skill = loader.get_skill("remote-skill", eligible_only=False)
    assert skill is not None
    assert skill.source == SkillSource.REMOTE
    assert skill.description == "remote variant"
