"""P19 rollout weekly KPI aggregation and report rendering helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import re
from typing import Any, Callable


_KNOWN_RESULT_STATUSES = {"PASS", "FAIL", "WARN", "SKIP", "READY", "BLOCKED", "UNKNOWN"}
_TARGET_STATUS_VALUES = {"PASS", "ATTENTION", "TRACK"}


@dataclass(frozen=True)
class ReportSnapshot:
    """One parsed markdown report artifact in the review window."""

    path: Path
    started_at: datetime
    status: str

    def __post_init__(self) -> None:
        normalized = self.status.strip().upper()
        if normalized not in _KNOWN_RESULT_STATUSES:
            normalized = "UNKNOWN"
        object.__setattr__(self, "status", normalized)


@dataclass(frozen=True)
class RuntimeCounterSnapshot:
    """Runtime diagnostics counter snapshot captured during Studio Ops smoke."""

    path: Path
    captured_at: datetime
    mode: str
    active_sessions: int
    max_active_sessions: int
    team_saturation_rejections: int
    team_workspace_conflict_rejections: int


@dataclass(frozen=True)
class RolloutChecklistStatus:
    """Boolean completion view for weekly rollout checkpoints."""

    has_matrix_runs: bool
    has_deterministic_runs: bool
    latest_matrix_pass: bool
    latest_deterministic_pass: bool
    latest_promotion_ready: bool

    @property
    def ready(self) -> bool:
        return (
            self.has_matrix_runs
            and self.has_deterministic_runs
            and self.latest_matrix_pass
            and self.latest_deterministic_pass
            and self.latest_promotion_ready
        )


@dataclass(frozen=True)
class WeeklyRolloutSummary:
    """Windowed KPI summary for P19 rollout weekly review."""

    window_start: datetime
    window_end: datetime
    matrix_reports: list[ReportSnapshot]
    deterministic_reports: list[ReportSnapshot]
    promotion_reports: list[ReportSnapshot]
    advisory_statuses: list[str]
    runtime_snapshots: list[RuntimeCounterSnapshot]
    checklist: RolloutChecklistStatus

    @property
    def matrix_pass_count(self) -> int:
        return sum(1 for item in self.matrix_reports if item.status == "PASS")

    @property
    def deterministic_pass_count(self) -> int:
        return sum(1 for item in self.deterministic_reports if item.status == "PASS")

    @property
    def promotion_ready_count(self) -> int:
        return sum(1 for item in self.promotion_reports if item.status == "READY")

    @property
    def matrix_pass_rate(self) -> float:
        return _rate(self.matrix_pass_count, len(self.matrix_reports))

    @property
    def deterministic_pass_rate(self) -> float:
        return _rate(self.deterministic_pass_count, len(self.deterministic_reports))

    @property
    def promotion_ready_rate(self) -> float:
        return _rate(self.promotion_ready_count, len(self.promotion_reports))

    @property
    def advisory_pass_count(self) -> int:
        return sum(1 for status in self.advisory_statuses if status == "PASS")

    @property
    def advisory_warn_fail_count(self) -> int:
        return sum(1 for status in self.advisory_statuses if status in {"WARN", "FAIL"})

    @property
    def advisory_skip_count(self) -> int:
        return sum(1 for status in self.advisory_statuses if status == "SKIP")

    @property
    def latest_matrix(self) -> ReportSnapshot | None:
        return self.matrix_reports[-1] if self.matrix_reports else None

    @property
    def latest_deterministic(self) -> ReportSnapshot | None:
        return self.deterministic_reports[-1] if self.deterministic_reports else None

    @property
    def latest_promotion(self) -> ReportSnapshot | None:
        return self.promotion_reports[-1] if self.promotion_reports else None

    @property
    def latest_advisory_status(self) -> str:
        if not self.advisory_statuses:
            return "UNKNOWN"
        return self.advisory_statuses[-1]

    @property
    def latest_runtime_snapshot(self) -> RuntimeCounterSnapshot | None:
        return self.runtime_snapshots[-1] if self.runtime_snapshots else None

    @property
    def saturation_values(self) -> list[int]:
        return [item.team_saturation_rejections for item in self.runtime_snapshots]

    @property
    def conflict_values(self) -> list[int]:
        return [item.team_workspace_conflict_rejections for item in self.runtime_snapshots]

    @property
    def saturation_last(self) -> int | None:
        return self.saturation_values[-1] if self.saturation_values else None

    @property
    def saturation_min(self) -> int | None:
        return min(self.saturation_values) if self.saturation_values else None

    @property
    def saturation_max(self) -> int | None:
        return max(self.saturation_values) if self.saturation_values else None

    @property
    def conflict_last(self) -> int | None:
        return self.conflict_values[-1] if self.conflict_values else None

    @property
    def conflict_min(self) -> int | None:
        return min(self.conflict_values) if self.conflict_values else None

    @property
    def conflict_max(self) -> int | None:
        return max(self.conflict_values) if self.conflict_values else None

    @property
    def saturation_trend(self) -> str:
        return _counter_trend(self.saturation_values)

    @property
    def conflict_trend(self) -> str:
        return _counter_trend(self.conflict_values)

    @property
    def overall(self) -> str:
        return "READY" if self.checklist.ready else "ATTENTION"


@dataclass(frozen=True)
class RolloutTargetBands:
    """Target KPI bands for rollout environments."""

    profile: str
    matrix_pass_rate_min: float
    deterministic_pass_rate_min: float
    promotion_ready_rate_min: float
    advisory_warn_fail_max: int
    advisory_skip_max: int
    saturation_last_max: int
    conflict_last_max: int


@dataclass(frozen=True)
class TargetKpiRow:
    """Rendered row for target KPI dashboard."""

    kpi: str
    value: str
    target: str
    status: str

    def __post_init__(self) -> None:
        normalized = self.status.strip().upper()
        if normalized not in _TARGET_STATUS_VALUES:
            normalized = "TRACK"
        object.__setattr__(self, "status", normalized)


@dataclass(frozen=True)
class TargetEvaluation:
    """Target profile KPI evaluation."""

    profile: str
    rows: list[TargetKpiRow]

    @property
    def pass_all(self) -> bool:
        return all(row.status in {"PASS", "TRACK"} for row in self.rows)


_TARGET_BANDS: dict[str, RolloutTargetBands] = {
    "dev": RolloutTargetBands(
        profile="dev",
        matrix_pass_rate_min=0.95,
        deterministic_pass_rate_min=0.95,
        promotion_ready_rate_min=0.95,
        advisory_warn_fail_max=2,
        advisory_skip_max=14,
        saturation_last_max=5,
        conflict_last_max=3,
    ),
    "stage": RolloutTargetBands(
        profile="stage",
        matrix_pass_rate_min=1.0,
        deterministic_pass_rate_min=1.0,
        promotion_ready_rate_min=1.0,
        advisory_warn_fail_max=1,
        advisory_skip_max=7,
        saturation_last_max=2,
        conflict_last_max=1,
    ),
    "prod": RolloutTargetBands(
        profile="prod",
        matrix_pass_rate_min=1.0,
        deterministic_pass_rate_min=1.0,
        promotion_ready_rate_min=1.0,
        advisory_warn_fail_max=0,
        advisory_skip_max=2,
        saturation_last_max=0,
        conflict_last_max=0,
    ),
}


def list_target_profiles() -> list[str]:
    """Return supported target profile keys."""

    return sorted(_TARGET_BANDS.keys())


def get_target_bands(profile: str) -> RolloutTargetBands:
    """Resolve target profile bands."""

    key = (profile or "").strip().lower()
    if key not in _TARGET_BANDS:
        key = "stage"
    return _TARGET_BANDS[key]


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return numerator / denominator


def _format_percent(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_delta(value: float, *, suffix: str = "") -> str:
    sign = "+" if value >= 0 else ""
    return f"{sign}{value:.1f}{suffix}"


def _counter_trend(values: list[int]) -> str:
    if len(values) < 2:
        return "n/a"
    if values[-1] > values[0]:
        return "up"
    if values[-1] < values[0]:
        return "down"
    return "flat"


def _extract_field(text: str, field: str) -> str | None:
    marker = f"- {field}: "
    for line in text.splitlines():
        if line.startswith(marker):
            return line[len(marker) :].strip()
    return None


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _parse_started_at(text: str) -> datetime | None:
    return _parse_datetime(_extract_field(text, "Started"))


def _safe_int(value: Any, *, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return default


def parse_report_overall(path: Path) -> str:
    """Parse report `- Overall: ...` status from matrix/release-gate artifacts."""

    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return "UNKNOWN"
    value = _extract_field(text, "Overall")
    if not value:
        return "UNKNOWN"
    return value.strip().upper()


def parse_promotion_decision(path: Path) -> str:
    """Parse promotion checklist decision (`READY` / `BLOCKED`)."""

    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return "UNKNOWN"
    value = _extract_field(text, "Decision")
    if not value:
        return "UNKNOWN"
    return value.strip().upper()


def parse_promotion_advisory_status(path: Path) -> str:
    """Parse advisory gate status from promotion checklist report."""

    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return "UNKNOWN"

    lines = text.splitlines()
    in_advisory_gate = False
    status_marker = "- Status: "
    for line in lines:
        if line.startswith("### "):
            title = line.strip()[4:].strip().lower()
            in_advisory_gate = "no-dry-run gate" in title
            continue
        if not in_advisory_gate:
            continue
        if line.startswith(status_marker):
            return line[len(status_marker) :].strip().upper()

    advisory_signal_pattern = re.compile(r"^- .*no-dry-run gate:\s*([A-Za-z]+)\b", re.IGNORECASE)
    for line in lines:
        matched = advisory_signal_pattern.match(line.strip())
        if matched:
            return matched.group(1).strip().upper()
    return "UNKNOWN"


def parse_runtime_snapshot(path: Path) -> RuntimeCounterSnapshot | None:
    """Parse Studio Ops runtime snapshot artifact."""

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None

    runtime_raw = payload.get("runtime")
    runtime = runtime_raw if isinstance(runtime_raw, dict) else payload
    captured_at = _parse_datetime(str(payload.get("captured_at", "")).strip())
    if captured_at is None:
        captured_at = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)

    return RuntimeCounterSnapshot(
        path=path.resolve(),
        captured_at=captured_at,
        mode=str(runtime.get("mode", "unknown")),
        active_sessions=_safe_int(runtime.get("active_sessions", 0)),
        max_active_sessions=_safe_int(runtime.get("max_active_sessions", 0)),
        team_saturation_rejections=_safe_int(runtime.get("team_saturation_rejections", 0)),
        team_workspace_conflict_rejections=_safe_int(runtime.get("team_workspace_conflict_rejections", 0)),
    )


def _collect_reports(
    *,
    repo_root: Path,
    pattern: str,
    cutoff: datetime,
    parser: Callable[[Path], str],
) -> list[ReportSnapshot]:
    resolved_root = repo_root.resolve()
    artifacts = sorted(
        (item.resolve() for item in resolved_root.glob(pattern) if item.is_file()),
        key=lambda item: item.stat().st_mtime,
    )
    snapshots: list[ReportSnapshot] = []
    for artifact in artifacts:
        try:
            text = artifact.read_text(encoding="utf-8")
        except Exception:
            text = ""
        started_at = _parse_started_at(text)
        if started_at is None:
            started_at = datetime.fromtimestamp(artifact.stat().st_mtime, tz=timezone.utc)
        if started_at < cutoff:
            continue
        snapshots.append(
            ReportSnapshot(
                path=artifact,
                started_at=started_at,
                status=parser(artifact),
            )
        )
    return snapshots


def _collect_runtime_snapshots(
    *,
    repo_root: Path,
    pattern: str,
    cutoff: datetime,
) -> list[RuntimeCounterSnapshot]:
    resolved_root = repo_root.resolve()
    artifacts = sorted(
        (item.resolve() for item in resolved_root.glob(pattern) if item.is_file()),
        key=lambda item: item.stat().st_mtime,
    )
    snapshots: list[RuntimeCounterSnapshot] = []
    for artifact in artifacts:
        parsed = parse_runtime_snapshot(artifact)
        if parsed is None:
            continue
        if parsed.captured_at < cutoff:
            continue
        snapshots.append(parsed)
    return snapshots


def summarize_weekly_rollout(
    *,
    repo_root: Path,
    now: datetime | None = None,
    window_days: int = 7,
    min_matrix_runs: int = 1,
    min_deterministic_runs: int = 1,
    matrix_pattern: str = "workspace/p19_matrix/p19_runtime_matrix_*.md",
    deterministic_pattern: str = "workspace/release_gate/release_gate_deterministic_*.md",
    promotion_pattern: str = "workspace/release_promotion/release_promotion_*.md",
    runtime_snapshot_pattern: str = "workspace/release_gate/studio_ops_runtime_*.json",
) -> WeeklyRolloutSummary:
    """Build a weekly rollout summary for Stage-C adoption tracking."""

    window_end = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    window_start = window_end - timedelta(days=max(1, window_days))

    matrix_reports = _collect_reports(
        repo_root=repo_root,
        pattern=matrix_pattern,
        cutoff=window_start,
        parser=parse_report_overall,
    )
    deterministic_reports = _collect_reports(
        repo_root=repo_root,
        pattern=deterministic_pattern,
        cutoff=window_start,
        parser=parse_report_overall,
    )
    promotion_reports = _collect_reports(
        repo_root=repo_root,
        pattern=promotion_pattern,
        cutoff=window_start,
        parser=parse_promotion_decision,
    )
    advisory_statuses = [parse_promotion_advisory_status(item.path) for item in promotion_reports]
    runtime_snapshots = _collect_runtime_snapshots(
        repo_root=repo_root,
        pattern=runtime_snapshot_pattern,
        cutoff=window_start,
    )

    latest_matrix = matrix_reports[-1] if matrix_reports else None
    latest_deterministic = deterministic_reports[-1] if deterministic_reports else None
    latest_promotion = promotion_reports[-1] if promotion_reports else None

    checklist = RolloutChecklistStatus(
        has_matrix_runs=len(matrix_reports) >= max(1, min_matrix_runs),
        has_deterministic_runs=len(deterministic_reports) >= max(1, min_deterministic_runs),
        latest_matrix_pass=latest_matrix is not None and latest_matrix.status == "PASS",
        latest_deterministic_pass=latest_deterministic is not None and latest_deterministic.status == "PASS",
        latest_promotion_ready=latest_promotion is not None and latest_promotion.status == "READY",
    )
    return WeeklyRolloutSummary(
        window_start=window_start,
        window_end=window_end,
        matrix_reports=matrix_reports,
        deterministic_reports=deterministic_reports,
        promotion_reports=promotion_reports,
        advisory_statuses=advisory_statuses,
        runtime_snapshots=runtime_snapshots,
        checklist=checklist,
    )


def evaluate_target_bands(*, summary: WeeklyRolloutSummary, target_profile: str = "stage") -> TargetEvaluation:
    """Evaluate KPI values against environment-specific target bands."""

    target = get_target_bands(target_profile)
    rows: list[TargetKpiRow] = []
    rows.append(
        TargetKpiRow(
            kpi="Matrix pass rate",
            value=f"{_format_percent(summary.matrix_pass_rate)} ({summary.matrix_pass_count}/{len(summary.matrix_reports)})",
            target=f">= {_format_percent(target.matrix_pass_rate_min)}",
            status="PASS" if summary.matrix_pass_rate >= target.matrix_pass_rate_min and bool(summary.matrix_reports) else "ATTENTION",
        )
    )
    rows.append(
        TargetKpiRow(
            kpi="Deterministic gate pass rate",
            value=f"{_format_percent(summary.deterministic_pass_rate)} ({summary.deterministic_pass_count}/{len(summary.deterministic_reports)})",
            target=f">= {_format_percent(target.deterministic_pass_rate_min)}",
            status="PASS"
            if summary.deterministic_pass_rate >= target.deterministic_pass_rate_min and bool(summary.deterministic_reports)
            else "ATTENTION",
        )
    )
    rows.append(
        TargetKpiRow(
            kpi="Promotion READY rate",
            value=f"{_format_percent(summary.promotion_ready_rate)} ({summary.promotion_ready_count}/{len(summary.promotion_reports)})",
            target=f">= {_format_percent(target.promotion_ready_rate_min)}",
            status="PASS"
            if summary.promotion_ready_rate >= target.promotion_ready_rate_min and bool(summary.promotion_reports)
            else "ATTENTION",
        )
    )
    rows.append(
        TargetKpiRow(
            kpi="Advisory WARN/FAIL count",
            value=str(summary.advisory_warn_fail_count),
            target=f"<= {target.advisory_warn_fail_max}",
            status="PASS" if summary.advisory_warn_fail_count <= target.advisory_warn_fail_max else "ATTENTION",
        )
    )
    rows.append(
        TargetKpiRow(
            kpi="Advisory SKIP count",
            value=str(summary.advisory_skip_count),
            target=f"<= {target.advisory_skip_max}",
            status="PASS" if summary.advisory_skip_count <= target.advisory_skip_max else "ATTENTION",
        )
    )

    if summary.saturation_last is None:
        rows.append(TargetKpiRow(kpi="Saturation counter (last)", value="n/a", target=f"<= {target.saturation_last_max}", status="TRACK"))
    else:
        rows.append(
            TargetKpiRow(
                kpi="Saturation counter (last)",
                value=str(summary.saturation_last),
                target=f"<= {target.saturation_last_max}",
                status="PASS" if summary.saturation_last <= target.saturation_last_max else "ATTENTION",
            )
        )
    if summary.conflict_last is None:
        rows.append(TargetKpiRow(kpi="Workspace conflict counter (last)", value="n/a", target=f"<= {target.conflict_last_max}", status="TRACK"))
    else:
        rows.append(
            TargetKpiRow(
                kpi="Workspace conflict counter (last)",
                value=str(summary.conflict_last),
                target=f"<= {target.conflict_last_max}",
                status="PASS" if summary.conflict_last <= target.conflict_last_max else "ATTENTION",
            )
        )

    return TargetEvaluation(profile=target.profile, rows=rows)


def build_target_remediation_hints(*, summary: WeeklyRolloutSummary, target_profile: str = "stage") -> list[str]:
    """Build actionable remediation hints for ATTENTION target rows."""

    target_eval = evaluate_target_bands(summary=summary, target_profile=target_profile)
    hints: list[str] = []
    for row in target_eval.rows:
        if row.status != "ATTENTION":
            continue
        if row.kpi == "Matrix pass rate":
            hints.append("Re-run `scripts/ci/p19_runtime_matrix.py` and block rollout expansion until matrix PASS rate recovers.")
        elif row.kpi == "Deterministic gate pass rate":
            hints.append("Run deterministic gate triage (`scripts/ci/release_gate.py`) and fix blockers before next promotion decision.")
        elif row.kpi == "Promotion READY rate":
            hints.append("Review promotion checklist reports and close mandatory FAIL items before rollout changes.")
        elif row.kpi == "Advisory WARN/FAIL count":
            hints.append("Investigate advisory no-dry-run instability and reduce WARN/FAIL frequency for the selected environment.")
        elif row.kpi == "Advisory SKIP count":
            hints.append("Reduce advisory skips by enabling advisory credentials and scheduling at least one no-dry-run validation in-window.")
        elif row.kpi == "Saturation counter (last)":
            hints.append("Reduce concurrency pressure or increase team slots only after validating workspace/session isolation.")
        elif row.kpi == "Workspace conflict counter (last)":
            hints.append("Audit caller `session_id` routing and workspace reuse policy to eliminate same-workspace conflicts.")
    if not hints:
        hints.append("No remediation needed. Keep current canary scope and monitoring cadence.")
    return hints


def _build_mode_split_rows(summary: WeeklyRolloutSummary) -> list[dict[str, str]]:
    by_mode: dict[str, list[RuntimeCounterSnapshot]] = {}
    for item in summary.runtime_snapshots:
        key = (item.mode or "unknown").strip().lower() or "unknown"
        by_mode.setdefault(key, []).append(item)
    rows: list[dict[str, str]] = []
    for mode in sorted(by_mode.keys()):
        items = by_mode[mode]
        saturation_values = [snapshot.team_saturation_rejections for snapshot in items]
        conflict_values = [snapshot.team_workspace_conflict_rejections for snapshot in items]
        rows.append(
            {
                "mode": mode,
                "samples": str(len(items)),
                "saturation_last": str(saturation_values[-1]),
                "saturation_max": str(max(saturation_values)),
                "conflict_last": str(conflict_values[-1]),
                "conflict_max": str(max(conflict_values)),
            }
        )
    return rows


def _build_kpi_sparkline(values: list[float | int | None], max_points: int = 20) -> list[float | int]:
    """Build a sparkline-compatible series from KPI values.

    Args:
        values: List of KPI values (may contain None for missing data)
        max_points: Maximum number of points to include (older values truncated)

    Returns:
        List of values suitable for sparkline rendering (None replaced with sentinel)
    """
    if not values:
        return []

    # Truncate to most recent max_points
    truncated = values[-max_points:] if len(values) > max_points else values

    # Replace None with -1 sentinel for numeric sparkline rendering
    result: list[float | int] = []
    for val in truncated:
        if val is None:
            result.append(-1)
        else:
            result.append(val)
    return result


def _build_kpi_sparklines(summary: WeeklyRolloutSummary) -> dict[str, list[float | int]]:
    """Build sparkline data for all tracked KPIs.

    Returns:
        Dict mapping KPI names to sparkline value series
    """
    sparklines: dict[str, list[float | int]] = {}

    # Matrix pass rate sparkline (from individual reports)
    matrix_rates: list[float] = []
    for report in summary.matrix_reports:
        matrix_rates.append(1.0 if report.status == "PASS" else 0.0)
    sparklines["matrix_pass_rate"] = _build_kpi_sparkline(matrix_rates)

    # Deterministic pass rate sparkline
    deterministic_rates: list[float] = []
    for report in summary.deterministic_reports:
        deterministic_rates.append(1.0 if report.status == "PASS" else 0.0)
    sparklines["deterministic_pass_rate"] = _build_kpi_sparkline(deterministic_rates)

    # Promotion ready rate sparkline
    promotion_rates: list[float] = []
    for report in summary.promotion_reports:
        promotion_rates.append(1.0 if report.status == "READY" else 0.0)
    sparklines["promotion_ready_rate"] = _build_kpi_sparkline(promotion_rates)

    # Saturation counter sparkline
    saturation_values = [float(v) for v in summary.saturation_values]
    sparklines["saturation_counter"] = _build_kpi_sparkline(saturation_values)

    # Conflict counter sparkline
    conflict_values = [float(v) for v in summary.conflict_values]
    sparklines["conflict_counter"] = _build_kpi_sparkline(conflict_values)

    # Active sessions sparkline (from runtime snapshots)
    active_sessions = [float(s.active_sessions) for s in summary.runtime_snapshots]
    sparklines["active_sessions"] = _build_kpi_sparkline(active_sessions)

    return sparklines


def _build_kpi_sparkline_metadata(summary: WeeklyRolloutSummary) -> dict[str, Any]:
    """Build sparkline metadata for dashboard rendering.

    Returns:
        Dict with sparkline data and metadata for each KPI
    """
    sparklines = _build_kpi_sparklines(summary)

    metadata: dict[str, Any] = {}
    for kpi_name, values in sparklines.items():
        if not values:
            metadata[kpi_name] = {
                "values": [],
                "count": 0,
                "min": None,
                "max": None,
                "last": None,
            }
            continue

        numeric_values = [v for v in values if v >= 0]
        metadata[kpi_name] = {
            "values": values,
            "count": len(values),
            "min": min(numeric_values) if numeric_values else None,
            "max": max(numeric_values) if numeric_values else None,
            "last": values[-1] if values else None,
        }

    return metadata


def build_weekly_rollout_payload(
    *,
    summary: WeeklyRolloutSummary,
    target_profile: str = "stage",
    previous_summary: WeeklyRolloutSummary | None = None,
) -> dict[str, Any]:
    """Build machine-readable weekly rollout summary payload."""

    target_eval = evaluate_target_bands(summary=summary, target_profile=target_profile)
    remediation_hints = build_target_remediation_hints(summary=summary, target_profile=target_profile)
    mode_split_rows = _build_mode_split_rows(summary)
    sparkline_metadata = _build_kpi_sparkline_metadata(summary)
    payload: dict[str, Any] = {
        "overall": summary.overall,
        "target_profile": target_eval.profile,
        "target_profile_status": "PASS" if target_eval.pass_all else "ATTENTION",
        "window_start_utc": summary.window_start.isoformat(),
        "window_end_utc": summary.window_end.isoformat(),
        "counts": {
            "matrix_reports": len(summary.matrix_reports),
            "deterministic_reports": len(summary.deterministic_reports),
            "promotion_reports": len(summary.promotion_reports),
            "runtime_snapshots": len(summary.runtime_snapshots),
        },
        "kpis": {
            "matrix_pass_rate": summary.matrix_pass_rate,
            "deterministic_pass_rate": summary.deterministic_pass_rate,
            "promotion_ready_rate": summary.promotion_ready_rate,
            "advisory_warn_fail_count": summary.advisory_warn_fail_count,
            "advisory_skip_count": summary.advisory_skip_count,
            "saturation_last": summary.saturation_last,
            "saturation_min": summary.saturation_min,
            "saturation_max": summary.saturation_max,
            "saturation_trend": summary.saturation_trend,
            "conflict_last": summary.conflict_last,
            "conflict_min": summary.conflict_min,
            "conflict_max": summary.conflict_max,
            "conflict_trend": summary.conflict_trend,
        },
        "sparklines": sparkline_metadata,
        "checklist": {
            "has_matrix_runs": summary.checklist.has_matrix_runs,
            "has_deterministic_runs": summary.checklist.has_deterministic_runs,
            "latest_matrix_pass": summary.checklist.latest_matrix_pass,
            "latest_deterministic_pass": summary.checklist.latest_deterministic_pass,
            "latest_promotion_ready": summary.checklist.latest_promotion_ready,
            "ready": summary.checklist.ready,
        },
        "target_rows": [
            {"kpi": row.kpi, "value": row.value, "target": row.target, "status": row.status}
            for row in target_eval.rows
        ],
        "remediation_hints": remediation_hints,
        "runtime_mode_split": mode_split_rows,
        "latest_artifacts": {
            "matrix": str(summary.latest_matrix.path) if summary.latest_matrix else None,
            "deterministic_gate": str(summary.latest_deterministic.path) if summary.latest_deterministic else None,
            "promotion": str(summary.latest_promotion.path) if summary.latest_promotion else None,
            "runtime_snapshot": str(summary.latest_runtime_snapshot.path) if summary.latest_runtime_snapshot else None,
        },
    }

    if previous_summary is not None:
        payload["delta_vs_previous_window"] = {
            "matrix_pass_rate_pp": (summary.matrix_pass_rate - previous_summary.matrix_pass_rate) * 100.0,
            "deterministic_pass_rate_pp": (summary.deterministic_pass_rate - previous_summary.deterministic_pass_rate) * 100.0,
            "promotion_ready_rate_pp": (summary.promotion_ready_rate - previous_summary.promotion_ready_rate) * 100.0,
            "advisory_warn_fail_count": summary.advisory_warn_fail_count - previous_summary.advisory_warn_fail_count,
            "advisory_skip_count": summary.advisory_skip_count - previous_summary.advisory_skip_count,
            "saturation_last": None
            if summary.saturation_last is None or previous_summary.saturation_last is None
            else summary.saturation_last - previous_summary.saturation_last,
            "conflict_last": None
            if summary.conflict_last is None or previous_summary.conflict_last is None
            else summary.conflict_last - previous_summary.conflict_last,
        }
    return payload


def build_weekly_rollout_report(
    *,
    summary: WeeklyRolloutSummary,
    target_profile: str = "stage",
    previous_summary: WeeklyRolloutSummary | None = None,
) -> str:
    """Render markdown report for weekly Stage-C rollout tracking."""

    checklist_rows = [
        ("At least one matrix run in window", summary.checklist.has_matrix_runs),
        ("At least one deterministic gate run in window", summary.checklist.has_deterministic_runs),
        ("Latest matrix report is PASS", summary.checklist.latest_matrix_pass),
        ("Latest deterministic gate report is PASS", summary.checklist.latest_deterministic_pass),
        ("Latest promotion decision is READY", summary.checklist.latest_promotion_ready),
    ]
    target_eval = evaluate_target_bands(summary=summary, target_profile=target_profile)

    remediation_hints = build_target_remediation_hints(summary=summary, target_profile=target_profile)
    mode_split_rows = _build_mode_split_rows(summary)
    lines: list[str] = [
        f"# P19 Weekly Rollout Review - {summary.window_end.strftime('%Y-%m-%d %H:%M:%S %Z')}",
        "",
        f"- Overall: {summary.overall}",
        f"- Target Profile: {target_eval.profile}",
        f"- Target Profile Status: {'PASS' if target_eval.pass_all else 'ATTENTION'}",
        f"- Window Start (UTC): {summary.window_start.isoformat()}",
        f"- Window End (UTC): {summary.window_end.isoformat()}",
        "",
        "## KPI Dashboard",
        "",
        "| KPI | Value | Target | Status |",
        "| --- | --- | --- | --- |",
    ]
    for row in target_eval.rows:
        lines.append(f"| {row.kpi} | {row.value} | {row.target} | {row.status} |")

    lines.extend(
        [
            "",
            "## Runtime Counter Trends",
            "",
            f"- Snapshots in window: {len(summary.runtime_snapshots)}",
            f"- Saturation counter: last={summary.saturation_last if summary.saturation_last is not None else 'n/a'}, min={summary.saturation_min if summary.saturation_min is not None else 'n/a'}, max={summary.saturation_max if summary.saturation_max is not None else 'n/a'}, trend={summary.saturation_trend}",
            f"- Workspace conflict counter: last={summary.conflict_last if summary.conflict_last is not None else 'n/a'}, min={summary.conflict_min if summary.conflict_min is not None else 'n/a'}, max={summary.conflict_max if summary.conflict_max is not None else 'n/a'}, trend={summary.conflict_trend}",
            "",
            "## Runtime Mode Split",
            "",
        ]
    )
    if mode_split_rows:
        lines.extend(
            [
                "| Mode | Samples | Saturation Last | Saturation Max | Conflict Last | Conflict Max |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for row in mode_split_rows:
            lines.append(
                f"| {row['mode']} | {row['samples']} | {row['saturation_last']} | {row['saturation_max']} | {row['conflict_last']} | {row['conflict_max']} |"
            )
    else:
        lines.append("- No runtime snapshots in window.")

    lines.extend(
        [
            "",
            "## Target Remediation Hints",
            "",
        ]
    )
    for hint in remediation_hints:
        lines.append(f"- {hint}")

    lines.extend(
        [
            "",
            "## Weekly Checklist",
            "",
        ]
    )
    for label, ok in checklist_rows:
        lines.append(f"- [{'x' if ok else ' '}] {label}")

    lines.extend(
        [
            "",
            "## Weekly Delta vs Previous Window",
            "",
        ]
    )
    if previous_summary is None:
        lines.append("- Previous window: unavailable")
    else:
        matrix_delta_pp = (summary.matrix_pass_rate - previous_summary.matrix_pass_rate) * 100.0
        deterministic_delta_pp = (summary.deterministic_pass_rate - previous_summary.deterministic_pass_rate) * 100.0
        promotion_delta_pp = (summary.promotion_ready_rate - previous_summary.promotion_ready_rate) * 100.0
        advisory_warn_delta = summary.advisory_warn_fail_count - previous_summary.advisory_warn_fail_count
        advisory_skip_delta = summary.advisory_skip_count - previous_summary.advisory_skip_count

        lines.append(
            f"- Matrix pass rate delta: {_format_delta(matrix_delta_pp, suffix='pp')} "
            f"(current {_format_percent(summary.matrix_pass_rate)} vs previous {_format_percent(previous_summary.matrix_pass_rate)})"
        )
        lines.append(
            f"- Deterministic pass rate delta: {_format_delta(deterministic_delta_pp, suffix='pp')} "
            f"(current {_format_percent(summary.deterministic_pass_rate)} vs previous {_format_percent(previous_summary.deterministic_pass_rate)})"
        )
        lines.append(
            f"- Promotion READY rate delta: {_format_delta(promotion_delta_pp, suffix='pp')} "
            f"(current {_format_percent(summary.promotion_ready_rate)} vs previous {_format_percent(previous_summary.promotion_ready_rate)})"
        )
        lines.append(
            f"- Advisory WARN/FAIL delta: {_format_delta(float(advisory_warn_delta))} "
            f"(current {summary.advisory_warn_fail_count} vs previous {previous_summary.advisory_warn_fail_count})"
        )
        lines.append(
            f"- Advisory SKIP delta: {_format_delta(float(advisory_skip_delta))} "
            f"(current {summary.advisory_skip_count} vs previous {previous_summary.advisory_skip_count})"
        )
        if summary.saturation_last is None or previous_summary.saturation_last is None:
            lines.append("- Saturation counter (last) delta: n/a")
        else:
            sat_delta = summary.saturation_last - previous_summary.saturation_last
            lines.append(
                f"- Saturation counter (last) delta: {_format_delta(float(sat_delta))} "
                f"(current {summary.saturation_last} vs previous {previous_summary.saturation_last})"
            )
        if summary.conflict_last is None or previous_summary.conflict_last is None:
            lines.append("- Workspace conflict counter (last) delta: n/a")
        else:
            conf_delta = summary.conflict_last - previous_summary.conflict_last
            lines.append(
                f"- Workspace conflict counter (last) delta: {_format_delta(float(conf_delta))} "
                f"(current {summary.conflict_last} vs previous {previous_summary.conflict_last})"
            )

    lines.extend(
        [
            "",
            "## Latest Artifacts",
            "",
            f"- Matrix: `{summary.latest_matrix.path if summary.latest_matrix else '-'}`",
            f"- Deterministic gate: `{summary.latest_deterministic.path if summary.latest_deterministic else '-'}`",
            f"- Promotion checklist: `{summary.latest_promotion.path if summary.latest_promotion else '-'}`",
            f"- Runtime snapshot: `{summary.latest_runtime_snapshot.path if summary.latest_runtime_snapshot else '-'}`",
            f"- Latest advisory status: {summary.latest_advisory_status}",
            "",
            "## Rollback Decision Log (Template)",
            "",
            "- Date (UTC): ",
            "- Trigger: (e.g., deterministic FAIL / matrix FAIL / sustained advisory WARN/FAIL)",
            "- Decision: (continue canary / freeze rollout / rollback to single_main)",
            "- Owner: ",
            "- Evidence links:",
            "- Follow-up actions:",
            "",
            "## Weekly Review Notes",
            "",
            "- KPI interpretation:",
            "- Risk updates:",
            "- Next-week rollout scope:",
            "",
        ]
    )
    return "\n".join(lines)
