"""Retention and cleanup helpers for P19 rollout artifacts.

This module provides utilities for managing artifact accumulation over time,
including cleanup of old weekly rollout reports and related artifacts.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sys
from typing import Any

if __name__ == "__main__":
    REPO_ROOT = Path(__file__).resolve().parents[2]
    SRC_ROOT = REPO_ROOT / "src"
    if str(SRC_ROOT) not in sys.path:
        sys.path.insert(0, str(SRC_ROOT))


def _parse_artifact_timestamp(filename: str) -> datetime | None:
    """Parse UTC timestamp from artifact filename.

    Supports formats like:
    - p19_weekly_rollout_20260510T101248Z.md
    - release_gate_deterministic_20260407T101000Z.md
    - studio_ops_runtime_20260414T101000Z.json

    Args:
        filename: The artifact filename

    Returns:
        Parsed datetime or None if not parseable
    """
    # Match ISO timestamp pattern with Z suffix
    pattern = r"(\d{8}T\d{6}Z)"
    match = re.search(pattern, filename)
    if not match:
        return None

    timestamp_str = match.group(1)
    try:
        # Parse YYYYMMDDTHHMMSSZ format
        return datetime.strptime(timestamp_str, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def list_rollout_artifacts(
    *,
    repo_root: Path,
    pattern: str = "workspace/p19_rollout/p19_weekly_rollout_*.md",
) -> list[Path]:
    """List all rollout artifacts matching the pattern.

    Args:
        repo_root: Repository root path
        pattern: Glob pattern for artifacts

    Returns:
        List of artifact paths sorted by modification time (oldest first)
    """
    resolved_root = repo_root.resolve()
    artifacts = sorted(
        (item.resolve() for item in resolved_root.glob(pattern) if item.is_file()),
        key=lambda item: item.stat().st_mtime,
    )
    return artifacts


def list_rollout_artifacts_multi(
    *,
    repo_root: Path,
    patterns: list[str],
) -> list[Path]:
    """List all rollout artifacts matching multiple patterns.

    Args:
        repo_root: Repository root path
        patterns: List of glob patterns for artifacts

    Returns:
        List of artifact paths sorted by modification time (oldest first)
    """
    resolved_root = repo_root.resolve()
    all_artifacts: set[Path] = set()
    for pattern in patterns:
        for item in resolved_root.glob(pattern):
            if item.is_file():
                all_artifacts.add(item.resolve())
    return sorted(all_artifacts, key=lambda item: item.stat().st_mtime)


def cleanup_old_artifacts(
    *,
    repo_root: Path,
    max_age_days: int = 30,
    max_count: int = 100,
    pattern: str = "workspace/p19_rollout/p19_weekly_rollout_*.md",
    patterns: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Clean up old rollout artifacts based on age and count limits.

    Args:
        repo_root: Repository root path
        max_age_days: Maximum age in days before cleanup (default 30)
        max_count: Maximum number of artifacts to keep (default 100)
        pattern: Glob pattern for artifacts (single pattern)
        patterns: List of glob patterns for artifacts (multiple patterns)
        dry_run: If True, only report what would be deleted

    Returns:
        Dict with cleanup statistics
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=max_age_days)

    # Use patterns list if provided, otherwise use single pattern
    if patterns:
        artifacts = list_rollout_artifacts_multi(repo_root=repo_root, patterns=patterns)
    else:
        artifacts = list_rollout_artifacts(repo_root=repo_root, pattern=pattern)

    to_delete: list[Path] = []
    kept: list[Path] = []

    # First pass: delete by age
    for artifact in artifacts:
        # Try parsing timestamp from filename
        parsed_ts = _parse_artifact_timestamp(artifact.name)
        if parsed_ts is None:
            # Fall back to file modification time
            parsed_ts = datetime.fromtimestamp(artifact.stat().st_mtime, tz=timezone.utc)

        if parsed_ts < cutoff:
            to_delete.append(artifact)
        else:
            kept.append(artifact)

    # Second pass: if still too many, delete oldest beyond max_count
    if len(kept) > max_count:
        # Sort kept by time (oldest first)
        kept.sort(key=lambda p: _parse_artifact_timestamp(p.name) or datetime.min.replace(tzinfo=timezone.utc))
        excess_count = len(kept) - max_count
        to_delete.extend(kept[:excess_count])
        kept = kept[excess_count:]

    # Perform deletion
    deleted_count = 0
    deleted_size_bytes = 0
    errors: list[str] = []

    for artifact in to_delete:
        try:
            size = artifact.stat().st_size
            if not dry_run:
                artifact.unlink()
            deleted_count += 1
            deleted_size_bytes += size
        except Exception as e:
            errors.append(f"{artifact}: {e}")

    return {
        "total_artifacts": len(artifacts),
        "deleted_count": deleted_count,
        "kept_count": len(kept),
        "deleted_size_bytes": deleted_size_bytes,
        "deleted_size_mb": round(deleted_size_bytes / (1024 * 1024), 2),
        "cutoff_date": cutoff.isoformat(),
        "max_age_days": max_age_days,
        "max_count": max_count,
        "dry_run": dry_run,
        "errors": errors,
    }


def cleanup_all_rollout_artifacts(
    *,
    repo_root: Path,
    max_age_days: int = 30,
    max_count: int = 100,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Clean up all rollout-related artifacts.

    Includes:
    - Weekly rollout reports (.md and .json)
    - Matrix reports
    - Release gate reports
    - Promotion reports
    - Runtime snapshots

    Args:
        repo_root: Repository root path
        max_age_days: Maximum age in days before cleanup
        max_count: Maximum number of artifacts to keep per category
        dry_run: If True, only report what would be deleted

    Returns:
        Dict with cleanup statistics for all categories
    """
    patterns_by_category = [
        ("rollout_reports", ["workspace/p19_rollout/p19_weekly_rollout_*.md", "workspace/p19_rollout/p19_weekly_rollout_*.json"]),
        ("matrix_reports", ["workspace/p19_matrix/p19_runtime_matrix_*.md"]),
        ("deterministic_gates", ["workspace/release_gate/release_gate_deterministic_*.md"]),
        ("promotion_reports", ["workspace/release_promotion/release_promotion_*.md"]),
        ("runtime_snapshots", ["workspace/release_gate/studio_ops_runtime_*.json"]),
    ]

    results: dict[str, Any] = {
        "categories": {},
        "total_deleted": 0,
        "total_deleted_mb": 0.0,
        "dry_run": dry_run,
    }

    for category, patterns in patterns_by_category:
        result = cleanup_old_artifacts(
            repo_root=repo_root,
            max_age_days=max_age_days,
            max_count=max_count,
            patterns=patterns,
            dry_run=dry_run,
        )
        results["categories"][category] = result
        results["total_deleted"] += result["deleted_count"]
        results["total_deleted_mb"] += result["deleted_size_mb"]

    return results


