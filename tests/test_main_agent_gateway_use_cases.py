"""Unit tests for main-agent gateway application-layer use cases."""

from __future__ import annotations

import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from mini_agent.application import MainAgentGatewayUseCases
from mini_agent.interfaces import MainAgentChatRequest
from mini_agent.runtime.main_agent_runtime_manager import (
    MainAgentRuntimeManager,
    MainAgentRuntimeMode,
    MainAgentRuntimePolicy,
)


class _DummyAgent:
    def __init__(self) -> None:
        self.messages = [SimpleNamespace(role="system", content="system")]
        self.api_total_tokens = 0

    def add_user_message(self, content: str) -> None:
        self.messages.append(SimpleNamespace(role="user", content=content))

    async def run(self) -> str:
        text = f"mock:{self.messages[-1].content}"
        self.messages.append(SimpleNamespace(role="assistant", content=text))
        self.api_total_tokens += 7
        return text


def _resolve_workspace_dir(workspace_dir: str | None) -> Path:
    return Path(workspace_dir or ".").resolve()


def _to_utc_iso(value: datetime) -> str:
    return value.isoformat()


def _sse_event(event: str, data: dict[str, object]) -> str:
    return f"{event}:{data}"


def _format_bootstrap_error(exc: Exception):
    raise RuntimeError(str(exc))


def test_use_case_chat_session_lifecycle() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = MainAgentRuntimeManager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = MainAgentGatewayUseCases(
            runtime_manager=runtime,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=64,
        )

        chat = await use_cases.run_chat(
            MainAgentChatRequest(message="hello", workspace_dir=".", session_id="sess-1", dry_run=False)
        )
        assert chat.session_id == "sess-1"
        assert chat.reply == "mock:hello"
        assert chat.message_count >= 3

        sessions = await use_cases.list_sessions()
        assert len(sessions) == 1
        assert sessions[0].session_id == "sess-1"

        reset = await use_cases.reset_session("sess-1")
        assert reset.status == "reset"

        deleted = await use_cases.delete_session("sess-1")
        assert deleted.status == "deleted"
        assert (await use_cases.list_sessions()) == []

    asyncio.run(_run())


def test_use_case_stream_dry_run_emits_done() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = MainAgentRuntimeManager(ttl_seconds=3600, build_agent=_build_agent)
        use_cases = MainAgentGatewayUseCases(
            runtime_manager=runtime,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=16,
        )

        events: list[str] = []
        async for event in use_cases.stream_chat_events(message="ping", dry_run=True):
            events.append(event)
        joined = "\n".join(events)
        assert "session" in joined
        assert "done" in joined

    asyncio.run(_run())


def test_runtime_manager_single_runtime_rejects_second_workspace() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = MainAgentRuntimeManager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(mode=MainAgentRuntimeMode.SINGLE_MAIN),
        )
        first_workspace = Path(".").resolve()
        second_workspace = (first_workspace / "workspace-b").resolve()

        session = await runtime.get_or_create_session("sess-1", first_workspace)
        assert session.session_id == "sess-1"

        with pytest.raises(Exception) as exc_info:
            await runtime.get_or_create_session("sess-2", second_workspace)
        exc = exc_info.value
        assert getattr(exc, "status_code", None) == 409

    asyncio.run(_run())


def test_runtime_manager_single_runtime_reuses_active_session_for_same_workspace() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        runtime = MainAgentRuntimeManager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(mode=MainAgentRuntimeMode.SINGLE_MAIN),
        )
        workspace = Path(".").resolve()
        first = await runtime.get_or_create_session("sess-1", workspace)
        second = await runtime.get_or_create_session(None, workspace)
        assert first.session_id == "sess-1"
        assert second.session_id == "sess-1"

    asyncio.run(_run())


def test_runtime_manager_single_main_workspace_only_rejects_other_workspace() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        main_workspace = Path(".").resolve()
        other_workspace = (main_workspace / "workspace-other").resolve()
        runtime = MainAgentRuntimeManager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.SINGLE_MAIN,
                main_workspace_dir=main_workspace,
                max_active_sessions=1,
            ),
        )

        with pytest.raises(Exception) as exc_info:
            await runtime.get_or_create_session("sess-main", other_workspace)
        exc = exc_info.value
        assert getattr(exc, "status_code", None) == 409
        assert "main workspace" in str(getattr(exc, "detail", "")).lower()

    asyncio.run(_run())


def test_use_case_dry_run_also_enforces_single_main_workspace() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        main_workspace = Path(".").resolve()
        runtime = MainAgentRuntimeManager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.SINGLE_MAIN,
                main_workspace_dir=main_workspace,
                max_active_sessions=1,
            ),
        )
        use_cases = MainAgentGatewayUseCases(
            runtime_manager=runtime,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_bootstrap_error,
            stream_chunk_size=32,
        )

        with pytest.raises(Exception) as exc_info:
            await use_cases.run_chat(
                MainAgentChatRequest(
                    message="dry-run-check",
                    dry_run=True,
                    workspace_dir=str((main_workspace / "other-workspace").resolve()),
                )
            )
        exc = exc_info.value
        assert getattr(exc, "status_code", None) == 409

    asyncio.run(_run())


