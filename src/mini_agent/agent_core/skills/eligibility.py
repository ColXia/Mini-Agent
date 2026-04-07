"""Skill eligibility checks for agent-core skill loading."""

from __future__ import annotations

from dataclasses import dataclass, field
import platform
import shutil
from typing import Any


@dataclass(frozen=True)
class SkillRequirements:
    """Normalized requirements declared in SKILL.md frontmatter."""

    os_names: tuple[str, ...] = ()
    bins: tuple[str, ...] = ()
    env_vars: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkillEligibilityResult:
    """Eligibility report for a skill on the current runtime."""

    eligible: bool
    missing_bins: tuple[str, ...] = ()
    missing_env_vars: tuple[str, ...] = ()
    os_mismatch: bool = False
    current_os: str = ""

    def blocked_reason(self) -> str | None:
        reasons: list[str] = []
        if self.os_mismatch:
            reasons.append(f"os_mismatch({self.current_os})")
        if self.missing_bins:
            reasons.append(f"missing_bins({', '.join(self.missing_bins)})")
        if self.missing_env_vars:
            reasons.append(f"missing_env({', '.join(self.missing_env_vars)})")
        if not reasons:
            return None
        return "; ".join(reasons)


def _normalize_str_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [item.strip() for item in value.split(",")]
    if not isinstance(value, list):
        return ()
    normalized = [str(item).strip() for item in value if str(item).strip()]
    return tuple(normalized)


def parse_skill_requirements(frontmatter: dict[str, Any] | None) -> SkillRequirements:
    """Parse requirements from SKILL.md frontmatter."""
    frontmatter = frontmatter or {}
    requires = frontmatter.get("requires")
    if not isinstance(requires, dict):
        return SkillRequirements()

    os_names = tuple(item.lower() for item in _normalize_str_list(requires.get("os")))
    bins = _normalize_str_list(requires.get("bins"))
    env_vars = _normalize_str_list(requires.get("env"))
    return SkillRequirements(os_names=os_names, bins=bins, env_vars=env_vars)


class SkillEligibilityChecker:
    """Evaluate SKILL.md requirement eligibility against local runtime."""

    def __init__(self, *, environment: dict[str, str] | None = None):
        self.environment = environment

    def check(self, requirements: SkillRequirements) -> SkillEligibilityResult:
        current_os = platform.system().strip().lower()

        os_mismatch = False
        if requirements.os_names:
            os_mismatch = current_os not in {name.lower() for name in requirements.os_names}

        missing_bins = tuple(sorted(item for item in requirements.bins if shutil.which(item) is None))
        env = self.environment if self.environment is not None else __import__("os").environ
        missing_env = tuple(sorted(item for item in requirements.env_vars if not env.get(item)))

        eligible = not os_mismatch and not missing_bins and not missing_env
        return SkillEligibilityResult(
            eligible=eligible,
            missing_bins=missing_bins,
            missing_env_vars=missing_env,
            os_mismatch=os_mismatch,
            current_os=current_os,
        )
