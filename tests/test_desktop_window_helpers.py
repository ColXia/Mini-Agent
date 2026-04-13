"""Tests for DesktopUI formatting helpers."""

from __future__ import annotations

from mini_agent.desktop.window import (
    _truncate_text,
    collect_model_options,
    first_pending_approval,
    format_model_catalog_text,
    format_session_context_text,
    format_session_row,
    render_activity_html,
    render_conversation_html,
)


def test_truncate_text_appends_ellipsis_when_limit_is_exceeded() -> None:
    assert _truncate_text("abcdefghijklmnopqrstuvwxyz", limit=10) == "abcdefghi…"


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

    assert text == "Session A | desktop | local | busy | model=astron-code-latest"


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
            "provider_source": "preset",
            "provider_id": "openai",
            "model_id": "gpt-5.4",
        }
    ]


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
