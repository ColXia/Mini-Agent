#!/usr/bin/env python3
"""Classify the current dirty worktree into honest cleanup slices."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


@dataclass(frozen=True)
class StatusEntry:
    raw_status: str
    index_status: str
    worktree_status: str
    path: str


@dataclass(frozen=True)
class SliceRule:
    name: str
    phase_hint: str
    description: str
    prefixes: tuple[str, ...] = ()
    exact_paths: tuple[str, ...] = ()
    test_prefixes: tuple[str, ...] = ()

    def matches(self, path: str) -> bool:
        if path in self.exact_paths:
            return True
        if any(path.startswith(prefix) for prefix in self.prefixes):
            return True
        if any(path.startswith(prefix) for prefix in self.test_prefixes):
            return True
        return False


SLICE_RULES: tuple[SliceRule, ...] = (
    SliceRule(
        name="docs-planning-governance",
        phase_hint="P32b/P38/P40",
        description="Active docs, planning-memory, and repo-hygiene guardrails.",
        prefixes=("docs/",),
        exact_paths=(
            ".gitignore",
            "task_plan.md",
            "progress.md",
            "findings.md",
            "scripts/README.md",
            "scripts/worktree_slice_report.py",
        ),
    ),
    SliceRule(
        name="model-runtime-substrate",
        phase_hint="P33b/P39",
        description="Model/provider/runtime substrate and adjacent validation.",
        prefixes=("src/mini_agent/model_manager/", "src/mini_agent/llm/"),
        exact_paths=("tests/test_config_local_env.py", "tests/test_llm.py", "tests/test_llm_clients.py"),
        test_prefixes=("tests/test_model_",),
    ),
    SliceRule(
        name="agent-core-and-cli-surface",
        phase_hint="P34/P35",
        description="Agent-core adoption, compatibility cleanup, and CLI/operator seams.",
        prefixes=(
            "src/mini_agent/agent_core/",
            "src/mini_agent/code_agent/",
            "src/mini_agent/core/",
            "src/mini_agent/commands/",
        ),
        exact_paths=(
            "src/mini_agent/__init__.py",
            "src/mini_agent/cli.py",
            "src/mini_agent/cli_interactive.py",
            "src/mini_agent/tools/bash_tool.py",
            "src/mini_agent/tools/mcp/command_service.py",
            "tests/test_bash_tool.py",
            "tests/test_agent.py",
            "tests/test_command_execution_service.py",
            "tests/test_security_policy.py",
        ),
        test_prefixes=("tests/test_agent_", "tests/test_code_agent_", "tests/test_cli_"),
    ),
    SliceRule(
        name="runtime-session-contract",
        phase_hint="P36",
        description="Runtime/session support seams, handlers, codecs, and state hydration.",
        prefixes=("src/mini_agent/runtime/",),
        exact_paths=("tests/runtime_contract_fixtures.py", "tests/test_sandbox_state.py"),
        test_prefixes=("tests/test_runtime_", "tests/test_session_"),
    ),
    SliceRule(
        name="surface-transport-orchestration",
        phase_hint="P37",
        description="TUI, transport, interaction, and desktop surface orchestration.",
        prefixes=(
            "src/mini_agent/tui/",
            "src/mini_agent/transport/",
            "src/mini_agent/interaction/",
            "src/mini_agent/desktop/",
        ),
        exact_paths=("tests/test_interface_dto_contracts.py",),
        test_prefixes=("tests/test_tui_", "tests/test_transport_", "tests/test_desktop_", "tests/test_interaction_"),
    ),
    SliceRule(
        name="memory-governance",
        phase_hint="P26",
        description="Memory ownership, runtime task-memory controls, and KB memory bridges.",
        prefixes=("src/mini_agent/memory/",),
        exact_paths=("src/mini_agent/tools/knowledge_base_control_service.py", "tests/test_knowledge_base_tool.py"),
        test_prefixes=("tests/test_memory_", "tests/test_memoria_"),
    ),
    SliceRule(
        name="interfaces-apps",
        phase_hint="cross-cutting",
        description="Interfaces, application entry surfaces, and subprogram hosts.",
        prefixes=("src/mini_agent/interfaces/", "src/apps/", "src/subprograms/"),
    ),
    SliceRule(
        name="developer-tooling-smokes",
        phase_hint="repo-tooling",
        description="Developer helpers, smoke scripts, and adjacent support utilities.",
        prefixes=("scripts/", "src/mini_agent/dev/"),
        exact_paths=("src/mini_agent/logger.py", "tests/test_integration.py", "tests/test_logger_events.py"),
    ),
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--format",
        choices=("text", "json", "markdown"),
        default="text",
        help="Output format.",
    )
    parser.add_argument(
        "--sample-limit",
        type=int,
        default=8,
        help="Number of sample paths to show for each slice.",
    )
    return parser.parse_args()


def normalize_path(path: str) -> str:
    return path.replace("\\", "/").strip()


def load_status_entries() -> list[StatusEntry]:
    result = subprocess.run(
        ["git", "status", "--short"],
        check=True,
        capture_output=True,
        text=True,
    )
    entries: list[StatusEntry] = []
    for raw_line in result.stdout.splitlines():
        if len(raw_line) < 4:
            continue
        raw_status = raw_line[:2]
        path = normalize_path(raw_line[3:])
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        entries.append(
            StatusEntry(
                raw_status=raw_status,
                index_status=raw_status[0],
                worktree_status=raw_status[1],
                path=path,
            )
        )
    return entries


def classify_slice(path: str) -> SliceRule | None:
    for rule in SLICE_RULES:
        if rule.matches(path):
            return rule
    return None


def bucket_top_path(path: str) -> str:
    parts = Path(path).parts
    if len(parts) >= 3 and parts[0] == "src" and parts[1] == "mini_agent":
        return "/".join(parts[:3])
    if len(parts) >= 2 and parts[0] == "src":
        return "/".join(parts[:2])
    if len(parts) >= 2 and parts[0] == "tests":
        return "tests"
    if len(parts) >= 1:
        return parts[0]
    return "<root>"


def describe_status(entry: StatusEntry) -> str:
    if entry.raw_status == "??":
        return "untracked"
    if "D" in entry.raw_status:
        return "deleted"
    if "M" in entry.raw_status:
        return "modified"
    return "other"


def build_report(entries: Iterable[StatusEntry], sample_limit: int) -> dict[str, object]:
    total_status = Counter()
    slices: dict[str, dict[str, object]] = {}
    unmatched: list[str] = []

    for entry in entries:
        total_status[describe_status(entry)] += 1
        rule = classify_slice(entry.path)
        if rule is None:
            unmatched.append(entry.path)
            continue
        payload = slices.setdefault(
            rule.name,
            {
                "phase_hint": rule.phase_hint,
                "description": rule.description,
                "count": 0,
                "status_counts": Counter(),
                "top_paths": Counter(),
                "samples": [],
            },
        )
        payload["count"] = int(payload["count"]) + 1
        payload["status_counts"][describe_status(entry)] += 1
        payload["top_paths"][bucket_top_path(entry.path)] += 1
        if len(payload["samples"]) < sample_limit:
            payload["samples"].append(f"{entry.raw_status} {entry.path}")

    sorted_slices = sorted(slices.items(), key=lambda item: int(item[1]["count"]), reverse=True)
    recommended_next_slice = None
    for preferred in (
        "docs-planning-governance",
        "memory-governance",
        "runtime-session-contract",
        "surface-transport-orchestration",
        "agent-core-and-cli-surface",
        "model-runtime-substrate",
        "interfaces-apps",
    ):
        if preferred in slices:
            recommended_next_slice = preferred
            break

    return {
        "total_dirty_paths": sum(total_status.values()),
        "status_counts": dict(total_status),
        "recommended_next_slice": recommended_next_slice,
        "slices": [
            {
                "name": name,
                "phase_hint": payload["phase_hint"],
                "description": payload["description"],
                "count": payload["count"],
                "status_counts": dict(payload["status_counts"]),
                "top_paths": dict(payload["top_paths"].most_common(5)),
                "samples": list(payload["samples"]),
            }
            for name, payload in sorted_slices
        ],
        "unmatched": sorted(unmatched),
    }


def render_text(report: dict[str, object]) -> str:
    lines = [
        "Mini-Agent dirty worktree slice report",
        f"total_dirty_paths: {report['total_dirty_paths']}",
        f"status_counts: {json.dumps(report['status_counts'], ensure_ascii=False, sort_keys=True)}",
        f"recommended_next_slice: {report['recommended_next_slice'] or 'none'}",
        "",
    ]
    for slice_payload in report["slices"]:
        lines.append(f"[{slice_payload['name']}] ({slice_payload['phase_hint']}) count={slice_payload['count']}")
        lines.append(f"  description: {slice_payload['description']}")
        lines.append(
            "  status_counts: "
            + json.dumps(slice_payload["status_counts"], ensure_ascii=False, sort_keys=True)
        )
        lines.append(
            "  top_paths: "
            + json.dumps(slice_payload["top_paths"], ensure_ascii=False, sort_keys=True)
        )
        if slice_payload["samples"]:
            lines.append("  samples:")
            lines.extend(f"    - {sample}" for sample in slice_payload["samples"])
        lines.append("")
    unmatched = report["unmatched"]
    lines.append(f"unmatched_count: {len(unmatched)}")
    if unmatched:
        lines.extend(f"  - {path}" for path in unmatched[:12])
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(report: dict[str, object]) -> str:
    lines = [
        "# Mini-Agent Dirty Worktree Slice Report",
        "",
        f"- total dirty paths: `{report['total_dirty_paths']}`",
        f"- status counts: `{json.dumps(report['status_counts'], ensure_ascii=False, sort_keys=True)}`",
        f"- recommended next slice: `{report['recommended_next_slice'] or 'none'}`",
        "",
    ]
    for slice_payload in report["slices"]:
        lines.append(f"## `{slice_payload['name']}`")
        lines.append("")
        lines.append(f"- phase hint: `{slice_payload['phase_hint']}`")
        lines.append(f"- description: {slice_payload['description']}")
        lines.append(
            f"- status counts: `{json.dumps(slice_payload['status_counts'], ensure_ascii=False, sort_keys=True)}`"
        )
        lines.append(f"- top paths: `{json.dumps(slice_payload['top_paths'], ensure_ascii=False, sort_keys=True)}`")
        if slice_payload["samples"]:
            lines.append("- sample paths:")
            lines.extend(f"  - `{sample}`" for sample in slice_payload["samples"])
        lines.append("")
    unmatched = report["unmatched"]
    lines.append(f"- unmatched count: `{len(unmatched)}`")
    if unmatched:
        lines.append("- unmatched sample:")
        lines.extend(f"  - `{path}`" for path in unmatched[:12])
    return "\n".join(lines).rstrip() + "\n"


def main() -> int:
    args = parse_args()
    try:
        entries = load_status_entries()
    except subprocess.CalledProcessError as exc:
        sys.stderr.write(exc.stderr)
        return exc.returncode

    report = build_report(entries, sample_limit=args.sample_limit)
    if args.format == "json":
        sys.stdout.write(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    elif args.format == "markdown":
        sys.stdout.write(render_markdown(report))
    else:
        sys.stdout.write(render_text(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
