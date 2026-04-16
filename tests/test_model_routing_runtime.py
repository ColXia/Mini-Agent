"""Tests for runtime routed LLM settings resolution."""

from __future__ import annotations

import json

import pytest

from mini_agent.config import (
    OFFICIAL_PRESET_ENV_KEYS,
    AgentConfig,
    Config,
    LLMConfig,
    SecurityConfig,
    ToolsConfig,
)
from mini_agent.model_manager import (
    RouteRequirementProfile,
    bootstrap_llm_settings_from_config,
)
from mini_agent.model_manager.preset_providers import PresetProvider, get_preset_provider_config
from mini_agent.model_manager.runtime import (
    get_circuit_breaker_registry,
    get_model_route_diagnostics_snapshot,
    get_model_route_diagnostics_state,
    reset_model_manager_runtime_state,
    resolve_pinned_llm_candidate,
    resolve_session_model_selection_identity,
    resolve_routed_llm_candidates,
    resolve_routed_llm_settings,
)


def _make_config(*, provider: str = "anthropic", model: str = "MiniMax-M2.5") -> Config:
    return Config(
        llm=LLMConfig(
            api_key="cfg-key",
            api_base="https://api.minimaxi.com",
            provider=provider,
            model=model,
        ),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_mcp=False, enable_skills=False),
        security=SecurityConfig(),
    )


@pytest.fixture(autouse=True)
def _reset_runtime_state():
    reset_model_manager_runtime_state()
    yield
    reset_model_manager_runtime_state()


@pytest.fixture(autouse=True)
def _clear_preset_provider_keys(monkeypatch):
    for env_key in OFFICIAL_PRESET_ENV_KEYS:
        # Keep keys present-but-empty so load_dotenv(override=False) cannot
        # repopulate real local keys from .env.local during this test module.
        monkeypatch.setenv(env_key, "")
    monkeypatch.setenv("MINI_AGENT_OLLAMA_ENABLED", "")
    monkeypatch.setenv("MINI_AGENT_ENABLE_OLLAMA", "")
    monkeypatch.setenv("OLLAMA_HOST", "")
    monkeypatch.setenv("MINI_AGENT_OLLAMA_BASE_URL", "")
    monkeypatch.setenv("MINI_AGENT_OLLAMA_PROTOCOL", "")


def test_resolve_routed_llm_settings_uses_bootstrap_registry_without_catalog(monkeypatch, tmp_path):
    # Isolate from machine-level ~/.mini-agent/providers.json.
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(tmp_path / "missing.json"))
    config = _make_config(provider="anthropic", model="MiniMax-M2.5")

    resolved = resolve_routed_llm_settings(
        bootstrap_llm=_bootstrap(config),
        requested_model="MiniMax-M2.5",
    )

    assert resolved.source == "bootstrap_provider_catalog"
    assert resolved.provider_id == "bootstrap-config"
    assert resolved.model == "MiniMax-M2.5"
    assert resolved.api_key == "cfg-key"
    assert resolved.api_base == "https://api.minimaxi.com"
    assert resolved.provider.value == "anthropic"


def _bootstrap(config: Config):
    return bootstrap_llm_settings_from_config(config)


def test_bootstrap_llm_settings_from_config_extracts_minimal_route_input() -> None:
    config = _make_config(provider="openai", model="gpt-5.4")
    bootstrap = _bootstrap(config)

    assert bootstrap is not None
    assert bootstrap.provider == "openai"
    assert bootstrap.api_base == "https://api.minimaxi.com"
    assert bootstrap.api_key == "cfg-key"
    assert bootstrap.model == "gpt-5.4"


def test_resolve_routed_llm_settings_uses_provider_catalog(monkeypatch, tmp_path):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "openai-secondary",
                        "name": "OpenAI Secondary",
                        "api_type": "openai",
                        "api_base": "https://openai.secondary.example.com/v1",
                        "api_key": "sk-openai-secondary",
                        "models": ["gpt-4o-mini"],
                        "enabled": True,
                        "priority": 4,
                    },
                    {
                        "id": "anth-primary",
                        "name": "Anthropic Primary",
                        "api_type": "anthropic",
                        "api_base": "https://anth.primary.example.com",
                        "api_key": "sk-anth-primary",
                        "models": ["claude-3-5-sonnet", "claude-3-7-sonnet"],
                        "enabled": True,
                        "priority": 7,
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="anthropic", model="claude")

    resolved = resolve_routed_llm_settings(
        bootstrap_llm=_bootstrap(config),
        requested_model="claude",
    )
    assert resolved.source == "provider_catalog"
    assert resolved.provider_id == "anth-primary"
    assert resolved.provider.value == "anthropic"
    assert resolved.api_base == "https://anth.primary.example.com"
    assert resolved.api_key == "sk-anth-primary"
    assert resolved.model in {"claude-3-5-sonnet", "claude-3-7-sonnet"}
    assert resolved.mapping_mode in {"exact", "partial", "fallback_default"}


