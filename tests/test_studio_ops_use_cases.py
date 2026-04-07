from __future__ import annotations

from datetime import datetime
from pathlib import Path

from mini_agent.application import StudioOpsUseCases
from mini_agent.interfaces import StudioProviderUpsertRequest
from mini_agent.tools.note_tool import MarkdownMemoryStore


def _build_use_cases(repo_root: Path, workspace_root: Path) -> StudioOpsUseCases:
    repo_root.mkdir(parents=True, exist_ok=True)
    workspace_root.mkdir(parents=True, exist_ok=True)
    return StudioOpsUseCases(repo_root=repo_root, workspace_root=workspace_root)


def test_studio_ops_use_cases_provider_crud(tmp_path: Path) -> None:
    repo_root = (tmp_path / "repo").resolve()
    workspace_root = (tmp_path / "workspace").resolve()
    catalog_path = (workspace_root / "providers.json").resolve()
    use_cases = _build_use_cases(repo_root=repo_root, workspace_root=workspace_root)

    listed = use_cases.list_providers(catalog_path=str(catalog_path))
    assert listed.provider_count == 0

    created = use_cases.create_provider(
        payload=StudioProviderUpsertRequest(
            name="OpenAI Primary",
            api_type="openai",
            api_base="https://api.openai.example.com/v1",
            api_key="sk-openai-primary-0001",
            models=["gpt-4o-mini"],
            enabled=True,
            priority=8,
            timeout=45,
            headers={},
        ),
        catalog_path=str(catalog_path),
    )
    assert created.id == "openai-primary"
    assert created.catalog_path == str(catalog_path)

    updated = use_cases.update_provider(
        provider_id=created.id,
        payload=StudioProviderUpsertRequest(
            name="OpenAI Primary Updated",
            api_type="openai",
            api_base="https://api.openai.example.com/v1",
            api_key="sk-openai-primary-9999",
            models=["gpt-4o-mini", "gpt-4.1-mini"],
            enabled=False,
            priority=3,
            timeout=60,
            headers={"x-studio": "1"},
        ),
        catalog_path=str(catalog_path),
    )
    assert updated.id == created.id
    assert updated.enabled is False
    assert sorted(updated.models) == ["gpt-4.1-mini", "gpt-4o-mini"]

    health = use_cases.get_provider_health(provider_id=created.id, catalog_path=str(catalog_path))
    assert health.provider_id == created.id
    assert health.breaker_state in {"closed", "open", "half_open"}

    deleted = use_cases.delete_provider(provider_id=created.id, catalog_path=str(catalog_path))
    assert deleted.status == "deleted"

    after_delete = use_cases.list_providers(catalog_path=str(catalog_path))
    assert after_delete.provider_count == 0


def test_studio_ops_use_cases_memory_summary_search_daily(tmp_path: Path) -> None:
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
