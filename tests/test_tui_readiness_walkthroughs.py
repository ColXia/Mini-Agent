from __future__ import annotations

import asyncio
from pathlib import Path

import scripts.tui_interaction_walkthrough as tui_interaction_walkthrough
import scripts.tui_manual_checklist as tui_manual_checklist


def test_tui_manual_checklist_context_check_passes(tmp_path: Path) -> None:
    result = asyncio.run(tui_manual_checklist._check_context(tmp_path / "context"))

    assert result.ok is True
    assert result.name == "context"
    assert "Context diagnostics:" in result.excerpts["context_stats"]
    assert "Relevant knowledge base context -> Hybrid retrieval combines BM25 and RRF." in result.excerpts["context_show"]


def test_tui_interaction_walkthrough_includes_context_commands_step(tmp_path: Path) -> None:
    results = asyncio.run(tui_interaction_walkthrough._run_walkthrough(tmp_path / "walkthrough"))

    context_step = next(item for item in results if item.name == "context-commands")
    assert context_step.ok is True
    assert "Context diagnostics:" in context_step.excerpts["context_stats"]
    assert "Relevant knowledge base context -> Hybrid retrieval combines BM25 and RRF." in context_step.excerpts["context_show"]
