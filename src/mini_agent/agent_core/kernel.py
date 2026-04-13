"""Unified agent-kernel builder for all runtime surfaces.

This module consolidates agent bootstrap logic (config, model routing,
tool initialization, and prompt assembly) into a single reusable path so
CLI/TUI/Gateway do not drift into duplicate runtime wiring.
"""

from __future__ import annotations

from contextlib import ExitStack, redirect_stderr, redirect_stdout
from dataclasses import dataclass
import io
from pathlib import Path
from typing import Any

from mini_agent.agent import Agent
from mini_agent.config import Config
from mini_agent.logger import create_agent_logger
from mini_agent.memory.automation import TurnMemoryAutomation
from mini_agent.memory.runtime_task_memory import TurnRuntimeTaskMemory
from mini_agent.model_manager.failover import FailoverLLMClient
from mini_agent.model_manager.runtime import (
    resolve_pinned_llm_candidate,
    resolve_routed_llm_candidates,
)
from mini_agent.retry import RetryConfig
from mini_agent.runtime.tooling import (
    build_approval_engine,
    build_turn_context_providers,
    build_workspace_sandbox_manager,
    initialize_agent_tools,
    resolve_runtime_policy,
)


_DEFAULT_SYSTEM_PROMPT = "You are Mini-Agent, an intelligent assistant powered by MiniMax."


@dataclass(frozen=True)
class AgentKernelBuildOptions:
    """Build options for one agent-kernel instance."""

    approval_profile: str | None = None
    access_level: str | None = None
    requested_model: str | None = None
    requested_provider_source: str | None = None
    requested_provider_id: str | None = None
    console_output: bool = True
    allow_interactive_setup: bool = True
    suppress_background_output: bool = False
    session_store_dir: str | Path | None = None


def _route_diagnostics(route: Any) -> dict[str, Any]:
    if route is None:
        return {}
    return {
        "source": str(getattr(route, "source", "") or ""),
        "provider": str(getattr(getattr(route, "provider", None), "value", getattr(route, "provider", "")) or ""),
        "provider_id": str(getattr(route, "provider_id", "") or ""),
        "provider_name": str(getattr(route, "provider_name", "") or ""),
        "model": str(getattr(route, "model", "") or ""),
        "mapping_mode": str(getattr(route, "mapping_mode", "") or ""),
        "token_limit": int(getattr(route, "token_limit", 0) or 0),
    }


def _turn_context_diagnostics(
    providers: list[Any],
    *,
    session_store_dir: str | Path | None,
) -> dict[str, Any]:
    return {
        "count": len(providers),
        "provider_types": [type(provider).__name__ for provider in providers],
        "session_store_dir": str(session_store_dir) if session_store_dir is not None else None,
    }


def _runtime_policy_diagnostics(runtime_policy: Any) -> dict[str, Any]:
    policy = getattr(runtime_policy, "policy", None)
    return {
        "approval_profile": str(getattr(policy, "approval_profile", "") or ""),
        "access_level": str(getattr(policy, "access_level", "") or ""),
        "sandbox_mode": str(getattr(policy, "sandbox_mode", "") or ""),
    }


def _build_kernel_diagnostics(
    *,
    workspace_dir: Path,
    options: AgentKernelBuildOptions,
    llm_route: Any,
    runtime_policy: Any,
    tool_diagnostics: dict[str, Any],
    turn_context_providers: list[Any],
) -> dict[str, Any]:
    return {
        "workspace_dir": str(workspace_dir),
        "console_output": bool(options.console_output),
        "allow_interactive_setup": bool(options.allow_interactive_setup),
        "background_output_suppressed": bool(options.suppress_background_output),
        "route": _route_diagnostics(llm_route),
        "runtime_policy": _runtime_policy_diagnostics(runtime_policy),
        "tools": dict(tool_diagnostics.get("total_tools", {})),
        "workspace_tools": dict(tool_diagnostics.get("workspace_tools", {})),
        "shared_tools": dict(tool_diagnostics.get("shared_tools", {})),
        "skills": dict(tool_diagnostics.get("skills", {})),
        "mcp": dict(tool_diagnostics.get("mcp", {})),
        "turn_context": _turn_context_diagnostics(
            turn_context_providers,
            session_store_dir=options.session_store_dir,
        ),
    }


