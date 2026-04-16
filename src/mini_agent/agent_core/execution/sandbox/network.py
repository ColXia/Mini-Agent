"""Network policy primitives for agent-core execution sandbox enforcement."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import re
from urllib.parse import urlsplit


_DOMAIN_PATTERN = re.compile(
    r"\b(?:https?://)?([A-Za-z0-9](?:[A-Za-z0-9-]{0,62}[A-Za-z0-9])?(?:\.[A-Za-z0-9-]{1,63})+)(?::\d+)?\b",
    re.IGNORECASE,
)


def _normalize_domain(value: str) -> str:
    raw = value.strip().lower()
    if not raw:
        return ""
    if "://" in raw:
        parsed = urlsplit(raw)
        raw = parsed.hostname or ""
    if "/" in raw:
        raw = raw.split("/", 1)[0]
    if ":" in raw:
        raw = raw.split(":", 1)[0]
    return raw.strip(".")


class NetworkAccessMode(str, Enum):
    """Network policy mode."""

    ALLOW_ALL = "allow_all"
    DENY_ALL = "deny_all"
    ALLOWLIST = "allowlist"
    BLOCKLIST = "blocklist"


def extract_domains_from_command(command: str) -> list[str]:
    """Best-effort domain extraction for command-level network checks."""
    found: set[str] = set()
    for matched in _DOMAIN_PATTERN.findall(command or ""):
        normalized = _normalize_domain(matched)
        if normalized:
            found.add(normalized)
    return sorted(found)


@dataclass(frozen=True)
class NetworkDomainPolicy:
    """Simple domain policy for command-time validation."""

    mode: NetworkAccessMode = NetworkAccessMode.ALLOW_ALL
    allow_domains: tuple[str, ...] = field(default_factory=tuple)
    block_domains: tuple[str, ...] = field(default_factory=tuple)

    def normalized(self) -> "NetworkDomainPolicy":
        allow = sorted(
            {
                item
                for item in (_normalize_domain(value) for value in self.allow_domains)
                if item
            }
        )
        blocked = sorted(
            {
                item
                for item in (_normalize_domain(value) for value in self.block_domains)
                if item
            }
        )
        return NetworkDomainPolicy(
            mode=self.mode,
            allow_domains=tuple(allow),
            block_domains=tuple(blocked),
        )

    def _matches(self, domain: str, rule: str) -> bool:
        return domain == rule or domain.endswith(f".{rule}")

    def allows(self, domain: str) -> bool:
        normalized = _normalize_domain(domain)
        if not normalized:
            return True
        policy = self.normalized()

        if policy.mode == NetworkAccessMode.ALLOW_ALL:
            return True
        if policy.mode == NetworkAccessMode.DENY_ALL:
            return False
        if policy.mode == NetworkAccessMode.ALLOWLIST:
            if not policy.allow_domains:
                return False
            return any(policy._matches(normalized, rule) for rule in policy.allow_domains)
        if policy.mode == NetworkAccessMode.BLOCKLIST:
            return not any(policy._matches(normalized, rule) for rule in policy.block_domains)
        return True

    def validate_domains(self, domains: list[str]) -> tuple[bool, list[str]]:
        blocked = [domain for domain in domains if not self.allows(domain)]
        return (len(blocked) == 0, blocked)

    def validate_command(self, command: str) -> tuple[bool, list[str]]:
        return self.validate_domains(extract_domains_from_command(command))