def test_resolve_routed_llm_settings_accepts_legacy_custom_api_type_as_openai_compatible(
    monkeypatch,
    tmp_path,
):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "legacy-custom",
                        "name": "Legacy Custom",
                        "api_type": "custom",
                        "api_base": "https://legacy.example.com/v1",
                        "api_key": "sk-legacy-custom",
                        "models": ["legacy-model"],
                        "enabled": True,
                        "priority": 7,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="openai", model="legacy-model")

    resolved = resolve_routed_llm_settings(
        bootstrap_llm=_bootstrap(config),
        requested_model="legacy-model",
    )

    assert resolved.provider_id == "legacy-custom"
    assert resolved.provider.value == "openai"
    assert resolved.model == "legacy-model"


def test_resolve_pinned_llm_candidate_preserves_custom_headers_and_timeout(monkeypatch, tmp_path):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v1",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest"],
                        "headers": {
                            "X-Tenant": "tenant-a",
                            "X-Workspace": "workspace-a",
                        },
                        "timeout": 45,
                        "enabled": True,
                        "priority": 8,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))

    candidate = resolve_pinned_llm_candidate(
        provider_source="custom",
        provider_id="maas",
        model_id="astron-code-latest",
    )

    assert candidate.provider_id == "maas"
    assert candidate.timeout == 45
    assert candidate.headers == {
        "X-Tenant": "tenant-a",
        "X-Workspace": "workspace-a",
    }


def test_resolve_routed_llm_candidates_skip_open_breaker_provider(monkeypatch, tmp_path):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "anth-primary",
                        "name": "Anthropic Primary",
                        "api_type": "anthropic",
                        "api_base": "https://anth.primary.example.com",
                        "api_key": "sk-anth-primary",
                        "models": ["claude-3-7-sonnet"],
                        "enabled": True,
                        "priority": 9,
                    },
                    {
                        "id": "openai-secondary",
                        "name": "OpenAI Secondary",
                        "api_type": "openai",
                        "api_base": "https://openai.secondary.example.com/v1",
                        "api_key": "sk-openai-secondary",
                        "models": ["gpt-4o-mini"],
                        "enabled": True,
                        "priority": 6,
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="anthropic", model="claude")

    breakers = get_circuit_breaker_registry()
    for _ in range(4):
        breakers.record_failure("anth-primary", reason="open-threshold")

    candidates = resolve_routed_llm_candidates(
        bootstrap_llm=_bootstrap(config),
        requested_model="claude",
    )
    assert candidates[0].provider_id == "openai-secondary"
    assert candidates[0].breaker_allowed is True
    assert all(item.provider_id != "anth-primary" for item in candidates)

    selected = resolve_routed_llm_settings(
        bootstrap_llm=_bootstrap(config),
        requested_model="claude",
    )
    assert selected.provider_id == "openai-secondary"


