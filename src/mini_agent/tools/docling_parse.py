"""Docling parse tool baseline with lean fallback and batch support."""

from __future__ import annotations

from dataclasses import dataclass, field
import html
import json
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any, Callable
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from mini_agent.tools.base import Tool, ToolResult


SUPPORTED_INPUT_EXTENSIONS = {
    ".pdf",
    ".docx",
    ".pptx",
    ".xlsx",
    ".html",
    ".htm",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".txt",
    ".md",
    ".json",
}
FALLBACK_TEXT_EXTENSIONS = {".txt", ".md", ".json", ".html", ".htm"}
SUPPORTED_OUTPUT_FORMATS = {"markdown", "html", "json"}


class DoclingParseError(RuntimeError):
    """Base docling parser error."""


class DoclingUnavailableError(DoclingParseError):
    """Raised when binary parsing needs docling backend but none is configured."""


@dataclass(frozen=True)
class DoclingParseResult:
    """Normalized parse output."""

    source_path: str
    output_format: str
    content: str
    used_docling: bool
    metadata: dict[str, Any] = field(default_factory=dict)


DoclingParserAdapter = Callable[[Path, str, bool], DoclingParseResult | dict[str, Any] | str]


class DoclingParser:
    """Parser facade that supports adapter injection and text fallback."""

    def __init__(self, adapter: DoclingParserAdapter | None = None) -> None:
        self._adapter = adapter

    def parse_file(
        self,
        *,
        path: str | Path,
        output_format: str = "markdown",
        enable_ocr: bool = False,
    ) -> DoclingParseResult:
        source = Path(path).expanduser().resolve()
        fmt = self._normalize_output_format(output_format)

        if not source.exists() or not source.is_file():
            raise DoclingParseError(f"document file not found: {source}")

        ext = source.suffix.lower()
        if ext not in SUPPORTED_INPUT_EXTENSIONS:
            raise DoclingParseError(f"unsupported document extension: {ext or '<none>'}")

        if self._adapter is not None:
            raw = self._adapter(source, fmt, bool(enable_ocr))
            return self._coerce_adapter_result(source=source, output_format=fmt, raw=raw)

        if ext in FALLBACK_TEXT_EXTENSIONS:
            return self._parse_text_fallback(source=source, output_format=fmt)

        builtin = self._parse_builtin_binary(
            source=source,
            output_format=fmt,
            enable_ocr=bool(enable_ocr),
        )
        if builtin is not None:
            return builtin

        raise DoclingUnavailableError(
            "docling backend is not configured for binary document parsing; provide an adapter."
        )

    def parse_batch(
        self,
        *,
        paths: list[str | Path],
        output_format: str = "markdown",
        enable_ocr: bool = False,
    ) -> list[DoclingParseResult]:
        results: list[DoclingParseResult] = []
        for item in paths:
            results.append(
                self.parse_file(
                    path=item,
                    output_format=output_format,
                    enable_ocr=enable_ocr,
                )
            )
        return results

    @staticmethod
    def _normalize_output_format(value: str) -> str:
        fmt = str(value).strip().lower()
        if fmt not in SUPPORTED_OUTPUT_FORMATS:
            raise DoclingParseError(f"unsupported output format: {fmt or '<none>'}")
        return fmt

    @staticmethod
    def _coerce_adapter_result(
        *,
        source: Path,
        output_format: str,
        raw: DoclingParseResult | dict[str, Any] | str,
    ) -> DoclingParseResult:
        if isinstance(raw, DoclingParseResult):
            return raw
        if isinstance(raw, str):
            return DoclingParseResult(
                source_path=str(source),
                output_format=output_format,
                content=raw,
                used_docling=True,
                metadata={},
            )
        if isinstance(raw, dict):
            content = str(raw.get("content", ""))
            metadata_raw = raw.get("metadata", {})
            metadata = dict(metadata_raw) if isinstance(metadata_raw, dict) else {}
            used_docling = bool(raw.get("used_docling", True))
            return DoclingParseResult(
                source_path=str(raw.get("source_path", source)),
                output_format=str(raw.get("output_format", output_format)),
                content=content,
                used_docling=used_docling,
                metadata=metadata,
            )
        raise TypeError("docling adapter must return DoclingParseResult, dict, or str.")

    @staticmethod
    def _parse_text_fallback(*, source: Path, output_format: str) -> DoclingParseResult:
        text = source.read_text(encoding="utf-8", errors="ignore")
        ext = source.suffix.lower()
        metadata = {
            "extension": ext,
            "parser": "fallback_text",
        }

        if output_format == "markdown":
            content = text
        elif output_format == "html":
            if ext in {".html", ".htm"}:
                content = text
            else:
                content = f"<pre>{html.escape(text)}</pre>"
        else:
            content = json.dumps(
                {
                    "text": text,
                    "source_path": str(source),
                    "extension": ext,
                },
                ensure_ascii=False,
            )
        return DoclingParseResult(
            source_path=str(source),
            output_format=output_format,
            content=content,
            used_docling=False,
            metadata=metadata,
        )

    def _parse_builtin_binary(
        self,
        *,
        source: Path,
        output_format: str,
        enable_ocr: bool,
    ) -> DoclingParseResult | None:
        ext = source.suffix.lower()
        _ = enable_ocr
        if ext == ".docx":
            text, metadata = self._parse_docx_builtin(source)
            return self._build_binary_result(
                source=source,
                output_format=output_format,
                text=text,
                metadata=metadata,
            )
        if ext == ".pptx":
            text, metadata = self._parse_pptx_builtin(source)
            return self._build_binary_result(
                source=source,
                output_format=output_format,
                text=text,
                metadata=metadata,
            )
        if ext == ".xlsx":
            text, metadata = self._parse_xlsx_builtin(source)
            return self._build_binary_result(
                source=source,
                output_format=output_format,
                text=text,
                metadata=metadata,
            )
        if ext == ".pdf":
            text, metadata = self._parse_pdf_optional(source)
            return self._build_binary_result(
                source=source,
                output_format=output_format,
                text=text,
                metadata=metadata,
            )
        return None

    @staticmethod
    def _build_binary_result(
        *,
        source: Path,
        output_format: str,
        text: str,
        metadata: dict[str, Any],
    ) -> DoclingParseResult:
        payload = {
            "text": text,
            "source_path": str(source),
            "extension": source.suffix.lower(),
            "metadata": metadata,
        }
        if output_format == "markdown":
            content = text
        elif output_format == "html":
            content = f"<pre>{html.escape(text)}</pre>"
        else:
            content = json.dumps(payload, ensure_ascii=False)
        return DoclingParseResult(
            source_path=str(source),
            output_format=output_format,
            content=content,
            used_docling=True,
            metadata=metadata,
        )

    @staticmethod
    def _parse_docx_builtin(source: Path) -> tuple[str, dict[str, Any]]:
        with ZipFile(source) as archive:
            xml = archive.read("word/document.xml")
        root = ET.fromstring(xml)
        paragraphs: list[str] = []
        for paragraph in root.iter():
            if not str(paragraph.tag).endswith("}p"):
                continue
            parts: list[str] = []
            for node in paragraph.iter():
                tag = str(node.tag)
                if tag.endswith("}t"):
                    parts.append(node.text or "")
                elif tag.endswith("}tab"):
                    parts.append("\t")
                elif tag.endswith("}br") or tag.endswith("}cr"):
                    parts.append("\n")
            text = "".join(parts).strip()
            if text:
                paragraphs.append(text)
        content = "\n\n".join(paragraphs).strip()
        return content, {
            "extension": ".docx",
            "parser": "builtin_ooxml_docx",
            "paragraph_count": len(paragraphs),
        }

    @staticmethod
    def _parse_pptx_builtin(source: Path) -> tuple[str, dict[str, Any]]:
        with ZipFile(source) as archive:
            slide_names = sorted(
                (
                    name
                    for name in archive.namelist()
                    if re.fullmatch(r"ppt/slides/slide\d+\.xml", name)
                ),
                key=lambda item: int(re.search(r"slide(\d+)\.xml", item).group(1)),
            )
            slides: list[str] = []
            for index, slide_name in enumerate(slide_names, start=1):
                root = ET.fromstring(archive.read(slide_name))
                texts = [
                    (node.text or "").strip()
                    for node in root.iter()
                    if str(node.tag).endswith("}t") and (node.text or "").strip()
                ]
                body = "\n".join(texts).strip()
                if body:
                    slides.append(f"# Slide {index}\n{body}")
                else:
                    slides.append(f"# Slide {index}")
        return "\n\n".join(slides).strip(), {
            "extension": ".pptx",
            "parser": "builtin_ooxml_pptx",
            "slide_count": len(slides),
        }

    @classmethod
    def _parse_xlsx_builtin(cls, source: Path) -> tuple[str, dict[str, Any]]:
        with ZipFile(source) as archive:
            shared_strings = cls._xlsx_shared_strings(archive)
            sheet_refs = cls._xlsx_sheet_refs(archive)
            sections: list[str] = []
            for sheet_name, sheet_path in sheet_refs:
                rows = cls._xlsx_sheet_rows(archive, sheet_path, shared_strings)
                lines = [f"## Sheet: {sheet_name}"]
                for row in rows:
                    lines.append("\t".join(row).rstrip())
                sections.append("\n".join(lines).rstrip())
        return "\n\n".join(section for section in sections if section.strip()).strip(), {
            "extension": ".xlsx",
            "parser": "builtin_ooxml_xlsx",
            "sheet_count": len(sheet_refs),
        }

    @staticmethod
    def _parse_pdf_optional(source: Path) -> tuple[str, dict[str, Any]]:
        try:
            from pypdf import PdfReader  # type: ignore

            reader = PdfReader(str(source))
            pages = [(page.extract_text() or "").strip() for page in reader.pages]
            text = "\n\n".join(
                f"# Page {index}\n{page_text}".rstrip()
                for index, page_text in enumerate(pages, start=1)
                if page_text
            ).strip()
            return text, {
                "extension": ".pdf",
                "parser": "optional_pypdf",
                "page_count": len(reader.pages),
            }
        except ModuleNotFoundError:
            pass
        except Exception as exc:  # noqa: BLE001
            raise DoclingParseError(f"pdf parsing failed: {exc}") from exc

        pdftotext = shutil.which("pdftotext")
        if pdftotext:
            try:
                output = subprocess.run(
                    [pdftotext, "-layout", str(source), "-"],
                    capture_output=True,
                    text=True,
                    check=True,
                )
            except subprocess.CalledProcessError as exc:
                raise DoclingParseError(
                    f"pdftotext parsing failed: {exc.stderr.strip() or exc}"
                ) from exc
            return output.stdout.strip(), {
                "extension": ".pdf",
                "parser": "optional_pdftotext",
            }

        raise DoclingUnavailableError(
            "pdf parsing backend is unavailable; install `pypdf`, ensure `pdftotext` is on PATH, or provide an adapter."
        )

    @staticmethod
    def _xlsx_shared_strings(archive: ZipFile) -> list[str]:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
        values: list[str] = []
        for item in root.iter():
            if str(item.tag).endswith("}si"):
                texts = [
                    (node.text or "")
                    for node in item.iter()
                    if str(node.tag).endswith("}t")
                ]
                values.append("".join(texts))
        return values

    @staticmethod
    def _xlsx_sheet_refs(archive: ZipFile) -> list[tuple[str, str]]:
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels_root = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rels = {
            rel.attrib.get("Id", ""): rel.attrib.get("Target", "")
            for rel in rels_root
            if str(rel.tag).endswith("}Relationship")
        }
        refs: list[tuple[str, str]] = []
        for sheet in workbook.iter():
            if not str(sheet.tag).endswith("}sheet"):
                continue
            name = sheet.attrib.get("name", "Sheet")
            rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id", "")
            target = rels.get(rel_id, "")
            if target:
                refs.append((name, f"xl/{target.lstrip('/')}"))
        return refs

    @classmethod
    def _xlsx_sheet_rows(
        cls,
        archive: ZipFile,
        sheet_path: str,
        shared_strings: list[str],
    ) -> list[list[str]]:
        root = ET.fromstring(archive.read(sheet_path))
        rows: list[list[str]] = []
        for row in root.iter():
            if not str(row.tag).endswith("}row"):
                continue
            values: list[str] = []
            for cell in row:
                if not str(cell.tag).endswith("}c"):
                    continue
                ref = cell.attrib.get("r", "")
                index = cls._xlsx_column_index(ref)
                while len(values) <= index:
                    values.append("")
                values[index] = cls._xlsx_cell_value(cell, shared_strings)
            while values and values[-1] == "":
                values.pop()
            if values:
                rows.append(values)
        return rows

    @staticmethod
    def _xlsx_column_index(cell_ref: str) -> int:
        letters = "".join(ch for ch in cell_ref if ch.isalpha()).upper()
        if not letters:
            return 0
        index = 0
        for char in letters:
            index = (index * 26) + (ord(char) - 64)
        return max(index - 1, 0)

    @staticmethod
    def _xlsx_cell_value(cell: ET.Element, shared_strings: list[str]) -> str:
        cell_type = cell.attrib.get("t", "")
        if cell_type == "inlineStr":
            texts = [
                (node.text or "")
                for node in cell.iter()
                if str(node.tag).endswith("}t")
            ]
            return "".join(texts).strip()
        value_node = next((node for node in cell if str(node.tag).endswith("}v")), None)
        raw = (value_node.text or "").strip() if value_node is not None else ""
        if cell_type == "s":
            try:
                return shared_strings[int(raw)]
            except Exception:  # noqa: BLE001
                return raw
        if cell_type == "b":
            return "TRUE" if raw == "1" else "FALSE"
        return raw


