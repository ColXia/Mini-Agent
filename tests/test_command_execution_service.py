from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

from mini_agent.commands.execution import (
    CommandExecutionResult,
    CatalogModelUseRequest,
    LocalOperatorCommandService,
    McpReloadOutcome,
    parse_memory_show_target,
    resolve_catalog_model_use_request,
)
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from mini_agent.memory.diagnostics import build_memory_diagnostics
from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime
from mini_agent.memory.service import MemoryService


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


def test_local_operator_command_service_builds_mcp_status_and_list_results() -> None:
    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: None,
        mcp_snapshot_loader=lambda config: SimpleNamespace(  # noqa: ARG005
            active_total=1,
            tool_total=2,
            configured_total=3,
        ),
        mcp_status_formatter=lambda snapshot: f"status:{snapshot.active_total}/{snapshot.tool_total}",
        mcp_server_list_formatter=lambda snapshot: f"servers:{snapshot.configured_total}",
    )

    async def _run() -> None:
        status = await service.execute_mcp(
            surface="cli",
            action="status",
            args=["status"],
        )
        listed = await service.execute_mcp(
            surface="tui",
            action="list",
            args=["list"],
        )

        assert status.kind == "info"
        assert status.summary == "1 active server(s) | 2 tool(s)"
        assert status.details == "status:1/2"
        assert listed.kind == "info"
        assert listed.summary == "3 configured server(s) | 1 active"
        assert listed.details == "status:1/2\n\nservers:3"

    asyncio.run(_run())


def test_local_operator_command_service_runs_reload_callback_and_carries_payload() -> None:
    cleanup_calls: list[str] = []

    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: cleanup_calls.append("cleanup"),
        mcp_snapshot_loader=lambda config: SimpleNamespace(  # noqa: ARG005
            active_total=2,
            tool_total=5,
            configured_total=4,
        ),
        mcp_status_formatter=lambda snapshot: f"status:{snapshot.active_total}/{snapshot.tool_total}",
        mcp_server_list_formatter=lambda snapshot: f"servers:{snapshot.configured_total}",
    )

    async def _reload() -> McpReloadOutcome:
        cleanup_calls.append("reload")
        return McpReloadOutcome(
            rebuilt_runtime=True,
            active_model_label="openai/gpt-5.4",
        )

    async def _run() -> None:
        result = await service.execute_mcp(
            surface="cli",
            action="reload",
            args=["reload"],
            reload_callback=_reload,
        )

        assert cleanup_calls == ["cleanup", "reload"]
        assert result.kind == "info"
        assert result.summary == "reloaded MCP | 2 active server(s) | 5 tool(s)"
        assert result.payload["rebuilt_runtime"] is True
        assert result.payload["active_model_label"] == "openai/gpt-5.4"

    asyncio.run(_run())


def test_local_operator_command_service_builds_sandbox_usage_and_status_results() -> None:
    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: None,
    )

    usage = service.execute_sandbox_status(
        surface="tui",
        action="reload",
        args=["reload"],
        diagnostics={},
    )
    status = service.execute_sandbox_status(
        surface="cli",
        action="status",
        args=["status"],
        diagnostics={
            "backend": "windows_restricted_token",
            "approval_profile": "build",
            "access_level": "default",
            "sandbox_mode": "workspace",
            "network_mode": "allow_all",
            "low_integrity": True,
        },
    )

    assert usage.kind == "usage"
    assert usage.details == "Usage: /sandbox status"
    assert status.kind == "info"
    assert "Sandbox Status" in status.details


def test_local_operator_command_service_builds_kb_status_and_toggle_results() -> None:
    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: None,
    )

    async def _run() -> None:
        status = await service.execute_kb(
            surface="cli",
            action="status",
            args=["status"],
            current_enabled=True,
            session_label="this session",
            runtime_attached=True,
        )
        toggled = await service.execute_kb(
            surface="tui",
            action="off",
            args=["off"],
            current_enabled=True,
            session_label="Session 1",
            runtime_attached=True,
            toggle_callback=lambda enabled: enabled,
        )

        assert status.kind == "info"
        assert status.summary == "knowledge base enabled"
        assert status.details == "Knowledge Base: enabled"
        assert toggled.kind == "info"
        assert toggled.summary == "knowledge base disabled"
        assert toggled.details == "Knowledge base is disabled for Session 1."
        assert toggled.payload["enabled"] is False

    asyncio.run(_run())


