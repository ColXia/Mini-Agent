from __future__ import annotations

from pathlib import Path

from mini_agent.agent_core.skills.command_service import (
    SkillCommandRequest,
    SkillCommandService,
)
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig


def _write_skill(
    skill_dir: Path,
    *,
    name: str,
    description: str,
    body: str,
) -> Path:
    skill_dir.mkdir(parents=True, exist_ok=True)
    skill_file = skill_dir / "SKILL.md"
    skill_file.write_text(
        "\n".join(
            [
                "---",
                f"name: {name}",
                f"description: {description}",
                "---",
                "",
                body.strip(),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return skill_file


def _skill_config(builtin_dir: Path) -> Config:
    return Config(
        llm=LLMConfig(
            api_key="sk-test",
            api_base="https://api.example.com/v1",
            model="model-default",
            provider="openai",
        ),
        agent=AgentConfig(
            max_steps=8,
            max_tool_calls_per_step=2,
            system_prompt_path="system_prompt.md",
        ),
        tools=ToolsConfig(
            enable_file_tools=False,
            enable_bash=False,
            enable_note=False,
            enable_skills=True,
            enable_mcp=False,
            skills_dir=str(builtin_dir),
        ),
    )


def test_skill_command_service_lists_skills_from_resolved_catalog(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin-skills"
    workspace_skill_dir = tmp_path / ".mini-agent" / "skills" / "repo-helper"
    _write_skill(
        builtin_dir / "doc-coauthoring",
        name="doc-coauthoring",
        description="Draft structured docs with the user.",
        body="Use this skill for documentation.",
    )
    _write_skill(
        workspace_skill_dir,
        name="repo-helper",
        description="Workspace-local repo guidance.",
        body="Use this skill for the current workspace.",
    )

    prepared = SkillCommandService().prepare(
        workspace_dir=tmp_path,
        command=SkillCommandRequest(action="list"),
        config=_skill_config(builtin_dir),
    )

    assert prepared.status == "ok"
    assert prepared.mutation is None
    assert prepared.result is not None
    assert prepared.result["counts"]["total"] == 2
    assert prepared.result["counts"]["workspace"] == 1
    assert "doc-coauthoring [builtin] active" in prepared.result["details"]
    assert "repo-helper [workspace] active" in prepared.result["details"]


def test_skill_command_service_builds_mode_mutation_queue_feedback(tmp_path: Path) -> None:
    builtin_dir = tmp_path / "builtin-skills"
    _write_skill(
        builtin_dir / "doc-coauthoring",
        name="doc-coauthoring",
        description="Draft structured docs with the user.",
        body="Use this skill for documentation.",
    )

    service = SkillCommandService()
    prepared = service.prepare(
        workspace_dir=tmp_path,
        command=SkillCommandRequest(action="mode", mode="allowlist"),
        config=_skill_config(builtin_dir),
    )

    assert prepared.status == "ok"
    assert prepared.result is None
    assert prepared.mutation is not None
    assert prepared.mutation.action == "mode"
    assert prepared.mutation.command_name == "skill mode allowlist"
    assert prepared.mutation.reload_reason == "workspace skill mode updated"

    payload = service.build_busy_result(
        session_id="sess-1",
        mutation=prepared.mutation,
        queued_ids=("sess-1", "sess-2"),
        include_current_note=True,
    )

    assert payload["summary"] == "skill mode set to allowlist; reload queued"
    assert payload["reload_pending"] is True
    assert payload["reload_queued_other_sessions"] == 1
    assert payload["mutation"] == "mode"
    assert payload["mode"] == "allowlist"
    assert payload["policy"]["mode"] == "allowlist"
    assert "Current session skill reload is queued" in payload["details"]
    assert "Queued skill runtime reload for 1 other workspace session: sess-2." in payload["details"]
