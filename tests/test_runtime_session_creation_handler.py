from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from mini_agent.runtime.handlers.session_creation_handler import (
    RuntimeSessionCreationCommand,
    RuntimeSessionCreationHandler,
)
from mini_agent.session import DEFAULT_SESSION_TITLE
from tests.runtime_contract_fixtures import RuntimeContractAgentStub


def _dt() -> datetime:
    return datetime(2026, 4, 16, 18, 30, 0, tzinfo=timezone.utc)


@pytest.mark.asyncio
async def test_runtime_session_creation_handler_supports_default_session_bootstrap(tmp_path: Path) -> None:
    handler = RuntimeSessionCreationHandler(
        allocate_session_title=lambda base_title, _workspace_dir: f"{base_title} 2",
        normalize_surface=lambda value: " ".join(str(value or "").strip().lower().split()) or "api",
        normalize_channel_type=lambda value: str(value).lower() if value else None,
        build_agent_for_identity=lambda _workspace_dir, _identity: _build_agent(),
        default_model_identity=None,
        bootstrap_session_lifecycle=lambda session_id, workspace_dir, now_utc: {
            "session_id": session_id,
            "workspace_dir": workspace_dir,
            "now_utc": now_utc,
        },
        agent_knowledge_base_enabled=lambda _agent: True,
        collect_sandbox_diagnostics=lambda _agent: {"backend": "none"},
        route_model_identity=lambda _agent: ("preset", "openai", "gpt-5.4"),
    )

    session = await handler.create(
        RuntimeSessionCreationCommand(
            session_id="default",
            workspace_dir=tmp_path,
            default_title=DEFAULT_SESSION_TITLE,
            is_default=True,
            default_surface="tui",
        ),
        now_utc=_dt(),
    )

    assert session.lifecycle_state["session_id"] == "default"
    assert session.projection.title == DEFAULT_SESSION_TITLE
    assert session.projection.is_default is True
    assert session.projection.origin_surface == "tui"


@pytest.mark.asyncio
async def test_runtime_session_creation_handler_supports_legacy_lifecycle_wiring(tmp_path: Path) -> None:
    handler = RuntimeSessionCreationHandler(
        allocate_session_title=lambda base_title, _workspace_dir: f"{base_title} 2",
        normalize_surface=lambda value: " ".join(str(value or "").strip().lower().split()) or "api",
        normalize_channel_type=lambda value: str(value).lower() if value else None,
        build_agent_for_identity=lambda _workspace_dir, _identity: _build_agent(),
        default_model_identity=None,
        build_session_key=lambda session_id, workspace_dir: (session_id, str(workspace_dir)),
        lifecycle_bootstrap=lambda session_key, now_utc: {
            "session_key": session_key,
            "now_utc": now_utc,
        },
        agent_knowledge_base_enabled=lambda _agent: False,
        collect_sandbox_diagnostics=lambda _agent: {"backend": "none"},
        route_model_identity=lambda _agent: None,
    )

    session = await handler.create(
        RuntimeSessionCreationCommand(
            session_id="sess-legacy",
            workspace_dir=tmp_path,
            title="Task",
            default_surface="qq",
            shared=True,
        ),
        now_utc=_dt(),
    )

    assert session.lifecycle_state == {
        "session_key": ("sess-legacy", str(tmp_path)),
        "now_utc": _dt(),
    }
    assert session.projection.title == "Task 2"
    assert session.projection.is_default is False
    assert session.projection.shared is True
    assert session.projection.origin_surface == "qq"


@pytest.mark.asyncio
async def test_runtime_session_creation_handler_uses_default_model_identity_for_build_and_projection(
    tmp_path: Path,
) -> None:
    seen_identities: list[tuple[str, str, str] | None] = []

    async def _build_agent(
        _workspace_dir: Path,
        identity: tuple[str, str, str] | None,
    ) -> RuntimeContractAgentStub:
        seen_identities.append(identity)
        if identity is None:
            return RuntimeContractAgentStub(model="fallback-model")
        provider_source, provider_id, model_id = identity
        return RuntimeContractAgentStub(
            model=model_id,
            provider_source=provider_source,
            provider_id=provider_id,
        )

    handler = RuntimeSessionCreationHandler(
        allocate_session_title=lambda base_title, _workspace_dir: base_title,
        normalize_surface=lambda value: " ".join(str(value or "").strip().lower().split()) or "api",
        normalize_channel_type=lambda value: str(value).lower() if value else None,
        build_agent_for_identity=_build_agent,
        default_model_identity=lambda: ("custom", "maas", "astron-code-latest"),
        bootstrap_session_lifecycle=lambda session_id, workspace_dir, now_utc: {
            "session_id": session_id,
            "workspace_dir": workspace_dir,
            "now_utc": now_utc,
        },
        agent_knowledge_base_enabled=lambda _agent: True,
        collect_sandbox_diagnostics=lambda _agent: {"backend": "none"},
        route_model_identity=lambda agent: getattr(agent, "runtime_route", None)
        and ("custom", "maas", "astron-code-latest"),
    )

    session = await handler.create(
        RuntimeSessionCreationCommand(
            session_id="sess-explicit",
            workspace_dir=tmp_path,
            title="Task",
            default_surface="desktop",
        ),
        now_utc=_dt(),
    )

    assert seen_identities == [("custom", "maas", "astron-code-latest")]
    assert session.projection.selected_model_source == "custom"
    assert session.projection.selected_provider_id == "maas"
    assert session.projection.selected_model_id == "astron-code-latest"


async def _build_agent() -> RuntimeContractAgentStub:
    return RuntimeContractAgentStub()
