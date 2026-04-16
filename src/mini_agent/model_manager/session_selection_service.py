"""Shared session-scoped model selection semantics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(frozen=True, slots=True)
class SessionModelSelectionRequest:
    provider_source: str
    provider_id: str
    model_id: str

    @property
    def identity(self) -> tuple[str, str, str]:
        return self.provider_source, self.provider_id, self.model_id


@dataclass(frozen=True, slots=True)
class SessionModelSelectionPlan:
    status: str
    applied: bool
    queued: bool
    bind_surface: bool = False
    touch_and_persist: bool = False
    update_pending_identity: bool = False
    pending_identity: tuple[str, str, str] | None = None
    activate_identity: tuple[str, str, str] | None = None
    already_selected: bool = False
    already_queued: bool = False


@dataclass(frozen=True, slots=True)
class SessionModelSelectionFeedback:
    status_text: str
    compact_text: str


@dataclass(slots=True)
class SessionModelSelectionService:
    normalize_model_identity: Callable[..., tuple[str, str, str] | None] | None = None
    resolve_selection_identity: Callable[..., tuple[str, str, str]] | None = None

    def resolve_request(
        self,
        *,
        provider_source: str | None,
        provider_id: str,
        model_id: str,
    ) -> SessionModelSelectionRequest:
        if self.normalize_model_identity is None:
            raise ValueError("normalize_model_identity is required for resolve_request().")
        try:
            if _safe_text(provider_source):
                requested_identity = self.normalize_model_identity(
                    source=provider_source,
                    provider_id=provider_id,
                    model_id=model_id,
                )
            else:
                if self.resolve_selection_identity is None:
                    raise ValueError("resolve_selection_identity is required when provider_source is omitted.")
                requested_identity = self.resolve_selection_identity(
                    provider_source=provider_source,
                    provider_id=provider_id,
                    model_id=model_id,
                )
        except ValueError:
            raise
        if requested_identity is None:
            raise ValueError("Invalid model selection payload.")
        return SessionModelSelectionRequest(
            provider_source=requested_identity[0],
            provider_id=requested_identity[1],
            model_id=requested_identity[2],
        )

    @staticmethod
    def plan_update(
        *,
        request: SessionModelSelectionRequest,
        current_identity: tuple[str, str, str] | None,
        pending_identity: tuple[str, str, str] | None,
        busy: bool,
        runtime_attached: bool,
    ) -> SessionModelSelectionPlan:
        requested_identity = request.identity

        if busy:
            if current_identity == requested_identity and pending_identity is None:
                return SessionModelSelectionPlan(
                    status="selected",
                    applied=True,
                    queued=False,
                    already_selected=True,
                )
            if pending_identity != requested_identity:
                return SessionModelSelectionPlan(
                    status="queued",
                    applied=False,
                    queued=True,
                    bind_surface=True,
                    touch_and_persist=True,
                    update_pending_identity=True,
                    pending_identity=requested_identity,
                )
            return SessionModelSelectionPlan(
                status="queued",
                applied=False,
                queued=True,
                already_queued=True,
            )

        if current_identity == requested_identity and runtime_attached:
            return SessionModelSelectionPlan(
                status="selected",
                applied=True,
                queued=False,
                bind_surface=True,
                touch_and_persist=True,
                update_pending_identity=True,
                pending_identity=None,
                already_selected=True,
            )

        return SessionModelSelectionPlan(
            status="selected",
            applied=True,
            queued=False,
            bind_surface=True,
            touch_and_persist=True,
            activate_identity=requested_identity,
        )

    @staticmethod
    def pending_identity_to_apply(
        *,
        pending_identity: tuple[str, str, str] | None,
        busy: bool,
    ) -> tuple[str, str, str] | None:
        if pending_identity is None or busy:
            return None
        return pending_identity

    @staticmethod
    def queued_feedback(*, model_label: str, session_title: str) -> SessionModelSelectionFeedback:
        normalized_label = _safe_text(model_label) or "model"
        normalized_title = _safe_text(session_title) or "session"
        return SessionModelSelectionFeedback(
            status_text=f"Queued {normalized_label} for {normalized_title}; it will apply after the current turn.",
            compact_text=f"Model queued: {normalized_label}",
        )

    @staticmethod
    def applied_feedback(*, model_label: str, session_title: str) -> SessionModelSelectionFeedback:
        normalized_label = _safe_text(model_label) or "model"
        normalized_title = _safe_text(session_title) or "session"
        return SessionModelSelectionFeedback(
            status_text=f"Applied {normalized_label} to {normalized_title}.",
            compact_text=f"Model applied: {normalized_label}",
        )

    @staticmethod
    def already_selected_feedback(*, model_label: str, session_title: str) -> SessionModelSelectionFeedback:
        normalized_label = _safe_text(model_label) or "model"
        normalized_title = _safe_text(session_title) or "session"
        return SessionModelSelectionFeedback(
            status_text=f"{normalized_title} is already using {normalized_label}.",
            compact_text=f"Model already selected: {normalized_label}",
        )

    @staticmethod
    def already_queued_feedback(*, model_label: str, session_title: str) -> SessionModelSelectionFeedback:
        normalized_label = _safe_text(model_label) or "model"
        normalized_title = _safe_text(session_title) or "session"
        return SessionModelSelectionFeedback(
            status_text=f"{normalized_label} is already queued for {normalized_title}.",
            compact_text=f"Model already queued: {normalized_label}",
        )


__all__ = [
    "SessionModelSelectionFeedback",
    "SessionModelSelectionPlan",
    "SessionModelSelectionRequest",
    "SessionModelSelectionService",
]
