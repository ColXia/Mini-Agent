"""Typed runtime binding helpers for agent-core wiring."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field, replace
from typing import Any, Iterator


UNSET_RUNTIME_VALUE = object()


def _normalized_kernel_diagnostics(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return dict(value)


@dataclass(frozen=True)
class AgentRuntimeBindings:
    """Typed runtime attachments assembled around one agent instance."""

    runtime_route: Any | None = None
    skill_runtime: Any | None = None
    skill_catalog_loader: Any | None = None
    kernel_diagnostics: dict[str, Any] = field(default_factory=dict)

    def with_updates(
        self,
        *,
        runtime_route: Any = UNSET_RUNTIME_VALUE,
        skill_runtime: Any = UNSET_RUNTIME_VALUE,
        skill_catalog_loader: Any = UNSET_RUNTIME_VALUE,
        kernel_diagnostics: Any = UNSET_RUNTIME_VALUE,
    ) -> "AgentRuntimeBindings":
        updates: dict[str, Any] = {}
        if runtime_route is not UNSET_RUNTIME_VALUE:
            updates["runtime_route"] = runtime_route
        if skill_runtime is not UNSET_RUNTIME_VALUE:
            updates["skill_runtime"] = skill_runtime
        if skill_catalog_loader is not UNSET_RUNTIME_VALUE:
            updates["skill_catalog_loader"] = skill_catalog_loader
        if kernel_diagnostics is not UNSET_RUNTIME_VALUE:
            updates["kernel_diagnostics"] = _normalized_kernel_diagnostics(kernel_diagnostics)
        if not updates:
            return self
        return replace(self, **updates)


@dataclass(frozen=True)
class AgentRuntimeServices:
    """Typed runtime service state assembled around one agent instance."""

    runtime_policy_engine: Any | None = None
    approval_engine: Any | None = None
    sandbox_manager: Any | None = None
    tool_approval_handler: Any | None = None

    def with_updates(
        self,
        *,
        runtime_policy_engine: Any = UNSET_RUNTIME_VALUE,
        approval_engine: Any = UNSET_RUNTIME_VALUE,
        sandbox_manager: Any = UNSET_RUNTIME_VALUE,
        tool_approval_handler: Any = UNSET_RUNTIME_VALUE,
    ) -> "AgentRuntimeServices":
        updates: dict[str, Any] = {}
        if runtime_policy_engine is not UNSET_RUNTIME_VALUE:
            updates["runtime_policy_engine"] = runtime_policy_engine
        if approval_engine is not UNSET_RUNTIME_VALUE:
            updates["approval_engine"] = approval_engine
        if sandbox_manager is not UNSET_RUNTIME_VALUE:
            updates["sandbox_manager"] = sandbox_manager
        if tool_approval_handler is not UNSET_RUNTIME_VALUE:
            updates["tool_approval_handler"] = tool_approval_handler
        if not updates:
            return self
        return replace(self, **updates)


def get_agent_runtime_services(agent: Any) -> AgentRuntimeServices:
    """Resolve runtime services from the strongest available agent contract."""

    current = getattr(agent, "runtime_services", None)
    if isinstance(current, AgentRuntimeServices):
        return current
    return AgentRuntimeServices(
        runtime_policy_engine=getattr(agent, "runtime_policy_engine", None),
        approval_engine=getattr(agent, "approval_engine", None),
        sandbox_manager=getattr(agent, "sandbox_manager", None),
        tool_approval_handler=getattr(agent, "tool_approval_handler", None),
    )


def _current_runtime_services(agent: Any) -> AgentRuntimeServices:
    return get_agent_runtime_services(agent)


def _try_setattr(target: Any, name: str, value: Any) -> bool:
    try:
        setattr(target, name, value)
    except Exception:
        return False
    return True


def set_agent_runtime_bindings(
    agent: Any,
    *,
    runtime_route: Any = UNSET_RUNTIME_VALUE,
    skill_runtime: Any = UNSET_RUNTIME_VALUE,
    skill_catalog_loader: Any = UNSET_RUNTIME_VALUE,
    kernel_diagnostics: Any = UNSET_RUNTIME_VALUE,
) -> Any:
    """Apply runtime binding updates using the strongest available contract."""

    binder = getattr(agent, "set_runtime_bindings", None)
    if callable(binder):
        return binder(
            runtime_route=runtime_route,
            skill_runtime=skill_runtime,
            skill_catalog_loader=skill_catalog_loader,
            kernel_diagnostics=kernel_diagnostics,
        )

    if runtime_route is not UNSET_RUNTIME_VALUE:
        setattr(agent, "runtime_route", runtime_route)
    if skill_runtime is not UNSET_RUNTIME_VALUE:
        setattr(agent, "skill_runtime", skill_runtime)
    if skill_catalog_loader is not UNSET_RUNTIME_VALUE:
        setattr(agent, "skill_catalog_loader", skill_catalog_loader)
    if kernel_diagnostics is not UNSET_RUNTIME_VALUE:
        setattr(agent, "kernel_diagnostics", _normalized_kernel_diagnostics(kernel_diagnostics))
    return getattr(agent, "runtime_bindings", None)


def set_agent_runtime_services(
    agent: Any,
    *,
    runtime_policy_engine: Any = UNSET_RUNTIME_VALUE,
    approval_engine: Any = UNSET_RUNTIME_VALUE,
    sandbox_manager: Any = UNSET_RUNTIME_VALUE,
    tool_approval_handler: Any = UNSET_RUNTIME_VALUE,
) -> AgentRuntimeServices | None:
    """Apply explicit runtime service dependencies to one agent."""

    updater = getattr(agent, "set_runtime_services", None)
    if callable(updater):
        update_kwargs: dict[str, Any] = {}
        if runtime_policy_engine is not UNSET_RUNTIME_VALUE:
            update_kwargs["runtime_policy_engine"] = runtime_policy_engine
        if approval_engine is not UNSET_RUNTIME_VALUE:
            update_kwargs["approval_engine"] = approval_engine
        if sandbox_manager is not UNSET_RUNTIME_VALUE:
            update_kwargs["sandbox_manager"] = sandbox_manager
        if tool_approval_handler is not UNSET_RUNTIME_VALUE:
            update_kwargs["tool_approval_handler"] = tool_approval_handler
        return updater(**update_kwargs)

    services = _current_runtime_services(agent).with_updates(
        runtime_policy_engine=runtime_policy_engine,
        approval_engine=approval_engine,
        sandbox_manager=sandbox_manager,
        tool_approval_handler=tool_approval_handler,
    )
    contract_applied = _try_setattr(agent, "runtime_services", services)

    if runtime_policy_engine is not UNSET_RUNTIME_VALUE:
        direct_applied = _try_setattr(agent, "runtime_policy_engine", runtime_policy_engine)
        if not (contract_applied or direct_applied):
            raise AttributeError("Agent does not accept runtime_policy_engine runtime service.")
    if approval_engine is not UNSET_RUNTIME_VALUE:
        direct_applied = _try_setattr(agent, "approval_engine", approval_engine)
        if not (contract_applied or direct_applied):
            raise AttributeError("Agent does not accept approval_engine runtime service.")
    if sandbox_manager is not UNSET_RUNTIME_VALUE:
        direct_applied = _try_setattr(agent, "sandbox_manager", sandbox_manager)
        if not (contract_applied or direct_applied):
            raise AttributeError("Agent does not accept sandbox_manager runtime service.")
    if tool_approval_handler is not UNSET_RUNTIME_VALUE:
        direct_applied = _try_setattr(agent, "tool_approval_handler", tool_approval_handler)
        if not (contract_applied or direct_applied):
            raise AttributeError("Agent does not accept tool_approval_handler runtime service.")
    return services


def set_agent_tool_approval_handler(agent: Any, handler: Any) -> None:
    """Bind one tool-approval handler to an agent-like object."""

    setter = getattr(agent, "set_tool_approval_handler", None)
    if callable(setter):
        setter(handler)
        return
    set_agent_runtime_services(agent, tool_approval_handler=handler)


@contextmanager
def override_agent_tool_approval_handler(agent: Any, handler: Any) -> Iterator[Any | None]:
    """Temporarily override the tool-approval handler for one agent-like object."""

    override = getattr(agent, "override_tool_approval_handler", None)
    if callable(override):
        with override(handler) as previous:
            yield previous
        return

    previous = _current_runtime_services(agent).tool_approval_handler
    set_agent_tool_approval_handler(agent, handler)
    try:
        yield previous
    finally:
        set_agent_tool_approval_handler(agent, previous)


__all__ = [
    "AgentRuntimeBindings",
    "AgentRuntimeServices",
    "UNSET_RUNTIME_VALUE",
    "get_agent_runtime_services",
    "override_agent_tool_approval_handler",
    "set_agent_runtime_bindings",
    "set_agent_runtime_services",
    "set_agent_tool_approval_handler",
]
