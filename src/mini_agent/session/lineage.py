"""Session-owned lineage records."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from mini_agent.agent_core.session.lineage import SessionLineageNode, SessionLineageStore
from mini_agent.utils.text import safe_text

if TYPE_CHECKING:
    from mini_agent.session.store_records import MainAgentSessionState


@dataclass(slots=True)
class MainAgentSessionLineageState:
    parent_session_id: str | None = None
    root_session_id: str | None = None
    reason: str = "root"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: dict[str, Any] = field(default_factory=dict)


def _safe_text(value: object) -> str:
    return safe_text(value)


@dataclass(slots=True)
class RuntimeSessionLineageRegistry:
    store: SessionLineageStore

    def replace_store(self, store: SessionLineageStore) -> None:
        self.store = store

    def register_session(self, session: "MainAgentSessionState") -> None:
        lineage = session.lineage_state
        parent_session_id = _safe_text(lineage.parent_session_id) or None
        root_session_id = _safe_text(lineage.root_session_id) or None
        reason = _safe_text(lineage.reason) or ("child" if parent_session_id else "root")
        created_at = (lineage.created_at or session.created_at).astimezone(timezone.utc)
        metadata = dict(lineage.metadata) if isinstance(lineage.metadata, dict) else {}

        if parent_session_id is not None:
            parent_node = self.store.get(parent_session_id)
            resolved_root_session_id = (
                root_session_id
                or self._lineage_root_from_node(parent_node)
                or parent_session_id
            )
            lineage.parent_session_id = parent_session_id
            lineage.root_session_id = resolved_root_session_id
            lineage.reason = reason
            lineage.created_at = created_at
            lineage.metadata = metadata
            metadata["root_session_id"] = resolved_root_session_id
            self.store.restore_node(
                SessionLineageNode(
                    session_key=session.session_id,
                    parent_session_key=parent_session_id,
                    reason=reason,
                    created_utc=created_at,
                    metadata=metadata,
                )
            )
            return

        resolved_root_session_id = root_session_id or session.session_id
        lineage.parent_session_id = None
        lineage.root_session_id = resolved_root_session_id
        lineage.reason = "root"
        lineage.created_at = created_at
        lineage.metadata = metadata
        metadata["root_session_id"] = resolved_root_session_id
        self.store.restore_node(
            SessionLineageNode(
                session_key=session.session_id,
                parent_session_key=None,
                reason="root",
                created_utc=created_at,
                metadata=metadata,
            )
        )

    def remove_session(self, session_id: str) -> None:
        self.store.remove(session_id)

    @staticmethod
    def _lineage_root_from_node(node: SessionLineageNode | None) -> str | None:
        if node is None:
            return None
        root_session_id = _safe_text(node.metadata.get("root_session_id"))
        if root_session_id:
            return root_session_id
        if node.parent_session_key is None:
            return node.session_key
        return None


__all__ = ["MainAgentSessionLineageState", "RuntimeSessionLineageRegistry"]
