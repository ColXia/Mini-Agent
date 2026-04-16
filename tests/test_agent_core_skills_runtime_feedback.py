from __future__ import annotations

from mini_agent.agent_core.skills.runtime_feedback import (
    describe_skill_runtime_reload,
    format_cli_skill_reload_failure,
    format_cli_skill_reload_success,
)


def test_skill_runtime_reload_feedback_for_install_includes_surface_and_cli_semantics() -> None:
    feedback = describe_skill_runtime_reload(
        {
            "mutation": "install",
            "skill_name": "repo-helper",
            "reload_reason": "workspace skill installed",
            "summary": "installed repo-helper",
        }
    )

    assert feedback.reason == "workspace skill installed"
    assert feedback.busy_summary == "installed repo-helper; runtime busy"
    assert feedback.warm_prefix_base == "Workspace skill installed"
    assert feedback.success_status == "Installed skill repo-helper."
    assert format_cli_skill_reload_success(
        feedback,
        rebuilt=True,
        active_model="openai/gpt-5.4",
    ) == "Installed repo-helper; current CLI agent reloaded on openai/gpt-5.4"
    assert format_cli_skill_reload_failure(feedback, RuntimeError("boom")) == (
        "Skill installed, but the current CLI agent did not reload: boom"
    )


def test_skill_runtime_reload_feedback_for_refresh_preserves_result_status_fallback() -> None:
    feedback = describe_skill_runtime_reload(
        {
            "mutation": "refresh",
            "reload_reason": "skill catalog refreshed",
            "summary": "skill catalog refreshed",
        }
    )

    assert feedback.reason == "skill catalog refreshed"
    assert feedback.busy_summary == "catalog refreshed; runtime busy"
    assert feedback.warm_prefix_base == "Skill catalog refreshed"
    assert feedback.success_status == ""
    assert format_cli_skill_reload_success(
        feedback,
        rebuilt=False,
        active_model="",
    ) == "Skill catalog refreshed"


def test_skill_runtime_reload_feedback_falls_back_for_unknown_mutation() -> None:
    feedback = describe_skill_runtime_reload(
        {
            "mutation": "custom",
            "summary": "custom skill update",
        }
    )

    assert feedback.reason == "workspace skill runtime changed"
    assert feedback.busy_summary == "custom skill update; runtime busy"
    assert feedback.warm_prefix_base == "Workspace skill updated"
    assert feedback.success_status == "Skill command completed."
    assert format_cli_skill_reload_success(
        feedback,
        rebuilt=False,
        active_model="",
    ) == "custom skill update"