def test_resolve_routed_llm_settings_records_model_route_snapshot_with_breaker_failover(
    monkeypatch,
    tmp_path,
):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "anth-primary",
                        "name": "Anthropic Primary",
                        "api_type": "anthropic",
                        "api_base": "https://anth.primary.example.com",
                        "api_key": "sk-anth-primary",
                        "models": ["claude-3-7-sonnet"],
                        "model_metadata": {
                            "claude-3-7-sonnet": {
                                "supports_tools": True,
                                "supports_thinking": True,
                            }
                        },
                        "enabled": True,
                        "priority": 9,
                    },
                    {
                        "id": "openai-secondary",
                        "name": "OpenAI Secondary",
                        "api_type": "openai",
                        "api_base": "https://openai.secondary.example.com/v1",
                        "api_key": "sk-openai-secondary",
                        "models": ["gpt-5.4"],
                        "model_metadata": {
                            "gpt-5.4": {
                                "supports_tools": True,
                                "supports_thinking": True,
                            }
                        },
                        "enabled": True,
                        "priority": 6,
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="openai", model="gpt-5.4")

    breakers = get_circuit_breaker_registry()
    for _ in range(4):
        breakers.record_failure("anth-primary", reason="open-threshold")

    selected = resolve_routed_llm_settings(
        bootstrap_llm=_bootstrap(config),
        requested_model=None,
        route_requirements=RouteRequirementProfile(require_tools=True),
    )

    snapshot = get_model_route_diagnostics_snapshot()
    state = get_model_route_diagnostics_state()

    assert selected.provider_id == "openai-secondary"
    assert state["resolution_count"] == 1
    assert snapshot is not None
    assert snapshot["resolution_kind"] == "routed"
    assert snapshot["catalog_source"] == "provider_catalog"
    assert snapshot["route_intent"] == "automatic"
    assert snapshot["selected_provider_id"] == "openai-secondary"
    assert snapshot["selected_reason"] == "automatic_provider_default"
    assert snapshot["fallback_reason"] == "higher_ranked_candidates_blocked_by_circuit_breaker"
    assert snapshot["require_tools"] is True
    assert snapshot["candidate_count"] == 2
    assert snapshot["allowed_candidate_count"] == 1
    assert snapshot["blocked_candidate_count"] == 1
    assert snapshot["candidates"][0]["provider_id"] == "anth-primary"
    assert snapshot["candidates"][0]["breaker_allowed"] is False
    assert snapshot["candidates"][1]["provider_id"] == "openai-secondary"
    assert snapshot["candidates"][1]["selected"] is True
    assert snapshot["candidates"][1]["supports_tools_truth"] == "supported"


def test_resolve_routed_llm_settings_explicit_requested_model_rejects_unmatched_fallback(
    monkeypatch,
    tmp_path,
):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "openai-primary",
                        "name": "OpenAI Primary",
                        "api_type": "openai",
                        "api_base": "https://openai.example.com/v1",
                        "api_key": "sk-openai",
                        "models": ["gpt-4o-mini"],
                        "enabled": True,
                        "priority": 9,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="openai", model="gpt-4o-mini")

    with pytest.raises(
        ValueError,
        match="explicit requested model 'missing-model' did not match any enabled provider route",
    ):
        resolve_routed_llm_settings(
            bootstrap_llm=_bootstrap(config),
            requested_model="missing-model",
            route_intent="explicit",
        )


def test_resolve_routed_llm_settings_records_error_snapshot_for_explicit_route_failure(
    monkeypatch,
    tmp_path,
):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "openai-primary",
                        "name": "OpenAI Primary",
                        "api_type": "openai",
                        "api_base": "https://openai.example.com/v1",
                        "api_key": "sk-openai",
                        "models": ["gpt-4o-mini"],
                        "enabled": True,
                        "priority": 9,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="openai", model="gpt-4o-mini")

    with pytest.raises(
        ValueError,
        match="explicit requested model 'missing-model' did not match any enabled provider route",
    ):
        resolve_routed_llm_settings(
            bootstrap_llm=_bootstrap(config),
            requested_model="missing-model",
            route_intent="explicit",
        )

    snapshot = get_model_route_diagnostics_snapshot()
    state = get_model_route_diagnostics_state()

    assert state["resolution_count"] == 1
    assert snapshot is not None
    assert snapshot["resolution_kind"] == "routed"
    assert snapshot["route_intent"] == "explicit"
    assert snapshot["requested_model"] == "missing-model"
    assert snapshot["selected_provider_id"] is None
    assert snapshot["candidate_count"] == 0
    assert "explicit requested model 'missing-model'" in snapshot["error"]


def test_resolve_routed_llm_settings_automatic_route_can_fall_back_to_provider_default(
    monkeypatch,
    tmp_path,
):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "openai-primary",
                        "name": "OpenAI Primary",
                        "api_type": "openai",
                        "api_base": "https://openai.example.com/v1",
                        "api_key": "sk-openai",
                        "models": ["gpt-4o-mini"],
                        "enabled": True,
                        "priority": 9,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="openai", model="gpt-4o-mini")

    resolved = resolve_routed_llm_settings(
        bootstrap_llm=_bootstrap(config),
        requested_model="missing-model",
        route_intent="automatic",
    )

    assert resolved.provider_id == "openai-primary"
    assert resolved.model == "gpt-4o-mini"
    assert resolved.mapping_mode == "fallback_default"