def test_local_operator_command_service_reports_kb_busy_and_unknown_actions() -> None:
    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: None,
    )

    async def _run() -> None:
        busy = await service.execute_kb(
            surface="tui",
            action="on",
            args=["on"],
            current_enabled=False,
            session_label="Session 1",
            runtime_attached=True,
            busy=True,
            toggle_callback=lambda enabled: enabled,
        )
        unknown = await service.execute_kb(
            surface="cli",
            action="flip",
            args=["flip"],
            current_enabled=True,
            session_label="this session",
            runtime_attached=True,
        )

        assert busy.kind == "error"
        assert busy.summary == "session busy"
        assert busy.status_text == "Session 1 is busy."
        assert unknown.kind == "error"
        assert unknown.summary == "unknown action"
        assert "Unknown kb action" in unknown.details

    asyncio.run(_run())


def test_resolve_catalog_model_use_request_builds_identity_and_errors() -> None:
    providers = [
        {
            "source": "preset",
            "provider_id": "openai",
            "models": [
                {"model_id": "gpt-5.4"},
                {"model_id": "gpt-5.3"},
            ],
        },
        {
            "source": "custom",
            "provider_id": "maas",
            "models": [
                {"model_id": "astron-code-latest"},
            ],
        },
    ]

    resolved = resolve_catalog_model_use_request(
        surface="tui",
        providers=providers,
        args=["use", "openai", "gpt-5.4"],
    )
    assert isinstance(resolved, CatalogModelUseRequest)
    assert resolved.identity == ("preset", "openai", "gpt-5.4")

    usage = resolve_catalog_model_use_request(
        surface="cli",
        providers=providers,
        args=["use"],
    )
    assert isinstance(usage, CommandExecutionResult)
    assert usage.kind == "usage"
    assert usage.details == "Usage: /model use <provider_id> <model_id>"

    provider_missing = resolve_catalog_model_use_request(
        surface="tui",
        providers=providers,
        args=["use", "missing", "gpt-5.4"],
    )
    assert isinstance(provider_missing, CommandExecutionResult)
    assert provider_missing.summary == "provider not found"
    assert provider_missing.status_text == "Provider not found: missing"

    model_missing = resolve_catalog_model_use_request(
        surface="cli",
        providers=providers,
        args=["use", "openai", "missing-model"],
    )
    assert isinstance(model_missing, CommandExecutionResult)
    assert model_missing.summary == "model not found"
    assert model_missing.details == "Model not found in openai: missing-model"


def test_local_operator_command_service_builds_context_show_and_stats_results() -> None:
    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: None,
    )

    result_show = service.execute_context(
        surface="cli",
        action="show",
        args=["show", "brief"],
        current_policy={"include_sources": ["knowledge_base"], "max_items": 2},
        prepared_context={
            "item_count": 1,
            "sources": ["knowledge_base"],
            "items": [
                {
                    "source": "knowledge_base",
                    "title": "Relevant knowledge base context",
                    "preview": "Hybrid retrieval combines BM25 and RRF.",
                }
            ],
        },
        prepared_context_diagnostics={"turn_count": 1, "turns_with_context": 1, "total_item_count": 1},
        session_label="Session 1",
    )
    result_stats = service.execute_context(
        surface="tui",
        action="stats",
        args=["stats"],
        current_policy={},
        prepared_context=None,
        prepared_context_diagnostics={"turn_count": 2, "turns_with_context": 1, "total_item_count": 1},
        session_label="Session 1",
    )

    assert result_show.kind == "info"
    assert result_show.command == "context show brief"
    assert "Policy:" in result_show.details
    assert "Relevant knowledge base context" in result_show.details
    assert result_stats.kind == "info"
    assert result_stats.summary == "prepared-context diagnostics"
    assert "Context diagnostics:" in result_stats.details


