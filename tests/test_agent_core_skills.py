"""Tests for P15 T3.2 skills-platform baseline."""

from __future__ import annotations

from pathlib import Path
import zipfile

import pytest

from mini_agent.agent_core import (
    AgentSkillLoader,
    SkillRequirements,
    SkillSource,
    WorkspaceSkillInstaller,
    WorkspaceSkillPolicyStore,
    WorkspaceSkillRuntimeBridge,
)


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


def _write_skill_zip_archive(archive_path: Path, skill_root: Path, *, prefix: str = "skill-package") -> Path:
    archive_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in skill_root.rglob("*"):
            if path.is_dir():
                continue
            relative = path.relative_to(skill_root).as_posix()
            archive.write(path, arcname=f"{prefix}/{relative}")
    return archive_path


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
    assert "routing hint" in metadata_prompt
    assert "more than one relevant skill" in metadata_prompt

    skill = bridge.get_skill("bridge-skill")
    assert skill is not None
    assert "bridge instructions" in skill.to_prompt()


def test_skill_metadata_prompt_marks_metadata_as_routing_only(tmp_path: Path) -> None:
    builtin_root = tmp_path / "builtin"
    _write_skill(
        builtin_root / "bridge",
        name="bridge-skill",
        description="bridge description",
        body="bridge instructions",
    )

    loader = AgentSkillLoader(builtin_dir=builtin_root)
    loader.discover()

    metadata_prompt = loader.get_skills_metadata_prompt()

    assert "routing hint" in metadata_prompt
    assert "call `get_skill(skill_name)` before relying on it" in metadata_prompt


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


def test_workspace_skill_policy_allowlist_filters_runtime_bridge(tmp_path: Path):
    builtin_root = tmp_path / "builtin"
    workspace_root = tmp_path / "workspace"
    _write_skill(
        builtin_root / "docs",
        name="doc-coauthoring",
        description="doc helper",
        body="Use for docs.",
    )
    _write_skill(
        builtin_root / "foundry",
        name="foundry-helper",
        description="foundry helper",
        body="Use for foundry.",
    )

    loader = AgentSkillLoader(builtin_dir=builtin_root, workspace_dir=workspace_root / ".mini-agent" / "skills")
    loader.discover()
    store = WorkspaceSkillPolicyStore(workspace_root)
    store.set_mode("allowlist")
    store.enable(["doc-coauthoring"])

    bridge = WorkspaceSkillRuntimeBridge(loader, workspace_dir=workspace_root)

    assert bridge.list_skills() == ["doc-coauthoring"]
    assert bridge.get_skill("doc-coauthoring") is not None
    assert bridge.get_skill("foundry-helper") is None
    metadata = bridge.get_skills_metadata_prompt()
    assert "doc-coauthoring" in metadata
    assert "foundry-helper" not in metadata


def test_workspace_skill_policy_denylist_filters_runtime_bridge_in_all_mode(tmp_path: Path):
    builtin_root = tmp_path / "builtin"
    workspace_root = tmp_path / "workspace"
    _write_skill(
        builtin_root / "docs",
        name="doc-coauthoring",
        description="doc helper",
        body="Use for docs.",
    )
    _write_skill(
        builtin_root / "foundry",
        name="foundry-helper",
        description="foundry helper",
        body="Use for foundry.",
    )

    loader = AgentSkillLoader(builtin_dir=builtin_root)
    loader.discover()
    store = WorkspaceSkillPolicyStore(workspace_root)
    store.disable(["foundry-helper"])

    bridge = WorkspaceSkillRuntimeBridge(loader, workspace_dir=workspace_root)

    assert bridge.list_skills() == ["doc-coauthoring"]
    assert bridge.get_skill("doc-coauthoring") is not None
    assert bridge.get_skill("foundry-helper") is None


