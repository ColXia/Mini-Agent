"""Lean agent routing skeleton with deterministic priority matching."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class BindingScope(str, Enum):
    """Supported binding scopes in descending priority."""

    PEER = "peer"
    PARENT = "parent"
    WILDCARD = "wildcard"
    GUILD = "guild"
    ROLES = "roles"
    TEAM = "team"
    ACCOUNT = "account"
    CHANNEL = "channel"
    DEFAULT = "default"


SCOPE_PRIORITY: tuple[BindingScope, ...] = (
    BindingScope.PEER,
    BindingScope.PARENT,
    BindingScope.WILDCARD,
    BindingScope.GUILD,
    BindingScope.ROLES,
    BindingScope.TEAM,
    BindingScope.ACCOUNT,
    BindingScope.CHANNEL,
    BindingScope.DEFAULT,
)


@dataclass(frozen=True)
class AgentBinding:
    """Route binding record."""

    scope: BindingScope
    key: str
    agent_id: str


@dataclass(frozen=True)
class RoutingContext:
    """Lookup context for resolving one agent route."""

    peer: str | None = None
    parent: str | None = None
    guild: str | None = None
    roles: tuple[str, ...] = ()
    team: str | None = None
    account_id: str | None = None
    channel: str | None = None

    def cache_key(self) -> str:
        return "|".join(
            [
                self.peer or "",
                self.parent or "",
                self.guild or "",
                ",".join(self.roles),
                self.team or "",
                self.account_id or "",
                self.channel or "",
            ]
        )


@dataclass(frozen=True)
class RouteResolution:
    """Resolved route output."""

    agent_id: str
    matched_scope: BindingScope
    matched_key: str
    from_cache: bool = False


class AgentRouteTable:
    """In-memory route table with explicit priority order."""

    def __init__(self) -> None:
        self._bindings: list[AgentBinding] = []

    def add_binding(self, *, scope: BindingScope, key: str, agent_id: str) -> None:
        normalized_key = key.strip()
        normalized_agent = agent_id.strip()
        if not normalized_key:
            raise ValueError("Binding key must not be empty.")
        if not normalized_agent:
            raise ValueError("Agent id must not be empty.")
        self._bindings.append(AgentBinding(scope=scope, key=normalized_key, agent_id=normalized_agent))

    def list_bindings(self) -> tuple[AgentBinding, ...]:
        return tuple(self._bindings)

    def resolve(self, context: RoutingContext, *, default_agent_id: str = "default-agent") -> RouteResolution:
        by_scope: dict[BindingScope, list[AgentBinding]] = {scope: [] for scope in SCOPE_PRIORITY}
        for binding in self._bindings:
            by_scope[binding.scope].append(binding)

        for scope in SCOPE_PRIORITY:
            candidates = by_scope.get(scope, [])
            if not candidates:
                continue

            if scope == BindingScope.PEER:
                value = context.peer
                match = _find_exact(candidates, value)
            elif scope == BindingScope.PARENT:
                value = context.parent
                match = _find_exact(candidates, value)
            elif scope == BindingScope.WILDCARD:
                match = _find_exact(candidates, "*")
            elif scope == BindingScope.GUILD:
                value = context.guild
                match = _find_exact(candidates, value)
            elif scope == BindingScope.ROLES:
                match = _find_first_role(candidates, context.roles)
            elif scope == BindingScope.TEAM:
                value = context.team
                match = _find_exact(candidates, value)
            elif scope == BindingScope.ACCOUNT:
                value = context.account_id
                match = _find_exact(candidates, value)
            elif scope == BindingScope.CHANNEL:
                value = context.channel
                match = _find_exact(candidates, value)
            else:
                match = _find_exact(candidates, "default")

            if match is not None:
                return RouteResolution(
                    agent_id=match.agent_id,
                    matched_scope=match.scope,
                    matched_key=match.key,
                    from_cache=False,
                )

        return RouteResolution(
            agent_id=default_agent_id,
            matched_scope=BindingScope.DEFAULT,
            matched_key="fallback",
            from_cache=False,
        )


def _find_exact(candidates: list[AgentBinding], value: str | None) -> AgentBinding | None:
    if value is None:
        return None
    for binding in candidates:
        if binding.key == value:
            return binding
    return None


def _find_first_role(candidates: list[AgentBinding], roles: tuple[str, ...]) -> AgentBinding | None:
    if not roles:
        return None
    role_set = {role for role in roles if role}
    for binding in candidates:
        if binding.key in role_set:
            return binding
    return None


class AgentRouteResolver:
    """Route resolver with small LRU-like cache."""

    def __init__(self, route_table: AgentRouteTable, *, max_cache_entries: int = 4000) -> None:
        self.route_table = route_table
        self.max_cache_entries = max(64, int(max_cache_entries))
        self._cache: dict[str, RouteResolution] = {}

    def resolve(self, context: RoutingContext, *, default_agent_id: str = "default-agent") -> RouteResolution:
        key = context.cache_key()
        cached = self._cache.get(key)
        if cached is not None:
            return RouteResolution(
                agent_id=cached.agent_id,
                matched_scope=cached.matched_scope,
                matched_key=cached.matched_key,
                from_cache=True,
            )

        resolved = self.route_table.resolve(context, default_agent_id=default_agent_id)
        self._cache[key] = resolved
        if len(self._cache) > self.max_cache_entries:
            oldest_key = next(iter(self._cache))
            self._cache.pop(oldest_key, None)
        return resolved

    def clear_cache(self) -> None:
        self._cache.clear()
