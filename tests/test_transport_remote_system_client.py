from __future__ import annotations

from mini_agent.transport.remote_system_client import RemoteSystemClient


class _DummyGatewayClient:
    def get_system_health_sync(self):
        return {
            "status": "healthy",
            "now_utc": "2026-04-18T08:00:00Z",
            "workspace_root": "D:/file/Mini-Agent",
            "runtime": {
                "mode": "single_main",
                "active_sessions": 1,
                "max_active_sessions": 4,
                "available_session_slots": 3,
                "reserved_team_slots": 1,
                "workspace_application_required": False,
                "team_saturation_rejections": 0,
                "team_workspace_conflict_rejections": 0,
                "lifecycle_auto_resets": 0,
                "session_reset_mode": "none",
                "session_idle_seconds": 1800,
                "main_workspace_dir": "D:/file/Mini-Agent",
            },
        }


def test_remote_system_client_shapes_gateway_payload_into_typed_model() -> None:
    service = RemoteSystemClient(system_transport=_DummyGatewayClient())

    health = service.get_system_health_sync()

    assert health.status == "healthy"
    assert health.runtime.active_sessions == 1
    assert health.runtime.mode == "single_main"