def test_workspace_skill_installer_installs_from_path_and_activates(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    source_root = tmp_path / "source-skill"
    _write_skill(
        source_root,
        name="repo-helper",
        description="Workspace-local guidance.",
        body="Use for this repo.",
    )
    (source_root / "references").mkdir(parents=True, exist_ok=True)
    (source_root / "references" / "note.md").write_text("hello", encoding="utf-8")

    installer = WorkspaceSkillInstaller(workspace_root)
    result = installer.install_from_path(source_root)

    installed_skill_file = workspace_root / ".mini-agent" / "skills" / "repo-helper" / "SKILL.md"
    assert result.skill_name == "repo-helper"
    assert result.activated is True
    assert installed_skill_file.exists()
    assert (installed_skill_file.parent / "references" / "note.md").exists()
    assert result.ledger_path is not None
    policy = WorkspaceSkillPolicyStore(workspace_root).load()
    assert "repo-helper" in policy.allowlist
    ledger_file = workspace_root / ".mini-agent" / "skill_sources.json"
    assert ledger_file.exists()
    assert "repo-helper" in ledger_file.read_text(encoding="utf-8")


def test_workspace_skill_installer_installs_inline_and_refreshes_loader(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    loader = AgentSkillLoader(
        builtin_dir=tmp_path / "builtin-skills",
        workspace_dir=workspace_root / ".mini-agent" / "skills",
    )
    loader.discover()

    installer = WorkspaceSkillInstaller(workspace_root)
    result = installer.install_inline(
        skill_name="task-wrapup",
        description="Summarize and close tasks cleanly.",
        instructions="Use this skill to prepare concise wrap-up summaries.",
        loader=loader,
    )

    assert result.skill_name == "task-wrapup"
    skill = loader.get_skill("task-wrapup", eligible_only=False)
    assert skill is not None
    assert "wrap-up summaries" in skill.instructions


def test_workspace_skill_installer_installs_from_archive(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    source_root = tmp_path / "source-skill"
    _write_skill(
        source_root,
        name="archive-helper",
        description="Workspace-local guidance from archive.",
        body="Use for archive-based installs.",
    )
    (source_root / "references").mkdir(parents=True, exist_ok=True)
    (source_root / "references" / "note.md").write_text("archive hello", encoding="utf-8")
    archive_path = _write_skill_zip_archive(tmp_path / "archive-helper.zip", source_root)

    installer = WorkspaceSkillInstaller(workspace_root)
    result = installer.install_from_path(archive_path)

    installed_skill_file = workspace_root / ".mini-agent" / "skills" / "archive-helper" / "SKILL.md"
    assert result.skill_name == "archive-helper"
    assert result.source_kind == "archive"
    assert installed_skill_file.exists()
    assert (installed_skill_file.parent / "references" / "note.md").read_text(encoding="utf-8") == "archive hello"


def test_workspace_skill_installer_installs_from_url_archive(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from mini_agent.agent_core.skills import install as install_module

    workspace_root = tmp_path / "workspace"
    source_root = tmp_path / "url-source-skill"
    _write_skill(
        source_root,
        name="url-helper",
        description="Workspace-local guidance from URL.",
        body="Use for URL-based installs.",
    )
    archive_path = _write_skill_zip_archive(tmp_path / "url-helper.zip", source_root)
    archive_bytes = archive_path.read_bytes()

    class _FakeResponse:
        def __init__(self, content: bytes) -> None:
            self.content = content

        def raise_for_status(self) -> None:
            return None

    def _fake_get(url: str, timeout: int = 30) -> _FakeResponse:
        assert url == "https://example.com/url-helper.zip"
        assert timeout == 30
        return _FakeResponse(archive_bytes)

    monkeypatch.setattr(install_module.requests, "get", _fake_get)

    installer = WorkspaceSkillInstaller(workspace_root)
    result = installer.install_from_path("https://example.com/url-helper.zip")

    installed_skill_file = workspace_root / ".mini-agent" / "skills" / "url-helper" / "SKILL.md"
    assert result.skill_name == "url-helper"
    assert result.source_kind == "url_archive"
    assert result.source_path == "https://example.com/url-helper.zip"
    assert installed_skill_file.exists()


def test_workspace_skill_installer_uninstall_and_rollback(tmp_path: Path):
    workspace_root = tmp_path / "workspace"
    installer = WorkspaceSkillInstaller(workspace_root)

    install_result = installer.install_inline(
        skill_name="task-wrapup",
        description="Summarize and close tasks cleanly.",
        instructions="Use this skill to prepare concise wrap-up summaries.",
    )
    installed_skill_file = Path(install_result.installed_path) / "SKILL.md"
    assert installed_skill_file.exists()

    uninstall_result = installer.uninstall("task-wrapup")
    assert Path(uninstall_result.removed_path).exists() is False
    assert uninstall_result.backup_path is not None
    assert "task-wrapup" not in WorkspaceSkillPolicyStore(workspace_root).load().allowlist

    rollback_result = installer.rollback("task-wrapup")
    restored_skill_file = Path(rollback_result.restored_path) / "SKILL.md"
    assert restored_skill_file.exists()
    assert rollback_result.backup_path == uninstall_result.backup_path
    assert "task-wrapup" in WorkspaceSkillPolicyStore(workspace_root).load().allowlist


def test_repo_builtin_catalog_includes_first_p28_realignment_slice() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    builtin_root = repo_root / "src" / "mini_agent" / "skills"

    loader = AgentSkillLoader(builtin_dir=builtin_root)
    discovered = loader.discover()
    names = {item.name for item in discovered}

    assert "frontend-dev" in names
    assert "fullstack-dev" in names
    assert "android-native-dev" in names
    assert "ios-application-dev" in names
    assert "flutter-dev" in names
    assert "react-native-dev" in names
    assert "shader-dev" in names
    assert "minimax-music-gen" in names
    assert "buddy-sings" in names
    assert "minimax-music-playlist" in names
    assert "vision-analysis" in names
    assert "gif-sticker-maker" in names
    assert "artifacts-builder" not in names
    assert "slack-gif-creator" not in names
    assert "algorithmic-art" not in names
    assert "brand-guidelines" not in names
    assert "canvas-design" not in names
    assert "internal-comms" not in names
    assert "template-skill" not in names
    assert "theme-factory" not in names
