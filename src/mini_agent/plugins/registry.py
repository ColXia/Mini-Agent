"""Plugin capability registry with explicit domain boundaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class CapabilityDomain(str, Enum):
    """Supported capability domains for plugin registration."""

    PROVIDER = "provider"
    CHANNEL = "channel"
    TOOL = "tool"
    HOOK = "hook"


def _normalize_domain(domain: str | CapabilityDomain) -> CapabilityDomain:
    if isinstance(domain, CapabilityDomain):
        return domain
    try:
        return CapabilityDomain(domain.strip().lower())
    except Exception as exc:
        raise ValueError(
            "Invalid capability domain. Use one of: provider, channel, tool, hook."
        ) from exc


def _normalize_id(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} cannot be empty.")
    return normalized


@dataclass(frozen=True)
class PluginCapability:
    """Single plugin capability registration entry."""

    plugin_id: str
    domain: CapabilityDomain
    name: str
    description: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


class PluginCapabilityRegistry:
    """Registry keyed by capability domain + name."""

    def __init__(self) -> None:
        self._capabilities: dict[tuple[CapabilityDomain, str], PluginCapability] = {}

    def register(
        self,
        plugin_id: str,
        domain: str | CapabilityDomain,
        name: str,
        description: str = "",
        metadata: dict[str, Any] | None = None,
        replace: bool = False,
    ) -> PluginCapability:
        normalized_plugin_id = _normalize_id(plugin_id, "plugin_id")
        normalized_name = _normalize_id(name, "name")
        normalized_domain = _normalize_domain(domain)
        capability_key = (normalized_domain, normalized_name)

        existing = self._capabilities.get(capability_key)
        if existing and existing.plugin_id != normalized_plugin_id and not replace:
            raise ValueError(
                f"Capability '{normalized_domain.value}:{normalized_name}' is already "
                f"owned by plugin '{existing.plugin_id}'."
            )

        capability = PluginCapability(
            plugin_id=normalized_plugin_id,
            domain=normalized_domain,
            name=normalized_name,
            description=description.strip(),
            metadata=dict(metadata or {}),
        )
        self._capabilities[capability_key] = capability
        return capability

    def resolve(
        self,
        domain: str | CapabilityDomain,
        name: str,
    ) -> PluginCapability | None:
        normalized_domain = _normalize_domain(domain)
        normalized_name = _normalize_id(name, "name")
        return self._capabilities.get((normalized_domain, normalized_name))

    def list(self, domain: str | CapabilityDomain | None = None) -> list[PluginCapability]:
        if domain is None:
            values = list(self._capabilities.values())
        else:
            normalized_domain = _normalize_domain(domain)
            values = [
                capability
                for capability in self._capabilities.values()
                if capability.domain == normalized_domain
            ]
        return sorted(values, key=lambda capability: (capability.domain.value, capability.name))

    def list_by_plugin(self, plugin_id: str) -> list[PluginCapability]:
        normalized_plugin_id = _normalize_id(plugin_id, "plugin_id")
        values = [
            capability
            for capability in self._capabilities.values()
            if capability.plugin_id == normalized_plugin_id
        ]
        return sorted(values, key=lambda capability: (capability.domain.value, capability.name))

    def unregister(
        self,
        plugin_id: str,
        domain: str | CapabilityDomain | None = None,
        name: str | None = None,
    ) -> int:
        normalized_plugin_id = _normalize_id(plugin_id, "plugin_id")
        normalized_domain = _normalize_domain(domain) if domain is not None else None
        normalized_name = _normalize_id(name, "name") if name is not None else None

        to_remove: list[tuple[CapabilityDomain, str]] = []
        for key, capability in self._capabilities.items():
            if capability.plugin_id != normalized_plugin_id:
                continue
            if normalized_domain is not None and capability.domain != normalized_domain:
                continue
            if normalized_name is not None and capability.name != normalized_name:
                continue
            to_remove.append(key)

        for key in to_remove:
            self._capabilities.pop(key, None)

        return len(to_remove)

    def clear(self) -> None:
        self._capabilities.clear()
