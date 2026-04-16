"""Tests for doctor diagnostics and startup self-check."""

import json
from pathlib import Path

from mini_agent.config import AgentConfig, Config, LLMConfig, SecurityConfig, ToolsConfig
from mini_agent.ops.doctor import format_doctor_report, run_doctor, run_startup_self_check


def _make_config(tmp_path: Path, *, enable_mcp: bool, mcp_path: Path | None = None) -> Config:
    tools = ToolsConfig(
        enable_mcp=enable_mcp,
        enable_skills=False,
        mcp_config_path=str(mcp_path) if mcp_path else "missing-mcp.json",
    )
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(workspace_dir=str(tmp_path / "workspace")),
        tools=tools,
        security=SecurityConfig(),
    )


def _isolate_model_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.chdir(tmp_path)
    for key in (
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
        "MINIMAX_API_KEY",
        "MINI_AGENT_OLLAMA_ENABLED",
        "MINI_AGENT_ENABLE_OLLAMA",
        "MINI_AGENT_OLLAMA_BASE_URL",
        "MINI_AGENT_OLLAMA_PROTOCOL",
        "OLLAMA_HOST",
        "MINI_AGENT_PROVIDER_CATALOG_PATH",
    ):
        monkeypatch.delenv(key, raising=False)


def test_doctor_reports_pass_without_mcp(tmp_path: Path):
    config = _make_config(tmp_path, enable_mcp=False)
    findings = run_doctor(config=config, workspace=tmp_path / "workspace")

    assert any(item.status == "pass" and item.title == "Python Version" for item in findings)
    assert any(item.status == "pass" and item.title == "Workspace Writable" for item in findings)
    assert any(item.title == "MCP Disabled" for item in findings)

    report = format_doctor_report(findings)
    assert "Doctor Report" in report
    assert "Summary:" in report


