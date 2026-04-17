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
from typing import Any, Callable

from mini_agent.agent_core.engine import Agent
from mini_agent.agent_core.runtime_bindings import set_agent_runtime_bindings
from mini_agent.config import Config
from mini_agent.logger import create_agent_logger
from mini_agent.memory.automation import TurnMemoryAutomation
from mini_agent.memory.runtime_task_memory import TurnRuntimeTaskMemory
from mini_agent.model_manager.bootstrap import bootstrap_llm_settings_from_config
from mini_agent.model_manager.failover import FailoverLLMClient
from mini_agent.model_manager.rectifier import RequestRectifierOptions
from mini_agent.model_manager.model_mapper import RouteIntent
from mini_agent.model_manager.model_mapper import RouteRequirementProfile
from mini_agent.model_manager.runtime import (
    resolve_pinned_llm_candidate,
    resolve_routed_llm_candidates,
)
from mini_agent.retry import RetryConfig
from mini_agent.llm.protocol_binding import ProtocolRequestPolicy
from mini_agent.runtime.support.tooling import (
    build_approval_engine,
    build_workspace_sandbox_manager,
    initialize_agent_tools,
    resolve_runtime_policy,
)
from mini_agent.runtime.support.turn_context_provider_builder import build_turn_context_providers


_DEFAULT_SYSTEM_PROMPT = "You are Mini-Agent, an intelligent assistant powered by MiniMax."


@dataclass(frozen=True)
class AgentKernelBuildOptions:
    """Build options for one agent-kernel instance."""

    config: Config | None = None
    config_loader: Callable[[bool], Config] | None = None
    approval_profile: str | None = None
    access_level: str | None = None
    requested_model: str | None = None
    requested_model_route_intent: RouteIntent | None = None
    requested_provider_source: str | None = None
    requested_provider_id: str | None = None
    console_output: bool = True
    allow_interactive_setup: bool = True
    suppress_background_output: bool = False
    session_store_dir: str | Path | None = None


def _route_diagnostics(route: Any) -> dict[str, Any]:
    if route is None:
        return {}
    diagnostics = {
        "source": str(getattr(route, "source", "") or ""),
        "provider": str(getattr(getattr(route, "provider", None), "value", getattr(route, "provider", "")) or ""),
        "provider_source": str(getattr(route, "provider_source", "") or ""),
        "provider_id": str(getattr(route, "provider_id", "") or ""),
        "provider_name": str(getattr(route, "provider_name", "") or ""),
        "model": str(getattr(route, "model", "") or ""),
        "mapping_mode": str(getattr(route, "mapping_mode", "") or ""),
        "requested_model": str(getattr(route, "requested_model", "") or ""),
        "catalog_path": str(getattr(route, "catalog_path", "") or ""),
        "priority": getattr(route, "priority", None),
        "breaker_state": str(getattr(route, "breaker_state", "") or ""),
        "breaker_allowed": getattr(route, "breaker_allowed", None),
        "context_window": getattr(route, "context_window", None),
        "learned_token_limit": getattr(route, "learned_token_limit", None),
        "token_limit": int(getattr(route, "token_limit", 0) or 0),
        "supports_tools": getattr(route, "supports_tools", None),
        "supports_tools_truth": str(getattr(route, "supports_tools_truth", "") or ""),
        "supports_tools_confidence": str(getattr(route, "supports_tools_confidence", "") or ""),
        "supports_tools_source": str(getattr(route, "supports_tools_source", "") or ""),
        "supports_thinking": getattr(route, "supports_thinking", None),
        "supports_thinking_truth": str(getattr(route, "supports_thinking_truth", "") or ""),
        "supports_thinking_confidence": str(getattr(route, "supports_thinking_confidence", "") or ""),
        "supports_thinking_source": str(getattr(route, "supports_thinking_source", "") or ""),
    }
    model_route = getattr(route, "route_diagnostics", None)
    if isinstance(model_route, dict):
        diagnostics.update(
            {
                "resolution_kind": model_route.get("resolution_kind"),
                "catalog_source": model_route.get("catalog_source"),
                "route_intent": model_route.get("route_intent"),
                "selected_reason": model_route.get("selected_reason"),
                "fallback_reason": model_route.get("fallback_reason"),
                "candidate_count": model_route.get("candidate_count"),
                "allowed_candidate_count": model_route.get("allowed_candidate_count"),
                "blocked_candidate_count": model_route.get("blocked_candidate_count"),
                "bootstrap_selected_provider": model_route.get("bootstrap_selected_provider"),
                "bootstrap_selection_reason": model_route.get("bootstrap_selection_reason"),
                "bootstrap_selection_policy": model_route.get("bootstrap_selection_policy"),
                "bootstrap_preferred_provider": model_route.get("bootstrap_preferred_provider"),
                "bootstrap_preferred_provider_available": (
                    model_route.get("bootstrap_preferred_provider_available")
                ),
                "bootstrap_alternatives": list(model_route.get("bootstrap_alternatives", [])),
                "error": model_route.get("error"),
                "candidates": [
                    dict(item)
                    for item in model_route.get("candidates", [])
                    if isinstance(item, dict)
                ],
            }
        )
    return diagnostics


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


def _route_requirements_diagnostics(requirements: RouteRequirementProfile) -> dict[str, Any]:
    return {
        "require_tools": bool(requirements.require_tools),
        "prefer_thinking": bool(requirements.prefer_thinking),
        "min_context_window": (
            int(requirements.min_context_window)
            if requirements.min_context_window is not None
            else None
        ),
    }


