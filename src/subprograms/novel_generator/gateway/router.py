"""HTTP transport for the novel-generator subprogram."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter

from mini_agent.interfaces import (
    ChapterRollbackRequest,
    ChapterVersionMetaUpdateRequest,
    NovelChapterSaveRequest,
    NovelCoverRequest,
    NovelFinalizeRequest,
    NovelIllustrateRequest,
    NovelSetupRequest,
    NovelWriteRequest,
)
from mini_agent.novel.runtime import get_novel_use_cases


REPO_ROOT = Path(__file__).resolve().parents[4]
WORKSPACE_ROOT = REPO_ROOT / "workspace"

router = APIRouter(tags=["Novel"])


def _novel_use_cases():
    return get_novel_use_cases(repo_root=REPO_ROOT, workspace_root=WORKSPACE_ROOT)


@router.get("/config")
async def get_novel_config(project_dir: str | None = None) -> dict[str, Any]:
    return await _novel_use_cases().get_config(project_dir=project_dir)


@router.post("/setup")
async def novel_setup(request: NovelSetupRequest) -> dict[str, Any]:
    return await _novel_use_cases().setup(
        topic=request.topic,
        genre=request.genre,
        num_chapters=request.num_chapters,
        words_per_chapter=request.words_per_chapter,
        project_dir=request.project_dir,
        dry_run=request.dry_run,
        api_host=request.api_host,
    )


@router.post("/write")
async def novel_write(request: NovelWriteRequest) -> dict[str, Any]:
    return await _novel_use_cases().write(
        chapter=request.chapter,
        guidance=request.guidance,
        project_dir=request.project_dir,
        dry_run=request.dry_run,
        api_host=request.api_host,
    )


@router.post("/finalize")
async def novel_finalize(request: NovelFinalizeRequest) -> dict[str, Any]:
    return await _novel_use_cases().finalize(
        chapter=request.chapter,
        project_dir=request.project_dir,
        dry_run=request.dry_run,
        api_host=request.api_host,
    )


@router.post("/cover")
async def novel_cover(request: NovelCoverRequest) -> dict[str, Any]:
    return await _novel_use_cases().cover(
        prompt=request.prompt,
        output_name=request.output_name,
        aspect_ratio=request.aspect_ratio,
        style_type=request.style_type,
        style_weight=request.style_weight,
        project_dir=request.project_dir,
        dry_run=request.dry_run,
        api_host=request.api_host,
    )


@router.post("/illustrate")
async def novel_illustrate(request: NovelIllustrateRequest) -> dict[str, Any]:
    return await _novel_use_cases().illustrate(
        chapter=request.chapter,
        count=request.count,
        aspect_ratio=request.aspect_ratio,
        style_type=request.style_type,
        style_weight=request.style_weight,
        project_dir=request.project_dir,
        dry_run=request.dry_run,
        api_host=request.api_host,
    )


@router.get("/chapters")
async def list_novel_chapters(project_dir: str | None = None) -> dict[str, Any]:
    return await _novel_use_cases().list_chapters(project_dir=project_dir)


@router.get("/chapter/{chapter_number}")
async def get_novel_chapter(
    chapter_number: int,
    project_dir: str | None = None,
    final: bool = False,
) -> dict[str, Any]:
    return await _novel_use_cases().get_chapter(
        chapter_number=chapter_number,
        project_dir=project_dir,
        final=final,
    )


@router.put("/chapter/{chapter_number}")
async def save_novel_chapter(chapter_number: int, request: NovelChapterSaveRequest) -> dict[str, Any]:
    return await _novel_use_cases().save_chapter(
        chapter_number=chapter_number,
        text=request.text,
        final=request.final,
        project_dir=request.project_dir,
        note=request.note,
        tags=request.tags,
    )


@router.post("/chapter/{chapter_number}/rollback")
async def rollback_novel_chapter(chapter_number: int, request: ChapterRollbackRequest) -> dict[str, Any]:
    return await _novel_use_cases().rollback_chapter(
        chapter_number=chapter_number,
        version_id=request.version_id,
        project_dir=request.project_dir,
        final=request.final,
        note=request.note,
        tags=request.tags,
    )


@router.get("/chapter/{chapter_number}/versions")
async def list_chapter_versions(
    chapter_number: int,
    project_dir: str | None = None,
    final: bool = False,
) -> dict[str, Any]:
    return await _novel_use_cases().list_chapter_versions(
        chapter_number=chapter_number,
        project_dir=project_dir,
        final=final,
    )


@router.get("/chapter/{chapter_number}/version/{version_id}")
async def get_chapter_version(
    chapter_number: int,
    version_id: str,
    project_dir: str | None = None,
    final: bool = False,
) -> dict[str, Any]:
    return await _novel_use_cases().get_chapter_version(
        chapter_number=chapter_number,
        version_id=version_id,
        project_dir=project_dir,
        final=final,
    )


@router.patch("/chapter/{chapter_number}/version/{version_id}")
async def update_chapter_version(
    chapter_number: int,
    version_id: str,
    request: ChapterVersionMetaUpdateRequest,
) -> dict[str, Any]:
    return await _novel_use_cases().update_chapter_version(
        chapter_number=chapter_number,
        version_id=version_id,
        project_dir=request.project_dir,
        final=request.final,
        update_note="note" in request.model_fields_set,
        note=request.note,
        update_tags="tags" in request.model_fields_set,
        tags=request.tags,
    )


@router.get("/chapter/{chapter_number}/diff")
async def get_chapter_diff(
    chapter_number: int,
    from_version: str,
    to_version: str,
    project_dir: str | None = None,
    final: bool = False,
) -> dict[str, Any]:
    return await _novel_use_cases().get_chapter_diff(
        chapter_number=chapter_number,
        from_version=from_version,
        to_version=to_version,
        project_dir=project_dir,
        final=final,
    )


@router.get("/assets")
async def list_assets(project_dir: str | None = None) -> dict[str, Any]:
    return await _novel_use_cases().list_assets(project_dir=project_dir)
