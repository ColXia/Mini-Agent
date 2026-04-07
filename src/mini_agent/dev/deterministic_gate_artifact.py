"""Deterministic release-gate artifact discovery and validation helpers."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DeterministicGateArtifactStatus:
    """Validation result for deterministic gate artifact checks."""

    pattern: str
    matched_count: int
    latest_artifact: str | None
    latest_pass: bool

    @property
    def ok(self) -> bool:
        return self.matched_count > 0 and self.latest_pass


def list_gate_artifacts(*, repo_root: Path, pattern: str) -> list[Path]:
    """Resolve and sort matching artifacts by mtime (oldest -> newest)."""

    root = repo_root.resolve()
    matches = sorted(
        (path.resolve() for path in root.glob(pattern) if path.is_file()),
        key=lambda item: item.stat().st_mtime,
    )
    return matches


def report_has_pass_status(path: Path) -> bool:
    """Return True when release-gate report clearly marks Overall PASS."""

    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return False
    normalized = text.replace("\r\n", "\n")
    return "- Overall: PASS" in normalized or "Overall: PASS" in normalized


def validate_deterministic_gate_artifact(
    *,
    repo_root: Path,
    pattern: str = "workspace/release_gate/release_gate_deterministic_*.md",
) -> DeterministicGateArtifactStatus:
    """Validate deterministic gate artifact presence and PASS outcome."""

    artifacts = list_gate_artifacts(repo_root=repo_root, pattern=pattern)
    if not artifacts:
        return DeterministicGateArtifactStatus(
            pattern=pattern,
            matched_count=0,
            latest_artifact=None,
            latest_pass=False,
        )
    latest = artifacts[-1]
    return DeterministicGateArtifactStatus(
        pattern=pattern,
        matched_count=len(artifacts),
        latest_artifact=str(latest),
        latest_pass=report_has_pass_status(latest),
    )

