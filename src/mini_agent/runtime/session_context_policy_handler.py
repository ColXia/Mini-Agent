"""Session prepared-context policy routing extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable

from fastapi import HTTPException
from mini_agent.interfaces import MainAgentSessionContextResponse

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


SUPPORTED_SESSION_CONTEXT_ACTIONS = frozenset({"include", "exclude", "budget", "reset"})


@dataclass(frozen=True, slots=True)
class RuntimeSessionContextPolicyCommand:
    action: str
    sources: tuple[str, ...] = ()
    max_items: int | None = None
    max_total_chars: int | None = None
    max_items_per_source: int | None = None


@dataclass(slots=True)
class RuntimeSessionContextPolicyExecution:
    response: MainAgentSessionContextResponse
    transcript_command: str
    transcript_summary: str
    transcript_details: str


@dataclass(slots=True)
class RuntimeSessionContextPolicyHandler:
    normalize_context_policy_payload: Callable[[Any], dict[str, Any]]
    format_context_policy_details: Callable[..., str]
    context_policy_summary_line: Callable[..., str]
    normalize_surface: Callable[[str | None], str | None]

    @staticmethod
    def normalize_action(action: str) -> str:
        return _safe_text(action).lower().replace("-", "_")

    def validate_action(self, action: str) -> str:
        normalized = self.normalize_action(action)
        if normalized not in SUPPORTED_SESSION_CONTEXT_ACTIONS:
            raise HTTPException(status_code=400, detail=f"Unsupported session context action: {action}")
        return normalized

    def execute(
        self,
        session: "MainAgentSessionState",
        command: RuntimeSessionContextPolicyCommand,
    ) -> RuntimeSessionContextPolicyExecution:
        normalized_action = self.validate_action(command.action)
        if session.projection.busy:
            raise HTTPException(status_code=409, detail="Session is busy. Wait for the current turn to finish.")

        normalized_policy = self.normalize_context_policy_payload(session.projection.context_policy)
        if normalized_action in {"include", "exclude"}:
            normalized_sources = [
                item
                for item in (_safe_text(value).lower() for value in command.sources)
                if item
            ]
            if not normalized_sources:
                raise HTTPException(
                    status_code=400,
                    detail=f"Session context action requires sources: {normalized_action}",
                )
            field_name = "include_sources" if normalized_action == "include" else "exclude_sources"
            normalized_policy[field_name] = normalized_sources
            normalized_policy = self.normalize_context_policy_payload(normalized_policy)
        elif normalized_action == "budget":
            if command.max_items is None:
                raise HTTPException(
                    status_code=400,
                    detail="Session context budget requires max_items.",
                )
            normalized_policy["max_items"] = max(1, int(command.max_items))
            if command.max_total_chars is not None:
                normalized_policy["max_total_chars"] = max(200, int(command.max_total_chars))
            if command.max_items_per_source is not None:
                normalized_policy["max_items_per_source"] = max(1, int(command.max_items_per_source))
            normalized_policy = self.normalize_context_policy_payload(normalized_policy)
        else:
            normalized_policy = self.normalize_context_policy_payload({})

        session.projection.context_policy = normalized_policy
        transcript_command = f"context {normalized_action}"
        transcript_summary = self.context_policy_summary_line(normalized_policy, include_default=True)
        transcript_details = self.format_context_policy_details(normalized_policy, include_header=True)

        response = MainAgentSessionContextResponse(
            status="updated",
            session_id=session.session_id,
            action=normalized_action,
            active_surface=self.normalize_surface(session.projection.active_surface or session.projection.origin_surface),
            context_policy=dict(normalized_policy),
        )
        return RuntimeSessionContextPolicyExecution(
            response=response,
            transcript_command=transcript_command,
            transcript_summary=transcript_summary,
            transcript_details=transcript_details,
        )


__all__ = [
    "RuntimeSessionContextPolicyCommand",
    "RuntimeSessionContextPolicyExecution",
    "RuntimeSessionContextPolicyHandler",
    "SUPPORTED_SESSION_CONTEXT_ACTIONS",
]
