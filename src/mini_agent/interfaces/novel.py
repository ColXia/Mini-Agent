"""Novel-subprogram interface-layer DTOs for API v1."""

from __future__ import annotations

from pydantic import BaseModel, Field


class NovelSetupRequest(BaseModel):
    """Request model for novel project setup."""

    topic: str
    genre: str
    num_chapters: int = Field(default=8, ge=1, le=200)
    words_per_chapter: int = Field(default=1800, ge=200, le=20000)
    project_dir: str | None = None
    dry_run: bool = False
    api_host: str | None = None


class NovelWriteRequest(BaseModel):
    """Request model for novel chapter writing."""

    chapter: int = Field(ge=1)
    guidance: str = ""
    project_dir: str | None = None
    dry_run: bool = False
    api_host: str | None = None


class NovelFinalizeRequest(BaseModel):
    """Request model for novel chapter finalize flow."""

    chapter: int = Field(ge=1)
    project_dir: str | None = None
    dry_run: bool = False
    api_host: str | None = None


class NovelCoverRequest(BaseModel):
    """Request model for novel cover generation."""

    prompt: str
    output_name: str = "cover.png"
    aspect_ratio: str | None = None
    style_type: str | None = None
    style_weight: float | None = None
    project_dir: str | None = None
    dry_run: bool = False
    api_host: str | None = None


class NovelIllustrateRequest(BaseModel):
    """Request model for chapter illustration generation."""

    chapter: int = Field(ge=1)
    count: int = Field(default=3, ge=1, le=12)
    aspect_ratio: str | None = None
    style_type: str | None = None
    style_weight: float | None = None
    project_dir: str | None = None
    dry_run: bool = False
    api_host: str | None = None


class NovelChapterSaveRequest(BaseModel):
    """Request model for manual chapter content save."""

    text: str
    final: bool = False
    project_dir: str | None = None
    note: str | None = None
    tags: list[str] | None = None


class ChapterVersionMetaUpdateRequest(BaseModel):
    """Request model for chapter version metadata patch."""

    project_dir: str | None = None
    final: bool = False
    note: str | None = None
    tags: list[str] | None = None


class ChapterRollbackRequest(BaseModel):
    """Request model for rolling chapter to a prior version."""

    version_id: str = Field(min_length=1)
    project_dir: str | None = None
    final: bool = False
    note: str | None = None
    tags: list[str] | None = None


class NovelChapterResponse(BaseModel):
    """Canonical novel chapter operation response."""

    chapter: int = Field(ge=1)
    project_dir: str
    text: str
    updated_at: str | None = None