def _load_system_prompt(config: Config, skill_loader: Any) -> str:
    prompt_path = Config.find_config_file(config.agent.system_prompt_path)
    if prompt_path and prompt_path.exists():
        system_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = _DEFAULT_SYSTEM_PROMPT

    skills_metadata = ""
    if skill_loader:
        skills_metadata = skill_loader.get_skills_metadata_prompt() or ""

    if "{SKILLS_METADATA}" in system_prompt:
        system_prompt = system_prompt.replace("{SKILLS_METADATA}", skills_metadata)
    elif skills_metadata:
        system_prompt = f"{system_prompt.rstrip()}\n\n{skills_metadata}"

    return system_prompt


def _build_retry_config(config: Config) -> RetryConfig | None:
    if not config.llm.retry.enabled:
        return None
    return RetryConfig(
        enabled=config.llm.retry.enabled,
        max_retries=config.llm.retry.max_retries,
        initial_delay=config.llm.retry.initial_delay,
        max_delay=config.llm.retry.max_delay,
        exponential_base=config.llm.retry.exponential_base,
    )


async def build_agent_kernel(
    *,
    workspace_dir: Path,
    options: AgentKernelBuildOptions | None = None,
) -> Agent:
    """Build one runtime Agent via the unified kernel path."""
    resolved_workspace = workspace_dir.expanduser().resolve()
    resolved_workspace.mkdir(parents=True, exist_ok=True)

    opts = options or AgentKernelBuildOptions()
    stdout_sink = io.StringIO()
    stderr_sink = io.StringIO()
    with ExitStack() as stack:
        if opts.suppress_background_output:
            stack.enter_context(redirect_stdout(stdout_sink))
            stack.enter_context(redirect_stderr(stderr_sink))

        if opts.allow_interactive_setup:
            config = Config.load()
        else:
            config = Config.load(allow_interactive_setup=False)

        requested_model = (opts.requested_model or config.llm.model).strip()
        if opts.requested_provider_source and opts.requested_provider_id:
            llm_routes = [
                resolve_pinned_llm_candidate(
                    config,
                    provider_source=opts.requested_provider_source,
                    provider_id=opts.requested_provider_id,
                    model_id=requested_model,
                )
            ]
        else:
            llm_routes = resolve_routed_llm_candidates(
                config,
                requested_model=requested_model,
            )
        llm_client = FailoverLLMClient(
            routes=llm_routes,
            retry_config=_build_retry_config(config),
        )

        tools, skill_loader, tool_diagnostics = await initialize_agent_tools(
            config=config,
            workspace_dir=resolved_workspace,
            approval_profile_override=opts.approval_profile,
            access_level_override=opts.access_level,
        )
    system_prompt = _load_system_prompt(config, skill_loader)
    runtime_policy = resolve_runtime_policy(
        config,
        approval_profile_override=opts.approval_profile,
        access_level_override=opts.access_level,
    )
    sandbox_manager = build_workspace_sandbox_manager(
        config,
        resolved_workspace,
        policy_engine=runtime_policy,
    )

    turn_context_providers = build_turn_context_providers(
        config,
        resolved_workspace,
        session_store_dir=opts.session_store_dir,
    )
    agent = Agent(
        llm_client=llm_client,
        system_prompt=system_prompt,
        tools=tools,
        max_steps=config.agent.max_steps,
        max_tool_calls_per_step=config.agent.max_tool_calls_per_step,
        workspace_dir=str(resolved_workspace),
        token_limit=max(
            1,
            int(
                getattr(llm_routes[0], "token_limit", 0) or 80_000
            ),
        ),
        logger=create_agent_logger(config),
        console_output=opts.console_output,
        approval_engine=build_approval_engine(
            config,
            approval_profile_override=opts.approval_profile,
            access_level_override=opts.access_level,
        ),
        runtime_policy_engine=runtime_policy,
        sandbox_manager=sandbox_manager,
        turn_context_providers=turn_context_providers,
        turn_memory_automation=(
            TurnMemoryAutomation(str(resolved_workspace))
            if getattr(config.tools, "enable_note", False)
            else None
        ),
        turn_runtime_task_memory=TurnRuntimeTaskMemory(str(resolved_workspace)),
    )
    setattr(agent, "runtime_route", llm_routes[0] if llm_routes else None)
    setattr(agent, "skill_runtime", skill_loader)
    setattr(
        agent,
        "skill_catalog_loader",
        getattr(skill_loader, "loader", skill_loader) if skill_loader is not None else None,
    )
    setattr(
        agent,
        "kernel_diagnostics",
        _build_kernel_diagnostics(
            workspace_dir=resolved_workspace,
            options=opts,
            llm_route=llm_routes[0] if llm_routes else None,
            runtime_policy=runtime_policy,
            tool_diagnostics=tool_diagnostics,
            turn_context_providers=turn_context_providers,
        ),
    )
    return agent
