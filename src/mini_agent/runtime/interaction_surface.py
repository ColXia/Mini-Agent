"""Compatibility re-export for runtime interaction-surface helpers."""

from __future__ import annotations

from importlib import import_module

__all__ = [
    "ACTIVE_REMOTE_CHANNEL_ADAPTERS",
    "InteractionBinding",
    "InteractionSurface",
    "USER_ENTRANCES",
    "normalize_channel_type",
    "normalize_surface_label",
    "resolve_interaction_binding",
    "resolve_interaction_surface",
    "resolve_remote_channel",
    "resolve_user_entrance",
]

_COMPAT_EXPORTS: dict[str, tuple[str, str]] = {
    "ACTIVE_REMOTE_CHANNEL_ADAPTERS": (".support.interaction_surface", "ACTIVE_REMOTE_CHANNEL_ADAPTERS"),
    "InteractionBinding": (".support.interaction_surface", "InteractionBinding"),
    "InteractionSurface": (".support.interaction_surface", "InteractionSurface"),
    "USER_ENTRANCES": (".support.interaction_surface", "USER_ENTRANCES"),
    "normalize_channel_type": (".support.interaction_surface", "normalize_channel_type"),
    "normalize_surface_label": (".support.interaction_surface", "normalize_surface_label"),
    "resolve_interaction_binding": (".support.interaction_surface", "resolve_interaction_binding"),
    "resolve_interaction_surface": (".support.interaction_surface", "resolve_interaction_surface"),
    "resolve_remote_channel": (".support.interaction_surface", "resolve_remote_channel"),
    "resolve_user_entrance": (".support.interaction_surface", "resolve_user_entrance"),
}


def __getattr__(name: str):
    export = _COMPAT_EXPORTS.get(name)
    if export is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attr_name = export
    module = import_module(module_name, __package__)
    value = getattr(module, attr_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
