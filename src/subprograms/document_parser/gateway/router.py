"""Document parser API router."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from mini_agent.model_manager.feature_runtime import FeatureModelRuntime
from mini_agent.tools.docling_parse import DoclingParser


router = APIRouter(prefix="/api/document-parser", tags=["Document Parser"])
_PARSER = DoclingParser()


def _configure_runtime_parser() -> DoclingParser:
    try:
        ocr_adapter = FeatureModelRuntime().get_docling_ocr_adapter()
    except Exception:
        ocr_adapter = None
    _PARSER.set_ocr_adapter(ocr_adapter)
    return _PARSER


class ParseRequest(BaseModel):
    """Single document parse request."""

    path: str = Field(min_length=1)
    output_format: str = Field(default="markdown")
    enable_ocr: bool = False


class BatchParseRequest(BaseModel):
    """Batch document parse request."""

    paths: list[str] = Field(default_factory=list, min_length=1)
    output_format: str = Field(default="markdown")
    enable_ocr: bool = False


@router.post("/parse")
async def parse_document(request: ParseRequest) -> dict[str, Any]:
    try:
        result = _configure_runtime_parser().parse_file(
            path=request.path,
            output_format=request.output_format,
            enable_ocr=request.enable_ocr,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"{type(exc).__name__}: {exc}") from exc

    return {
        "status": "ok",
        "source_path": result.source_path,
        "output_format": result.output_format,
        "used_docling": result.used_docling,
        "metadata": result.metadata,
        "content": result.content,
    }


@router.post("/parse/batch")
async def parse_document_batch(request: BatchParseRequest) -> dict[str, Any]:
    parsed_items: list[dict[str, Any]] = []
    for raw_path in request.paths:
        path_text = str(raw_path).strip()
        if not path_text:
            parsed_items.append(
                {
                    "path": raw_path,
                    "success": False,
                    "error": "path is empty",
                }
            )
            continue
        try:
            result = _configure_runtime_parser().parse_file(
                path=path_text,
                output_format=request.output_format,
                enable_ocr=request.enable_ocr,
            )
            parsed_items.append(
                {
                    "path": str(Path(path_text).expanduser().resolve()),
                    "success": True,
                    "output_format": result.output_format,
                    "used_docling": result.used_docling,
                    "metadata": result.metadata,
                    "content": result.content,
                }
            )
        except Exception as exc:  # noqa: BLE001
            parsed_items.append(
                {
                    "path": path_text,
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )
    return {
        "status": "ok",
        "total": len(parsed_items),
        "succeeded": sum(1 for item in parsed_items if item["success"]),
        "failed": sum(1 for item in parsed_items if not item["success"]),
        "items": parsed_items,
    }


@router.get("/formats")
async def list_supported_formats() -> dict[str, Any]:
    from mini_agent.tools.docling_parse import SUPPORTED_INPUT_EXTENSIONS, SUPPORTED_OUTPUT_FORMATS

    return {
        "status": "ok",
        "input_extensions": sorted(SUPPORTED_INPUT_EXTENSIONS),
        "output_formats": sorted(SUPPORTED_OUTPUT_FORMATS),
    }


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "document-parser"}
