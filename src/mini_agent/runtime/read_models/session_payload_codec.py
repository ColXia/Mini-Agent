"""Runtime session payload/message/token normalization helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Sequence

from mini_agent.agent_core.context.context_compaction import estimate_tokens
from mini_agent.agent_core.engine import Agent
from mini_agent.agent_core.context.turn_context import resolve_turn_context_policy
from mini_agent.runtime.support.sandbox_state import normalize_sandbox_diagnostics
from mini_agent.schema import Message

if TYPE_CHECKING:
    from mini_agent.runtime.session_state import MainAgentSessionState


class RuntimeSessionPayloadCodec:
    """Own payload normalization, message serialization, and token-state helpers."""

    @staticmethod
    def normalize_mapping_payload(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def normalize_context_policy_payload(value: Any) -> dict[str, Any]:
        return resolve_turn_context_policy(value or {})

    @classmethod
    def normalize_prepared_context_payload(cls, value: Any) -> dict[str, Any]:
        return cls.normalize_mapping_payload(value)

    @classmethod
    def normalize_prepared_context_diagnostics_payload(cls, value: Any) -> dict[str, Any]:
        return cls.normalize_mapping_payload(value)

    @classmethod
    def normalize_memory_diagnostics_payload(cls, value: Any) -> dict[str, Any]:
        return cls.normalize_mapping_payload(value)

    @staticmethod
    def normalize_sandbox_diagnostics_payload(value: Any) -> dict[str, Any]:
        return normalize_sandbox_diagnostics(value)

    @staticmethod
    def serialize_agent_messages(messages: Sequence[Any]) -> list[dict[str, Any]]:
        serialized: list[dict[str, Any]] = []
        for item in messages or []:
            if hasattr(item, "model_dump"):
                payload = item.model_dump()
            elif isinstance(item, dict):
                payload = dict(item)
            elif hasattr(item, "__dict__"):
                payload = dict(vars(item))
            else:
                payload = {"role": "assistant", "content": str(item)}
            serialized.append(
                {
                    "role": payload.get("role", "assistant"),
                    "content": payload.get("content", ""),
                    "thinking": payload.get("thinking"),
                    "tool_calls": payload.get("tool_calls"),
                    "tool_call_id": payload.get("tool_call_id"),
                    "name": payload.get("name"),
                }
            )
        return serialized

    @staticmethod
    def agent_messages(agent: Any | None) -> list[Any]:
        messages = getattr(agent, "messages", None)
        return list(messages) if isinstance(messages, list) else []

    @classmethod
    def serialize_live_agent_messages(cls, agent: Any | None) -> list[dict[str, Any]]:
        return cls.serialize_agent_messages(cls.agent_messages(agent))

    @classmethod
    def agent_message_count(cls, agent: Any | None) -> int:
        return len(cls.agent_messages(agent))

    @staticmethod
    def restore_agent_messages_payload(
        raw_messages: Sequence[Any],
        agent: Agent,
    ) -> None:
        restored: list[Message] = []
        for raw in raw_messages or []:
            if not isinstance(raw, dict):
                continue
            try:
                restored.append(Message.model_validate(raw))
            except Exception:
                continue
        if not restored:
            return
        if restored[0].role != "system":
            base_messages = getattr(agent, "messages", None)
            if isinstance(base_messages, list) and base_messages:
                try:
                    base_system = base_messages[0]
                    if hasattr(base_system, "model_dump"):
                        restored.insert(0, Message.model_validate(base_system.model_dump()))
                    elif isinstance(base_system, dict):
                        restored.insert(0, Message.model_validate(base_system))
                    else:
                        restored.insert(
                            0,
                            Message(
                                role=str(getattr(base_system, "role", "system") or "system"),
                                content=str(getattr(base_system, "content", "")),
                            ),
                        )
                except Exception:
                    pass
        agent.messages = restored

    @staticmethod
    def normalize_nonnegative_int(value: Any, *, default: int = 0) -> int:
        try:
            parsed = int(value or 0)
        except Exception:
            return max(0, int(default))
        return max(0, parsed)

    @classmethod
    def estimate_raw_message_tokens(cls, raw_messages: Sequence[Any] | None) -> int:
        restored: list[Message] = []
        for raw in raw_messages or []:
            if not isinstance(raw, dict):
                continue
            try:
                restored.append(Message.model_validate(raw))
            except Exception:
                continue
        if not restored:
            return 0
        try:
            return cls.normalize_nonnegative_int(estimate_tokens(restored))
        except Exception:
            return 0

    @classmethod
    def agent_token_usage(cls, agent: Any | None) -> int:
        live = cls.normalize_nonnegative_int(getattr(agent, "api_total_tokens", 0))
        if live > 0:
            return live
        messages = cls.agent_messages(agent)
        if not messages:
            return 0
        try:
            return cls.normalize_nonnegative_int(estimate_tokens(messages))
        except Exception:
            return 0

    @classmethod
    def agent_token_limit(cls, agent: Any | None) -> int:
        return cls.normalize_nonnegative_int(getattr(agent, "token_limit", 0))

    @classmethod
    def agent_last_prepared_context(cls, agent: Any | None) -> dict[str, Any]:
        return cls.normalize_prepared_context_payload(getattr(agent, "last_prepared_turn_context", None))

    @classmethod
    def agent_prepared_context_diagnostics(cls, agent: Any | None) -> dict[str, Any]:
        return cls.normalize_prepared_context_diagnostics_payload(
            getattr(agent, "prepared_context_diagnostics", None)
        )

    @classmethod
    def agent_last_memory_automation(cls, agent: Any | None) -> dict[str, Any]:
        return cls.normalize_mapping_payload(getattr(agent, "last_memory_automation", None))

    @classmethod
    def agent_last_runtime_task_memory(cls, agent: Any | None) -> dict[str, Any]:
        return cls.normalize_mapping_payload(getattr(agent, "last_runtime_task_memory", None))

    @classmethod
    def session_token_usage(cls, session: "MainAgentSessionState") -> int:
        return cls.agent_token_usage(session.runtime.agent)

    @classmethod
    def session_token_limit(cls, session: "MainAgentSessionState") -> int:
        return cls.agent_token_limit(session.runtime.agent)

    @classmethod
    def record_token_usage(cls, record: dict[str, Any]) -> int:
        explicit = cls.normalize_nonnegative_int(record.get("token_usage"))
        if explicit > 0:
            return explicit
        raw_messages = record.get("messages")
        if isinstance(raw_messages, list):
            return cls.estimate_raw_message_tokens(raw_messages)
        return 0

    @classmethod
    def record_token_limit(cls, record: dict[str, Any]) -> int:
        return cls.normalize_nonnegative_int(record.get("token_limit"))

    @classmethod
    def restore_agent_token_state(
        cls,
        agent: Agent,
        *,
        token_usage: Any = None,
        token_limit: Any = None,
        raw_messages: Sequence[Any] | None = None,
    ) -> None:
        usage = cls.normalize_nonnegative_int(token_usage)
        if usage <= 0:
            usage = cls.estimate_raw_message_tokens(raw_messages)
        if hasattr(agent, "api_total_tokens"):
            agent.api_total_tokens = usage

        limit = cls.normalize_nonnegative_int(token_limit)
        if limit > 0:
            setattr(agent, "token_limit", limit)


__all__ = ["RuntimeSessionPayloadCodec"]