def main(argv: list[str] | None = None) -> int:
    """CLI entry point for rollout artifact cleanup."""
    import argparse

    parser = argparse.ArgumentParser(description="Clean up old P19 rollout artifacts.")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=30,
        help="Maximum age in days before cleanup (default: 30)",
    )
    parser.add_argument(
        "--max-count",
        type=int,
        default=100,
        help="Maximum number of artifacts to keep per category (default: 100)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Only report what would be deleted, do not actually delete",
    )
    parser.add_argument(
        "--all-categories",
        action="store_true",
        help="Clean up all rollout artifact categories (not just weekly reports)",
    )

    args = parser.parse_args(argv)

    REPO_ROOT = Path(__file__).resolve().parents[2]

    if args.all_categories:
        result = cleanup_all_rollout_artifacts(
            repo_root=REPO_ROOT,
            max_age_days=args.max_age_days,
            max_count=args.max_count,
            dry_run=args.dry_run,
        )
        print(f"[cleanup] Dry run: {result['dry_run']}")
        print(f"[cleanup] Total deleted: {result['total_deleted']} files, {result['total_deleted_mb']:.2f} MB")
        for category, stats in result["categories"].items():
            print(f"[cleanup] {category}: deleted={stats['deleted_count']}, kept={stats['kept_count']}")
            if stats["errors"]:
                for error in stats["errors"]:
                    print(f"[cleanup]   error: {error}", file=sys.stderr)
    else:
        result = cleanup_old_artifacts(
            repo_root=REPO_ROOT,
            max_age_days=args.max_age_days,
            max_count=args.max_count,
            dry_run=args.dry_run,
        )
        print(f"[cleanup] Dry run: {result['dry_run']}")
        print(f"[cleanup] Deleted: {result['deleted_count']} files, {result['deleted_size_mb']:.2f} MB")
        print(f"[cleanup] Kept: {result['kept_count']} files")
        if result["errors"]:
            for error in result["errors"]:
                print(f"[cleanup] error: {error}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
