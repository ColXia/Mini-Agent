"""Tests for docling parse tool baseline (P16 T4.1)."""

from __future__ import annotations

import json
from pathlib import Path
from zipfile import ZipFile

import pytest

from mini_agent.config import AgentConfig, Config, LLMConfig, SecurityConfig, ToolsConfig
from mini_agent.runtime.support.tooling import add_workspace_tools, resolve_runtime_policy
from mini_agent.tools.docling_parse import (
    DoclingParseTool,
    DoclingParser,
    DoclingParseResult,
    DoclingUnavailableError,
)
from mini_agent.workspace_runtime import DefaultOutsideZonePolicy, DirectWorkspaceExecutor, WorkspaceAccessScope


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


def test_docling_parser_binary_asset_without_adapter_raises(tmp_path):
    source = tmp_path / "image.png"
    source.write_bytes(b"\x89PNG\r\n\x1a\n")

    parser = DoclingParser()
    with pytest.raises(DoclingUnavailableError):
        parser.parse_file(path=source, output_format="markdown")


def test_docling_parser_builtin_docx_parse(tmp_path):
    source = tmp_path / "report.docx"
    with ZipFile(source, "w") as archive:
        archive.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
              <w:body>
                <w:p><w:r><w:t>Hello Mini-Agent</w:t></w:r></w:p>
                <w:p><w:r><w:t>Second paragraph</w:t></w:r></w:p>
              </w:body>
            </w:document>
            """,
        )

    parser = DoclingParser()
    result = parser.parse_file(path=source, output_format="markdown")

    assert result.used_docling is True
    assert result.metadata["parser"] == "builtin_ooxml_docx"
    assert "Hello Mini-Agent" in result.content
    assert "Second paragraph" in result.content


def test_docling_parser_builtin_pptx_parse(tmp_path):
    source = tmp_path / "slides.pptx"
    with ZipFile(source, "w") as archive:
        archive.writestr(
            "ppt/slides/slide1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <p:sld
              xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld>
                <p:spTree>
                  <p:sp>
                    <p:txBody>
                      <a:p><a:r><a:t>Mini-Agent Slide 1</a:t></a:r></a:p>
                    </p:txBody>
                  </p:sp>
                </p:spTree>
              </p:cSld>
            </p:sld>
            """,
        )
        archive.writestr(
            "ppt/slides/slide2.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <p:sld
              xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"
              xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">
              <p:cSld>
                <p:spTree>
                  <p:sp>
                    <p:txBody>
                      <a:p><a:r><a:t>Mini-Agent Slide 2</a:t></a:r></a:p>
                    </p:txBody>
                  </p:sp>
                </p:spTree>
              </p:cSld>
            </p:sld>
            """,
        )

    parser = DoclingParser()
    result = parser.parse_file(path=source, output_format="markdown")

    assert result.used_docling is True
    assert result.metadata["parser"] == "builtin_ooxml_pptx"
    assert "# Slide 1" in result.content
    assert "Mini-Agent Slide 1" in result.content
    assert "# Slide 2" in result.content
    assert "Mini-Agent Slide 2" in result.content


def test_docling_parser_builtin_xlsx_parse(tmp_path):
    source = tmp_path / "table.xlsx"
    with ZipFile(source, "w") as archive:
        archive.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <workbook
              xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
              xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
              <sheets>
                <sheet name="Tasks" sheetId="1" r:id="rId1"/>
              </sheets>
            </workbook>
            """,
        )
        archive.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
            <Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
              <Relationship
                Id="rId1"
                Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet"
                Target="worksheets/sheet1.xml"/>
            </Relationships>
            """,
        )
        archive.writestr(
            "xl/sharedStrings.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <si><t>Task</t></si>
              <si><t>Status</t></si>
              <si><t>Build Mini-Agent</t></si>
              <si><t>Done</t></si>
            </sst>
            """,
        )
        archive.writestr(
            "xl/worksheets/sheet1.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
            <worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
              <sheetData>
                <row r="1">
                  <c r="A1" t="s"><v>0</v></c>
                  <c r="B1" t="s"><v>1</v></c>
                </row>
                <row r="2">
                  <c r="A2" t="s"><v>2</v></c>
                  <c r="B2" t="s"><v>3</v></c>
                </row>
              </sheetData>
            </worksheet>
            """,
        )

    parser = DoclingParser()
    result = parser.parse_file(path=source, output_format="markdown")

    assert result.used_docling is True
    assert result.metadata["parser"] == "builtin_ooxml_xlsx"
    assert "## Sheet: Tasks" in result.content
    assert "Task\tStatus" in result.content
    assert "Build Mini-Agent\tDone" in result.content


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


def test_docling_parser_rejects_outside_source_when_workspace_executor_bound(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside", encoding="utf-8")

    parser = DoclingParser(workspace_executor=DirectWorkspaceExecutor(workspace))

    with pytest.raises(PermissionError, match="escapes workspace root"):
        parser.parse_file(path=outside, output_format="markdown")


def test_docling_parser_allows_outside_source_read_when_outside_zone_scope_enabled(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("outside via outside-zone", encoding="utf-8")

    parser = DoclingParser(
        workspace_executor=DirectWorkspaceExecutor(
            workspace,
            scope=WorkspaceAccessScope.WITH_OUTSIDE_ZONE,
            outside_zone_policy=DefaultOutsideZonePolicy(protected_roots=()),
        )
    )

    result = parser.parse_file(path=outside, output_format="markdown")

    assert result.used_docling is False
    assert "outside via outside-zone" in result.content


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


def _make_config() -> Config:
    return Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(enable_mcp=False, enable_skills=False),
        security=SecurityConfig(),
    )


def test_workspace_tooling_includes_docling_parse_tool(tmp_path: Path) -> None:
    config = _make_config()
    engine = resolve_runtime_policy(config)

    tools: list[object] = []
    add_workspace_tools(
        tools,
        config,
        tmp_path,
        policy_engine=engine,
    )

    assert any(getattr(tool, "name", None) == "docling_parse" for tool in tools)


def test_workspace_tooling_skips_docling_parse_when_file_tools_disabled(tmp_path: Path) -> None:
    config = Config(
        llm=LLMConfig(api_key="test-key"),
        agent=AgentConfig(),
        tools=ToolsConfig(
            enable_mcp=False,
            enable_skills=False,
            enable_file_tools=False,
        ),
        security=SecurityConfig(),
    )
    engine = resolve_runtime_policy(config)

    tools: list[object] = []
    add_workspace_tools(
        tools,
        config,
        tmp_path,
        policy_engine=engine,
    )

    assert all(getattr(tool, "name", None) != "docling_parse" for tool in tools)


def test_docling_parser_uses_ocr_adapter_for_images(tmp_path: Path) -> None:
    source = tmp_path / "scan.png"
    source.write_bytes(b"fake-image")

    parser = DoclingParser(
        ocr_adapter=lambda path, output_format, enable_ocr: {
            "source_path": str(path),
            "output_format": output_format,
            "content": "ocr text",
            "used_docling": True,
            "metadata": {"parser": "fake_ocr", "enable_ocr": enable_ocr},
        }
    )

    result = parser.parse_file(path=source, output_format="markdown", enable_ocr=True)

    assert result.used_docling is True
    assert result.content == "ocr text"
    assert result.metadata["parser"] == "fake_ocr"
