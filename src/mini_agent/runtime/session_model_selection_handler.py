"""Session model-selection routing extracted from the runtime manager."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from fastapi import HTTPException

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True, slots=True)
class RuntimeSessionModelSelectionRequest:
    provider_source: str
    provider_id: str
    model_id: str


@dataclass(frozen=True, slots=True)
class RuntimeSessionModelSelectionPlan:
    status: str
    applied: bool
    queued: bool
    bind_surface: bool = False
    touch_and_persist: bool = False
    update_pending_identity: bool = False
    pending_identity: tuple[str, str, str] | None = None
    rebuild_identity: tuple[str, str, str] | None = None


@dataclass(slots=True)
class RuntimeSessionModelSelectionHandler:
    normalize_model_identity: Callable[..., tuple[str, str, str] | None]
    resolve_selection_identity: Callable[..., tuple[str, str, str]]
    selected_model_identity: Callable[["MainAgentSessionState"], tuple[str, str, str] | None]
    pending_model_identity: Callable[["MainAgentSessionState"], tuple[str, str, str] | None]

    def resolve_request(
        self,
        *,
        provider_source: str | None,
        provider_id: str,
        model_id: str,
    ) -> RuntimeSessionModelSelectionRequest:
        try:
            if _safe_text(provider_source):
                requested_identity = self.normalize_model_identity(
                    source=provider_source,
                    provider_id=provider_id,
                    model_id=model_id,
                )
            else:
                requested_identity = self.resolve_selection_identity(
                    provider_source=provider_source,
                    provider_id=provider_id,
                    model_id=model_id,
                )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if requested_identity is None:
            raise HTTPException(status_code=400, detail="Invalid model selection payload.")
        return RuntimeSessionModelSelectionRequest(
            provider_source=requested_identity[0],
            provider_id=requested_identity[1],
            model_id=requested_identity[2],
        )

    def plan_update(
        self,
        session: "MainAgentSessionState",
        request: RuntimeSessionModelSelectionRequest,
    ) -> RuntimeSessionModelSelectionPlan:
        requested_identity = self._request_identity(request)
        current_identity = self.selected_model_identity(session)
        pending_identity = self.pending_model_identity(session)

        if session.projection.busy:
            if current_identity == requested_identity and pending_identity is None:
                return RuntimeSessionModelSelectionPlan(
                    status="selected",
                    applied=True,
                    queued=False,
                )
            if pending_identity != requested_identity:
                return RuntimeSessionModelSelectionPlan(
                    status="queued",
                    applied=False,
                    queued=True,
                    bind_surface=True,
                    touch_and_persist=True,
                    update_pending_identity=True,
                    pending_identity=requested_identity,
                )
            return RuntimeSessionModelSelectionPlan(
                status="queued",
                applied=False,
                queued=True,
            )

        if current_identity == requested_identity and session.runtime.agent is not None:
            return RuntimeSessionModelSelectionPlan(
                status="selected",
                applied=True,
                queued=False,
                bind_surface=True,
                touch_and_persist=True,
                update_pending_identity=True,
                pending_identity=None,
            )

        return RuntimeSessionModelSelectionPlan(
            status="selected",
            applied=True,
            queued=False,
            bind_surface=True,
            touch_and_persist=True,
            rebuild_identity=requested_identity,
        )

    def pending_identity_to_apply(
        self,
        session: "MainAgentSessionState",
    ) -> tuple[str, str, str] | None:
        pending_identity = self.pending_model_identity(session)
        if pending_identity is None or session.projection.busy:
            return None
        return pending_identity

    @staticmethod
    def _request_identity(
        request: RuntimeSessionModelSelectionRequest,
    ) -> tuple[str, str, str]:
        return request.provider_source, request.provider_id, request.model_id


__all__ = [
    "RuntimeSessionModelSelectionHandler",
    "RuntimeSessionModelSelectionPlan",
    "RuntimeSessionModelSelectionRequest",
]
