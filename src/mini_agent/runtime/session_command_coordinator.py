"""Shared command-entry orchestration extracted from the runtime manager."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


@dataclass(frozen=True, slots=True)
class RuntimeSessionCommandTranscript:
    command: str
    summary: str
    content: str
    level: str = "info"
    threads_visible: bool | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class RuntimeSessionCommandCoordinator:
    append_transcript: Callable[..., Any]
    persist_session: Callable[["MainAgentSessionState"], None]

    async def execute_locked(
        self,
        session: "MainAgentSessionState",
        *,
        operation: Callable[[], Any | Awaitable[Any]],
        transcript_builder: Callable[[Any], RuntimeSessionCommandTranscript | None] | None = None,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        touch: bool | Callable[[Any], bool] = True,
        persist: bool | Callable[[Any], bool] = True,
    ) -> Any:
        async with session.runtime.lock:
            result = operation()
            if inspect.isawaitable(result):
                result = await result
            if transcript_builder is not None:
                transcript = transcript_builder(result)
                if transcript is not None:
                    self.record(
                        session,
                        transcript=transcript,
                        surface=surface,
                        channel_type=channel_type,
                        conversation_id=conversation_id,
                        sender_id=sender_id,
                        touch=False,
                        persist=False,
                    )
            should_touch = touch(result) if callable(touch) else bool(touch)
            should_persist = persist(result) if callable(persist) else bool(persist)
            if should_touch:
                session.touch()
            if should_persist:
                self.persist_session(session)
            return result

    def record(
        self,
        session: "MainAgentSessionState",
        *,
        transcript: RuntimeSessionCommandTranscript,
        surface: str | None = None,
        channel_type: str | None = None,
        conversation_id: str | None = None,
        sender_id: str | None = None,
        touch: bool = True,
        persist: bool = True,
    ) -> None:
        metadata = {
            "kind": "command",
            "command": transcript.command,
            "summary": transcript.summary,
            "level": transcript.level,
        }
        if transcript.threads_visible is not None:
            metadata["threads_visible"] = transcript.threads_visible
        if isinstance(transcript.metadata, dict):
            metadata.update(dict(transcript.metadata))
        self.append_transcript(
            session,
            role="system",
            content=transcript.content,
            surface=surface or session.projection.active_surface or session.projection.origin_surface,
            metadata=metadata,
            channel_type=channel_type,
            conversation_id=conversation_id,
            sender_id=sender_id,
        )
        if touch:
            session.touch()
        if persist:
            self.persist_session(session)


__all__ = [
    "RuntimeSessionCommandCoordinator",
    "RuntimeSessionCommandTranscript",
]
