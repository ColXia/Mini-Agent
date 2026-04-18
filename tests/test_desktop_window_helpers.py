"""Tests for DesktopUI formatting helpers."""

from __future__ import annotations

from mini_agent.desktop.window import (
    _truncate_text,
    append_desktop_activity_entry,
    collect_memory_file_entries,
    collect_model_options,
    collect_provider_draft_model_entries,
    collect_provider_entries,
    collect_registry_model_entries,
    desktop_error_detail,
    desktop_page_specs,
    desktop_provider_preset_specs,
    desktop_stream_activity_payload,
    first_pending_approval,
    format_desktop_approval_failure,
    format_feature_bindings_text,
    format_memory_summary_text,
    format_model_catalog_text,
    format_provider_detail_text,
    format_provider_validation_text,
    format_registry_model_detail_text,
    format_session_context_text,
    format_session_row,
    format_settings_summary_text,
    render_activity_html,
    render_conversation_html,
    resolve_desktop_context_usage_stats,
)
from mini_agent.transport import GatewayTransportError


def test_truncate_text_appends_ellipsis_when_limit_is_exceeded() -> None:
    assert _truncate_text("abcdefghijklmnopqrstuvwxyz", limit=10) == "abcdefghi…"


def test_desktop_page_specs_exposes_first_wave_product_shell_order() -> None:
    specs = desktop_page_specs()

    assert [item["id"] for item in specs[:4]] == ["chat", "models", "providers", "settings"]
    assert specs[-2]["id"] == "sessions"
    assert specs[-1]["id"] == "memory"


def test_desktop_provider_preset_specs_exposes_expected_quick_fill_presets() -> None:
    presets = desktop_provider_preset_specs()

    assert [item["label"] for item in presets] == ["OpenAI", "Anthropic", "MiniMax", "Ollama"]
    assert presets[2]["api_type"] == "anthropic"
    assert presets[3]["api_base"] == "http://127.0.0.1:11434/v1"


def test_format_session_row_shapes_compact_left_rail_text() -> None:
    text = format_session_row(
        {
            "title": "  Session A  ",
            "busy": True,
            "active_surface": "desktop",
            "shared": False,
            "selected_model_id": "astron-code-latest",
        }
    )

    assert text == "Session A | Busy"


def test_format_session_context_text_includes_key_runtime_fields() -> None:
    text = format_session_context_text(
        {
            "title": "Desk Session",
            "session_id": "sess-1",
            "workspace_dir": "D:/file/Mini-Agent",
            "active_surface": "desktop",
            "shared": False,
            "busy": True,
            "running_state": "tool running",
            "selected_provider_id": "maas",
            "selected_model_id": "astron-code-latest",
            "updated_at": "2026-04-13T10:00:00Z",
            "pending_approvals": [],
            "memory_diagnostics": {"global": 1},
            "sandbox_diagnostics": {"mode": "default"},
        }
    )

    assert "Title: Desk Session" in text
    assert "Running: tool running" in text
    assert "\"global\": 1" in text
    assert "\"mode\": \"default\"" in text


def test_format_model_catalog_text_marks_current_session_model() -> None:
    text = format_model_catalog_text(
        {
            "items": [
                {
                    "source": "custom",
                    "provider_id": "maas",
                    "provider_name": "MaaS",
                    "default_model_id": "astron-code-latest",
                    "models": [
                        {
                            "model_id": "astron-code-latest",
                            "display_name": "GLM-5/K2.5",
                            "is_default": True,
                        }
                    ],
                }
            ]
        },
        {
            "selected_provider_id": "maas",
            "selected_model_id": "astron-code-latest",
        },
    )

    assert "MaaS [C] | default astron-code-latest" in text
    assert "astron-code-latest (GLM-5/K2.5) [session]" in text


