"""Runtime session model identity normalization helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from mini_agent.agent_core.engine import Agent

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


_BOOTSTRAP_PROVIDER_ID = "bootstrap-config"


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


class RuntimeSessionModelIdentityCodec:
    """Own model source normalization and selected/pending identity translation."""

    @staticmethod
    def normalize_model_source(value: object) -> str | None:
        normalized = _safe_text(value).lower()
        return normalized or None

    @classmethod
    def normalize_model_identity(
        cls,
        source: object,
        provider_id: object,
        model_id: object,
    ) -> tuple[str, str, str] | None:
        normalized_source = cls.normalize_model_source(source)
        normalized_provider_id = _safe_text(provider_id)
        normalized_model_id = _safe_text(model_id)
        if normalized_source and normalized_provider_id and normalized_model_id:
            return normalized_source, normalized_provider_id, normalized_model_id
        return None

    @staticmethod
    def normalize_identity_value(value: object) -> tuple[str, str, str] | None:
        if not isinstance(value, (tuple, list)) or len(value) != 3:
            return None
        return RuntimeSessionModelIdentityCodec.normalize_model_identity(
            source=value[0],
            provider_id=value[1],
            model_id=value[2],
        )

    @staticmethod
    def route_model_identity_from_route(route: Any | None) -> tuple[str, str, str] | None:
        if route is None:
            return None
        model_id = _safe_text(getattr(route, "model", ""))
        provider_id = _safe_text(getattr(route, "provider_id", ""))
        if not model_id:
            return None
        if provider_id.startswith("preset-"):
            return "preset", provider_id.removeprefix("preset-"), model_id
        if provider_id == _BOOTSTRAP_PROVIDER_ID or not provider_id:
            return "bootstrap", _BOOTSTRAP_PROVIDER_ID, model_id
        if provider_id:
            return "custom", provider_id, model_id
        return None

    @classmethod
    def route_model_identity(cls, agent: Agent | None) -> tuple[str, str, str] | None:
        return cls.route_model_identity_from_route(getattr(agent, "runtime_route", None))

    @classmethod
    def selected_identity_from_projection(cls, projection: Any) -> tuple[str, str, str] | None:
        return cls.normalize_model_identity(
            source=getattr(projection, "selected_model_source", None),
            provider_id=getattr(projection, "selected_provider_id", None),
            model_id=getattr(projection, "selected_model_id", None),
        )

    @classmethod
    def pending_identity_from_projection(cls, projection: Any) -> tuple[str, str, str] | None:
        return cls.normalize_model_identity(
            source=getattr(projection, "pending_model_source", None),
            provider_id=getattr(projection, "pending_provider_id", None),
            model_id=getattr(projection, "pending_model_id", None),
        )

    @classmethod
    def set_selected_identity_on_projection(
        cls,
        projection: Any,
        identity: tuple[str, str, str] | None,
    ) -> None:
        normalized_identity = cls.normalize_identity_value(identity)
        setattr(projection, "selected_model_source", normalized_identity[0] if normalized_identity is not None else None)
        setattr(projection, "selected_provider_id", normalized_identity[1] if normalized_identity is not None else None)
        setattr(projection, "selected_model_id", normalized_identity[2] if normalized_identity is not None else None)

    @classmethod
    def set_pending_identity_on_projection(
        cls,
        projection: Any,
        identity: tuple[str, str, str] | None,
    ) -> None:
        normalized_identity = cls.normalize_identity_value(identity)
        setattr(projection, "pending_model_source", normalized_identity[0] if normalized_identity is not None else None)
        setattr(projection, "pending_provider_id", normalized_identity[1] if normalized_identity is not None else None)
        setattr(projection, "pending_model_id", normalized_identity[2] if normalized_identity is not None else None)

    @classmethod
    def selected_model_identity(cls, session: "MainAgentSessionState") -> tuple[str, str, str] | None:
        explicit = cls.selected_identity_from_projection(session.projection)
        if explicit is not None:
            return explicit
        return cls.route_model_identity(session.runtime.agent)

    @classmethod
    def pending_model_identity(cls, session: "MainAgentSessionState") -> tuple[str, str, str] | None:
        return cls.pending_identity_from_projection(session.projection)

    @classmethod
    def set_selected_model_identity(
        cls,
        session: "MainAgentSessionState",
        identity: tuple[str, str, str] | None,
    ) -> None:
        cls.set_selected_identity_on_projection(session.projection, identity)

    @classmethod
    def set_pending_model_identity(
        cls,
        session: "MainAgentSessionState",
        identity: tuple[str, str, str] | None,
    ) -> None:
        cls.set_pending_identity_on_projection(session.projection, identity)


__all__ = ["RuntimeSessionModelIdentityCodec"]
