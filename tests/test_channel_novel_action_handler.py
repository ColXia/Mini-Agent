from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import HTTPException

from mini_agent.application.use_cases.channel_novel_action_handler import ChannelNovelActionHandler
from mini_agent.interfaces import ChannelMessageRequest


class _FakeNovelUseCases:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str | None]] = []

    async def get_config(self, project_dir: str | None = None) -> dict[str, object]:
        self.calls.append(("config", project_dir))
        return {"exists": False, "project_dir": project_dir}


def _resolve_workspace_dir(workspace_dir: str | None) -> Path:
    return Path(workspace_dir or ".").resolve()


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def test_channel_novel_action_handler_handles_prefix_command(tmp_path: Path) -> None:
    async def _run() -> None:
        novel = _FakeNovelUseCases()
        handler = ChannelNovelActionHandler(
            novel_use_cases=novel,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
        )

        response = await handler.maybe_handle(
            ChannelMessageRequest(
                channel_type="qq",
                conversation_id="dm:novel",
                message="/novel config",
                workspace_dir=str(tmp_path / "workspace"),
                dry_run=True,
            )
        )

        assert response is not None
        assert response.session_id.startswith("novel-action-")
        assert "\"kind\": \"novel_action\"" in response.reply
        assert "\"action\": \"config\"" in response.reply
        assert novel.calls == [("config", None)]

    asyncio.run(_run())


def test_channel_novel_action_handler_handles_metadata_action(tmp_path: Path) -> None:
    async def _run() -> None:
        novel = _FakeNovelUseCases()
        handler = ChannelNovelActionHandler(
            novel_use_cases=novel,
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
        )

        response = await handler.maybe_handle(
            ChannelMessageRequest(
                channel_type="qq",
                conversation_id="group:novel-meta",
                message="ignored",
                workspace_dir=str(tmp_path / "workspace"),
                metadata={"novel_action": {"action": "config", "params": {"project_dir": "demo-project"}}},
            )
        )

        assert response is not None
        assert "demo-project" in response.reply
        assert novel.calls == [("config", "demo-project")]

    asyncio.run(_run())


def test_channel_novel_action_handler_returns_none_for_regular_messages(tmp_path: Path) -> None:
    async def _run() -> None:
        handler = ChannelNovelActionHandler(
            novel_use_cases=_FakeNovelUseCases(),
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
        )

        response = await handler.maybe_handle(
            ChannelMessageRequest(
                channel_type="qq",
                conversation_id="group:plain",
                message="hello there",
                workspace_dir=str(tmp_path / "workspace"),
            )
        )

        assert response is None

    asyncio.run(_run())


def test_channel_novel_action_handler_rejects_invalid_json_params() -> None:
    async def _run() -> None:
        handler = ChannelNovelActionHandler(
            novel_use_cases=_FakeNovelUseCases(),
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
        )

        with pytest.raises(HTTPException) as excinfo:
            await handler.maybe_handle(
                ChannelMessageRequest(
                    channel_type="qq",
                    conversation_id="group:invalid",
                    message="/novel config {bad-json}",
                    workspace_dir=".",
                )
            )

        assert excinfo.value.status_code == 400
        assert "Invalid novel action JSON params" in str(excinfo.value.detail)

    asyncio.run(_run())
