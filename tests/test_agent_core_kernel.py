from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from mini_agent.agent_core.kernel import AgentKernelBuildOptions, build_agent_kernel
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig
from mini_agent.model_manager.runtime import RoutedLLMSettings
from mini_agent.schema import LLMProvider
from mini_agent.runtime.tooling import initialize_agent_tools
from mini_agent.tools.base import Tool, ToolResult


class _DummyTool(Tool):
    @property
    def name(self) -> str:
        return "dummy_tool"

    @property
    def description(self) -> str:
        return "dummy"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    async def execute(self, *args, **kwargs) -> ToolResult:  # type: ignore[override]
        _ = (args, kwargs)
        return ToolResult(success=True, content="ok")


def _build_test_config() -> Config:
    return Config(
        llm=LLMConfig(
            api_key="sk-test",
            api_base="https://api.example.com/v1",
            model="model-default",
            provider="openai",
        ),
        agent=AgentConfig(
            max_steps=12,
            max_tool_calls_per_step=3,
            system_prompt_path="system_prompt.md",
        ),
        tools=ToolsConfig(
            enable_file_tools=False,
            enable_bash=False,
            enable_note=False,
            enable_skills=False,
            enable_mcp=False,
        ),
    )


def _single_route(
    model_id: str = "model-routed",
    *,
    token_limit: int | None = None,
) -> list[RoutedLLMSettings]:
    return [
        RoutedLLMSettings(
            source="provider_catalog",
            provider=LLMProvider.OPENAI,
            api_key="sk-routed",
            api_base="https://api.example.com/v1",
            model=model_id,
            provider_id="preset-openai",
            provider_name="OpenAI",
            mapping_mode="exact",
            token_limit=token_limit,
        )
    ]


