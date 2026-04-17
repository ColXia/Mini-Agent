from __future__ import annotations

import asyncio
from pathlib import Path

from apps.agent_studio_gateway.composition import GatewayComposition, GatewayCompositionSettings
from mini_agent.application.legacy import (
    SessionAgentCompatibilityAdapter,
    SessionModelSelectionCompatibilityAdapter,
    SessionTaskCompatibilityAdapter,
)
from mini_agent.application import SessionTaskService


def test_gateway_composition_wires_explicit_session_task_service(tmp_path: Path) -> None:
    composition = GatewayComposition(
        settings=GatewayCompositionSettings(
            repo_root=Path(".").resolve(),
            workspace_root=tmp_path,
            session_ttl_seconds=3600,
            chat_stream_chunk_size=64,
            studio_gateway_host="127.0.0.1",
            studio_gateway_port=18080,
            studio_instance_lock_enabled=False,
            session_store_dir=tmp_path / "sessions",
        ),
        require_ops_auth=lambda: None,
    )

    session_task_service = composition.get_session_task_service()
    session_service = composition.get_session_service()
    run_control_service = composition.get_run_control_service()
    surface_service = composition.get_surface_service()

    assert isinstance(session_task_service, SessionTaskService)
    assert composition.get_session_task_service() is session_task_service
    assert session_service.session_task_service is session_task_service
    assert composition.get_run_control_service() is run_control_service
    assert surface_service._session_task_service is session_task_service
    assert surface_service._run_control_service is run_control_service
    assert surface_service._chat_flow.session_task_service is session_task_service
    assert isinstance(session_service.run_control_service.session_tasks, SessionTaskCompatibilityAdapter)
    assert isinstance(session_service.agent_service.session_agent_runtime, SessionAgentCompatibilityAdapter)
    assert isinstance(session_service.model_service.session_model_runtime, SessionModelSelectionCompatibilityAdapter)

    asyncio.run(composition.shutdown())


def test_gateway_composition_reuses_preassembled_session_owners_across_access_order(tmp_path: Path) -> None:
    composition = GatewayComposition(
        settings=GatewayCompositionSettings(
            repo_root=Path(".").resolve(),
            workspace_root=tmp_path,
            session_ttl_seconds=3600,
            chat_stream_chunk_size=64,
            studio_gateway_host="127.0.0.1",
            studio_gateway_port=18080,
            studio_instance_lock_enabled=False,
            session_store_dir=tmp_path / "sessions",
        ),
        require_ops_auth=lambda: None,
    )

    session_task_service = composition.get_session_task_service()
    run_control_service = composition.get_run_control_service()
    agent_service = composition.get_agent_service()
    model_service = composition.get_model_service()
    session_service = composition.get_session_service()

    assert session_service.session_task_service is session_task_service
    assert session_service.run_control_service is run_control_service
    assert session_service.agent_service is agent_service
    assert session_service.model_service is model_service

    asyncio.run(composition.shutdown())


def test_gateway_composition_builds_surface_without_materializing_session_facade(tmp_path: Path) -> None:
    composition = GatewayComposition(
        settings=GatewayCompositionSettings(
            repo_root=Path(".").resolve(),
            workspace_root=tmp_path,
            session_ttl_seconds=3600,
            chat_stream_chunk_size=64,
            studio_gateway_host="127.0.0.1",
            studio_gateway_port=18080,
            studio_instance_lock_enabled=False,
            session_store_dir=tmp_path / "sessions",
        ),
        require_ops_auth=lambda: None,
    )

    surface_service = composition.get_surface_service()

    assert surface_service is composition.get_surface_service()
    assert composition._session_service is None
    assert composition._run_control_service is not None
    assert composition._agent_service is not None
    assert composition._model_service is not None

    asyncio.run(composition.shutdown())
