"""Tests for docling parse tool baseline (P16 T4.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mini_agent.tools.docling_parse import (
    DoclingParseTool,
    DoclingParser,
    DoclingParseResult,
    DoclingUnavailableError,
)


def test_docling_parser_text_fallback_markdown(tmp_path):
    source = tmp_path / "notes.txt"
    source.write_text("hello mini-agent", encoding="utf-8")

    parser = DoclingParser()
    result = parser.parse_file(path=source, output_format="markdown")

    assert result.used_docling is False
    assert result.output_format == "markdown"
    assert "hello mini-agent" in result.content


def test_docling_parser_text_fallback_json_output(tmp_path):
    source = tmp_path / "index.md"
    source.write_text("# Title\nbody", encoding="utf-8")

    parser = DoclingParser()
    result = parser.parse_file(path=source, output_format="json")
    payload = json.loads(result.content)

    assert payload["source_path"] == str(source.resolve())
    assert payload["extension"] == ".md"
    assert "Title" in payload["text"]


def test_docling_parser_binary_without_adapter_raises(tmp_path):
    source = tmp_path / "report.pdf"
    source.write_bytes(b"%PDF-1.7")

    parser = DoclingParser()
    with pytest.raises(DoclingUnavailableError):
        parser.parse_file(path=source, output_format="markdown")


def test_docling_parser_custom_adapter_for_binary(tmp_path):
    source = tmp_path / "slides.pptx"
    source.write_bytes(b"pptx-binary")

    def _adapter(path: Path, output_format: str, enable_ocr: bool):  # noqa: ARG001
        return DoclingParseResult(
            source_path=str(path),
            output_format=output_format,
            content="converted content",
            used_docling=True,
            metadata={"adapter": "stub"},
        )

    parser = DoclingParser(adapter=_adapter)
    result = parser.parse_file(path=source, output_format="html", enable_ocr=True)

    assert result.used_docling is True
    assert result.output_format == "html"
    assert result.content == "converted content"


@pytest.mark.asyncio
async def test_docling_parse_tool_execute_success_and_failure(tmp_path):
    source = tmp_path / "plain.txt"
    source.write_text("abc", encoding="utf-8")

    tool = DoclingParseTool(parser=DoclingParser())
    ok = await tool.execute(path=str(source), output_format="markdown")
    failed = await tool.execute(path=str(tmp_path / "missing.txt"), output_format="markdown")

    assert ok.success is True
    payload = json.loads(ok.content)
    assert payload["used_docling"] is False
    assert "abc" in payload["content"]
    assert failed.success is False
    assert "not found" in (failed.error or "").lower()
