from __future__ import annotations

import json
from types import SimpleNamespace

from mini_agent.model_manager.capability_probe import (
    CapabilityEvidence,
    DiscoveryProbeResult,
    ModelCapabilityProbeService,
)


def test_capability_probe_persists_discovery_and_active_probe_facts(tmp_path, monkeypatch) -> None:
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v2",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest"],
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        ModelCapabilityProbeService,
        "_discover_model_capabilities",
        lambda self, **kwargs: DiscoveryProbeResult(
            context_window=256000,
            supports_tools=CapabilityEvidence(
                value=None,
                truth="unknown",
                confidence="low",
                source="no_capability_evidence",
            ),
            supports_thinking=CapabilityEvidence(
                value=None,
                truth="unknown",
                confidence="low",
                source="no_capability_evidence",
            ),
        ),
    )
    monkeypatch.setattr(
        ModelCapabilityProbeService,
        "_probe_tools_support",
        lambda self, **kwargs: (
            CapabilityEvidence(
                value=True,
                truth="supported",
                confidence="high",
                source="active_probe_tool_call",
            ),
            None,
        ),
    )
    monkeypatch.setattr(
        ModelCapabilityProbeService,
        "_probe_thinking_support",
        lambda self, **kwargs: (
            CapabilityEvidence(
                value=False,
                truth="unsupported",
                confidence="medium",
                source="active_probe_no_thinking",
            ),
            None,
        ),
    )

    service = ModelCapabilityProbeService(catalog_path=catalog_path)
    result = service.probe_model(
        source="custom",
        provider_id="maas",
        model_id="astron-code-latest",
    )

    assert result["updated_fields"] == [
        "context_window",
        "supports_tools",
        "supports_thinking",
    ]
    model = result["model"]
    assert model["context_window"] == 256000
    assert model["supports_tools"] is True
    assert model["supports_tools_truth"] == "supported"
    assert model["supports_thinking"] is False
    assert model["supports_thinking_truth"] == "unsupported"

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    model_metadata = payload["providers"][0]["model_metadata"]["astron-code-latest"]
    assert payload["providers"][0]["model_context_windows"]["astron-code-latest"] == 256000
    assert model_metadata["supports_tools_source"] == "active_probe_tool_call"
    assert model_metadata["supports_thinking_source"] == "active_probe_no_thinking"


def test_capability_probe_preserves_known_facts_without_reprobing(tmp_path, monkeypatch) -> None:
    catalog_path = tmp_path / "providers.json"
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "maas",
                        "name": "MaaS",
                        "api_type": "openai",
                        "api_base": "https://maas.example.com/v2",
                        "api_key": "sk-maas",
                        "models": ["astron-code-latest"],
                        "model_context_windows": {"astron-code-latest": 256000},
                        "model_metadata": {
                            "astron-code-latest": {
                                "supports_tools": True,
                                "supports_thinking": True,
                            }
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    def _unexpected(*args, **kwargs):
        raise AssertionError("probe helpers should not be called when facts are already known")

    monkeypatch.setattr(ModelCapabilityProbeService, "_discover_model_capabilities", _unexpected)
    monkeypatch.setattr(ModelCapabilityProbeService, "_probe_tools_support", _unexpected)
    monkeypatch.setattr(ModelCapabilityProbeService, "_probe_thinking_support", _unexpected)

    service = ModelCapabilityProbeService(catalog_path=catalog_path)
    result = service.probe_model(
        source="custom",
        provider_id="maas",
        model_id="astron-code-latest",
    )

    assert result["updated_fields"] == []
    assert result["discovery_attempted"] is False
    assert result["active_probe_attempted"] is False
    assert result["model"]["supports_tools"] is True
    assert result["model"]["supports_thinking"] is True


def test_probe_tools_support_falls_back_to_auto_mode_when_required_fails(tmp_path, monkeypatch) -> None:
    catalog_path = tmp_path / "providers.json"
    probe_calls: list[str] = []

    async def _fake_run_probe_completion(self, **kwargs):
        probe_calls.append(str(kwargs["request_policy"].tool_choice_policy))
        if kwargs["request_policy"].tool_choice_policy == "required":
            raise RuntimeError("Request timed out.")
        return SimpleNamespace(tool_calls=[SimpleNamespace(id="call_1")])

    monkeypatch.setattr(
        ModelCapabilityProbeService,
        "_run_probe_completion",
        _fake_run_probe_completion,
    )

    service = ModelCapabilityProbeService(catalog_path=catalog_path)
    evidence, note = service._probe_tools_support(
        source="custom",
        provider_id="maas",
        model_id="astron-code-latest",
    )

    assert probe_calls == ["required", "auto"]
    assert evidence is not None
    assert evidence.value is True
    assert evidence.truth == "supported"
    assert evidence.source == "active_probe_tool_call"
    assert note is not None
    assert "auto-mode succeeded" in note
    assert "required-mode failure" in note
