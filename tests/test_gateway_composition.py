from __future__ import annotations

import asyncio
from pathlib import Path

from apps.agent_studio_gateway.composition import GatewayComposition, GatewayCompositionSettings
from mini_agent.application import RuntimeBackedUserServicePorts, SessionTaskService
from mini_agent.application.user_services.model_runtime_adapter import AgentModelRuntimeAdapter
from mini_agent.application.user_services import WorkspaceUserService


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
    runtime_backed_ports = composition.get_runtime_backed_user_service_ports()
    interaction_service = composition.get_agent_interaction_service()
    run_control_service = composition.get_run_control_service()
    agent_service = composition.get_agent_service()
    workspace_service = composition.get_workspace_service()

    assert isinstance(session_task_service, SessionTaskService)
    assert isinstance(runtime_backed_ports, RuntimeBackedUserServicePorts)
    assert isinstance(workspace_service, WorkspaceUserService)
    assert composition.get_session_task_service() is session_task_service
    assert composition.get_runtime_backed_user_service_ports() is runtime_backed_ports
    assert composition.get_run_control_service() is run_control_service
    assert composition.get_workspace_service() is workspace_service
    assert composition.get_agent_interaction_service() is interaction_service
    assert agent_service.interaction_service is interaction_service
    assert interaction_service.chat_flow.session_task_service is session_task_service
    assert runtime_backed_ports.session_task_runtime is composition.get_runtime_manager()
    assert runtime_backed_ports.session_task_port is composition.get_runtime_manager()
    assert runtime_backed_ports.session_agent_runtime is composition.get_runtime_manager()
    assert runtime_backed_ports.model_runtime is composition.get_model_runtime_adapter()
    assert runtime_backed_ports.workspace_runtime is composition.get_workspace_runtime()
    assert isinstance(composition.get_model_runtime_adapter(), AgentModelRuntimeAdapter)
    assert session_task_service._runtime_manager is runtime_backed_ports.session_task_runtime
    assert session_task_service._session_agent_runtime is runtime_backed_ports.session_agent_runtime
    assert run_control_service.session_tasks is runtime_backed_ports.session_task_port
    assert run_control_service.run_runtime is composition.get_runtime_manager()
    assert run_control_service.run_runtime is runtime_backed_ports.run_runtime
    assert agent_service.session_agent_runtime is runtime_backed_ports.session_agent_runtime
    assert composition.get_model_service().model_runtime is runtime_backed_ports.model_runtime

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
    workspace_service = composition.get_workspace_service()
    interaction_service = composition.get_agent_interaction_service()

    assert agent_service.interaction_service is interaction_service
    assert interaction_service.chat_flow.session_task_service is session_task_service
    assert workspace_service is composition.get_workspace_service()
    assert model_service is composition.get_model_service()
    assert run_control_service is composition.get_run_control_service()

    asyncio.run(composition.shutdown())


def test_gateway_composition_avoids_surface_facade_materialization(tmp_path: Path) -> None:
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

    interaction_service = composition.get_agent_interaction_service()
    session_task_service = composition.get_session_task_service()
    workspace_service = composition.get_workspace_service()
    agent_service = composition.get_agent_service()

    assert not hasattr(composition, "get_surface_service")
    assert not hasattr(composition, "_surface_service")
    assert interaction_service.chat_flow.session_task_service is session_task_service
    assert agent_service.interaction_service is interaction_service
    assert composition._run_control_service is not None
    assert composition._agent_service is not None
    assert composition._model_service is not None
    assert workspace_service is composition.get_workspace_service()

    asyncio.run(composition.shutdown())


def test_gateway_composition_workspace_service_reports_active_workspace(tmp_path: Path) -> None:
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

    workspace_service = composition.get_workspace_service()
    assert workspace_service is not None

    active = asyncio.run(workspace_service.get_active_workspace())

    assert active["default"] is True
    assert active["workspace_dir"] == str(Path(".").resolve())

    asyncio.run(composition.shutdown())


def test_gateway_composition_router_dependencies_expose_explicit_workspace_and_model_services(
    tmp_path: Path,
) -> None:
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

    deps = composition.build_main_agent_router_dependencies(list_models=lambda: {"items": []})

    assert deps.resolve_workspace_dir("workspace") == composition.resolve_workspace_dir("workspace")
    assert deps.get_routing_diagnostics.__self__ is composition
    assert deps.run_main_agent_chat.__self__ is composition
    assert deps.stream_main_agent_chat.__self__ is composition
    assert deps.get_session_task_service() is composition.get_session_task_service()
    assert deps.get_run_control_service() is composition.get_run_control_service()
    assert deps.get_workspace_service() is composition.get_workspace_service()
    assert deps.get_model_service() is composition.get_model_service()

    asyncio.run(composition.shutdown())