def test_resolve_pinned_llm_candidate_rejects_wrong_provider_model_pair(monkeypatch, tmp_path):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v1",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest"],
                        "enabled": True,
                        "priority": 9,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))

    with pytest.raises(
        ValueError,
        match="model 'gpt-5.4' is not available in provider 'maas'",
    ):
        resolve_pinned_llm_candidate(
            provider_source="custom",
            provider_id="maas",
            model_id="gpt-5.4",
        )


def test_resolve_routed_llm_candidates_filters_known_non_tool_models(monkeypatch, tmp_path):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "no-tools",
                        "name": "No Tools",
                        "api_type": "openai",
                        "api_base": "https://no-tools.example.com/v1",
                        "api_key": "sk-no-tools",
                        "models": ["gpt-4o-mini"],
                        "model_metadata": {
                            "gpt-4o-mini": {
                                "supports_tools": False,
                                "supports_thinking": False,
                            }
                        },
                        "enabled": True,
                        "priority": 10,
                    },
                    {
                        "id": "tools-ok",
                        "name": "Tools OK",
                        "api_type": "openai",
                        "api_base": "https://tools-ok.example.com/v1",
                        "api_key": "sk-tools-ok",
                        "models": ["gpt-4.1"],
                        "model_metadata": {
                            "gpt-4.1": {
                                "supports_tools": True,
                                "supports_thinking": False,
                            }
                        },
                        "enabled": True,
                        "priority": 1,
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="openai", model="gpt-4o-mini")

    candidates = resolve_routed_llm_candidates(
        bootstrap_llm=_bootstrap(config),
        requested_model=None,
        route_requirements=RouteRequirementProfile(require_tools=True),
    )

    assert [item.provider_id for item in candidates] == ["tools-ok"]
    assert candidates[0].supports_tools is True
    assert candidates[0].supports_tools_truth == "supported"


def test_resolve_routed_llm_candidates_prefers_thinking_when_mapping_quality_ties(monkeypatch, tmp_path):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "thinking-low-priority",
                        "name": "Thinking Low",
                        "api_type": "openai",
                        "api_base": "https://thinking.example.com/v1",
                        "api_key": "sk-thinking",
                        "models": ["gpt-5.4"],
                        "model_metadata": {
                            "gpt-5.4": {
                                "supports_tools": True,
                                "supports_thinking": True,
                            }
                        },
                        "enabled": True,
                        "priority": 1,
                    },
                    {
                        "id": "non-thinking-high-priority",
                        "name": "Non Thinking High",
                        "api_type": "openai",
                        "api_base": "https://non-thinking.example.com/v1",
                        "api_key": "sk-non-thinking",
                        "models": ["gpt-4.1"],
                        "model_metadata": {
                            "gpt-4.1": {
                                "supports_tools": True,
                                "supports_thinking": False,
                            }
                        },
                        "enabled": True,
                        "priority": 9,
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="openai", model="gpt-4.1")

    selected = resolve_routed_llm_settings(
        bootstrap_llm=_bootstrap(config),
        requested_model=None,
        route_requirements=RouteRequirementProfile(
            require_tools=True,
            prefer_thinking=True,
        ),
    )

    assert selected.provider_id == "thinking-low-priority"
    assert selected.supports_thinking is True
    assert selected.supports_thinking_truth == "supported"


def test_resolve_routed_llm_candidates_marks_unknown_capability_truth_without_evidence(
    monkeypatch,
    tmp_path,
):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "unknown-tools",
                        "name": "Unknown Tools",
                        "api_type": "openai",
                        "api_base": "https://unknown-tools.example.com/v1",
                        "api_key": "sk-unknown-tools",
                        "models": ["gpt-4.1"],
                        "enabled": True,
                        "priority": 9,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="openai", model="gpt-4.1")

    resolved = resolve_routed_llm_settings(
        bootstrap_llm=_bootstrap(config),
        requested_model=None,
        route_requirements=RouteRequirementProfile(require_tools=True),
    )

    assert resolved.provider_id == "unknown-tools"
    assert resolved.supports_tools is None
    assert resolved.supports_tools_truth == "unknown"


