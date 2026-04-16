"""Shared interaction normalization and entrance/channel semantics."""

from .surface import (
    ACTIVE_REMOTE_CHANNEL_ADAPTERS,
    InteractionBinding,
    InteractionSurface,
    USER_ENTRANCES,
    normalize_channel_type,
    normalize_surface_label,
    resolve_interaction_binding,
    resolve_interaction_surface,
    resolve_remote_channel,
    resolve_user_entrance,
)

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
