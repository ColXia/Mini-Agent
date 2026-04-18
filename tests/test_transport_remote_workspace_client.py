from __future__ import annotations

import asyncio

from mini_agent.interfaces import MainAgentWorkspaceSwitchRequest
from mini_agent.transport.remote_workspace_client import RemoteWorkspaceClient


class _DummyGatewayClient:
    async def list_workspaces(self):
        return [
            {
                "workspace_id": "ws-1",
                "workspace_dir": "D:/file/Mini-Agent",
                "title": "Default Workspace",
                "default": True,
                "active": True,
            }
        ]

    def list_workspaces_sync(self):
        return asyncio.run(self.list_workspaces())

    async def get_workspace(self, workspace_id: str):
        return {
            "workspace_id": workspace_id,
            "workspace_dir": "D:/file/Mini-Agent",
            "title": "Resolved Workspace",
            "default": True,
            "active": True,
        }

    def get_workspace_sync(self, workspace_id: str):
        return asyncio.run(self.get_workspace(workspace_id))

    async def get_active_workspace(self):
        return {
            "workspace_id": "ws-1",
            "workspace_dir": "D:/file/Mini-Agent",
            "title": "Default Workspace",
            "default": True,
            "active": True,
        }

    def get_active_workspace_sync(self):
        return asyncio.run(self.get_active_workspace())

    async def switch_workspace(self, workspace_id: str):
        return {
            "workspace_id": workspace_id,
            "workspace_dir": "D:/file/Mini-Agent",
            "title": "Switched Workspace",
            "active": True,
            "switched": True,
        }

    def switch_workspace_sync(self, workspace_id: str):
        return asyncio.run(self.switch_workspace(workspace_id))

    async def get_workspace_runtime_summary(self, *, workspace_id: str | None = None):
        return {
            "workspace_id": workspace_id or "ws-1",
            "workspace_dir": "D:/file/Mini-Agent",
            "title": "Runtime Workspace",
            "default": True,
            "active": True,
            "runtime_policy": {"mode": "single_main"},
            "runtime": {"mode": "direct", "scope": "workspace_only"},
        }

    def get_workspace_runtime_summary_sync(self, *, workspace_id: str | None = None):
        return asyncio.run(self.get_workspace_runtime_summary(workspace_id=workspace_id))


def test_remote_workspace_client_shapes_gateway_payloads_into_typed_models() -> None:
    async def _run() -> None:
        service = RemoteWorkspaceClient(workspace_transport=_DummyGatewayClient())

        listed = await service.list_workspaces()
        resolved = await service.get_workspace("ws-resolved")
        active = await service.get_active_workspace()
        switched = await service.switch_workspace(MainAgentWorkspaceSwitchRequest(workspace_id="ws-switched"))
        runtime = await service.get_workspace_runtime_summary(workspace_id="ws-runtime")

        assert listed[0].workspace_id == "ws-1"
        assert listed[0].active is True
        assert resolved.workspace_id == "ws-resolved"
        assert active.default is True
        assert switched.workspace_id == "ws-switched"
        assert switched.switched is True
        assert runtime.workspace_id == "ws-runtime"
        assert runtime.runtime_policy["mode"] == "single_main"
        assert runtime.runtime["scope"] == "workspace_only"

    asyncio.run(_run())


def test_remote_workspace_client_sync_methods_return_typed_models() -> None:
    service = RemoteWorkspaceClient(workspace_transport=_DummyGatewayClient())

    listed = service.list_workspaces_sync()
    resolved = service.get_workspace_sync("ws-sync")
    active = service.get_active_workspace_sync()
    switched = service.switch_workspace_sync(MainAgentWorkspaceSwitchRequest(workspace_id="ws-switch-sync"))
    runtime = service.get_workspace_runtime_summary_sync(workspace_id="ws-runtime-sync")

    assert listed[0].workspace_id == "ws-1"
    assert resolved.workspace_id == "ws-sync"
    assert active.active is True
    assert switched.switched is True
    assert runtime.workspace_id == "ws-runtime-sync"
    assert runtime.runtime["mode"] == "direct"
