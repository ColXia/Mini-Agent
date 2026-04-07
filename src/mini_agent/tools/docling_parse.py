"""Docling parse tool baseline with lean fallback and batch support."""

from __future__ import annotations

from dataclasses import dataclass, field
import html
import json
from pathlib import Path
from typing import Any, Callable

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


class DoclingParseTool(Tool):
    """Tool wrapper for document parsing with optional OCR flag."""

    def __init__(self, parser: DoclingParser | None = None) -> None:
        self._parser = parser or DoclingParser()

    @property
    def name(self) -> str:
        return "docling_parse"

    @property
    def description(self) -> str:
        return "Parse PDF/DOCX/PPTX/XLSX/HTML/image documents into markdown/html/json."

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
