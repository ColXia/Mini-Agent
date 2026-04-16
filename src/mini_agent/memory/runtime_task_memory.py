"""Conservative post-turn runtime task-memory writeback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from mini_agent.memory.knowledge_base_grounding import extract_knowledge_base_grounding_from_turn_messages
from mini_agent.memory.quality import clean_memory_text, is_low_signal_control_turn
from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime
from mini_agent.memory.promotion import evaluate_workspace_shared_runtime_promotion


def _clean_text(value: Any) -> str:
    return clean_memory_text(value)


@dataclass(frozen=True)
class TurnRuntimeTaskMemoryResult:
    enabled: bool
    skipped_reason: str
    stored: bool
    duplicate: bool
    namespace: str | None
    engram_id: str | None
    content: str
    workspace_shared_candidate: bool
    workspace_shared_candidate_reason: str
    workspace_shared_candidate_text: str
    knowledge_base_grounded: bool
    knowledge_base_query: str
    knowledge_base_id: str
    knowledge_base_hits: int
    knowledge_base_refs: list[str]

    def to_payload(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "skipped_reason": self.skipped_reason,
            "stored": self.stored,
            "duplicate": self.duplicate,
            "namespace": self.namespace,
            "engram_id": self.engram_id,
            "content": self.content,
            "workspace_shared_candidate": self.workspace_shared_candidate,
            "workspace_shared_candidate_reason": self.workspace_shared_candidate_reason,
            "workspace_shared_candidate_text": self.workspace_shared_candidate_text,
            "knowledge_base_grounded": self.knowledge_base_grounded,
            "knowledge_base_query": self.knowledge_base_query,
            "knowledge_base_id": self.knowledge_base_id,
            "knowledge_base_hits": self.knowledge_base_hits,
            "knowledge_base_refs": list(self.knowledge_base_refs),
        }


class TurnRuntimeTaskMemory:
    """Persist one compact per-turn runtime summary into session task memory."""

    def __init__(
        self,
        workspace_dir: str,
        *,
        state_root: str | None = None,
        enabled: bool = True,
        max_part_chars: int = 180,
    ) -> None:
        self.enabled = bool(enabled)
        self.max_part_chars = max(60, int(max_part_chars))
        self.runtime = WorkspaceMemoriaRuntime(workspace_dir, state_root=state_root)

    def process_turn(
        self,
        *,
        stop_reason: str,
        turn_messages: list[Any],
        turn_context: Any | None = None,
        assistant_message: str = "",
    ) -> TurnRuntimeTaskMemoryResult:
        if not self.enabled:
            return self._result(skipped_reason="disabled")
        if _clean_text(stop_reason).lower() != "end_turn":
            return self._result(skipped_reason="turn_not_completed")

        session_id = self._resolve_session_id(turn_context)
        if not session_id:
            return self._result(skipped_reason="missing_session_id")

        user_message = self._last_message_text(turn_messages, role="user")
        assistant_text = _clean_text(assistant_message) or self._last_message_text(turn_messages, role="assistant")
        if not user_message or not assistant_text:
            return self._result(skipped_reason="missing_turn_messages")

        tool_count = len(self._tool_names(turn_messages))
        if is_low_signal_control_turn(
            user_message=user_message,
            assistant_message=assistant_text,
            tool_count=tool_count,
        ):
            return self._result(skipped_reason="low_signal_control_turn")
        content = self._build_summary(
            user_message=user_message,
            assistant_message=assistant_text,
            tool_count=tool_count,
        )
        kb_grounding = extract_knowledge_base_grounding_from_turn_messages(turn_messages)
        shared_candidate = evaluate_workspace_shared_runtime_promotion(assistant_text)
        saved = self.runtime.save_session_memory(
            session_id,
            content=content,
            importance=0.75 if tool_count > 0 else 0.6,
            metadata={
                "kind": "turn_summary",
                "session_id": session_id,
                "workspace_shared_candidate": bool(shared_candidate.allowed),
                "workspace_shared_candidate_reason": shared_candidate.reason,
                "workspace_shared_candidate_text": shared_candidate.normalized_text,
                "knowledge_base_used": bool(kb_grounding.get("used")),
                "knowledge_base_grounded": bool(kb_grounding.get("grounded")),
                "knowledge_base_query": _clean_text(kb_grounding.get("query")),
                "knowledge_base_id": _clean_text(kb_grounding.get("knowledge_base_id")),
                "knowledge_base_hits": max(0, int(kb_grounding.get("hits") or 0)),
                "knowledge_base_refs": list(kb_grounding.get("refs") or []),
            },
        )
        return TurnRuntimeTaskMemoryResult(
            enabled=True,
            skipped_reason="",
            stored=bool(saved.get("stored")),
            duplicate=bool(saved.get("duplicate")),
            namespace=str(saved.get("namespace") or ""),
            engram_id=str(saved.get("engram_id") or "") or None,
            content=content,
            workspace_shared_candidate=bool(shared_candidate.allowed),
            workspace_shared_candidate_reason=shared_candidate.reason,
            workspace_shared_candidate_text=shared_candidate.normalized_text,
            knowledge_base_grounded=bool(kb_grounding.get("grounded")),
            knowledge_base_query=_clean_text(kb_grounding.get("query")),
            knowledge_base_id=_clean_text(kb_grounding.get("knowledge_base_id")),
            knowledge_base_hits=max(0, int(kb_grounding.get("hits") or 0)),
            knowledge_base_refs=list(kb_grounding.get("refs") or []),
        )

    def _result(self, *, skipped_reason: str) -> TurnRuntimeTaskMemoryResult:
        return TurnRuntimeTaskMemoryResult(
            enabled=self.enabled,
            skipped_reason=skipped_reason,
            stored=False,
            duplicate=False,
            namespace=None,
            engram_id=None,
            content="",
            workspace_shared_candidate=False,
            workspace_shared_candidate_reason="",
            workspace_shared_candidate_text="",
            knowledge_base_grounded=False,
            knowledge_base_query="",
            knowledge_base_id="",
            knowledge_base_hits=0,
            knowledge_base_refs=[],
        )

    def _build_summary(
        self,
        *,
        user_message: str,
        assistant_message: str,
        tool_count: int,
    ) -> str:
        user_part = self._truncate(user_message)
        assistant_part = self._truncate(assistant_message)
        tool_suffix = f" | tools={tool_count}" if tool_count > 0 else ""
        return f"task: {user_part} | latest: {assistant_part}{tool_suffix}".strip()

    @staticmethod
    def _resolve_session_id(turn_context: Any | None) -> str:
        if isinstance(turn_context, dict):
            return _clean_text(turn_context.get("session_id"))
        return _clean_text(getattr(turn_context, "session_id", ""))

    @staticmethod
    def _last_message_text(turn_messages: list[Any], *, role: str) -> str:
        normalized_role = _clean_text(role).lower()
        for message in reversed(turn_messages):
            if _clean_text(getattr(message, "role", "")).lower() != normalized_role:
                continue
            content = getattr(message, "content", "")
            if isinstance(content, list):
                content = " ".join(str(item) for item in content)
            text = _clean_text(content)
            if text:
                return text
        return ""

    @staticmethod
    def _tool_names(turn_messages: list[Any]) -> set[str]:
        names: set[str] = set()
        for message in turn_messages:
            if _clean_text(getattr(message, "role", "")).lower() == "tool":
                tool_name = _clean_text(getattr(message, "name", "")).lower()
                if tool_name:
                    names.add(tool_name)
        return names

    def _truncate(self, value: str) -> str:
        text = _clean_text(value)
        if len(text) <= self.max_part_chars:
            return text
        return f"{text[: max(0, self.max_part_chars - 3)]}..."


__all__ = [
    "TurnRuntimeTaskMemory",
    "TurnRuntimeTaskMemoryResult",
]
