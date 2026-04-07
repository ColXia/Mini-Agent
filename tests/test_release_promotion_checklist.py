from __future__ import annotations

from datetime import datetime, timezone

from mini_agent.dev.release_promotion_checklist import (
    PromotionChecklistItem,
    build_promotion_report,
    collect_advisories,
    is_promotion_ready,
)


def test_promotion_ready_requires_all_mandatory_pass() -> None:
    items = [
        PromotionChecklistItem(name="Deterministic release gate", mandatory=True, status="FAIL", note="exit_code=1"),
        PromotionChecklistItem(name="No-dry-run gate", mandatory=False, status="PASS"),
    ]
    assert is_promotion_ready(items) is False


def test_promotion_ready_allows_advisory_warn() -> None:
    items = [
        PromotionChecklistItem(name="Deterministic release gate", mandatory=True, status="PASS"),
        PromotionChecklistItem(name="No-dry-run gate", mandatory=False, status="WARN", note="timeout"),
    ]
    assert is_promotion_ready(items) is True
    advisories = collect_advisories(items)
    assert len(advisories) == 1
    assert "No-dry-run gate: WARN" in advisories[0]


def test_build_promotion_report_contains_policy_and_decision() -> None:
    started_at = datetime(2026, 4, 7, 4, 0, 0, tzinfo=timezone.utc)
    ended_at = datetime(2026, 4, 7, 4, 1, 0, tzinfo=timezone.utc)
    items = [
        PromotionChecklistItem(
            name="Deterministic release gate",
            mandatory=True,
            status="PASS",
            report_file="workspace/release_gate/release_gate_deterministic.md",
        ),
        PromotionChecklistItem(
            name="OpenWebUI no-dry-run gate",
            mandatory=False,
            status="WARN",
            note="advisory failure: timeout",
        ),
    ]
    report = build_promotion_report(started_at=started_at, ended_at=ended_at, items=items)
    assert "- Decision: READY" in report
    assert "deterministic gate is mandatory; no-dry-run gate is advisory" in report
    assert "OpenWebUI no-dry-run gate" in report