def test_runtime_manager_team_mode_allows_multi_workspace_sessions() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        root = Path(".").resolve()
        workspace_a = root
        workspace_b = (root / "workspace-b").resolve()

        runtime = MainAgentRuntimeManager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=root,
                max_active_sessions=4,
                reserved_team_slots=4,
            ),
        )

        session_a = await runtime.get_or_create_session("sess-a", workspace_a)
        session_b = await runtime.get_or_create_session("sess-b", workspace_b)
        assert session_a.session_id == "sess-a"
        assert session_b.session_id == "sess-b"
        sessions = await runtime.list_sessions()
        assert len(sessions) == 2

    asyncio.run(_run())


def test_runtime_manager_team_mode_reuses_workspace_session_without_session_id() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        root = Path(".").resolve()
        workspace_a = root
        runtime = MainAgentRuntimeManager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=root,
                max_active_sessions=4,
                reserved_team_slots=4,
            ),
        )

        first = await runtime.get_or_create_session("sess-a", workspace_a)
        second = await runtime.get_or_create_session(None, workspace_a)
        assert first.session_id == "sess-a"
        assert second.session_id == "sess-a"
        sessions = await runtime.list_sessions()
        assert len(sessions) == 1

    asyncio.run(_run())


def test_runtime_manager_team_mode_rejects_when_max_active_sessions_reached() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        root = Path(".").resolve()
        workspace_a = root
        workspace_b = (root / "workspace-b").resolve()
        workspace_c = (root / "workspace-c").resolve()
        runtime = MainAgentRuntimeManager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=root,
                max_active_sessions=2,
                reserved_team_slots=4,
            ),
        )

        await runtime.get_or_create_session("sess-a", workspace_a)
        await runtime.get_or_create_session("sess-b", workspace_b)
        with pytest.raises(Exception) as exc_info:
            await runtime.get_or_create_session("sess-c", workspace_c)
        exc = exc_info.value
        assert getattr(exc, "status_code", None) == 409
        assert "max_active_sessions" in str(getattr(exc, "detail", ""))

    asyncio.run(_run())


def test_runtime_manager_runtime_diagnostics_snapshot_tracks_capacity() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        root = Path(".").resolve()
        runtime = MainAgentRuntimeManager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=root,
                max_active_sessions=3,
                reserved_team_slots=5,
                workspace_application_required=True,
            ),
        )

        empty_diag = await runtime.get_runtime_diagnostics()
        assert empty_diag.mode == "team"
        assert empty_diag.active_sessions == 0
        assert empty_diag.max_active_sessions == 3
        assert empty_diag.available_session_slots == 3
        assert empty_diag.reserved_team_slots == 5
        assert empty_diag.workspace_application_required is True
        assert empty_diag.team_saturation_rejections == 0
        assert empty_diag.team_workspace_conflict_rejections == 0
        assert empty_diag.main_workspace_dir

        await runtime.get_or_create_session("sess-a", root)
        after_diag = await runtime.get_runtime_diagnostics()
        assert after_diag.active_sessions == 1
        assert after_diag.available_session_slots == 2
        assert after_diag.team_saturation_rejections == 0
        assert after_diag.team_workspace_conflict_rejections == 0

    asyncio.run(_run())


def test_runtime_manager_team_mode_diagnostics_track_conflicts_and_saturation() -> None:
    async def _run() -> None:
        async def _build_agent(_workspace: Path):
            return _DummyAgent()

        root = Path(".").resolve()
        workspace_a = root
        workspace_b = (root / "workspace-b").resolve()
        runtime = MainAgentRuntimeManager(
            ttl_seconds=3600,
            build_agent=_build_agent,
            policy=MainAgentRuntimePolicy(
                mode=MainAgentRuntimeMode.TEAM,
                main_workspace_dir=root,
                max_active_sessions=1,
                reserved_team_slots=2,
            ),
        )

        await runtime.get_or_create_session("sess-a", workspace_a)

        with pytest.raises(Exception) as conflict_exc:
            await runtime.get_or_create_session("sess-a", workspace_b)
        assert getattr(conflict_exc.value, "status_code", None) == 400

        with pytest.raises(Exception) as saturation_exc:
            await runtime.get_or_create_session("sess-b", workspace_b)
        assert getattr(saturation_exc.value, "status_code", None) == 409

        diagnostics = await runtime.get_runtime_diagnostics()
        assert diagnostics.team_workspace_conflict_rejections == 1
        assert diagnostics.team_saturation_rejections == 1

    asyncio.run(_run())
