from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.runtime.main_agent_runtime_manager import MainAgentRuntimeManager
from tests.runtime_contract_fixtures import RuntimeContractAgentStub


@pytest.mark.asyncio
async def test_runtime_manager_uses_explicit_agent_model_identity_for_new_sessions_and_ephemeral_agents(
    tmp_path: Path,
) -> None:
    build_calls: list[tuple[str, str | None, str | None, str | None]] = []

    async def _build_default(_workspace_dir: Path) -> RuntimeContractAgentStub:
        build_calls.append(("default", None, None, None))
        return RuntimeContractAgentStub(
            model="gpt-5.4",
            provider_source="preset",
            provider_id="openai",
        )

    async def _build_selected(
        _workspace_dir: Path,
        provider_source: str | None,
        provider_id: str | None,
        model_id: str | None,
    ) -> RuntimeContractAgentStub:
        build_calls.append(("selected", provider_source, provider_id, model_id))
        return RuntimeContractAgentStub(
            model=model_id or "fallback-model",
            provider_source=provider_source,
            provider_id=provider_id,
        )

    runtime = MainAgentRuntimeManager(
        ttl_seconds=3600,
        build_agent=_build_default,
        build_agent_with_selection=_build_selected,
        load_runtime_config=lambda: object(),
        storage_dir=tmp_path / "session-store",
        resolve_agent_model_identity=lambda: ("custom", "maas", "astron-code-latest"),
    )

    session = await runtime.get_or_create_session("sess-explicit", tmp_path)
    ephemeral = await runtime.build_ephemeral_agent(tmp_path)

    assert build_calls == [
        ("selected", "custom", "maas", "astron-code-latest"),
        ("selected", "custom", "maas", "astron-code-latest"),
    ]
    assert session.projection.selected_model_source == "custom"
    assert session.projection.selected_provider_id == "maas"
    assert session.projection.selected_model_id == "astron-code-latest"
    assert getattr(ephemeral.runtime_route, "provider_id", None) == "maas"
    assert getattr(ephemeral.runtime_route, "model", None) == "astron-code-latest"


@pytest.mark.asyncio
async def test_runtime_manager_keeps_default_builder_when_no_explicit_agent_model_identity(
    tmp_path: Path,
) -> None:
    build_calls: list[str] = []

    async def _build_default(_workspace_dir: Path) -> RuntimeContractAgentStub:
        build_calls.append("default")
        return RuntimeContractAgentStub(
            model="gpt-5.4",
            provider_source="preset",
            provider_id="openai",
        )

    async def _build_selected(
        _workspace_dir: Path,
        provider_source: str | None,
        provider_id: str | None,
        model_id: str | None,
    ) -> RuntimeContractAgentStub:
        _ = (provider_source, provider_id, model_id)
        build_calls.append("selected")
        return RuntimeContractAgentStub(model="should-not-run")

    runtime = MainAgentRuntimeManager(
        ttl_seconds=3600,
        build_agent=_build_default,
        build_agent_with_selection=_build_selected,
        load_runtime_config=lambda: object(),
        storage_dir=tmp_path / "session-store",
        resolve_agent_model_identity=None,
    )

    session = await runtime.get_or_create_session("sess-default", tmp_path)
    ephemeral = await runtime.build_ephemeral_agent(tmp_path)

    assert build_calls == ["default", "default"]
    assert session.projection.selected_model_source == "preset"
    assert session.projection.selected_provider_id == "openai"
    assert session.projection.selected_model_id == "gpt-5.4"
    assert getattr(ephemeral.runtime_route, "provider_id", None) == "preset-openai"