def test_collect_model_options_flattens_provider_models_for_comboboxes() -> None:
    items = collect_model_options(
        {
            "items": [
                {
                    "source": "preset",
                    "provider_id": "openai",
                    "provider_name": "OpenAI",
                    "models": [
                        {
                            "model_id": "gpt-5.4",
                            "display_name": "GPT-5.4",
                        }
                    ],
                }
            ]
        }
    )

    assert items == [
        {
            "label": "OpenAI [P] | gpt-5.4 (GPT-5.4)",
            "combo_label": "GPT-5.4",
            "display_name": "GPT-5.4",
            "provider_name": "OpenAI",
            "provider_source": "preset",
            "provider_id": "openai",
            "model_id": "gpt-5.4",
            "context_window": "",
            "learned_token_limit": "",
            "token_limit": "",
        }
    ]


def test_resolve_desktop_context_usage_stats_uses_reported_runtime_budget_first() -> None:
    stats = resolve_desktop_context_usage_stats(
        {
            "token_usage": 4096,
            "token_limit": 16384,
        }
    )

    assert stats["usage"] == 4096
    assert stats["limit"] == 16384
    assert stats["percent"] == 25
    assert stats["tone"] == "low"
    assert stats["usage_source"] == "reported"
    assert stats["limit_source"] == "token_limit"
    assert stats["ring_text"] == "25"


def test_resolve_desktop_context_usage_stats_falls_back_to_catalog_limit_and_estimate() -> None:
    stats = resolve_desktop_context_usage_stats(
        {
            "recent_messages": [
                {
                    "role": "user",
                    "content": "hello world " * 40,
                }
            ]
        },
        {
            "learned_token_limit": "8192",
        },
    )

    assert stats["usage"] > 0
    assert stats["limit"] == 8192
    assert stats["usage_source"] == "estimated"
    assert stats["limit_source"] == "model_learned_token_limit"

def test_collect_provider_entries_flattens_provider_payload_for_list_views() -> None:
    entries = collect_provider_entries(
        {
            "items": [
                {
                    "id": "ollama-local",
                    "name": "Ollama Local",
                    "api_type": "openai",
                    "api_base": "http://127.0.0.1:11434/v1",
                    "health_status": "healthy",
                    "models": ["qwen3.5:9b", "gemma4:e4b"],
                }
            ]
        }
    )

    assert len(entries) == 1
    assert entries[0]["label"] == "Ollama Local"
    assert entries[0]["provider_id"] == "ollama-local"
    assert entries[0]["provider_name"] == "Ollama Local"
    assert entries[0]["api_type"] == "ollama"
    assert entries[0]["api_base"] == "http://127.0.0.1:11434/v1"
    assert entries[0]["health_status"] == "healthy"
    assert "Models: 2" in entries[0]["detail"]


def test_collect_provider_draft_model_entries_projects_registry_and_feature_binding_state() -> None:
    entries = collect_provider_draft_model_entries(
        provider_id="ollama-local",
        model_ids=["qwen3.5:9b", "qwen3-embedding:0.6b"],
        default_model_id="qwen3.5:9b",
        registry_payload={
            "items": [
                {
                    "source": "custom",
                    "provider_id": "ollama-local",
                    "models": [
                        {
                            "model_id": "qwen3.5:9b",
                            "model_role": "chat",
                            "supports_tools_truth": "supported",
                            "supports_thinking_truth": "unsupported",
                        },
                        {
                            "model_id": "qwen3-embedding:0.6b",
                            "model_role": "embedding",
                            "supports_tools_truth": "unsupported",
                            "supports_thinking_truth": "unknown",
                        },
                    ],
                }
            ]
        },
        feature_bindings={
            "items": [
                {
                    "provider_id": "ollama-local",
                    "model_id": "qwen3-embedding:0.6b",
                    "feature_role": "embedding",
                }
            ]
        },
    )

    assert entries[0]["model_id"] == "qwen3.5:9b"
    assert entries[0]["status"] == "saved"
    assert entries[0]["is_default"] == "true"
    assert "default" in entries[0]["label"]
    assert entries[1]["model_role"] == "embedding"
    assert entries[1]["feature_roles"] == "embedding"
    assert "feature=embedding" in entries[1]["label"]