def test_local_operator_command_service_updates_context_policy_locally() -> None:
    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: None,
    )

    include_result = service.execute_context(
        surface="cli",
        action="include",
        args=["include", "knowledge_base", "workspace_memory", "knowledge_base"],
        current_policy={"exclude_sources": ["knowledge_base", "mcp_catalog"]},
        session_label="this session",
    )
    budget_result = service.execute_context(
        surface="tui",
        action="budget",
        args=["budget", "2", "1200", "1"],
        current_policy={},
        session_label="Session 1",
    )
    reset_result = service.execute_context(
        surface="tui",
        action="reset",
        args=["reset"],
        current_policy={"include_sources": ["knowledge_base"], "max_items": 2},
        session_label="Session 1",
    )

    assert include_result.kind == "info"
    assert include_result.payload["policy"]["include_sources"] == ["knowledge_base", "workspace_memory"]
    assert include_result.payload["policy"]["exclude_sources"] == ["mcp_catalog"]
    assert budget_result.kind == "info"
    assert budget_result.payload["policy"]["max_items"] == 2
    assert budget_result.payload["policy"]["max_total_chars"] == 1200
    assert budget_result.payload["policy"]["max_items_per_source"] == 1
    assert reset_result.kind == "info"
    assert reset_result.payload["policy"] == {}
    assert "Policy: budget=4 item(s)/2400 chars/1 per-source" in reset_result.details


def test_local_operator_command_service_reports_context_usage_and_unknown_action() -> None:
    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: None,
    )

    usage_result = service.execute_context(
        surface="cli",
        action="budget",
        args=["budget"],
        current_policy={},
        session_label="this session",
    )
    invalid_result = service.execute_context(
        surface="tui",
        action="budget",
        args=["budget", "two"],
        current_policy={},
        session_label="Session 1",
    )
    unknown_result = service.execute_context(
        surface="tui",
        action="flip",
        args=["flip"],
        current_policy={},
        session_label="Session 1",
    )

    assert usage_result.kind == "usage"
    assert usage_result.details == "Usage: /context budget <max_items> [max_total_chars] [max_items_per_source]"
    assert invalid_result.kind == "error"
    assert invalid_result.summary == "invalid number"
    assert invalid_result.status_text == "Context budget values must be integers."
    assert unknown_result.kind == "error"
    assert "Unknown context action" in unknown_result.details


def test_local_operator_command_service_lists_and_shows_skills_from_shared_catalog(
    tmp_path: Path,
) -> None:
    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: None,
    )
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

    list_result = service.execute_skill(
        surface="tui",
        workspace=tmp_path,
        action="list",
        args=["list"],
        config=_skill_config(builtin_dir),
    )
    show_result = service.execute_skill(
        surface="cli",
        workspace=tmp_path,
        action="show",
        args=["show", "repo-helper"],
        config=_skill_config(builtin_dir),
    )

    assert list_result.kind == "info"
    assert list_result.command == "skill list"
    assert "repo-helper [workspace] active" in list_result.details
    assert "doc-coauthoring [builtin] active" in list_result.details
    assert list_result.payload["counts"]["workspace"] == 1
    assert show_result.kind == "info"
    assert show_result.command == "skill show repo-helper"
    assert "Workspace-local repo guidance." in show_result.details


def test_local_operator_command_service_installs_workspace_skill_and_marks_reload_required(
    tmp_path: Path,
) -> None:
    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: None,
    )
    builtin_dir = tmp_path / "builtin-skills"
    source_root = tmp_path / "skill-source" / "repo-helper"
    _write_skill(
        source_root,
        name="repo-helper",
        description="Workspace-local repo guidance.",
        body="Use this skill for the current workspace.",
    )

    result = service.execute_skill(
        surface="tui",
        workspace=tmp_path,
        action="install",
        args=["install", str(source_root)],
        raw_text=f"skill install {source_root}",
        config=_skill_config(builtin_dir),
    )

    assert result.kind == "info"
    assert result.summary == "installed repo-helper"
    assert result.status_text == "Workspace skill installed."
    assert result.payload["reload_required"] is True
    assert result.payload["mutation"] == "install"
    assert result.payload["skill_name"] == "repo-helper"
    assert (tmp_path / ".mini-agent" / "skills" / "repo-helper" / "SKILL.md").exists()


