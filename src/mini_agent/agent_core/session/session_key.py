"""Session-key model and lookup helpers for agent-core."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib


class SessionKeyError(ValueError):
    """Base session-key parsing error."""


class AmbiguousSessionKeyError(SessionKeyError):
    """Raised when a partial key matches multiple sessions."""


@dataclass(frozen=True)
class AgentSessionKey:
    """Canonical agent-core session key."""

    agent_id: str
    channel: str
    peer_kind: str
    peer_id: str
    thread_id: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("agent_id", "channel", "peer_kind", "peer_id"):
            value = getattr(self, field_name)
            if not str(value).strip():
                raise SessionKeyError(f"{field_name} must not be empty.")

    def base_key(self) -> str:
        return f"agent:{self.agent_id}:{self.channel}:{self.peer_kind}:{self.peer_id}"

    def to_key(self) -> str:
        if self.thread_id:
            return f"{self.base_key()}:thread:{self.thread_id}"
        return self.base_key()

    def with_thread(self, thread_id: str) -> "AgentSessionKey":
        normalized = thread_id.strip()
        if not normalized:
            raise SessionKeyError("thread_id must not be empty.")
        return AgentSessionKey(
            agent_id=self.agent_id,
            channel=self.channel,
            peer_kind=self.peer_kind,
            peer_id=self.peer_id,
            thread_id=normalized,
        )

    def slug(self, *, length: int = 10) -> str:
        length = max(6, min(int(length), 32))
        digest = hashlib.sha256(self.to_key().encode("utf-8")).hexdigest()
        return digest[:length]

    @staticmethod
    def parse(raw: str) -> "AgentSessionKey":
        text = raw.strip()
        if not text:
            raise SessionKeyError("session key must not be empty.")

        parts = text.split(":")
        if len(parts) < 5 or parts[0] != "agent":
            raise SessionKeyError("invalid session key format.")

        agent_id, channel, peer_kind, peer_id = parts[1], parts[2], parts[3], parts[4]
        thread_id: str | None = None
        if len(parts) > 5:
            if len(parts) != 7 or parts[5] != "thread":
                raise SessionKeyError("invalid threaded session key format.")
            thread_id = parts[6]

        return AgentSessionKey(
            agent_id=agent_id,
            channel=channel,
            peer_kind=peer_kind,
            peer_id=peer_id,
            thread_id=thread_id,
        )


class SessionKeyIndex:
    """Index for full/partial/slug session-key lookup."""

    def __init__(self) -> None:
        self._keys: dict[str, AgentSessionKey] = {}

    def add(self, key: AgentSessionKey) -> None:
        self._keys[key.to_key()] = key

    def remove(self, raw_key: str) -> bool:
        return self._keys.pop(raw_key, None) is not None

    def list(self) -> tuple[AgentSessionKey, ...]:
        return tuple(self._keys.values())

    def _matches(self, query: str) -> list[AgentSessionKey]:
        query = query.strip()
        if not query:
            return []
        if query in self._keys:
            return [self._keys[query]]

        matched: list[AgentSessionKey] = []
        for key in self._keys.values():
            full = key.to_key()
            if full.startswith(query) or query in full:
                matched.append(key)
                continue
            if key.slug() == query:
                matched.append(key)
                continue
            if key.peer_id == query:
                matched.append(key)
        return matched

    def resolve(self, query: str) -> AgentSessionKey:
        matches = self._matches(query)
        if not matches:
            raise SessionKeyError(f"session key not found: {query}")
        if len(matches) > 1:
            samples = ", ".join(item.to_key() for item in matches[:3])
            raise AmbiguousSessionKeyError(
                f"session key query '{query}' is ambiguous ({len(matches)} matches): {samples}"
            )
        return matches[0]
