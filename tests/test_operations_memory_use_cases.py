from __future__ import annotations

from datetime import datetime
from pathlib import Path

from mini_agent.application.use_cases.operations_memory_use_cases import MemoryOperationsUseCases
from mini_agent.tools.note_tool import MarkdownMemoryStore


def _build_use_cases(repo_root: Path, workspace_root: Path) -> MemoryOperationsUseCases:
    repo_root.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    return MemoryOperationsUseCases(repo_root=repo_root, workspace_root=workspace_root)


def test_memory_operations_use_cases_summary_search_daily(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    workspace_root = (tmp_path / "workspace").resolve()
    use_cases = _build_use_cases(repo_root=repo_root, workspace_root=workspace_root)

    store = MarkdownMemoryStore(memory_root=str(workspace_root))
    now = datetime.now()
    store.append_note(content="alpha launch decision", category="planning", scope="long_term", now=now)
    store.append_note(content="alpha rollout today", category="daily", scope="daily", now=now)
    day = now.date().isoformat()

    summary = use_cases.get_memory_summary(workspace_dir=str(workspace_root))
    assert summary.workspace_dir == str(workspace_root)
    assert summary.notes_count >= 2
    assert "planning" in summary.categories

    search = use_cases.search_memory(query="alpha", limit=10, workspace_dir=str(workspace_root))
    assert search.total >= 2
    assert any("alpha" in item.content for item in search.items)

    daily = use_cases.get_memory_daily(day=day, workspace_dir=str(workspace_root))
    assert daily.day == day
    assert daily.note_count >= 1
    assert "alpha rollout today" in daily.content