async def test_build_agent_kernel_uses_unified_routing_and_tool_init(monkeypatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("System Prompt\n{SKILLS_METADATA}", encoding="utf-8")

    captured: dict[str, Any] = {}

    monkeypatch.setattr("mini_agent.agent_core.kernel.Config.load", lambda: _build_test_config())
    monkeypatch.setattr("mini_agent.agent_core.kernel.Config.find_config_file", lambda _name: prompt_file)

    def _fake_routes(config: Config, *, requested_model: str | None = None, catalog_path=None):
        _ = (config, catalog_path)
        captured["requested_model"] = requested_model
        return _single_route("model-picked")

    monkeypatch.setattr("mini_agent.agent_core.kernel.resolve_routed_llm_candidates", _fake_routes)

    async def _fake_init_tools(*, config, workspace_dir, approval_profile_override, access_level_override=None):
        _ = (config, access_level_override)
        captured["workspace_dir"] = str(workspace_dir)
        captured["approval_profile_override"] = approval_profile_override
        catalog_loader = SimpleNamespace(list_tier1=lambda eligible_only=False: [])
        captured["catalog_loader"] = catalog_loader
        loader = SimpleNamespace(
            get_skills_metadata_prompt=lambda: "SKILL_METADATA",
            loader=catalog_loader,
        )
        return [_DummyTool()], loader, {
            "workspace_tools": {"count": 1, "tool_names": ["dummy_tool"]},
            "shared_tools": {"count": 0, "tool_names": []},
            "skills": {
                "enabled": True,
                "loader_ready": True,
                "catalog_count": 0,
                "eligible_count": 0,
                "active_skill_count": 0,
                "tool_names": [],
                "error": None,
            },
            "mcp": {
                "enabled": False,
                "config_path": None,
                "tool_count": 0,
                "tool_names": [],
                "error": None,
            },
            "total_tools": {"count": 1, "tool_names": ["dummy_tool"]},
        }

    monkeypatch.setattr("mini_agent.agent_core.kernel.initialize_agent_tools", _fake_init_tools)
    monkeypatch.setattr("mini_agent.agent_core.kernel.create_agent_logger", lambda _config: SimpleNamespace())

    agent = await build_agent_kernel(
        workspace_dir=tmp_path / "workspace-a",
        options=AgentKernelBuildOptions(
            approval_profile="plan",
            requested_model="model-explicit",
            console_output=False,
        ),
    )

    assert captured["requested_model"] == "model-explicit"
    assert captured["approval_profile_override"] == "plan"
    assert captured["workspace_dir"].endswith("workspace-a")
    assert "{SKILLS_METADATA}" not in agent.system_prompt
    assert "SKILL_METADATA" in agent.system_prompt
    assert agent.console_output is False
    assert "dummy_tool" in agent.tools
    assert getattr(agent.llm, "model", "") == "model-picked"
    assert getattr(agent, "skill_runtime", None) is not None
    assert getattr(agent, "skill_catalog_loader", None) is captured["catalog_loader"]
    assert agent.kernel_diagnostics["route"]["model"] == "model-picked"
    assert agent.kernel_diagnostics["runtime_policy"]["approval_profile"] == "plan"
    assert agent.kernel_diagnostics["tools"]["tool_names"] == ["dummy_tool"]
    assert "RuntimeRecoveryTurnContextProvider" in agent.kernel_diagnostics["turn_context"]["provider_types"]


async def test_build_agent_kernel_appends_skill_metadata_when_placeholder_absent(
    monkeypatch,
    tmp_path: Path,
) -> None:
    prompt_file = tmp_path / "prompt-no-placeholder.md"
    prompt_file.write_text("Base Prompt", encoding="utf-8")

    monkeypatch.setattr("mini_agent.agent_core.kernel.Config.load", lambda: _build_test_config())
    monkeypatch.setattr("mini_agent.agent_core.kernel.Config.find_config_file", lambda _name: prompt_file)
    monkeypatch.setattr(
        "mini_agent.agent_core.kernel.resolve_routed_llm_candidates",
        lambda config, *, requested_model=None, catalog_path=None: _single_route(),
    )

    async def _fake_init_tools(*, config, workspace_dir, approval_profile_override, access_level_override=None):
        _ = (config, workspace_dir, approval_profile_override, access_level_override)
        loader = SimpleNamespace(get_skills_metadata_prompt=lambda: "SKILL_BLOCK")
        return [_DummyTool()], loader, {
            "workspace_tools": {"count": 1, "tool_names": ["dummy_tool"]},
            "shared_tools": {"count": 0, "tool_names": []},
            "skills": {"enabled": True, "loader_ready": True, "catalog_count": 0, "eligible_count": 0, "active_skill_count": 0, "tool_names": [], "error": None},
            "mcp": {"enabled": False, "config_path": None, "tool_count": 0, "tool_names": [], "error": None},
            "total_tools": {"count": 1, "tool_names": ["dummy_tool"]},
        }

    monkeypatch.setattr("mini_agent.agent_core.kernel.initialize_agent_tools", _fake_init_tools)
    monkeypatch.setattr("mini_agent.agent_core.kernel.create_agent_logger", lambda _config: SimpleNamespace())

    agent = await build_agent_kernel(workspace_dir=tmp_path / "workspace-b")
    assert "Base Prompt" in agent.system_prompt
    assert "SKILL_BLOCK" in agent.system_prompt


async def test_build_agent_kernel_uses_pinned_provider_route_when_requested(
    monkeypatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr("mini_agent.agent_core.kernel.Config.load", lambda: _build_test_config())
    monkeypatch.setattr(
        "mini_agent.agent_core.kernel.resolve_pinned_llm_candidate",
        lambda config, *, provider_source, provider_id, model_id, catalog_path=None: (
            _single_route(model_id or "model-routed")[0]
        ),
    )
    monkeypatch.setattr(
        "mini_agent.agent_core.kernel.resolve_routed_llm_candidates",
        lambda config, *, requested_model=None, catalog_path=None: _single_route("should-not-be-used"),
    )

    async def _fake_init_tools(*, config, workspace_dir, approval_profile_override, access_level_override=None):
        _ = (config, workspace_dir, approval_profile_override, access_level_override)
        loader = SimpleNamespace(get_skills_metadata_prompt=lambda: "")
        return [_DummyTool()], loader, {
            "workspace_tools": {"count": 1, "tool_names": ["dummy_tool"]},
            "shared_tools": {"count": 0, "tool_names": []},
            "skills": {"enabled": True, "loader_ready": True, "catalog_count": 0, "eligible_count": 0, "active_skill_count": 0, "tool_names": [], "error": None},
            "mcp": {"enabled": False, "config_path": None, "tool_count": 0, "tool_names": [], "error": None},
            "total_tools": {"count": 1, "tool_names": ["dummy_tool"]},
        }

    monkeypatch.setattr("mini_agent.agent_core.kernel.initialize_agent_tools", _fake_init_tools)
    monkeypatch.setattr("mini_agent.agent_core.kernel.create_agent_logger", lambda _config: SimpleNamespace())

    agent = await build_agent_kernel(
        workspace_dir=tmp_path / "workspace-pinned",
        options=AgentKernelBuildOptions(
            requested_model="gpt-5.3",
            requested_provider_source="preset",
            requested_provider_id="openai",
            console_output=False,
        ),
    )

    assert getattr(agent.llm, "model", "") == "gpt-5.3"
    assert getattr(getattr(agent, "runtime_route", None), "provider_id", "") == "preset-openai"


async def test_build_agent_kernel_can_disable_interactive_setup(monkeypatch, tmp_path: Path) -> None:
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Base Prompt", encoding="utf-8")

    captured: dict[str, Any] = {}

    def _fake_config_load(*, allow_interactive_setup: bool = True):
        captured["allow_interactive_setup"] = allow_interactive_setup
        return _build_test_config()

    monkeypatch.setattr("mini_agent.agent_core.kernel.Config.load", _fake_config_load)
    monkeypatch.setattr("mini_agent.agent_core.kernel.Config.find_config_file", lambda _name: prompt_file)
    monkeypatch.setattr(
        "mini_agent.agent_core.kernel.resolve_routed_llm_candidates",
        lambda config, *, requested_model=None, catalog_path=None: _single_route(),
    )

    async def _fake_init_tools(*, config, workspace_dir, approval_profile_override, access_level_override=None):
        _ = (config, workspace_dir, approval_profile_override, access_level_override)
        return [_DummyTool()], None, {
            "workspace_tools": {"count": 1, "tool_names": ["dummy_tool"]},
            "shared_tools": {"count": 0, "tool_names": []},
            "skills": {"enabled": False, "loader_ready": False, "catalog_count": 0, "eligible_count": 0, "active_skill_count": 0, "tool_names": [], "error": None},
            "mcp": {"enabled": False, "config_path": None, "tool_count": 0, "tool_names": [], "error": None},
            "total_tools": {"count": 1, "tool_names": ["dummy_tool"]},
        }

    monkeypatch.setattr("mini_agent.agent_core.kernel.initialize_agent_tools", _fake_init_tools)
    monkeypatch.setattr("mini_agent.agent_core.kernel.create_agent_logger", lambda _config: SimpleNamespace())

    await build_agent_kernel(
        workspace_dir=tmp_path / "workspace-c",
        options=AgentKernelBuildOptions(allow_interactive_setup=False),
    )

    assert captured["allow_interactive_setup"] is False


async def test_build_agent_kernel_can_suppress_background_output(monkeypatch, tmp_path: Path, capsys) -> None:
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Base Prompt", encoding="utf-8")

    monkeypatch.setattr("mini_agent.agent_core.kernel.Config.load", lambda: _build_test_config())
    monkeypatch.setattr("mini_agent.agent_core.kernel.Config.find_config_file", lambda _name: prompt_file)
    monkeypatch.setattr(
        "mini_agent.agent_core.kernel.resolve_routed_llm_candidates",
        lambda config, *, requested_model=None, catalog_path=None: _single_route(),
    )

    async def _fake_init_tools(*, config, workspace_dir, approval_profile_override, access_level_override=None):
        _ = (config, workspace_dir, approval_profile_override, access_level_override)
        print("noisy bootstrap output")
        return [_DummyTool()], None, {
            "workspace_tools": {"count": 1, "tool_names": ["dummy_tool"]},
            "shared_tools": {"count": 0, "tool_names": []},
            "skills": {"enabled": False, "loader_ready": False, "catalog_count": 0, "eligible_count": 0, "active_skill_count": 0, "tool_names": [], "error": None},
            "mcp": {"enabled": False, "config_path": None, "tool_count": 0, "tool_names": [], "error": None},
            "total_tools": {"count": 1, "tool_names": ["dummy_tool"]},
        }

    monkeypatch.setattr("mini_agent.agent_core.kernel.initialize_agent_tools", _fake_init_tools)
    monkeypatch.setattr("mini_agent.agent_core.kernel.create_agent_logger", lambda _config: SimpleNamespace())

    await build_agent_kernel(
        workspace_dir=tmp_path / "workspace-d",
        options=AgentKernelBuildOptions(
            console_output=False,
            suppress_background_output=True,
        ),
    )

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


async def test_build_agent_kernel_uses_route_token_limit_for_agent_budget(
    monkeypatch,
    tmp_path: Path,
) -> None:
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("Base Prompt", encoding="utf-8")

    monkeypatch.setattr("mini_agent.agent_core.kernel.Config.load", lambda: _build_test_config())
    monkeypatch.setattr("mini_agent.agent_core.kernel.Config.find_config_file", lambda _name: prompt_file)
    monkeypatch.setattr(
        "mini_agent.agent_core.kernel.resolve_routed_llm_candidates",
        lambda config, *, requested_model=None, catalog_path=None: _single_route(
            "model-budgeted",
            token_limit=123456,
        ),
    )

    async def _fake_init_tools(*, config, workspace_dir, approval_profile_override, access_level_override=None):
        _ = (config, workspace_dir, approval_profile_override, access_level_override)
        return [_DummyTool()], None, {
            "workspace_tools": {"count": 1, "tool_names": ["dummy_tool"]},
            "shared_tools": {"count": 0, "tool_names": []},
            "skills": {"enabled": False, "loader_ready": False, "catalog_count": 0, "eligible_count": 0, "active_skill_count": 0, "tool_names": [], "error": None},
            "mcp": {"enabled": False, "config_path": None, "tool_count": 0, "tool_names": [], "error": None},
            "total_tools": {"count": 1, "tool_names": ["dummy_tool"]},
        }

    monkeypatch.setattr("mini_agent.agent_core.kernel.initialize_agent_tools", _fake_init_tools)
    monkeypatch.setattr("mini_agent.agent_core.kernel.create_agent_logger", lambda _config: SimpleNamespace())

    agent = await build_agent_kernel(workspace_dir=tmp_path / "workspace-budget")

    assert agent.token_limit == 123456


async def test_initialize_agent_tools_reports_skill_and_mcp_bootstrap_failures(
    monkeypatch,
    tmp_path: Path,
) -> None:
    config = _build_test_config()
    config.tools.enable_file_tools = False
    config.tools.enable_bash = False
    config.tools.enable_note = False
    config.tools.enable_knowledge_base = False
    config.tools.enable_skills = True
    config.tools.enable_mcp = True

    monkeypatch.setattr(
        "mini_agent.tools.skill_tool.create_skill_tools",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("skills boom")),
    )

    async def _fake_load_mcp_tools_async(_path: str):
        raise RuntimeError("mcp boom")

    monkeypatch.setattr("mini_agent.tools.mcp_loader.load_mcp_tools_async", _fake_load_mcp_tools_async)
    monkeypatch.setattr("mini_agent.tools.mcp_loader.set_mcp_timeout_config", lambda **kwargs: None)
    monkeypatch.setattr(
        "mini_agent.runtime.tooling.resolve_runtime_mcp_config_path",
        lambda _config: tmp_path / "mcp.json",
    )

    tools, skill_loader, diagnostics = await initialize_agent_tools(
        config,
        tmp_path / "workspace-e",
    )

    assert tools == []
    assert skill_loader is None
    assert diagnostics["skills"]["enabled"] is True
    assert diagnostics["skills"]["loader_ready"] is False
    assert "skills boom" in str(diagnostics["skills"]["error"])
    assert diagnostics["mcp"]["enabled"] is True
    assert "mcp boom" in str(diagnostics["mcp"]["error"])