def test_collect_registry_model_entries_supports_filtering_and_capability_projection() -> None:
    entries = collect_registry_model_entries(
        {
            "items": [
                {
                    "source": "custom",
                    "provider_id": "ollama",
                    "provider_name": "Ollama",
                    "provider_family": "ollama",
                    "provider_variant": "local",
                    "api_type": "ollama",
                    "api_base": "http://127.0.0.1:11434",
                    "models": [
                        {
                            "model_id": "qwen3-embedding:0.6b",
                            "display_name": "Qwen Embedding",
                            "model_role": "embedding",
                            "supports_tools_truth": "no",
                            "supports_thinking_truth": "unknown",
                            "context_window": 8192,
                            "learned_token_limit": 4096,
                        }
                    ],
                }
            ]
        },
        filter_text="embedding",
    )

    assert len(entries) == 1
    assert entries[0]["provider_family"] == "ollama"
    assert entries[0]["model_role"] == "embedding"
    assert entries[0]["supports_tools_truth"] == "no"
    assert entries[0]["learned_token_limit"] == "4096"


def test_collect_memory_file_entries_shapes_long_term_and_daily_files() -> None:
    entries = collect_memory_file_entries(
        {
            "long_term_file": "D:/file/Mini-Agent/MEMORY.md",
            "daily_dir": "D:/file/Mini-Agent/memory",
            "daily_files": ["2026-04-17.md", "2026-04-16.md"],
        },
        workspace_dir="D:/file/Mini-Agent",
    )

    assert entries[0] == {
        "label": "Long-Term | MEMORY.md",
        "path": "D:/file/Mini-Agent/MEMORY.md",
        "kind": "long_term",
    }
    assert entries[1]["label"] == "Daily | 2026-04-17.md"
    assert entries[1]["kind"] == "daily"
    assert entries[1]["path"].endswith("memory\\2026-04-17.md")


def test_first_pending_approval_returns_first_item() -> None:
    approval = first_pending_approval(
        {
            "pending_approvals": [
                {"token": "tok-1", "tool_name": "shell"},
                {"token": "tok-2", "tool_name": "fetch"},
            ]
        }
    )

    assert approval == {"token": "tok-1", "tool_name": "shell"}


def test_first_pending_approval_prefers_run_approval_wait() -> None:
    approval = first_pending_approval(
        {
            "pending_approvals": [
                {"token": "tok-session", "tool_name": "shell"},
            ]
        },
        {
            "approval_wait": {
                "wait_id": "wait-1",
                "approval_token": "tok-run",
                "tool_name": "python",
                "tool_arguments_summary": {"path": "script.py"},
                "approval_kind": "tool",
                "policy_reason": "outside workspace",
                "cache_key": "python:script.py",
                "can_escalate": True,
            }
        },
    )

    assert approval == {
        "token": "tok-run",
        "tool_name": "python",
        "arguments": {"path": "script.py"},
        "kind": "tool",
        "reason": "outside workspace",
        "cache_key": "python:script.py",
        "can_escalate": True,
        "wait_id": "wait-1",
    }


def test_render_conversation_html_separates_roles_and_escapes_content() -> None:
    html_text = render_conversation_html(
        [
            {"role": "user", "content": "hello <world>", "surface": "desktop"},
            {"role": "assistant", "content": "line 1\nline 2", "surface": "desktop"},
        ]
    )

    assert "user | desktop" in html_text
    assert "assistant | desktop" in html_text
    assert "hello &lt;world&gt;" in html_text
    assert "line 1<br>line 2" in html_text


def test_render_activity_html_renders_cards_with_detail_and_preview() -> None:
    html_text = render_activity_html(
        [
            {
                "timestamp": "12:34:56",
                "kind": "approval",
                "title": "shell needs approval",
                "preview": "cmd /c dir",
                "detail": "reason: elevated shell",
            }
        ]
    )

    assert "12:34:56 | approval" in html_text
    assert "shell needs approval" in html_text
    assert "cmd /c dir" in html_text
    assert "reason: elevated shell" in html_text


