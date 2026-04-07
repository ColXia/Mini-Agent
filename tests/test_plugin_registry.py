"""Tests for plugin capability registration boundaries."""

import pytest

from mini_agent.plugins import CapabilityDomain, PluginCapabilityRegistry


def test_register_and_resolve_capability():
    registry = PluginCapabilityRegistry()

    created = registry.register(
        plugin_id="plugin.alpha",
        domain="tool",
        name="web_search",
        description="Search the web.",
        metadata={"version": "1"},
    )
    resolved = registry.resolve(CapabilityDomain.TOOL, "web_search")

    assert resolved == created
    assert resolved is not None
    assert resolved.plugin_id == "plugin.alpha"
    assert resolved.metadata["version"] == "1"


def test_domain_boundary_keeps_namespaced_slots():
    registry = PluginCapabilityRegistry()
    registry.register("plugin.alpha", "tool", "dispatch")
    registry.register("plugin.alpha", "hook", "dispatch")

    tool_capability = registry.resolve("tool", "dispatch")
    hook_capability = registry.resolve("hook", "dispatch")

    assert tool_capability is not None
    assert hook_capability is not None
    assert tool_capability.domain == CapabilityDomain.TOOL
    assert hook_capability.domain == CapabilityDomain.HOOK


def test_conflict_requires_replace_flag():
    registry = PluginCapabilityRegistry()
    registry.register("plugin.alpha", "provider", "openai")

    with pytest.raises(ValueError):
        registry.register("plugin.beta", "provider", "openai")

    replaced = registry.register("plugin.beta", "provider", "openai", replace=True)
    assert replaced.plugin_id == "plugin.beta"


def test_unregister_respects_plugin_and_domain_filters():
    registry = PluginCapabilityRegistry()
    registry.register("plugin.alpha", "provider", "openai")
    registry.register("plugin.alpha", "tool", "web_search")
    registry.register("plugin.beta", "tool", "web_search_v2")

    removed_count = registry.unregister("plugin.alpha", domain="tool")
    assert removed_count == 1

    assert registry.resolve("provider", "openai") is not None
    assert registry.resolve("tool", "web_search") is None
    assert registry.resolve("tool", "web_search_v2") is not None


def test_invalid_domain_is_rejected():
    registry = PluginCapabilityRegistry()

    with pytest.raises(ValueError):
        registry.register("plugin.alpha", "executor", "run")