class DoclingParseTool(Tool):
    """Tool wrapper for document parsing with optional OCR flag."""

    def __init__(self, parser: DoclingParser | None = None) -> None:
        self._parser = parser or DoclingParser()

    @property
    def name(self) -> str:
        return "docling_parse"

    @property
    def description(self) -> str:
        return (
            "Parse DOCX/PPTX/XLSX/HTML/text documents into markdown/html/json using "
            "normalized extraction. PDF parsing requires an optional backend or adapter."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Absolute or relative document path.",
                },
                "output_format": {
                    "type": "string",
                    "enum": ["markdown", "html", "json"],
                    "default": "markdown",
                },
                "enable_ocr": {
                    "type": "boolean",
                    "default": False,
                    "description": "Enable OCR path if adapter backend supports it.",
                },
            },
            "required": ["path"],
        }

    async def execute(self, *args, **kwargs) -> ToolResult:  # type: ignore[override]
        path = kwargs.get("path")
        output_format = kwargs.get("output_format", "markdown")
        enable_ocr = bool(kwargs.get("enable_ocr", False))
        if not path:
            return ToolResult(success=False, error="path is required.")
        try:
            result = self._parser.parse_file(
                path=str(path),
                output_format=str(output_format),
                enable_ocr=enable_ocr,
            )
            payload = {
                "source_path": result.source_path,
                "output_format": result.output_format,
                "used_docling": result.used_docling,
                "metadata": result.metadata,
                "content": result.content,
            }
            return ToolResult(success=True, content=json.dumps(payload, ensure_ascii=False))
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")
