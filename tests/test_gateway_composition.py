from __future__ import annotations

import asyncio
from pathlib import Path

from apps.agent_studio_gateway.composition import GatewayComposition, GatewayCompositionSettings
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
    surface_service = composition.get_surface_service()

    assert isinstance(session_task_service, SessionTaskService)
    assert composition.get_session_task_service() is session_task_service
    assert session_service.session_task_service is session_task_service
    assert surface_service._session_task_service is session_task_service
    assert surface_service._chat_flow.session_task_service is session_task_service

    asyncio.run(composition.shutdown())
