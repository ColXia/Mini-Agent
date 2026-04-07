"""Tests for P12 T0.7 user modeling baseline."""

from __future__ import annotations

from pathlib import Path
import tempfile

import pytest

from mini_agent.memory.builtin_memory import BuiltinMemoryProvider
from mini_agent.tools.user_modeling import UserModelingTool


def test_builtin_memory_provider_entry_management_and_search():
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)
        provider = BuiltinMemoryProvider(root)

        initial = provider.profile()
        assert initial["fact_count"] == 0
        assert Path(initial["user_file"]).exists()

        added_a = provider.add_fact("User prefers deterministic planner transitions")
        assert added_a["status"] == "added"
        added_b = provider.add_fact("User uses Windows PowerShell by default")
        assert added_b["status"] == "added"

        duplicate = provider.add_fact("User prefers deterministic planner transitions")
        assert duplicate["status"] == "exists"
        assert duplicate["changed"] is False

        hits = provider.search("planner transitions", limit=5)
        assert len(hits) == 1
        assert "deterministic planner transitions" in hits[0]["fact"].lower()

        replaced = provider.replace_fact(
            match="planner transitions",
            fact="User prefers strict deterministic transitions in rollout planning",
        )
        assert replaced["status"] == "replaced"
        assert replaced["replaced"] == 1

        removed = provider.remove_fact(match="windows powershell")
        assert removed["status"] == "removed"
        assert removed["removed"] == 1

        final_snapshot = provider.profile()
        assert final_snapshot["fact_count"] == 1
        assert "strict deterministic transitions" in final_snapshot["facts"][0].lower()


def test_builtin_memory_provider_uses_discovered_anchor():
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        nested_workspace = project_root / "src" / "feature"
        nested_workspace.mkdir(parents=True, exist_ok=True)

        (project_root / "GEMINI.md").write_text("# Project Memory\n", encoding="utf-8")
        (project_root / "MEMORY.md").write_text("# Long-Term Memory\n\n", encoding="utf-8")

        provider = BuiltinMemoryProvider(nested_workspace)
        provider.add_fact("User timezone is Asia/Shanghai")

        root_user_file = project_root / "USER.md"
        nested_user_file = nested_workspace / "USER.md"
        assert root_user_file.exists()
        assert not nested_user_file.exists()
        assert "Asia/Shanghai" in root_user_file.read_text(encoding="utf-8")

        snapshot = provider.prefetch()
        assert snapshot["anchor_dir"] == str(project_root.resolve())
        provider.sync_turn(user_message="hello", assistant_message="hi")
        provider.on_delegation(delegated_task="summarize logs", delegation_summary="done")
        provider.on_session_end()


@pytest.mark.asyncio
async def test_user_modeling_tool_profile_search_conclude_replace_remove():
    with tempfile.TemporaryDirectory() as tmpdir:
        tool = UserModelingTool(memory_root=tmpdir)

        empty_profile = await tool.execute(action="profile")
        assert empty_profile.success
        assert "(no facts yet)" in empty_profile.content

        conclude = await tool.execute(
            action="conclude",
            fact="User prefers concise responses for quick operational checks",
        )
        assert conclude.success
        assert "status=added" in conclude.content

        search = await tool.execute(action="search", query="concise responses")
        assert search.success
        assert "concise responses" in search.content

        replace = await tool.execute(
            action="replace",
            match="concise responses",
            fact="User prefers concise updates but detailed architecture plans",
        )
        assert replace.success
        assert "status=replaced" in replace.content

        profile = await tool.execute(action="profile")
        assert profile.success
        assert "detailed architecture plans" in profile.content

        remove = await tool.execute(action="remove", match="detailed architecture plans")
        assert remove.success
        assert "status=removed" in remove.content

        invalid = await tool.execute(action="unknown")
        assert invalid.success is False
        assert "Invalid action" in (invalid.error or "")