def test_append_desktop_activity_entry_updates_existing_entry_by_activity_id() -> None:
    entries: list[dict[str, object]] = []

    append_desktop_activity_entry(
        entries,
        "Thinking",
        kind="thinking",
        detail="plan step 1",
        activity_id="remote-thinking",
        timestamp="10:00:00",
    )
    append_desktop_activity_entry(
        entries,
        "Thinking",
        kind="thinking",
        detail="plan step 1\nplan step 2",
        activity_id="remote-thinking",
        timestamp="10:00:01",
    )

    assert entries == [
        {
            "timestamp": "10:00:01",
            "kind": "thinking",
            "title": "Thinking",
            "detail": "plan step 1\nplan step 2",
            "preview": "",
            "activity_id": "remote-thinking",
        }
    ]


def test_desktop_stream_activity_payload_maps_remote_thinking_delta_to_update_card() -> None:
    payload = desktop_stream_activity_payload(
        "thinking_delta",
        {"chunk": "ignored"},
        thinking_text="plan next step",
    )

    assert payload == {
        "kind": "thinking",
        "title": "Thinking",
        "detail": "plan next step",
        "activity_id": "remote-thinking",
    }


def test_render_activity_html_supports_thinking_cards() -> None:
    html_text = render_activity_html(
        [
            {
                "timestamp": "12:34:56",
                "kind": "thinking",
                "title": "Thinking",
                "detail": "plan next step",
            }
        ]
    )

    assert "12:34:56 | thinking" in html_text
    assert "Thinking" in html_text
    assert "plan next step" in html_text


def test_format_feature_bindings_text_renders_binding_lines() -> None:
    text = format_feature_bindings_text(
        {
            "items": [
                {
                    "feature_role": "embedding",
                    "provider_name": "Ollama",
                    "model_id": "qwen3-embedding:0.6b",
                    "resolved": True,
                }
            ]
        }
    )

    assert "Feature Bindings:" in text
    assert "- embedding: Ollama / qwen3-embedding:0.6b (resolved)" in text


def test_format_provider_detail_text_includes_health_snapshot() -> None:
    text = format_provider_detail_text(
        {
            "id": "maas",
            "name": "MaaS",
            "api_type": "openai",
            "api_base": "https://example.com/v2",
            "enabled": True,
            "priority": 10,
            "timeout": 45,
            "health_status": "degraded",
            "breaker_state": "half-open",
            "models": ["astron-code-latest"],
            "headers": {"x-tenant": "demo"},
        },
        health={
            "status": "degraded",
            "breaker_state": "half-open",
            "selected_count": 7,
            "consecutive_failures": 2,
            "error_rate": 0.25,
            "last_failure_reason": "timeout",
        },
    )

    assert "Provider ID: maas" in text
    assert "Health Snapshot:" in text
    assert "- error_rate: 0.25" in text
    assert "\"x-tenant\": \"demo\"" in text


def test_format_provider_detail_text_surfaces_local_ollama_alias() -> None:
    text = format_provider_detail_text(
        {
            "id": "ollama-local",
            "name": "Ollama Local",
            "api_type": "openai",
            "api_base": "http://127.0.0.1:11434/v1",
            "enabled": True,
            "priority": 5,
            "timeout": 45,
            "health_status": "healthy",
            "breaker_state": "closed",
            "models": ["qwen3.5:9b"],
        }
    )

    assert "Type: ollama" in text


def test_format_provider_validation_text_handles_reachable_and_empty_inventory_states() -> None:
    reachable = format_provider_validation_text(
        {
            "status": "reachable",
            "model_count": 2,
            "latest_model_id": "qwen3.5:9b",
            "message": "Use Discover Models to import them into the draft.",
        }
    )
    empty_inventory = format_provider_validation_text(
        {
            "status": "reachable_no_models",
            "model_count": 0,
            "message": "Enter a model id manually if this supplier requires explicit onboarding.",
        }
    )

    assert "Connection OK. 2 model(s) reachable." in reachable
    assert "Latest: qwen3.5:9b." in reachable
    assert "Connection OK, but no models were listed." in empty_inventory


