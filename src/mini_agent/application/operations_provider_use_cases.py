"""Compatibility re-export for provider operations use cases."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "ModelCapabilityProbeService",
    "ModelDiscoveryService",
    "ProviderOperationsUseCases",
    "ProviderType",
    "recommend_discovered_model",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "ModelCapabilityProbeService": (
        "mini_agent.model_manager.capability_probe",
        "ModelCapabilityProbeService",
    ),
    "ModelDiscoveryService": ("mini_agent.model_manager.model_discovery", "ModelDiscoveryService"),
    "ProviderOperationsUseCases": (
        ".use_cases.operations_provider_use_cases",
        "ProviderOperationsUseCases",
    ),
    "ProviderType": ("mini_agent.model_manager.model_discovery", "ProviderType"),
    "recommend_discovered_model": (
        "mini_agent.model_manager.model_discovery",
        "recommend_discovered_model",
    ),
}


def __getattr__(name: str):
    export = _COMPAT_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = export
    import_package = None if module_name.startswith("mini_agent.") else __package__
    module = import_module(module_name, import_package)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
