"""Pending-approval state normalization and mutations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from fastapi import HTTPException

from .run_control_store import RuntimeSessionRunControlStore

if TYPE_CHECKING:
    import asyncio

    from mini_agent.session.store_records import MainAgentSessionState


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


@dataclass(slots=True)
class RuntimeSessionPendingApprovalStateHandler:
    run_control_store: RuntimeSessionRunControlStore | None = None

    @staticmethod
    def normalize_pending_approval(item: Any) -> dict[str, Any] | None:
        if not isinstance(item, dict):
            return None
        token = _safe_text(item.get("token"))
        tool_name = _safe_text(item.get("tool_name")) or "tool"
        if not token:
            return None
        return {
            "token": token,
            "tool_name": tool_name,
            "arguments": dict(item.get("arguments")) if isinstance(item.get("arguments"), dict) else {},
            "kind": _safe_text(item.get("kind")) or None,
            "reason": _safe_text(item.get("reason")) or None,
            "cache_key": _safe_text(item.get("cache_key")) or None,
            "can_escalate": bool(item.get("can_escalate", False)),
            "step": max(0, int(item.get("step") or 0)),
        }

    @classmethod
    def pending_approvals_from_raw(cls, raw_items: Any) -> list[dict[str, Any]]:
        if not isinstance(raw_items, list):
            return []
        approvals: list[dict[str, Any]] = []
        for item in raw_items:
            normalized = cls.normalize_pending_approval(item)
            if normalized is not None:
                approvals.append(normalized)
        return approvals

    def record_pending_approval(
        self,
        session: "MainAgentSessionState",
        *,
        payload: dict[str, Any],
        future: "asyncio.Future[bool | None]",
        now_utc: datetime | None = None,
    ) -> dict[str, Any]:
        normalized = self.normalize_pending_approval(payload)
        if normalized is None:
            raise HTTPException(status_code=400, detail="Invalid pending approval payload.")
        self._store().replace_active_approval_wait(
            session,
            payload=normalized,
            future=future,
        )
        session.touch(now_utc=now_utc)
        return dict(normalized)

    def clear_pending_approval(
        self,
        session: "MainAgentSessionState",
        *,
        token: str | None = None,
        now_utc: datetime | None = None,
    ) -> None:
        self._store().clear_pending_approval(
            session,
            token=token,
        )
        session.touch(now_utc=now_utc)

    def _store(self) -> RuntimeSessionRunControlStore:
        if self.run_control_store is None:
            self.run_control_store = RuntimeSessionRunControlStore()
        return self.run_control_store


__all__ = ["RuntimeSessionPendingApprovalStateHandler"]

