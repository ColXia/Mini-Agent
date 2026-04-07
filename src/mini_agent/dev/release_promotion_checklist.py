"""Release promotion checklist policy and report rendering utilities."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


_VALID_STATUSES = {"PASS", "FAIL", "WARN", "SKIP"}


@dataclass(frozen=True)
class PromotionChecklistItem:
    """One promotion checklist item and its evaluation result."""

    name: str
    mandatory: bool
    status: str
    note: str = ""
    report_file: str | None = None
    command: str | None = None
    duration_seconds: float | None = None

    def __post_init__(self) -> None:
        normalized = self.status.strip().upper()
        if normalized not in _VALID_STATUSES:
            raise ValueError(f"invalid checklist status: {self.status}")
        object.__setattr__(self, "status", normalized)


def is_promotion_ready(items: list[PromotionChecklistItem]) -> bool:
    """Return True when all mandatory checklist items are PASS."""

    for item in items:
        if item.mandatory and item.status != "PASS":
            return False
    return True


def collect_advisories(items: list[PromotionChecklistItem]) -> list[str]:
    """Collect advisory messages for non-mandatory WARN/FAIL/SKIP items."""

    warnings: list[str] = []
    for item in items:
        if item.mandatory:
            continue
        if item.status in {"WARN", "FAIL", "SKIP"}:
            note = item.note.strip() or "no additional note"
            warnings.append(f"{item.name}: {item.status} ({note})")
    return warnings


def build_promotion_report(
    *,
    started_at: datetime,
    ended_at: datetime,
    items: list[PromotionChecklistItem],
) -> str:
    """Render markdown report for promotion checklist decision."""

    ready = is_promotion_ready(items)
    advisories = collect_advisories(items)
    lines: list[str] = [
        f"# Release Promotion Checklist - {started_at.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        f"- Decision: {'READY' if ready else 'BLOCKED'}",
        "- Policy: deterministic gate is mandatory; no-dry-run gate is advisory.",
        f"- Started: {started_at.isoformat()}",
        f"- Ended: {ended_at.isoformat()}",
        f"- Duration: {(ended_at - started_at).total_seconds():.1f}s",
        "",
        "## Checklist",
        "",
    ]

    for item in items:
        role = "MANDATORY" if item.mandatory else "ADVISORY"
        lines.append(f"### {item.name}")
        lines.append(f"- Role: {role}")
        lines.append(f"- Status: {item.status}")
        if item.note:
            lines.append(f"- Note: {item.note}")
        if item.duration_seconds is not None:
            lines.append(f"- Duration: {item.duration_seconds:.1f}s")
        if item.report_file:
            lines.append(f"- Report: `{item.report_file}`")
        if item.command:
            lines.append(f"- Command: `{item.command}`")
        lines.append("")

    lines.append("## Advisory Signals")
    lines.append("")
    if advisories:
        for advisory in advisories:
            lines.append(f"- {advisory}")
    else:
        lines.append("- none")
    lines.append("")

    lines.append("## Promotion Rule")
    lines.append("")
    lines.append("- Proceed only when all MANDATORY items are PASS.")
    lines.append("- ADVISORY WARN/FAIL/SKIP must be tracked but do not block promotion.")
    lines.append("")

    return "\n".join(lines)

