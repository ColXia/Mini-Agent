"""Novel Generator API router.

This module provides the FastAPI router for the novel generator subprogram,
including all /api/novel/* endpoints.
"""

import difflib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

# Import the novel demo from the original location
# In a full refactor, this would be moved to subprograms/novel_generator/core/
import importlib.util
import sys

REPO_ROOT = Path(__file__).resolve().parents[3]
NOVEL_DEMO_FILE = REPO_ROOT / "examples" / "mini_agent_demo" / "minimax_novel_demo" / "novel_demo.py"

_NOVEL_DEMO_MODULE = None


def _load_novel_demo_module():
    """Load the novel demo module dynamically."""
    global _NOVEL_DEMO_MODULE
    if _NOVEL_DEMO_MODULE is not None:
        return _NOVEL_DEMO_MODULE

    if not NOVEL_DEMO_FILE.exists():
        raise FileNotFoundError(f"Novel demo script not found: {NOVEL_DEMO_FILE}")

    spec = importlib.util.spec_from_file_location(
        "mini_agent_novel_demo_module", NOVEL_DEMO_FILE
    )
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load novel demo module from: {NOVEL_DEMO_FILE}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _NOVEL_DEMO_MODULE = module
    return module


router = APIRouter(tags=["Novel Generator"])

# Workspace root for novel projects
WORKSPACE_ROOT = REPO_ROOT / "workspace"
DEFAULT_NOVEL_PROJECT_DIR = WORKSPACE_ROOT / "mini-agent-novel-demo"


def _to_utc_iso(value: datetime) -> str:
    """Convert datetime to UTC ISO format."""
    return value.astimezone(timezone.utc).isoformat()


def _resolve_project_dir(project_dir: str | None) -> Path:
    """Resolve the project directory path."""
    if not project_dir:
        target = DEFAULT_NOVEL_PROJECT_DIR
    else:
        raw = Path(project_dir).expanduser()
        target = raw if raw.is_absolute() else WORKSPACE_ROOT / raw
    target = target.resolve()
    if not str(target).startswith(str(WORKSPACE_ROOT.resolve())):
        raise HTTPException(
            status_code=400, detail="Project directory must be inside workspace root."
        )
    return target


def _chapter_file_path(project_dir: Path, chapter_number: int, final: bool) -> Path:
    """Get the chapter file path."""
    name = f"final_chapter_{chapter_number}.txt" if final else f"chapter_{chapter_number}.txt"
    return project_dir / "chapters" / name


def _chapter_versions_file(project_dir: Path, chapter_number: int, final: bool) -> Path:
    """Get the chapter versions file path."""
    kind = "final" if final else "draft"
    return project_dir / "chapters" / ".history" / f"chapter_{chapter_number}_{kind}.jsonl"


