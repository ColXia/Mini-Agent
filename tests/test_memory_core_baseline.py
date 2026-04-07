"""Baseline tests for mini memory core kickoff."""

from __future__ import annotations

from pathlib import Path

from mini_agent.memory import MemoriaEngine, append_memory_note, discover_memory_layout, ensure_memory_file


def test_memoria_engine_lifecycle_and_retrieval():
    engine = MemoriaEngine(max_working=1, max_stm=1, max_ltm=2)

    first = engine.save("alpha memory context", importance=0.4)
    second = engine.save("beta execution policy", importance=0.8)
    third = engine.save("gamma observability trend", importance=0.6)

    assert first.engram_id != second.engram_id
    assert second.engram_id != third.engram_id

    stats = engine.stats()
    assert stats["working"] <= 1
    assert stats["stm"] <= 1
    assert stats["ltm"] <= 2

    matches = engine.retrieve("execution policy", limit=2)
    assert len(matches) >= 1
    assert "execution policy" in matches[0].content


def test_memoria_engine_empty_query_prefers_recent_entries():
    engine = MemoriaEngine(max_working=3, max_stm=5, max_ltm=5)
    engine.save("old note")
    latest = engine.save("newer note")

    results = engine.retrieve("", limit=1)
    assert len(results) == 1
    assert results[0].engram_id == latest.engram_id


def test_memory_file_layout_discovery_and_append(tmp_path: Path):
    workspace = (tmp_path / "workspace").resolve()
    nested = workspace / "sub" / "deep"
    nested.mkdir(parents=True, exist_ok=True)

    gemini_file = workspace / "GEMINI.md"
    gemini_file.write_text("# GEMINI\n", encoding="utf-8")

    memory_file = workspace / "MEMORY.md"
    ensure_memory_file(memory_file)

    layout = discover_memory_layout(nested)
    assert layout.anchor_dir == workspace
    assert layout.gemini_file == gemini_file
    assert layout.memory_file == memory_file

    append_memory_note(
        memory_file,
        heading="P12 kickoff",
        content="memory core baseline landed",
        timestamp_utc="2026-04-05T08:00:00+00:00",
    )
    text = memory_file.read_text(encoding="utf-8")
    assert "## P12 kickoff" in text
    assert "memory core baseline landed" in text