def test_startup_self_check_fails_on_missing_stdio_command(tmp_path: Path):
    mcp_path = tmp_path / "mcp.json"
    mcp_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "broken": {
                        "command": "command-that-definitely-does-not-exist-xyz",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    config = _make_config(tmp_path, enable_mcp=True, mcp_path=mcp_path)
    is_ready, findings = run_startup_self_check(config=config, workspace=tmp_path / "workspace")

    assert is_ready is False
    assert any(
        item.status == "fail" and item.title == "MCP STDIO broken"
        for item in findings
    )


def test_doctor_deep_probe_includes_handshake_and_hint(tmp_path: Path):
    mcp_path = tmp_path / "mcp.json"
    mcp_path.write_text(
        json.dumps(
            {
                "mcpServers": {
                    "broken": {
                        "command": "command-that-definitely-does-not-exist-xyz",
                    }
                }
            }
        ),
        encoding="utf-8",
    )

    config = _make_config(tmp_path, enable_mcp=True, mcp_path=mcp_path)
    findings = run_doctor(
        config=config,
        workspace=tmp_path / "workspace",
        deep_mcp_probe=True,
    )

    stdio_failure = next(
        (
            item
            for item in findings
            if item.title == "MCP STDIO broken" and item.status == "fail"
        ),
        None,
    )
    assert stdio_failure is not None
    assert stdio_failure.remediation is not None

    report = format_doctor_report(findings)
    assert "Hint:" in report


def test_doctor_warns_on_local_role_gaps_and_unbound_embedding(tmp_path: Path, monkeypatch) -> None:
    _isolate_model_env(monkeypatch, tmp_path)
    catalog_path = tmp_path / "providers.json"
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "ollama-local",
                        "name": "Ollama Local",
                        "api_type": "openai",
                        "api_base": "http://localhost:11434/v1",
                        "api_key": "ollama",
                        "models": ["qwen3.5:9b", "qwen3-embedding:0.6b", "glm-ocr:bf16"],
                        "model_context_windows": {"qwen3.5:9b": 131072},
                        "model_metadata": {
                            "qwen3.5:9b": {
                                "model_role": "chat",
                                "supports_tools": True,
                                "supports_thinking": True,
                            },
                            "qwen3-embedding:0.6b": {
                                "model_role": "embedding",
                            },
                        },
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    config = _make_config(tmp_path, enable_mcp=False)
    findings = run_doctor(config=config, workspace=tmp_path / "workspace")

    role_coverage = next(item for item in findings if item.title == "Model Role Coverage")
    assert role_coverage.status == "warn"
    assert "glm-ocr:bf16" in role_coverage.detail

    embedding_binding = next(item for item in findings if item.title == "Embedding Binding")
    assert embedding_binding.status == "warn"
    assert "qwen3-embedding:0.6b" in embedding_binding.detail

    selected_route = next(item for item in findings if item.title == "Selected Chat Capability Evidence")
    assert selected_route.status == "pass"


def test_doctor_warns_on_capability_gaps_for_selected_chat_route(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _isolate_model_env(monkeypatch, tmp_path)
    catalog_path = tmp_path / "providers.json"
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
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
                        "model_metadata": {
                            "astron-code-latest": {
                                "model_role": "chat",
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

    config = _make_config(tmp_path, enable_mcp=False)
    findings = run_doctor(config=config, workspace=tmp_path / "workspace")

    capability = next(item for item in findings if item.title == "Selected Chat Capability Evidence")
    assert capability.status == "warn"
    assert "supports_tools" in capability.detail
    assert "supports_thinking" in capability.detail
    assert "token_limit/context_window" in capability.detail


def test_doctor_warns_on_stale_and_unsupported_feature_bindings(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _isolate_model_env(monkeypatch, tmp_path)
    catalog_path = tmp_path / "providers.json"
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
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
                                "model_role": "chat",
                                "supports_tools": True,
                                "supports_thinking": True,
                            }
                        },
                    },
                    {
                        "id": "feature-lab",
                        "name": "Feature Lab",
                        "api_type": "openai",
                        "api_base": "https://feature.example.com/v1",
                        "api_key": "sk-feature",
                        "models": ["text-embedding-3-large", "ocr-ish-model"],
                        "model_metadata": {
                            "text-embedding-3-large": {
                                "model_role": "embedding",
                            },
                            "ocr-ish-model": {
                                "model_role": "ocr",
                            },
                        },
                    },
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (tmp_path / "feature_model_bindings.json").write_text(
        json.dumps(
            {
                "bindings": {
                    "embedding": {
                        "source": "custom",
                        "provider_id": "feature-lab",
                        "model_id": "missing-embedding-model",
                        "updated_at": "2026-04-16T00:00:00+00:00",
                    },
                    "ocr": {
                        "source": "custom",
                        "provider_id": "feature-lab",
                        "model_id": "ocr-ish-model",
                        "updated_at": "2026-04-16T00:00:00+00:00",
                    },
                }
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    config = _make_config(tmp_path, enable_mcp=False)
    findings = run_doctor(config=config, workspace=tmp_path / "workspace")

    embedding_binding = next(item for item in findings if item.title == "Embedding Binding")
    assert embedding_binding.status == "warn"
    assert "missing or stale target" in embedding_binding.detail

    ocr_binding = next(item for item in findings if item.title == "OCR Binding")
    assert ocr_binding.status == "warn"
    assert "cannot build a ocr helper" in ocr_binding.detail


def test_startup_self_check_fails_when_only_feature_models_are_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _isolate_model_env(monkeypatch, tmp_path)
    catalog_path = tmp_path / "providers.json"
    monkeypatch.setenv("MINI_AGENT_PROVIDER_CATALOG_PATH", str(catalog_path))
    catalog_path.write_text(
        json.dumps(
            {
                "providers": [
                    {
                        "id": "feature-only",
                        "name": "Feature Only",
                        "api_type": "openai",
                        "api_base": "http://localhost:11434/v1",
                        "api_key": "ollama",
                        "models": ["qwen3-embedding:0.6b"],
                        "model_metadata": {
                            "qwen3-embedding:0.6b": {
                                "model_role": "embedding",
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

    config = _make_config(tmp_path, enable_mcp=False)
    is_ready, findings = run_startup_self_check(config=config, workspace=tmp_path / "workspace")

    assert is_ready is False
    runtime = next(item for item in findings if item.title == "Chat Runtime Availability")
    assert runtime.status == "fail"
