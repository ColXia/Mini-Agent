"""Tests for P15 T3.1 routing skeleton baseline."""

from __future__ import annotations

from mini_agent.agent_core import AgentRouteResolver, AgentRouteTable, BindingScope, RoutingContext


def test_route_table_respects_priority_order():
    table = AgentRouteTable()
    table.add_binding(scope=BindingScope.ACCOUNT, key="acct-1", agent_id="agent-account")
    table.add_binding(scope=BindingScope.PEER, key="peer-1", agent_id="agent-peer")

    resolved = table.resolve(
        RoutingContext(
            peer="peer-1",
            account_id="acct-1",
        )
    )

    assert resolved.agent_id == "agent-peer"
    assert resolved.matched_scope == BindingScope.PEER


def test_route_table_matches_roles_scope():
    table = AgentRouteTable()
    table.add_binding(scope=BindingScope.ROLES, key="maintainer", agent_id="agent-maintainer")
    table.add_binding(scope=BindingScope.CHANNEL, key="general", agent_id="agent-general")

    resolved = table.resolve(
        RoutingContext(
            roles=("reviewer", "maintainer"),
            channel="general",
        )
    )

    assert resolved.agent_id == "agent-maintainer"
    assert resolved.matched_scope == BindingScope.ROLES


def test_route_table_wildcard_and_default_fallback():
    table = AgentRouteTable()
    table.add_binding(scope=BindingScope.WILDCARD, key="*", agent_id="agent-any")

    wildcard = table.resolve(RoutingContext(channel="unknown"), default_agent_id="agent-default")
    assert wildcard.agent_id == "agent-any"
    assert wildcard.matched_scope == BindingScope.WILDCARD

    empty = AgentRouteTable().resolve(RoutingContext(), default_agent_id="agent-default")
    assert empty.agent_id == "agent-default"
    assert empty.matched_scope == BindingScope.DEFAULT


def test_route_resolver_cache_hit():
    table = AgentRouteTable()
    table.add_binding(scope=BindingScope.ACCOUNT, key="acct-2", agent_id="agent-account-2")

    resolver = AgentRouteResolver(table, max_cache_entries=8)
    context = RoutingContext(account_id="acct-2")

    first = resolver.resolve(context)
    second = resolver.resolve(context)

    assert first.from_cache is False
    assert second.from_cache is True
    assert second.agent_id == "agent-account-2"
