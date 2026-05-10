"""Model user service for v11.3.

This module provides the ModelUserService that sits between
User Surfaces and the Business Logic Layer for model-related operations.

Key responsibilities:
- Model list
- Model switching
- Model capability query
- Model diagnostics
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable

from mini_agent.model_manager.model_pool_contracts import (
    ModelCapabilityProfile,
    ModelDescriptor,
    ProviderSource,
)
from mini_agent.utils.text import safe_text


def _safe_text(value: Any) -> str:
    return safe_text(value)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ModelSwitchResultKind(str, Enum):
    """Result kinds for model switch."""

    SUCCESS = "success"
    REJECTED = "rejected"
    NOT_FOUND = "not_found"


@dataclass(frozen=True, slots=True)
class ModelView:
    """View of a model for user surfaces."""

    model_id: str
    provider_id: str
    provider_name: str
    display_name: str
    is_current: bool = False
    supports_tools: bool = False
    supports_thinking: bool = False
    context_window: int | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def full_id(self) -> str:
        return f"{self.provider_id}.{self.model_id}"


@dataclass(frozen=True, slots=True)
class ModelSwitchResult:
    """Result of model switch operation."""

    result_kind: ModelSwitchResultKind
    model_id: str | None = None
    provider_id: str | None = None
    previous_model_id: str | None = None
    error_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ModelCapabilityView:
    """View of model capabilities for user surfaces."""

    model_id: str
    provider_id: str
    supports_tools: bool
    supports_thinking: bool
    context_window: int | None
    token_limit: int | None
    streaming_support: bool = True
    confidence: str = "unknown"

    @property
    def is_tools_capable(self) -> bool:
        return self.supports_tools

    @property
    def is_thinking_capable(self) -> bool:
        return self.supports_thinking


@dataclass(slots=True)
class ModelUserService:
    """User service for model-related operations.

    This service provides a stable interface for TUI / Desktop / Remote
    to interact with models without directly accessing the model pool.

    The service aggregates:
    - Model pool queries
    - Model binding state
    - Model switching logic
    - Capability queries
    """

    _current_model_id: str | None = None
    _current_provider_id: str | None = None
    _models: dict[str, ModelView] = field(default_factory=dict)
    _model_switcher: Callable[[str, str | None], ModelSwitchResult] | None = None
    _model_lister: Callable[[], list[ModelView]] | None = None
    _capability_getter: Callable[[str, str | None], ModelCapabilityView | None] | None = None

    def list_available_models(self) -> list[ModelView]:
        """List all available models.

        Returns:
            A list of ModelView objects
        """
        if self._model_lister:
            try:
                models = self._model_lister()
                # Mark current model
                if self._current_model_id:
                    for i, model in enumerate(models):
                        if model.model_id == self._current_model_id:
                            models[i] = ModelView(
                                model_id=model.model_id,
                                provider_id=model.provider_id,
                                provider_name=model.provider_name,
                                display_name=model.display_name,
                                is_current=True,
                                supports_tools=model.supports_tools,
                                supports_thinking=model.supports_thinking,
                                context_window=model.context_window,
                                metadata=model.metadata,
                            )
                return models
            except Exception:
                pass
        return list(self._models.values())

    def get_current_model(self) -> ModelView | None:
        """Get the current model.

        Returns:
            The current ModelView, or None if no model is selected
        """
        if not self._current_model_id:
            return None
        return self._models.get(self._current_model_id)

    def get_model(self, model_id: str, provider_id: str | None = None) -> ModelView | None:
        """Get a specific model by ID.

        Args:
            model_id: The model ID
            provider_id: Optional provider ID

        Returns:
            The ModelView, or None if not found
        """
        normalized_model_id = _safe_text(model_id)
        if provider_id:
            full_id = f"{_safe_text(provider_id)}.{normalized_model_id}"
            return self._models.get(full_id)
        return self._models.get(normalized_model_id)

    def switch_model(self, model_id: str, provider_id: str | None = None) -> ModelSwitchResult:
        """Switch to a different model.

        Args:
            model_id: The target model ID
            provider_id: Optional provider ID

        Returns:
            A ModelSwitchResult indicating the outcome
        """
        normalized_model_id = _safe_text(model_id)
        if not normalized_model_id:
            return ModelSwitchResult(
                result_kind=ModelSwitchResultKind.REJECTED,
                error_reason="Model ID is required",
            )

        if self._model_switcher:
            return self._model_switcher(normalized_model_id, provider_id)

        # Default implementation
        previous_model_id = self._current_model_id
        self._current_model_id = normalized_model_id
        if provider_id:
            self._current_provider_id = _safe_text(provider_id)
        return ModelSwitchResult(
            result_kind=ModelSwitchResultKind.SUCCESS,
            model_id=normalized_model_id,
            provider_id=self._current_provider_id,
            previous_model_id=previous_model_id,
        )

    def get_model_capabilities(self, model_id: str | None = None, provider_id: str | None = None) -> ModelCapabilityView | None:
        """Get the capabilities of a model.

        Args:
            model_id: The model ID, or None for current model
            provider_id: Optional provider ID

        Returns:
            A ModelCapabilityView, or None if not found
        """
        target_model_id = model_id or self._current_model_id
        if not target_model_id:
            return None

        if self._capability_getter:
            try:
                return self._capability_getter(target_model_id, provider_id)
            except Exception:
                pass

        # Fallback to model view
        model = self.get_model(target_model_id, provider_id)
        if model is None:
            return None
        return ModelCapabilityView(
            model_id=model.model_id,
            provider_id=model.provider_id,
            supports_tools=model.supports_tools,
            supports_thinking=model.supports_thinking,
            context_window=model.context_window,
            token_limit=int(model.context_window * 0.8) if model.context_window else None,
        )

    def register_model(self, view: ModelView) -> None:
        """Register a model view.

        Args:
            view: The ModelView to register
        """
        self._models[view.full_id] = view
        # Also register by model_id only for convenience
        self._models[view.model_id] = view

    def unregister_model(self, model_id: str, provider_id: str | None = None) -> ModelView | None:
        """Unregister a model view.

        Args:
            model_id: The model ID
            provider_id: Optional provider ID

        Returns:
            The removed ModelView, or None if not found
        """
        normalized_model_id = _safe_text(model_id)
        if provider_id:
            full_id = f"{_safe_text(provider_id)}.{normalized_model_id}"
            return self._models.pop(full_id, None)
        return self._models.pop(normalized_model_id, None)

    def set_current_model(self, model_id: str, provider_id: str | None = None) -> None:
        """Set the current model directly.

        Args:
            model_id: The model ID
            provider_id: Optional provider ID
        """
        self._current_model_id = _safe_text(model_id)
        self._current_provider_id = _safe_text(provider_id) if provider_id else None

    def set_model_switcher(self, switcher: Callable[[str, str | None], ModelSwitchResult]) -> None:
        """Set the model switch handler.

        Args:
            switcher: A function that handles model switching
        """
        self._model_switcher = switcher

    def set_model_lister(self, lister: Callable[[], list[ModelView]]) -> None:
        """Set the model list handler.

        Args:
            lister: A function that returns the list of models
        """
        self._model_lister = lister

    def set_capability_getter(self, getter: Callable[[str, str | None], ModelCapabilityView | None]) -> None:
        """Set the capability getter.

        Args:
            getter: A function that returns model capabilities
        """
        self._capability_getter = getter

    def clear(self) -> None:
        """Clear all registered models."""
        self._models.clear()
        self._current_model_id = None
        self._current_provider_id = None


__all__ = [
    "ModelCapabilityView",
    "ModelSwitchResult",
    "ModelSwitchResultKind",
    "ModelUserService",
    "ModelView",
]
