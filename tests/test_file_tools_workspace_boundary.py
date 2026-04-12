from __future__ import annotations

from pathlib import Path

import pytest

from mini_agent.tools.file_tools import EditTool, ReadTool, WriteTool


@pytest.mark.asyncio
async def test_read_tool_rejects_absolute_path_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    tool = ReadTool(workspace_dir=str(workspace))
    result = await tool.execute(path=str(outside))

    assert result.success is False
    assert "escapes workspace root" in str(result.error or "").lower()


@pytest.mark.asyncio
async def test_write_tool_rejects_parent_traversal_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    tool = WriteTool(workspace_dir=str(workspace))
    result = await tool.execute(path="../outside.txt", content="blocked")

    assert result.success is False
    assert "escapes workspace root" in str(result.error or "").lower()
    assert (tmp_path / "outside.txt").exists() is False


@pytest.mark.asyncio
async def test_edit_tool_rejects_absolute_path_outside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("hello outside", encoding="utf-8")

    tool = EditTool(workspace_dir=str(workspace))
    result = await tool.execute(
        path=str(outside),
        old_str="hello",
        new_str="blocked",
    )

    assert result.success is False
    assert "escapes workspace root" in str(result.error or "").lower()
    assert outside.read_text(encoding="utf-8") == "hello outside"