def test_format_registry_model_detail_text_includes_feature_binding_summary() -> None:
    text = format_registry_model_detail_text(
        {
            "provider_name": "Ollama",
            "provider_id": "ollama",
            "source": "custom",
            "provider_family": "ollama",
            "provider_variant": "local",
            "api_type": "ollama",
            "api_base": "http://127.0.0.1:11434",
            "model_id": "glm-ocr:bf16",
            "display_name": "GLM OCR",
            "model_role": "ocr",
            "context_window": "32768",
            "learned_token_limit": "8192",
            "supports_tools_truth": "no",
            "supports_thinking_truth": "unknown",
        },
        feature_bindings={
            "items": [
                {
                    "feature_role": "ocr",
                    "provider_name": "Ollama",
                    "model_id": "glm-ocr:bf16",
                    "resolved": True,
                }
            ]
        },
    )

    assert "Model: glm-ocr:bf16" in text
    assert "Supports Thinking: unknown" in text
    assert "- ocr: Ollama / glm-ocr:bf16 (resolved)" in text


def test_format_memory_summary_text_includes_selection_and_search_totals() -> None:
    text = format_memory_summary_text(
        {
            "workspace_dir": "D:/file/Mini-Agent",
            "memory_root": "D:/file/Mini-Agent",
            "long_term_file": "D:/file/Mini-Agent/MEMORY.md",
            "daily_dir": "D:/file/Mini-Agent/memory",
            "daily_files": ["2026-04-17.md"],
            "notes_count": 3,
            "categories": ["fact", "decision"],
        },
        search_payload={"query": "routing", "total": 2},
        selected_path="D:/file/Mini-Agent/MEMORY.md",
    )

    assert "Memory Overview:" in text
    assert "- notes_count: 3" in text
    assert "- query: routing" in text
    assert "Selected File: D:/file/Mini-Agent/MEMORY.md" in text


def test_format_settings_summary_text_includes_connection_and_supply_counts() -> None:
    class _Conn:
        base_url = "http://127.0.0.1:8008"
        workspace = "D:/file/Mini-Agent"
        managed = True

    text = format_settings_summary_text(
        connection=_Conn(),
        selected_session_detail={
            "title": "Desk",
            "session_id": "sess-1",
            "selected_provider_id": "maas",
            "selected_model_id": "astron-code-latest",
            "pending_approvals": [{"token": "a"}],
        },
        workspace_summary={
            "workspace_dir": "D:/file/Mini-Agent",
            "session_count": 3,
            "shared_session_count": 1,
        },
        active_workspace={
            "title": "Default Workspace",
            "workspace_dir": "D:/file/Mini-Agent",
        },
        workspace_runtime_summary={
            "runtime_policy": {"mode": "single_main"},
            "runtime": {"scope": "workspace_only"},
        },
        workspace_list=[{"workspace_id": "ws-1"}],
        model_catalog={"items": [{"provider_id": "maas"}]},
        registry_payload={"items": [{"provider_id": "maas"}, {"provider_id": "ollama"}]},
        provider_payload={"items": [{"id": "maas"}]},
        feature_bindings={"items": [{"feature_role": "embedding"}]},
        refresh_interval_ms=5000,
        auto_refresh_enabled=False,
    )

    assert "Desktop Overview:" in text
    assert "- mode: managed" in text
    assert "- auto_refresh: paused" in text
    assert "- selected_model: astron-code-latest" in text
    assert "- active_title: Default Workspace" in text
    assert "- runtime_mode: single_main" in text
    assert "- runtime_scope: workspace_only" in text
    assert "- provider_count: 1" in text
    assert "- registry_provider_count: 2" in text


def test_desktop_error_detail_uses_gateway_detail_without_http_prefix() -> None:
    detail = desktop_error_detail(
        GatewayTransportError("Gateway HTTP 500: model registry offline", status_code=500)
    )

    assert detail == "model registry offline"


def test_format_desktop_approval_failure_uses_shared_pending_approval_semantics() -> None:
    activity_title, status_text = format_desktop_approval_failure(
        GatewayTransportError(
            "Gateway HTTP 409: Multiple approvals pending. Specify a token: approval-1, approval-2",
            status_code=409,
        )
    )

    assert activity_title.startswith("Approval token required:")
    assert "Multiple approvals pending. Specify a token" in activity_title
    assert status_text == "Specify approval token."