def test_local_operator_command_service_updates_skill_mode_through_shared_policy_flow(
    tmp_path: Path,
) -> None:
    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: None,
    )
    builtin_dir = tmp_path / "builtin-skills"
    _write_skill(
        builtin_dir / "doc-coauthoring",
        name="doc-coauthoring",
        description="Draft structured docs with the user.",
        body="Use this skill for documentation.",
    )

    result = service.execute_skill(
        surface="cli",
        workspace=tmp_path,
        action="mode",
        args=["mode", "allowlist"],
        config=_skill_config(builtin_dir),
    )

    assert result.kind == "info"
    assert result.command == "skill mode allowlist"
    assert result.summary == "skill mode set to allowlist"
    assert result.status_text == "Workspace skill mode updated."
    assert result.payload["reload_required"] is True
    assert result.payload["mutation"] == "mode"
    assert result.payload["mode"] == "allowlist"
    assert "- mode allowlist" in result.details


def _memory_diagnostics_loader(workspace: Path, *, session_id: str) -> dict[str, object]:
    return build_memory_diagnostics(
        workspace_dir=workspace,
        session_id=session_id,
        last_prepared_context=None,
        last_memory_automation={},
        last_runtime_task_memory={},
    )


def test_parse_memory_show_target_is_shared_across_surfaces() -> None:
    detail_mode, selector, usage_error = parse_memory_show_target("cli", ["brief"])
    assert detail_mode == "brief"
    assert selector is None
    assert usage_error is None

    detail_mode, selector, usage_error = parse_memory_show_target("tui", ["latest"])
    assert detail_mode == "full"
    assert selector == "latest"
    assert usage_error is None

    detail_mode, selector, usage_error = parse_memory_show_target("cli", ["brief", "latest"])
    assert detail_mode == "full"
    assert selector is None
    assert usage_error == "Usage: /memory show [brief|full|<selector>]"


def test_local_operator_command_service_builds_memory_list_from_runtime_state(tmp_path: Path) -> None:
    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: None,
    )
    runtime = WorkspaceMemoriaRuntime(tmp_path)
    runtime.save_session_memory("session-1", content="Need to revisit routing guardrails after demo.")

    result = service.execute_memory_action(
        workspace=tmp_path,
        session_id="session-1",
        diagnostics_loader=lambda: _memory_diagnostics_loader(tmp_path, session_id="session-1"),
        action="list",
    )

    assert result.kind == "info"
    assert result.command == "memory list"
    assert "Session Runtime Memory" in result.details
    assert "routing guardrails" in result.details
    assert result.payload["memory_diagnostics"]["runtime_task_memory"]["session_count"] == 1


def test_local_operator_command_service_runs_workspace_memory_mutations(tmp_path: Path) -> None:
    service = LocalOperatorCommandService(
        config_loader=lambda: object(),
        mcp_cleanup=lambda: None,
    )
    runtime = WorkspaceMemoriaRuntime(tmp_path)
    runtime.save_workspace_shared_memory(content="Shared scratchpad item for cleanup.")

    clear_result = service.execute_memory_action(
        workspace=tmp_path,
        session_id="session-1",
        diagnostics_loader=lambda: _memory_diagnostics_loader(tmp_path, session_id="session-1"),
        action="shared_clear",
    )
    assert clear_result.kind == "info"
    assert clear_result.summary == "workspace-shared runtime memory cleared"
    assert clear_result.payload["memory_diagnostics"]["runtime_task_memory"]["shared_count"] == 0

    save_result = service.execute_memory_action(
        workspace=tmp_path,
        session_id="session-1",
        diagnostics_loader=lambda: _memory_diagnostics_loader(tmp_path, session_id="session-1"),
        action="save_note",
        content="Confirmed during testing: keep Chinese replies in this workspace.",
        prepared_context=None,
    )
    summary = MemoryService(tmp_path).summary()
    assert save_result.kind == "info"
    assert save_result.summary == "operator note saved to workspace memory"
    assert save_result.payload["memory_diagnostics"]["workspace_note_count"] == 1
    assert summary.notes_count == 1