def _should_require_tools(config: Config, runtime_policy: Any) -> bool:
    allowed = runtime_policy.is_tool_allowed if runtime_policy is not None else (lambda _name: True)
    static_tool_groups = [
        (bool(config.tools.enable_bash), ("bash", "bash_output", "bash_kill")),
        (bool(config.tools.enable_file_tools), ("read_file", "write_file", "edit_file", "docling_parse")),
        (bool(getattr(config.tools, "enable_knowledge_base", True)), ("knowledge_base_query",)),
        (bool(config.tools.enable_note), ("record_note", "recall_notes", "user_modeling")),
    ]
    for enabled, tool_names in static_tool_groups:
        if enabled and any(allowed(name) for name in tool_names):
            return True

    # Skills and MCP are dynamic catalogs. If enabled, the agent is operating in a tool-using
    # mode even though the concrete tool names are not known before bootstrap.
    if bool(config.tools.enable_skills):
        return True
    if bool(config.tools.enable_mcp):
        return True
    return False


def _build_route_requirements(config: Config, runtime_policy: Any) -> RouteRequirementProfile:
    return RouteRequirementProfile(
        require_tools=_should_require_tools(config, runtime_policy),
        prefer_thinking=True,
        min_context_window=None,
    ).normalized()


def _build_kernel_diagnostics(
    *,
    workspace_dir: Path,
    options: AgentKernelBuildOptions,
    llm_route: Any,
    route_requirements: RouteRequirementProfile,
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
        "route_requirements": _route_requirements_diagnostics(route_requirements),
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
    if not config.runtime.retry.enabled:
        return None
    return RetryConfig(
        enabled=config.runtime.retry.enabled,
        max_retries=config.runtime.retry.max_retries,
        initial_delay=config.runtime.retry.initial_delay,
        max_delay=config.runtime.retry.max_delay,
        exponential_base=config.runtime.retry.exponential_base,
    )


def _build_request_policy(config: Config) -> ProtocolRequestPolicy:
    request_policy = config.runtime.request_policy
    return ProtocolRequestPolicy(
        max_output_tokens=request_policy.max_output_tokens,
        reasoning_split_enabled=request_policy.reasoning_split_enabled,
        thinking_budget_tokens=request_policy.thinking_budget_tokens,
        temperature=request_policy.temperature,
        streaming_enabled=request_policy.streaming_enabled,
        include_stream_usage=request_policy.include_stream_usage,
    )


def _build_rectifier_options(config: Config) -> RequestRectifierOptions:
    rectifier = config.runtime.rectifier
    return RequestRectifierOptions(
        enabled=rectifier.enabled,
        cache_injection=rectifier.cache_injection,
        strip_thinking_signature=rectifier.strip_thinking_signature,
    )


def _resolve_requested_model_route_intent(
    options: AgentKernelBuildOptions,
    *,
    requested_model: str | None,
) -> RouteIntent:
    if options.requested_model_route_intent == "automatic":
        return "automatic"
    if options.requested_model_route_intent == "explicit":
        return "explicit"
    return "explicit" if requested_model is not None else "automatic"


def _resolve_kernel_config(opts: AgentKernelBuildOptions) -> Config:
    if opts.config is not None:
        return opts.config
    if opts.config_loader is not None:
        return opts.config_loader(bool(opts.allow_interactive_setup))
    raise RuntimeError("Agent kernel config/config_loader was not injected.")


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

        config = _resolve_kernel_config(opts)

        runtime_policy = resolve_runtime_policy(
            config,
            approval_profile_override=opts.approval_profile,
            access_level_override=opts.access_level,
        )
        route_requirements = _build_route_requirements(config, runtime_policy)
        bootstrap_llm = bootstrap_llm_settings_from_config(config)
        requested_model = (opts.requested_model or "").strip() or None
        requested_model_route_intent = _resolve_requested_model_route_intent(
            opts,
            requested_model=requested_model,
        )
        if opts.requested_provider_source and opts.requested_provider_id:
            llm_routes = [
                resolve_pinned_llm_candidate(
                    provider_source=opts.requested_provider_source,
                    provider_id=opts.requested_provider_id,
                    model_id=requested_model,
                )
            ]
        else:
            llm_routes = resolve_routed_llm_candidates(
                bootstrap_llm=bootstrap_llm,
                requested_model=requested_model,
                route_requirements=route_requirements,
                route_intent=requested_model_route_intent,
            )
        llm_client = FailoverLLMClient(
            routes=llm_routes,
            retry_config=_build_retry_config(config),
            request_policy=_build_request_policy(config),
            rectifier_options=_build_rectifier_options(config),
        )

        tools, skill_loader, tool_diagnostics = await initialize_agent_tools(
            config=config,
            workspace_dir=resolved_workspace,
            approval_profile_override=opts.approval_profile,
            access_level_override=opts.access_level,
        )
    system_prompt = _load_system_prompt(config, skill_loader)
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
    set_agent_runtime_bindings(
        agent,
        runtime_route=llm_routes[0] if llm_routes else None,
        skill_runtime=skill_loader,
        skill_catalog_loader=(
            getattr(skill_loader, "loader", skill_loader) if skill_loader is not None else None
        ),
        kernel_diagnostics=_build_kernel_diagnostics(
            workspace_dir=resolved_workspace,
            options=opts,
            llm_route=llm_routes[0] if llm_routes else None,
            route_requirements=route_requirements,
            runtime_policy=runtime_policy,
            tool_diagnostics=tool_diagnostics,
            turn_context_providers=turn_context_providers,
        ),
    )
    return agent
