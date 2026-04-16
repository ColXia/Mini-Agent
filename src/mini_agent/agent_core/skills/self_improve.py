"""Self-improving skill primitives within the agent-core skills domain."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


@dataclass(frozen=True)
class SkillEvolutionRecord:
    """Record of a skill evolution event."""

    skill_name: str
    version: str
    evolution_type: str  # "created", "refined", "merged", "deprecated"
    timestamp: str
    changes: str
    metrics: dict[str, float] = field(default_factory=dict)


@dataclass
class SkillPerformanceMetrics:
    """Performance metrics for a skill."""

    total_invocations: int = 0
    successful_invocations: int = 0
    failed_invocations: int = 0
    total_latency_ms: float = 0.0
    user_satisfaction_score: float = 0.0
    last_invocation_at: datetime | None = None

    @property
    def success_rate(self) -> float:
        if self.total_invocations == 0:
            return 0.0
        return self.successful_invocations / self.total_invocations

    @property
    def avg_latency_ms(self) -> float:
        if self.total_invocations == 0:
            return 0.0
        return self.total_latency_ms / self.total_invocations


class SelfImprovingSkillEngine:
    """Engine for skill self-improvement and evolution."""

    def __init__(
        self,
        skills_dir: Path,
        *,
        min_invocations_for_refinement: int = 10,
        min_success_rate_threshold: float = 0.7,
        evolution_history_file: str = "skill_evolution_history.json",
    ) -> None:
        self.skills_dir = Path(skills_dir).expanduser().resolve()
        self.skills_dir.mkdir(parents=True, exist_ok=True)

        self.min_invocations_for_refinement = max(1, int(min_invocations_for_refinement))
        self.min_success_rate_threshold = max(0.0, min(1.0, float(min_success_rate_threshold)))

        self._metrics: dict[str, SkillPerformanceMetrics] = {}
        self._history: list[SkillEvolutionRecord] = []
        self._history_file = self.skills_dir / evolution_history_file

        self._load_history()

    def _load_history(self) -> None:
        """Load evolution history from disk."""
        if not self._history_file.exists():
            return
        try:
            with self._history_file.open("r", encoding="utf-8") as f:
                data = json.load(f)
            for item in data:
                self._history.append(SkillEvolutionRecord(
                    skill_name=item.get("skill_name", ""),
                    version=item.get("version", "1.0.0"),
                    evolution_type=item.get("evolution_type", "created"),
                    timestamp=item.get("timestamp", ""),
                    changes=item.get("changes", ""),
                    metrics=item.get("metrics", {}),
                ))
        except Exception:
            pass

    def _save_history(self) -> None:
        """Save evolution history to disk."""
        try:
            data = [
                {
                    "skill_name": r.skill_name,
                    "version": r.version,
                    "evolution_type": r.evolution_type,
                    "timestamp": r.timestamp,
                    "changes": r.changes,
                    "metrics": r.metrics,
                }
                for r in self._history
            ]
            with self._history_file.open("w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception:
            pass

    def record_invocation(
        self,
        skill_name: str,
        *,
        success: bool,
        latency_ms: float,
        user_satisfaction: float | None = None,
    ) -> None:
        """Record a skill invocation for performance tracking."""
        if skill_name not in self._metrics:
            self._metrics[skill_name] = SkillPerformanceMetrics()

        metrics = self._metrics[skill_name]
        metrics.total_invocations += 1
        metrics.total_latency_ms += latency_ms
        metrics.last_invocation_at = _utc_now()

        if success:
            metrics.successful_invocations += 1
        else:
            metrics.failed_invocations += 1

        if user_satisfaction is not None:
            # Running average of satisfaction
            current = metrics.user_satisfaction_score
            count = metrics.total_invocations
            metrics.user_satisfaction_score = (current * (count - 1) + user_satisfaction) / count

    def get_metrics(self, skill_name: str) -> SkillPerformanceMetrics:
        """Get performance metrics for a skill."""
        return self._metrics.get(skill_name, SkillPerformanceMetrics())

    def analyze_skill_health(self, skill_name: str) -> dict[str, Any]:
        """Analyze skill health and suggest improvements."""
        metrics = self.get_metrics(skill_name)

        health_status = "healthy"
        issues: list[str] = []
        suggestions: list[str] = []

        # Check invocation count
        if metrics.total_invocations < self.min_invocations_for_refinement:
            health_status = "insufficient_data"
            issues.append(f"Only {metrics.total_invocations} invocations recorded")
            suggestions.append("Collect more usage data before analysis")
            return {
                "skill_name": skill_name,
                "health_status": health_status,
                "issues": issues,
                "suggestions": suggestions,
                "metrics": {
                    "total_invocations": metrics.total_invocations,
                    "success_rate": metrics.success_rate,
                    "avg_latency_ms": metrics.avg_latency_ms,
                    "user_satisfaction": metrics.user_satisfaction_score,
                },
            }

        # Check success rate
        if metrics.success_rate < self.min_success_rate_threshold:
            health_status = "degraded"
            issues.append(f"Low success rate: {metrics.success_rate:.1%}")
            suggestions.append("Review skill prompts and error handling")

        # Check latency
        if metrics.avg_latency_ms > 5000:
            if health_status == "healthy":
                health_status = "slow"
            issues.append(f"High average latency: {metrics.avg_latency_ms:.0f}ms")
            suggestions.append("Optimize skill execution paths")

        # Check user satisfaction
        if metrics.user_satisfaction_score < 0.6 and metrics.total_invocations >= 5:
            if health_status == "healthy":
                health_status = "unsatisfactory"
            issues.append(f"Low user satisfaction: {metrics.user_satisfaction_score:.1%}")
            suggestions.append("Collect user feedback and refine skill behavior")

        return {
            "skill_name": skill_name,
            "health_status": health_status,
            "issues": issues,
            "suggestions": suggestions,
            "metrics": {
                "total_invocations": metrics.total_invocations,
                "success_rate": metrics.success_rate,
                "avg_latency_ms": metrics.avg_latency_ms,
                "user_satisfaction": metrics.user_satisfaction_score,
            },
        }

    def suggest_skill_refinement(self, skill_name: str, skill_content: str) -> dict[str, Any]:
        """Suggest refinements for a skill based on performance and content analysis."""
        health = self.analyze_skill_health(skill_name)
        suggestions: list[str] = health.get("suggestions", [])

        # Analyze skill content
        content_issues: list[str] = []

        # Check for missing sections
        required_sections = ["## Description", "## Usage", "## Examples"]
        for section in required_sections:
            if section not in skill_content:
                content_issues.append(f"Missing section: {section}")
                suggestions.append(f"Add {section} section to skill documentation")

        # Check for placeholder content
        placeholder_patterns = [
            r"\[TODO\]",
            r"\[TBD\]",
            r"\.\.\.",
            r"<.*?>",
        ]
        for pattern in placeholder_patterns:
            if re.search(pattern, skill_content, re.IGNORECASE):
                content_issues.append("Contains placeholder content")
                suggestions.append("Replace placeholder content with actual implementation")
                break

        # Check for error handling
        if "error" not in skill_content.lower() and "exception" not in skill_content.lower():
            content_issues.append("Missing error handling guidance")
            suggestions.append("Add error handling examples")

        return {
            "skill_name": skill_name,
            "health": health,
            "content_issues": content_issues,
            "refinement_suggestions": suggestions,
            "priority": "high" if health["health_status"] in ("degraded", "unsatisfactory") else "medium",
        }

    def record_evolution(
        self,
        skill_name: str,
        version: str,
        evolution_type: str,
        changes: str,
        metrics: dict[str, float] | None = None,
    ) -> SkillEvolutionRecord:
        """Record a skill evolution event."""
        record = SkillEvolutionRecord(
            skill_name=skill_name,
            version=version,
            evolution_type=evolution_type,
            timestamp=_utc_iso(_utc_now()) or "",
            changes=changes,
            metrics=metrics or {},
        )
        self._history.append(record)
        self._save_history()
        return record

    def get_evolution_history(self, skill_name: str | None = None) -> list[SkillEvolutionRecord]:
        """Get evolution history, optionally filtered by skill name."""
        if skill_name is None:
            return list(self._history)
        return [r for r in self._history if r.skill_name == skill_name]

    async def run_health_check(self, skill_names: list[str] | None = None) -> dict[str, Any]:
        """Run health check on specified skills or all tracked skills."""
        names = skill_names or list(self._metrics.keys())
        results: dict[str, Any] = {}

        for name in names:
            results[name] = self.analyze_skill_health(name)

        # Summary
        healthy_count = sum(1 for r in results.values() if r["health_status"] == "healthy")
        total_count = len(results)

        return {
            "summary": {
                "total_skills": total_count,
                "healthy": healthy_count,
                "needs_attention": total_count - healthy_count,
            },
            "details": results,
        }