def _append_chapter_version(
    project_dir: Path,
    chapter_number: int,
    final: bool,
    content: str,
    source: str,
    note: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    """Append a chapter version to the history file."""
    versions_file = _chapter_versions_file(project_dir, chapter_number, final)
    versions_file.parent.mkdir(parents=True, exist_ok=True)

    item = {
        "version_id": uuid4().hex,
        "chapter": chapter_number,
        "final": final,
        "source": source,
        "content_length": len(content),
        "created_at": _to_utc_iso(datetime.now(timezone.utc)),
        "note": note or "",
        "tags": tags or [],
        "content": content,
    }

    with versions_file.open("a", encoding="utf-8") as f:
        f.write(json.dumps(item, ensure_ascii=False) + "\n")

    return item


def _read_chapter_versions(
    project_dir: Path, chapter_number: int, final: bool
) -> list[dict[str, Any]]:
    """Read all versions of a chapter."""
    versions_file = _chapter_versions_file(project_dir, chapter_number, final)
    if not versions_file.exists():
        return []

    versions = []
    for line in versions_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
            if isinstance(parsed, dict):
                versions.append(parsed)
        except json.JSONDecodeError:
            continue

    return versions


def _get_version_by_id(
    project_dir: Path, chapter_number: int, final: bool, version_id: str
) -> dict[str, Any] | None:
    """Get a specific version by ID."""
    for item in reversed(_read_chapter_versions(project_dir, chapter_number, final)):
        if item.get("version_id") == version_id:
            return item
    return None


def _build_version_summary(
    item: dict[str, Any], chapter_number: int, final: bool
) -> dict[str, Any]:
    """Build a version summary without full content."""
    return {
        "version_id": str(item.get("version_id", "")),
        "chapter": int(item.get("chapter", chapter_number)),
        "final": bool(item.get("final", final)),
        "source": str(item.get("source", "")),
        "content_length": int(
            item.get("content_length", len(str(item.get("content", ""))))
        ),
        "created_at": str(item.get("created_at", "")),
        "note": item.get("note", ""),
        "tags": item.get("tags", []),
    }


def _create_novel_demo(
    project_dir: Path, dry_run: bool, api_host: str | None = None
) -> Any:
    """Create a MiniMaxNovelDemo instance."""
    module = _load_novel_demo_module()
    DemoConfig = getattr(module, "DemoConfig")
    MiniMaxNovelDemo = getattr(module, "MiniMaxNovelDemo")

    config_path = project_dir / "project_config.json"
    if config_path.exists():
        config = DemoConfig.load(config_path)
    else:
        config = DemoConfig(
            topic="Agent story sandbox",
            genre="Sci-fi",
            num_chapters=8,
            words_per_chapter=1800,
        )

    env_api_host = os.getenv("MINIMAX_API_HOST")
    host = (api_host or env_api_host or "https://api.minimaxi.com").rstrip("/")

    return MiniMaxNovelDemo(
        project_dir=project_dir,
        config=config,
        api_key=os.getenv("MINIMAX_API_KEY"),
        api_host=host,
        dry_run=dry_run,
    )


def _list_novel_assets(project_dir: Path) -> list[dict[str, str]]:
    """List all novel assets (covers, illustrations, audio)."""
    asset_dirs = {
        "covers": project_dir / "covers",
        "illustrations": project_dir / "illustrations",
        "audio": project_dir / "audio",
    }

    assets = []
    for asset_type, asset_dir in asset_dirs.items():
        if not asset_dir.exists():
            continue
        for path in sorted(asset_dir.glob("*")):
            if path.is_dir():
                continue
            assets.append(
                {
                    "asset_type": asset_type,
                    "name": path.name,
                    "path": str(path),
                }
            )

    return assets


# Request/Response Models
class NovelSetupRequest(BaseModel):
    """Novel setup request."""

    topic: str
    genre: str
    num_chapters: int = Field(default=8, ge=1, le=200)
    words_per_chapter: int = Field(default=1800, ge=200, le=20000)
    project_dir: str | None = None
    dry_run: bool = False
    api_host: str | None = None


class NovelWriteRequest(BaseModel):
    """Novel write request."""

    chapter: int = Field(ge=1)
    guidance: str = ""
    project_dir: str | None = None
    dry_run: bool = False
    api_host: str | None = None


class NovelFinalizeRequest(BaseModel):
    """Novel finalize request."""

    chapter: int = Field(ge=1)
    project_dir: str | None = None
    dry_run: bool = False
    api_host: str | None = None


class NovelCoverRequest(BaseModel):
    """Novel cover request."""

    prompt: str
    output_name: str = "cover.png"
    aspect_ratio: str = "1:1"
    style_type: str = "漫画"
    style_weight: float = 1.0
    project_dir: str | None = None
    dry_run: bool = False
    api_host: str | None = None


class NovelIllustrateRequest(BaseModel):
    """Novel illustrate request."""

    chapter: int = Field(ge=1)
    count: int = Field(default=3, ge=1, le=12)
    aspect_ratio: str = "16:9"
    style_type: str = "漫画"
    style_weight: float = 1.0
    project_dir: str | None = None
    dry_run: bool = False
    api_host: str | None = None


class NovelChapterSaveRequest(BaseModel):
    """Novel chapter save request."""

    text: str
    final: bool = False
    project_dir: str | None = None
    note: str | None = None
    tags: list[str] | None = None


class ChapterVersionMetaUpdateRequest(BaseModel):
    """Chapter version metadata update request."""

    project_dir: str | None = None
    final: bool = False
    note: str | None = None
    tags: list[str] | None = None


class ChapterRollbackRequest(BaseModel):
    """Chapter rollback request."""

    version_id: str = Field(min_length=1)
    project_dir: str | None = None
    final: bool = False
    note: str | None = None
    tags: list[str] | None = None


# API Endpoints
@router.get("/config")
async def get_novel_config(project_dir: str | None = None) -> dict[str, Any]:
    """Get novel project configuration."""
    project = _resolve_project_dir(project_dir)
    config_path = project / "project_config.json"
    if not config_path.exists():
        return {"project_dir": str(project), "exists": False}
    return {
        "project_dir": str(project),
        "exists": True,
        "config": config_path.read_text(encoding="utf-8"),
    }


@router.post("/setup")
async def novel_setup(request: NovelSetupRequest) -> dict[str, Any]:
    """Set up a new novel project."""
    module = _load_novel_demo_module()
    DemoConfig = getattr(module, "DemoConfig")

    project = _resolve_project_dir(request.project_dir)
    config = DemoConfig(
        topic=request.topic,
        genre=request.genre,
        num_chapters=request.num_chapters,
        words_per_chapter=request.words_per_chapter,
    )

    demo = _create_novel_demo(project, request.dry_run, request.api_host)
    demo.config = config
    demo.setup_project()

    return {
        "status": "ok",
        "project_dir": str(project),
        "setting_file": str(project / "Novel_setting.txt"),
        "directory_file": str(project / "Novel_directory.txt"),
    }


@router.post("/write")
async def novel_write(request: NovelWriteRequest) -> dict[str, Any]:
    """Write a chapter draft."""
    project = _resolve_project_dir(request.project_dir)
    demo = _create_novel_demo(project, request.dry_run, request.api_host)
    outline_path, chapter_path = demo.write_chapter(
        chapter_number=request.chapter, guidance=request.guidance
    )

    chapter_text = chapter_path.read_text(encoding="utf-8")
    _append_chapter_version(
        project_dir=project,
        chapter_number=request.chapter,
        final=False,
        content=chapter_text,
        source="generate_write",
    )

    return {
        "status": "ok",
        "project_dir": str(project),
        "chapter": request.chapter,
        "outline_file": str(outline_path),
        "chapter_file": str(chapter_path),
    }


@router.post("/finalize")
async def novel_finalize(request: NovelFinalizeRequest) -> dict[str, Any]:
    """Finalize a chapter."""
    project = _resolve_project_dir(request.project_dir)
    demo = _create_novel_demo(project, request.dry_run, request.api_host)
    demo.finalize_chapter(chapter_number=request.chapter)

    final_path = project / "chapters" / f"final_chapter_{request.chapter}.txt"
    if final_path.exists():
        _append_chapter_version(
            project_dir=project,
            chapter_number=request.chapter,
            final=True,
            content=final_path.read_text(encoding="utf-8"),
            source="finalize_step4",
        )

    return {
        "status": "ok",
        "project_dir": str(project),
        "chapter": request.chapter,
        "final_file": str(final_path),
        "summary_file": str(project / "global_summary.txt"),
    }


@router.post("/cover")
async def novel_cover(request: NovelCoverRequest) -> dict[str, Any]:
    """Generate a cover image."""
    project = _resolve_project_dir(request.project_dir)
    demo = _create_novel_demo(project, request.dry_run, request.api_host)
    output = demo.generate_cover_image(
        prompt=request.prompt,
        output_name=request.output_name,
        aspect_ratio=request.aspect_ratio,
        style_type=request.style_type,
        style_weight=request.style_weight,
    )

    return {
        "status": "ok",
        "project_dir": str(project),
        "file": str(output),
    }


@router.post("/illustrate")
async def novel_illustrate(request: NovelIllustrateRequest) -> dict[str, Any]:
    """Generate chapter illustrations."""
    project = _resolve_project_dir(request.project_dir)
    demo = _create_novel_demo(project, request.dry_run, request.api_host)
    paths = demo.generate_chapter_illustrations(
        chapter_number=request.chapter,
        count=request.count,
        aspect_ratio=request.aspect_ratio,
        style_type=request.style_type,
        style_weight=request.style_weight,
    )

    return {
        "status": "ok",
        "project_dir": str(project),
        "chapter": request.chapter,
        "files": [str(item) for item in paths],
    }


@router.get("/chapters")
async def list_novel_chapters(project_dir: str | None = None) -> dict[str, Any]:
    """List all chapters."""
    project = _resolve_project_dir(project_dir)
    directory_path = project / "Novel_directory.txt"
    chapter_entries = []

    if directory_path.exists():
        try:
            chapter_entries = json.loads(directory_path.read_text(encoding="utf-8"))
        except Exception:
            chapter_entries = []

    chapters_dir = project / "chapters"
    for entry in chapter_entries:
        chapter_no = int(entry.get("chapter", 0))
        entry["draft_exists"] = (chapters_dir / f"chapter_{chapter_no}.txt").exists()
        entry["final_exists"] = (
            chapters_dir / f"final_chapter_{chapter_no}.txt"
        ).exists()

    return {"project_dir": str(project), "chapters": chapter_entries}


@router.get("/chapter/{chapter_number}")
async def get_novel_chapter(
    chapter_number: int, project_dir: str | None = None, final: bool = False
) -> dict[str, Any]:
    """Get a chapter's content."""
    project = _resolve_project_dir(project_dir)
    filename = (
        f"final_chapter_{chapter_number}.txt"
        if final
        else f"chapter_{chapter_number}.txt"
    )
    chapter_file = project / "chapters" / filename

    if not chapter_file.exists():
        raise HTTPException(status_code=404, detail=f"Chapter file not found: {filename}")

    return {
        "project_dir": str(project),
        "chapter": chapter_number,
        "final": final,
        "file": str(chapter_file),
        "text": chapter_file.read_text(encoding="utf-8"),
    }


@router.put("/chapter/{chapter_number}")
async def save_novel_chapter(
    chapter_number: int, request: NovelChapterSaveRequest
) -> dict[str, Any]:
    """Save a chapter's content."""
    project = _resolve_project_dir(request.project_dir)
    filename = (
        f"final_chapter_{chapter_number}.txt"
        if request.final
        else f"chapter_{chapter_number}.txt"
    )
    chapter_file = project / "chapters" / filename
    chapter_file.parent.mkdir(parents=True, exist_ok=True)
    chapter_file.write_text(request.text, encoding="utf-8")

    version = _append_chapter_version(
        project_dir=project,
        chapter_number=chapter_number,
        final=request.final,
        content=request.text,
        source="manual_save",
        note=request.note,
        tags=request.tags,
    )
    version.pop("content", None)

    return {
        "status": "ok",
        "file": str(chapter_file),
        "version": _build_version_summary(
            version, chapter_number=chapter_number, final=request.final
        ),
    }


@router.get("/chapter/{chapter_number}/versions")
async def list_chapter_versions(
    chapter_number: int, project_dir: str | None = None, final: bool = False
) -> dict[str, Any]:
    """List all versions of a chapter."""
    project = _resolve_project_dir(project_dir)
    versions = _read_chapter_versions(
        project, chapter_number=chapter_number, final=final
    )
    summaries = [
        _build_version_summary(item, chapter_number=chapter_number, final=final)
        for item in versions
    ]
    return {
        "project_dir": str(project),
        "chapter": chapter_number,
        "final": final,
        "versions": summaries,
    }


@router.get("/chapter/{chapter_number}/version/{version_id}")
async def get_chapter_version(
    chapter_number: int,
    version_id: str,
    project_dir: str | None = None,
    final: bool = False,
) -> dict[str, Any]:
    """Get a specific version of a chapter."""
    project = _resolve_project_dir(project_dir)
    version = _get_version_by_id(
        project, chapter_number=chapter_number, final=final, version_id=version_id
    )

    if version is None:
        raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")

    return {
        "project_dir": str(project),
        "chapter": chapter_number,
        "final": final,
        "version_id": version_id,
        "created_at": version.get("created_at", ""),
        "source": version.get("source", ""),
        "note": version.get("note", ""),
        "tags": version.get("tags", []),
        "content": version.get("content", ""),
    }


@router.post("/chapter/{chapter_number}/rollback")
async def rollback_novel_chapter(
    chapter_number: int, request: ChapterRollbackRequest
) -> dict[str, Any]:
    """Rollback a chapter to a previous version."""
    project = _resolve_project_dir(request.project_dir)
    source_version = _get_version_by_id(
        project,
        chapter_number=chapter_number,
        final=request.final,
        version_id=request.version_id,
    )

    if source_version is None:
        raise HTTPException(status_code=404, detail=f"Version not found: {request.version_id}")

    source_content = str(source_version.get("content", ""))
    chapter_file = _chapter_file_path(
        project, chapter_number=chapter_number, final=request.final
    )
    chapter_file.parent.mkdir(parents=True, exist_ok=True)
    chapter_file.write_text(source_content, encoding="utf-8")

    rollback_note = request.note or f"Rollback to {request.version_id[:12]}"
    rollback_tags = request.tags or ["rollback"]
    rollback_version = _append_chapter_version(
        project_dir=project,
        chapter_number=chapter_number,
        final=request.final,
        content=source_content,
        source="rollback",
        note=rollback_note,
        tags=rollback_tags,
    )
    rollback_version.pop("content", None)

    return {
        "status": "ok",
        "project_dir": str(project),
        "chapter": chapter_number,
        "final": request.final,
        "file": str(chapter_file),
        "restored_from_version": _build_version_summary(
            source_version, chapter_number=chapter_number, final=request.final
        ),
        "version": _build_version_summary(
            rollback_version, chapter_number=chapter_number, final=request.final
        ),
        "text": source_content,
    }


@router.get("/chapter/{chapter_number}/diff")
async def get_chapter_diff(
    chapter_number: int,
    from_version: str,
    to_version: str,
    project_dir: str | None = None,
    final: bool = False,
) -> dict[str, Any]:
    """Get the diff between two versions."""
    project = _resolve_project_dir(project_dir)
    source = _get_version_by_id(
        project, chapter_number=chapter_number, final=final, version_id=from_version
    )
    target = _get_version_by_id(
        project, chapter_number=chapter_number, final=final, version_id=to_version
    )

    if source is None:
        raise HTTPException(status_code=404, detail=f"from_version not found: {from_version}")
    if target is None:
        raise HTTPException(status_code=404, detail=f"to_version not found: {to_version}")

    source_lines = str(source.get("content", "")).splitlines()
    target_lines = str(target.get("content", "")).splitlines()
    diff_lines = difflib.unified_diff(
        source_lines,
        target_lines,
        fromfile=from_version[:8],
        tofile=to_version[:8],
        lineterm="",
    )

    return {
        "project_dir": str(project),
        "chapter": chapter_number,
        "final": final,
        "from_version": from_version,
        "to_version": to_version,
        "diff": "\n".join(diff_lines),
    }


@router.get("/assets")
async def list_assets(project_dir: str | None = None) -> dict[str, Any]:
    """List all novel assets."""
    project = _resolve_project_dir(project_dir)
    return {"project_dir": str(project), "assets": _list_novel_assets(project)}