def test_resolve_routed_llm_settings_ignores_config_provider_bias_when_registry_exists(
    monkeypatch,
    tmp_path,
):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "anth-low",
                        "name": "Anthropic Low",
                        "api_type": "anthropic",
                        "api_base": "https://anth.example.com",
                        "api_key": "sk-anth",
                        "models": ["claude-3-7-sonnet"],
                        "enabled": True,
                        "priority": 1,
                    },
                    {
                        "id": "openai-high",
                        "name": "OpenAI High",
                        "api_type": "openai",
                        "api_base": "https://openai.example.com/v1",
                        "api_key": "sk-openai",
                        "models": ["gpt-5.4"],
                        "enabled": True,
                        "priority": 9,
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    config = _make_config(provider="anthropic", model="claude-3-7-sonnet")

    resolved = resolve_routed_llm_settings(
        bootstrap_llm=_bootstrap(config),
        requested_model=None,
    )

    assert resolved.source == "provider_catalog"
    assert resolved.provider_id == "openai-high"
    assert resolved.model == "gpt-5.4"


def test_resolve_session_model_selection_identity_infers_unique_custom_source(monkeypatch, tmp_path):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v1",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest"],
                        "enabled": True,
                        "priority": 10,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))

    identity = resolve_session_model_selection_identity(
        provider_id="maas",
        model_id="astron-code-latest",
    )

    assert identity == ("custom", "maas", "astron-code-latest")


def test_resolve_session_model_selection_identity_uses_provider_default_model_when_omitted(
    monkeypatch,
    tmp_path,
):
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v1",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest", "astron-code-stable"],
                        "enabled": True,
                        "priority": 10,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))

    identity = resolve_session_model_selection_identity(
        provider_source="custom",
        provider_id="maas",
        model_id=None,
    )

    assert identity == ("custom", "maas", "astron-code-latest")


def test_resolve_session_model_selection_identity_rejects_ambiguous_source(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-openai-preset")
    preset = get_preset_provider_config(PresetProvider.OPENAI, use_latest_model=False)
    assert preset is not None
    shared_model = str(preset["model"])

    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "openai",
                        "name": "OpenAI Mirror",
                        "api_type": "openai",
                        "api_base": "https://openai-mirror.example.com/v1",
                        "api_key": "sk-openai-mirror",
                        "models": [shared_model],
                        "enabled": True,
                        "priority": 10,
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))

    with pytest.raises(ValueError, match="ambiguous across sources"):
        resolve_session_model_selection_identity(
            provider_id="openai",
            model_id=shared_model,
        )


def test_resolve_routed_llm_settings_can_route_to_enabled_ollama_preset(monkeypatch, tmp_path):
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(tmp_path / "providers.json"))
    monkeypatch.setenv("MINI_AGENT_OLLAMA_ENABLED", "1")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(preset_providers, "_is_ollama_reachable", lambda host: True)
    monkeypatch.setattr(
        preset_providers,
        "_discover_preset_inventory",
        lambda provider, api_key, api_base=None: {
            "selected_model": "qwen3-coder",
            "selection_strategy": "curated_latest",
            "selection_confidence": "high",
            "discovery_source": "api_discovery",
            "discovered_models": ["qwen3-coder", "gpt-oss:20b"],
        },
    )
    config = _make_config(provider="anthropic", model="qwen3-coder")

    resolved = resolve_routed_llm_settings(
        bootstrap_llm=_bootstrap(config),
        requested_model="qwen3-coder",
    )

    assert resolved.source == "provider_catalog"
    assert resolved.provider_id == "preset-ollama"
    assert resolved.provider.value == "anthropic"
    assert resolved.api_key == "ollama"
    assert resolved.api_base == "http://localhost:11434"
    assert resolved.model == "qwen3-coder"


def test_resolve_session_model_selection_identity_infers_enabled_ollama_preset_source(
    monkeypatch,
    tmp_path,
):
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(tmp_path / "providers.json"))
    monkeypatch.setenv("MINI_AGENT_OLLAMA_ENABLED", "1")

    import mini_agent.model_manager.preset_providers as preset_providers

    monkeypatch.setattr(preset_providers, "_is_ollama_reachable", lambda host: True)
    monkeypatch.setattr(
        preset_providers,
        "_discover_preset_inventory",
        lambda provider, api_key, api_base=None: {
            "selected_model": "qwen3-coder",
            "selection_strategy": "curated_latest",
            "selection_confidence": "high",
            "discovery_source": "api_discovery",
            "discovered_models": ["qwen3-coder", "gpt-oss:20b"],
        },
    )

    identity = resolve_session_model_selection_identity(
        provider_id="ollama",
        model_id=None,
    )

    assert identity == ("preset", "ollama", "qwen3-coder")
