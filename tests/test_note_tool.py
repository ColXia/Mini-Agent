"""Test cases for markdown-based session note tools."""

import tempfile
from pathlib import Path

import pytest

from mini_agent.tools.note_tool import RecallNoteTool, SessionNoteTool


class FakeEmbeddingProvider:
    """Deterministic embedding provider for ranking tests."""

    def embed(self, text: str) -> list[float]:
        normalized = text.lower()
        if "python" in normalized or "event loop" in normalized:
            return [1.0, 0.0]
        if "rust" in normalized or "borrow checker" in normalized:
            return [0.0, 1.0]
        return [0.0, 0.0]


@pytest.mark.asyncio
async def test_record_and_recall_notes():
    """Record notes to long-term and daily memory, then recall them."""
    with tempfile.TemporaryDirectory() as tmpdir:
        memory_root = Path(tmpdir)

        record_tool = SessionNoteTool(memory_root=str(memory_root))
        recall_tool = RecallNoteTool(memory_root=str(memory_root))

        result = await record_tool.execute(
            content="User prefers concise responses",
            category="user_preference",
            scope="both",
        )
        assert result.success

        result = await record_tool.execute(
            content="Project uses Python 3.12",
            category="project_info",
            scope="daily",
        )
        assert result.success

        long_term_file = memory_root / "MEMORY.md"
        assert long_term_file.exists()
        assert "User prefers concise responses" in long_term_file.read_text(encoding="utf-8")
        assert "Project uses Python 3.12" not in long_term_file.read_text(encoding="utf-8")

        daily_files = sorted((memory_root / "memory").glob("*.md"))
        assert len(daily_files) == 1
        daily_content = daily_files[0].read_text(encoding="utf-8")
        assert "User prefers concise responses" in daily_content
        assert "Project uses Python 3.12" in daily_content

        result = await recall_tool.execute()
        assert result.success
        assert "User prefers concise responses" in result.content
        assert "Project uses Python 3.12" in result.content

        result = await recall_tool.execute(category="user_preference")
        assert result.success
        assert "User prefers concise responses" in result.content
        assert "Project uses Python 3.12" not in result.content

        result = await recall_tool.execute(query="Python 3.12")
        assert result.success
        assert "Project uses Python 3.12" in result.content


@pytest.mark.asyncio
async def test_empty_notes():
    """Recall returns a clear message when memory files do not exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        recall_tool = RecallNoteTool(memory_root=tmpdir)
        result = await recall_tool.execute()

        assert result.success
        assert "No notes recorded yet" in result.content


@pytest.mark.asyncio
async def test_note_persistence_across_instances():
    """Notes persist when tool instances are recreated."""
    with tempfile.TemporaryDirectory() as tmpdir:
        record_tool = SessionNoteTool(memory_root=tmpdir)
        result = await record_tool.execute(
            content="Important fact to remember",
            category="test",
            scope="long_term",
        )
        assert result.success

        recall_tool = RecallNoteTool(memory_root=tmpdir)
        result = await recall_tool.execute()

        assert result.success
        assert "Important fact to remember" in result.content


@pytest.mark.asyncio
async def test_hybrid_retrieval_with_optional_embedding():
    """Embedding provider enables semantic matches when keyword search misses."""
    with tempfile.TemporaryDirectory() as tmpdir:
        record_tool = SessionNoteTool(memory_root=tmpdir)
        await record_tool.execute(content="Python async runtime patterns", category="stack")
        await record_tool.execute(content="Rust borrow checker basics", category="stack")

        keyword_only_tool = RecallNoteTool(memory_root=tmpdir)
        keyword_result = await keyword_only_tool.execute(
            query="event loop language",
            use_embedding=False,
        )
        assert keyword_result.success
        assert "No notes matched query" in keyword_result.content

        hybrid_tool = RecallNoteTool(
            memory_root=tmpdir,
            embedding_provider=FakeEmbeddingProvider(),
        )
        hybrid_result = await hybrid_tool.execute(query="event loop language")

        assert hybrid_result.success
        assert "Python async runtime patterns" in hybrid_result.content


@pytest.mark.asyncio
async def test_record_note_supports_topic_tag():
    """record_note can persist optional topic tags for stronger self-save structure."""
    with tempfile.TemporaryDirectory() as tmpdir:
        memory_root = Path(tmpdir)
        record_tool = SessionNoteTool(memory_root=str(memory_root))
        recall_tool = RecallNoteTool(memory_root=str(memory_root))

        result = await record_tool.execute(
            content="Executor budget threshold updated",
            category="runtime_policy",
            topic="execution",
            scope="long_term",
        )
        assert result.success
        assert "topic: execution" in result.content

        memory_text = (memory_root / "MEMORY.md").read_text(encoding="utf-8")
        assert "[topic:execution] Executor budget threshold updated" in memory_text

        recall_result = await recall_tool.execute(query="topic:execution")
        assert recall_result.success
        assert "Executor budget threshold updated" in recall_result.content


@pytest.mark.asyncio
async def test_record_note_uses_discovered_memory_anchor():
    """When called from nested workspace, note tool writes to discovered project memory root."""
    with tempfile.TemporaryDirectory() as tmpdir:
        project_root = Path(tmpdir) / "project"
        nested_workspace = project_root / "src" / "feature"
        nested_workspace.mkdir(parents=True, exist_ok=True)

        (project_root / "GEMINI.md").write_text("# Project Memory\n", encoding="utf-8")
        (project_root / "MEMORY.md").write_text("# Long-Term Memory\n\n", encoding="utf-8")

        record_tool = SessionNoteTool(memory_root=str(nested_workspace))
        recall_tool = RecallNoteTool(memory_root=str(nested_workspace))

        result = await record_tool.execute(
            content="Prefer deterministic planner transitions",
            category="agent",
            scope="long_term",
        )
        assert result.success

        project_memory_file = project_root / "MEMORY.md"
        nested_memory_file = nested_workspace / "MEMORY.md"
        assert "Prefer deterministic planner transitions" in project_memory_file.read_text(encoding="utf-8")
        assert not nested_memory_file.exists()

        recall_result = await recall_tool.execute(query="deterministic planner")
        assert recall_result.success
        assert "source: MEMORY.md" in recall_result.content
