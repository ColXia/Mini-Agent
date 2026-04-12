from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from mini_agent.memory.consolidation import MemoryConsolidationPipeline
from mini_agent.memory.memoria_runtime import WorkspaceMemoriaRuntime
from mini_agent.memory.runtime_task_memory import TurnRuntimeTaskMemory
from mini_agent.memory.service import MemoryService
from mini_agent.session.persistence import SessionPersistence


@dataclass
class FileSnapshot:
    exists: bool
    content: str


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _snapshot_file(path: Path) -> FileSnapshot:
    if not path.exists():
        return FileSnapshot(exists=False, content="")
    return FileSnapshot(exists=True, content=path.read_text(encoding="utf-8"))


def _restore_file(path: Path, snapshot: FileSnapshot) -> None:
    if snapshot.exists:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(snapshot.content, encoding="utf-8")
        return
    if path.exists():
        path.unlink()


def _record(results: list[CheckResult], name: str, ok: bool, detail: str) -> None:
    results.append(CheckResult(name=name, ok=ok, detail=detail))


def _write_summary(summary_path: Path, results: list[CheckResult], *, sandbox_root: Path) -> None:
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at_utc": _utc_now().isoformat(),
        "sandbox_root": str(sandbox_root),
        "passed": all(item.ok for item in results),
        "checks": [asdict(item) for item in results],
    }
    summary_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def run_acceptance(*, repo_root: Path, keep_artifacts: bool) -> int:
    run_id = _utc_now().strftime("%Y%m%dT%H%M%SZ")
    acceptance_root = repo_root / "workspace" / ".acceptance-memory"
    sandbox_root = acceptance_root / run_id
    latest_summary_path = acceptance_root / "latest-summary.json"
    workspace_a = sandbox_root / "workspace-a"
    workspace_b = sandbox_root / "workspace-b"
    global_root = sandbox_root / "global"
    state_root = sandbox_root / "state"
    session_store_dir = sandbox_root / "sessions"
    summary_path = sandbox_root / "summary.json"

    root_memory_file = repo_root / "MEMORY.md"
    root_daily_file = repo_root / "memory" / f"{date.today().isoformat()}.md"
    root_memory_before = _snapshot_file(root_memory_file)
    root_daily_before = _snapshot_file(root_daily_file)

    results: list[CheckResult] = []
    cleanup_requested = not keep_artifacts

    try:
        workspace_a.mkdir(parents=True, exist_ok=True)
        workspace_b.mkdir(parents=True, exist_ok=True)
        global_root.mkdir(parents=True, exist_ok=True)
        state_root.mkdir(parents=True, exist_ok=True)
        session_store_dir.mkdir(parents=True, exist_ok=True)

        memory_a = MemoryService(
            workspace_a,
            session_store_dir=session_store_dir,
            global_memory_root=global_root,
        )
        memory_b = MemoryService(
            workspace_b,
            session_store_dir=session_store_dir,
            global_memory_root=global_root,
        )

        now = datetime.now()
        memory_a.append_note(
            content="验收：工作区 A 默认保持 TUI/CLI-first。",
            category="operator_note",
            scope="long_term",
            now=now,
        )
        memory_b.append_note(
            content="验收：工作区 B 保持独立的部署笔记。",
            category="operator_note",
            scope="long_term",
            now=now,
        )
        memory_a.add_profile_fact(fact="验收脚本写入：默认中文，先结论后步骤。")

        persistence = SessionPersistence(session_store_dir)
        timestamp = _utc_now().isoformat()
        persistence.save_session(
            session_id="accept-a-history",
            workspace_dir=str(workspace_a),
            created_at=timestamp,
            updated_at=timestamp,
            messages=[
                {"role": "user", "content": "Keep the opencode-style sidebar dominant."},
                {
                    "role": "assistant",
                    "content": "Workspace A keeps the opencode-style sidebar dominant.",
                },
            ],
        )
        persistence.save_session(
            session_id="accept-b-history",
            workspace_dir=str(workspace_b),
            created_at=timestamp,
            updated_at=timestamp,
            messages=[
                {"role": "user", "content": "Use a separate deployment runbook."},
                {
                    "role": "assistant",
                    "content": "Workspace B keeps a separate deployment runbook.",
                },
            ],
        )

        runtime_writer = TurnRuntimeTaskMemory(str(workspace_a), state_root=str(state_root))
        runtime_result = runtime_writer.process_turn(
            stop_reason="end_turn",
            turn_context=SimpleNamespace(session_id="accept-a-runtime"),
            assistant_message="Gateway shared sessions should route reply targets through the active surface.",
            turn_messages=[
                SimpleNamespace(role="user", content="How should shared-session reply targets be routed?"),
                SimpleNamespace(
                    role="assistant",
                    content="Gateway shared sessions should route reply targets through the active surface.",
                ),
            ],
        )
        runtime_a = WorkspaceMemoriaRuntime(workspace_a, state_root=state_root)
        runtime_b = WorkspaceMemoriaRuntime(workspace_b, state_root=state_root)

        if runtime_result.engram_id:
            runtime_a.promote_session_memory_to_workspace_shared(
                session_id="accept-a-runtime",
                engram_id=runtime_result.engram_id,
            )

        runtime_hits = runtime_a.retrieve_for_turn(
            session_id="accept-a-runtime",
            query="reply targets active surface",
            session_limit=2,
            shared_limit=2,
        )
        session_hits = memory_a.search_sessions(
            query="sidebar dominant",
            limit=10,
            workspace_anchor_dir=str(workspace_a),
            exclude_session_id="accept-current",
        )

        pipeline = MemoryConsolidationPipeline(
            session_store_dir=session_store_dir,
            workspace_dir=workspace_a,
        )
        consolidation = pipeline.run(phase="all", max_jobs=8, top_n=10)

        workspace_a_text = memory_a.long_term_file.read_text(encoding="utf-8")
        workspace_b_text = memory_b.long_term_file.read_text(encoding="utf-8")
        global_profile = memory_a.profile()
        global_profile_text = Path(str(global_profile["user_file"])).read_text(encoding="utf-8")

        _record(
            results,
            "global-profile-isolated",
            Path(str(global_profile["user_file"])).resolve() == (global_root / "USER.md").resolve()
            and "默认中文，先结论后步骤" in global_profile_text
            and not (workspace_a / "USER.md").exists()
            and not (workspace_b / "USER.md").exists(),
            f"user_file={global_profile['user_file']}",
        )
        _record(
            results,
            "workspace-durable-isolated",
            memory_a.long_term_file == workspace_a / "MEMORY.md"
            and memory_b.long_term_file == workspace_b / "MEMORY.md"
            and "工作区 A 默认保持 TUI/CLI-first" in workspace_a_text
            and "工作区 B 保持独立的部署笔记" in workspace_b_text
            and "工作区 B 保持独立的部署笔记" not in workspace_a_text
            and "工作区 A 默认保持 TUI/CLI-first" not in workspace_b_text,
            f"workspace_a_file={memory_a.long_term_file}; workspace_b_file={memory_b.long_term_file}",
        )
        _record(
            results,
            "runtime-workspace-anchor-isolated",
            runtime_a.anchor_dir == workspace_a
            and runtime_b.anchor_dir == workspace_b
            and runtime_a.workspace_hash != runtime_b.workspace_hash,
            f"hash_a={runtime_a.workspace_hash}; hash_b={runtime_b.workspace_hash}",
        )
        _record(
            results,
            "runtime-shared-promotion-works",
            bool(runtime_result.stored)
            and len(runtime_hits["session_hits"]) >= 1
            and len(runtime_hits["shared_hits"]) >= 1,
            f"stored={runtime_result.stored}; session_hits={len(runtime_hits['session_hits'])}; shared_hits={len(runtime_hits['shared_hits'])}",
        )
        _record(
            results,
            "session-search-scoped-to-workspace",
            bool(session_hits)
            and {item["session_id"] for item in session_hits} == {"accept-a-history"}
            and {item["workspace_anchor_dir"] for item in session_hits} == {str(workspace_a)},
            f"hits={[item['session_id'] for item in session_hits]}",
        )
        _record(
            results,
            "consolidation-scoped-to-workspace",
            consolidation["workspace_anchor_dir"] == str(workspace_a)
            and "opencode-style sidebar dominant" in workspace_a_text
            and "separate deployment runbook" not in workspace_a_text,
            f"workspace_anchor_dir={consolidation['workspace_anchor_dir']}",
        )

        root_memory_after = _snapshot_file(root_memory_file)
        root_daily_after = _snapshot_file(root_daily_file)
        root_untouched = (
            root_memory_after.exists == root_memory_before.exists
            and root_memory_after.content == root_memory_before.content
            and root_daily_after.exists == root_daily_before.exists
            and root_daily_after.content == root_daily_before.content
        )
        _record(
            results,
            "repo-root-memory-untouched",
            root_untouched,
            f"root_memory_changed={root_memory_after.content != root_memory_before.content}; root_daily_changed={root_daily_after.content != root_daily_before.content}",
        )

    finally:
        root_memory_after = _snapshot_file(root_memory_file)
        root_daily_after = _snapshot_file(root_daily_file)
        if (
            root_memory_after.exists != root_memory_before.exists
            or root_memory_after.content != root_memory_before.content
        ):
            _restore_file(root_memory_file, root_memory_before)
        if (
            root_daily_after.exists != root_daily_before.exists
            or root_daily_after.content != root_daily_before.content
        ):
            _restore_file(root_daily_file, root_daily_before)

        _write_summary(summary_path, results, sandbox_root=sandbox_root)
        _write_summary(latest_summary_path, results, sandbox_root=sandbox_root)

        passed = all(item.ok for item in results)
        print(f"Workspace Memory Acceptance: {'PASS' if passed else 'FAIL'}")
        print(f"Sandbox: {sandbox_root}")
        print(f"Summary: {summary_path}")
        print(f"Latest Summary: {latest_summary_path}")
        for item in results:
            status = "PASS" if item.ok else "FAIL"
            print(f"- [{status}] {item.name}: {item.detail}")

        if cleanup_requested and passed:
            shutil.rmtree(sandbox_root, ignore_errors=True)
            print(f"Cleaned sandbox: {sandbox_root}")
        elif not passed:
            print("Artifacts kept for inspection because at least one check failed.")

    return 0 if all(item.ok for item in results) else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Run workspace-memory acceptance checks.")
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root. Defaults to the current Mini-Agent repo.",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Keep the sandbox directory even when all checks pass.",
    )
    args = parser.parse_args()
    return run_acceptance(repo_root=args.repo_root.resolve(), keep_artifacts=bool(args.keep_artifacts))


if __name__ == "__main__":
    raise SystemExit(main())
