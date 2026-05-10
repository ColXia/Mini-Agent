"""Tests for v11.3 ModelUserService."""

from __future__ import annotations

import pytest

from mini_agent.user_services.model_user_service import (
    ModelCapabilityView,
    ModelSwitchResult,
    ModelSwitchResultKind,
    ModelUserService,
    ModelView,
)


class TestModelView:
    """Tests for ModelView."""

    def test_model_view_creation(self) -> None:
        view = ModelView(
            model_id="gpt-4",
            provider_id="openai",
            provider_name="OpenAI",
            display_name="GPT-4",
            is_current=True,
            supports_tools=True,
            supports_thinking=False,
            context_window=128000,
        )
        assert view.model_id == "gpt-4"
        assert view.provider_id == "openai"
        assert view.full_id == "openai.gpt-4"
        assert view.is_current is True

    def test_model_view_full_id(self) -> None:
        view = ModelView(
            model_id="claude-3",
            provider_id="anthropic",
            provider_name="Anthropic",
            display_name="Claude 3",
        )
        assert view.full_id == "anthropic.claude-3"


class TestModelCapabilityView:
    """Tests for ModelCapabilityView."""

    def test_capability_view_creation(self) -> None:
        view = ModelCapabilityView(
            model_id="gpt-4",
            provider_id="openai",
            supports_tools=True,
            supports_thinking=False,
            context_window=128000,
            token_limit=100000,
        )
        assert view.model_id == "gpt-4"
        assert view.is_tools_capable is True
        assert view.is_thinking_capable is False


class TestModelUserService:
    """Tests for ModelUserService."""

    def test_service_creation(self) -> None:
        service = ModelUserService()
        assert service._current_model_id is None
        assert len(service.list_available_models()) == 0

    def test_register_model(self) -> None:
        service = ModelUserService()
        view = ModelView(
            model_id="gpt-4",
            provider_id="openai",
            provider_name="OpenAI",
            display_name="GPT-4",
        )
        service.register_model(view)
        assert len(service.list_available_models()) >= 1
        assert service.get_model("gpt-4") is not None

    def test_unregister_model(self) -> None:
        service = ModelUserService()
        view = ModelView(
            model_id="gpt-4",
            provider_id="openai",
            provider_name="OpenAI",
            display_name="GPT-4",
        )
        service.register_model(view)
        removed = service.unregister_model("gpt-4")
        assert removed is not None
        assert removed.model_id == "gpt-4"

    def test_get_current_model_none(self) -> None:
        service = ModelUserService()
        current = service.get_current_model()
        assert current is None

    def test_get_current_model(self) -> None:
        service = ModelUserService()
        view = ModelView(
            model_id="gpt-4",
            provider_id="openai",
            provider_name="OpenAI",
            display_name="GPT-4",
        )
        service.register_model(view)
        service.set_current_model("gpt-4", "openai")
        current = service.get_current_model()
        assert current is not None
        assert current.model_id == "gpt-4"

    def test_switch_model_empty_id(self) -> None:
        service = ModelUserService()
        result = service.switch_model("")
        assert result.result_kind == ModelSwitchResultKind.REJECTED
        assert "required" in result.error_reason

    def test_switch_model_success(self) -> None:
        service = ModelUserService()
        view = ModelView(
            model_id="gpt-4",
            provider_id="openai",
            provider_name="OpenAI",
            display_name="GPT-4",
        )
        service.register_model(view)
        service.set_current_model("gpt-3.5", "openai")

        result = service.switch_model("gpt-4", "openai")
        assert result.result_kind == ModelSwitchResultKind.SUCCESS
        assert result.model_id == "gpt-4"

    def test_switch_model_with_handler(self) -> None:
        service = ModelUserService()

        def custom_switcher(model_id: str, provider_id: str | None) -> ModelSwitchResult:
            return ModelSwitchResult(
                result_kind=ModelSwitchResultKind.SUCCESS,
                model_id=model_id,
                provider_id=provider_id,
            )

        service.set_model_switcher(custom_switcher)
        result = service.switch_model("gpt-4", "openai")
        assert result.result_kind == ModelSwitchResultKind.SUCCESS

    def test_list_models_with_handler(self) -> None:
        service = ModelUserService()

        def custom_lister() -> list[ModelView]:
            return [
                ModelView(
                    model_id="gpt-4",
                    provider_id="openai",
                    provider_name="OpenAI",
                    display_name="GPT-4",
                ),
            ]

        service.set_model_lister(custom_lister)
        models = service.list_available_models()
        assert len(models) == 1

    def test_get_model_capabilities(self) -> None:
        service = ModelUserService()
        view = ModelView(
            model_id="gpt-4",
            provider_id="openai",
            provider_name="OpenAI",
            display_name="GPT-4",
            supports_tools=True,
            context_window=128000,
        )
        service.register_model(view)

        caps = service.get_model_capabilities("gpt-4")
        assert caps is not None
        assert caps.supports_tools is True
        assert caps.context_window == 128000

    def test_get_model_capabilities_with_handler(self) -> None:
        service = ModelUserService()

        def custom_getter(model_id: str, provider_id: str | None) -> ModelCapabilityView | None:
            return ModelCapabilityView(
                model_id=model_id,
                provider_id=provider_id or "unknown",
                supports_tools=True,
                supports_thinking=True,
                context_window=200000,
                token_limit=160000,
            )

        service.set_capability_getter(custom_getter)
        caps = service.get_model_capabilities("gpt-4")
        assert caps is not None
        assert caps.context_window == 200000

    def test_clear(self) -> None:
        service = ModelUserService()
        view = ModelView(
            model_id="gpt-4",
            provider_id="openai",
            provider_name="OpenAI",
            display_name="GPT-4",
        )
        service.register_model(view)
        service.set_current_model("gpt-4")
        service.clear()
        assert len(service.list_available_models()) == 0
        assert service.get_current_model() is None
