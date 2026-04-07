"""Session lineage tracking for reset/delegation/compression flows."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class SessionLineageNode:
    """One lineage node."""

    session_key: str
    parent_session_key: str | None = None
    reason: str = "root"
    created_utc: datetime = field(default_factory=_utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)


class SessionLineageStore:
    """In-memory lineage graph."""

    def __init__(self) -> None:
        self._nodes: dict[str, SessionLineageNode] = {}
        self._children: dict[str, set[str]] = {}

    def add_root(self, session_key: str, *, metadata: dict[str, Any] | None = None) -> SessionLineageNode:
        key = session_key.strip()
        if not key:
            raise ValueError("session_key must not be empty.")
        node = SessionLineageNode(
            session_key=key,
            parent_session_key=None,
            reason="root",
            metadata=dict(metadata or {}),
        )
        self._nodes[key] = node
        self._children.setdefault(key, set())
        return node

    def add_child(
        self,
        *,
        parent_session_key: str,
        child_session_key: str,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> SessionLineageNode:
        parent = parent_session_key.strip()
        child = child_session_key.strip()
        if not parent or not child:
            raise ValueError("parent/child session keys must not be empty.")
        if parent == child:
            raise ValueError("parent and child session keys must differ.")
        if parent not in self._nodes:
            self.add_root(parent)
        if self._creates_cycle(parent, child):
            raise ValueError(f"lineage cycle detected: parent={parent}, child={child}")

        node = SessionLineageNode(
            session_key=child,
            parent_session_key=parent,
            reason=reason.strip() or "child",
            metadata=dict(metadata or {}),
        )
        self._nodes[child] = node
        self._children.setdefault(parent, set()).add(child)
        self._children.setdefault(child, set())
        return node

    def get(self, session_key: str) -> SessionLineageNode | None:
        return self._nodes.get(session_key)

    def parent_of(self, session_key: str) -> SessionLineageNode | None:
        node = self._nodes.get(session_key)
        if node is None or node.parent_session_key is None:
            return None
        return self._nodes.get(node.parent_session_key)

    def children_of(self, session_key: str) -> list[SessionLineageNode]:
        child_keys = sorted(self._children.get(session_key, set()))
        return [self._nodes[item] for item in child_keys if item in self._nodes]

    def chain_to_root(self, session_key: str) -> list[SessionLineageNode]:
        if session_key not in self._nodes:
            return []
        chain: list[SessionLineageNode] = []
        current = self._nodes[session_key]
        seen: set[str] = set()
        while True:
            if current.session_key in seen:
                raise ValueError(f"lineage cycle detected at {current.session_key}")
            seen.add(current.session_key)
            chain.append(current)
            if current.parent_session_key is None:
                break
            parent = self._nodes.get(current.parent_session_key)
            if parent is None:
                break
            current = parent
        return chain

    def all_nodes(self) -> list[SessionLineageNode]:
        return [self._nodes[key] for key in sorted(self._nodes)]

    def _creates_cycle(self, parent: str, child: str) -> bool:
        if child not in self._nodes:
            return False
        current = self._nodes.get(parent)
        seen: set[str] = set()
        while current is not None:
            if current.session_key in seen:
                return True
            seen.add(current.session_key)
            if current.session_key == child:
                return True
            if current.parent_session_key is None:
                return False
            current = self._nodes.get(current.parent_session_key)
        return False
