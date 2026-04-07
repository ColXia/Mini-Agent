"""Application-layer use cases for Studio Gateway novel endpoints."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from fastapi import HTTPException

from .novel_agent_profile import NovelAgentProfile


ResolveProjectDirFn = Callable[[str | None], Path]
LoadNovelDemoModuleFn = Callable[[], Any]
CreateNovelDemoFn = Callable[[Path, bool, str | None], Any]
AppendChapterVersionFn = Callable[..., dict[str, Any]]
ListNovelAssetsFn = Callable[[Path], list[dict[str, str]]]
ChapterFilePathFn = Callable[[Path, int, bool], Path]
GetVersionByIdFn = Callable[[Path, int, bool, str], dict[str, Any] | None]
BuildVersionSummaryFn = Callable[[dict[str, Any], int, bool], dict[str, Any]]
UpdateChapterVersionMetadataFn = Callable[..., dict[str, Any] | None]
ReadChapterVersionsFn = Callable[[Path, int, bool], list[dict[str, Any]]]
BuildChapterDiffFn = Callable[[str, str, str, str], str]
NormalizeVersionNoteFn = Callable[[str | None], str]
NormalizeVersionTagsFn = Callable[[list[str] | None], list[str]]
SafeRelativeUrlFn = Callable[[Path], str]


class NovelServiceUseCases:
    """Novel-subprogram orchestration use cases."""

    def __init__(
        self,
        *,
        resolve_project_dir: ResolveProjectDirFn,
        load_novel_demo_module: LoadNovelDemoModuleFn,
        create_novel_demo: CreateNovelDemoFn,
        append_chapter_version: AppendChapterVersionFn,
        list_novel_assets: ListNovelAssetsFn,
        chapter_file_path: ChapterFilePathFn,
        get_version_by_id: GetVersionByIdFn,
        build_version_summary: BuildVersionSummaryFn,
        update_chapter_version_metadata: UpdateChapterVersionMetadataFn,
        read_chapter_versions: ReadChapterVersionsFn,
        build_chapter_diff: BuildChapterDiffFn,
        normalize_version_note: NormalizeVersionNoteFn,
        normalize_version_tags: NormalizeVersionTagsFn,
        safe_relative_url: SafeRelativeUrlFn,
        profile: NovelAgentProfile,
    ) -> None:
        self._resolve_project_dir = resolve_project_dir
        self._load_novel_demo_module = load_novel_demo_module
        self._create_novel_demo = create_novel_demo
        self._append_chapter_version = append_chapter_version
        self._list_novel_assets = list_novel_assets
        self._chapter_file_path = chapter_file_path
        self._get_version_by_id = get_version_by_id
        self._build_version_summary = build_version_summary
        self._update_chapter_version_metadata = update_chapter_version_metadata
        self._read_chapter_versions = read_chapter_versions
        self._build_chapter_diff = build_chapter_diff
        self._normalize_version_note = normalize_version_note
        self._normalize_version_tags = normalize_version_tags
        self._safe_relative_url = safe_relative_url
        self._profile = profile

    async def get_config(self, *, project_dir: str | None = None) -> dict[str, Any]:
        project = self._resolve_project_dir(project_dir)
        config_path = project / "project_config.json"
        profile_data = self._profile.to_public_payload()
        binding = self._read_profile_binding(project)
        if not config_path.exists():
            return {
                "project_dir": str(project),
                "exists": False,
                "profile": profile_data,
                "profile_binding": binding,
            }
        return {
            "project_dir": str(project),
            "exists": True,
            "config": config_path.read_text(encoding="utf-8"),
            "profile": profile_data,
            "profile_binding": binding,
        }

    async def setup(
        self,
        *,
        topic: str,
        genre: str,
        num_chapters: int,
        words_per_chapter: int,
        project_dir: str | None = None,
        dry_run: bool = False,
        api_host: str | None = None,
    ) -> dict[str, Any]:
        self._assert_profile_operation_allowed("setup")
        module = self._load_novel_demo_module()
        demo_config_cls = getattr(module, "DemoConfig")
        project = self._resolve_project_dir(project_dir)
        binding_path = self._ensure_profile_binding(project)
        config = demo_config_cls(
            topic=topic,
            genre=genre,
            num_chapters=num_chapters,
            words_per_chapter=words_per_chapter,
        )
        demo = self._create_novel_demo(project, dry_run, self._profile.resolve_api_host(api_host))
        demo.config = config
        demo.setup_project()
        return {
            "status": "ok",
            "project_dir": str(project),
            "setting_file": str(project / "Novel_setting.txt"),
            "directory_file": str(project / "Novel_directory.txt"),
            "profile_binding_file": str(binding_path),
        }

    async def write(
        self,
        *,
        chapter: int,
        guidance: str = "",
        project_dir: str | None = None,
        dry_run: bool = False,
        api_host: str | None = None,
    ) -> dict[str, Any]:
        self._assert_profile_operation_allowed("write")
        project = self._resolve_project_dir(project_dir)
        binding_path = self._ensure_profile_binding(project)
        demo = self._create_novel_demo(project, dry_run, self._profile.resolve_api_host(api_host))
        outline_path, chapter_path = demo.write_chapter(chapter_number=chapter, guidance=guidance)
        chapter_text = chapter_path.read_text(encoding="utf-8")
        self._append_chapter_version(
            project_dir=project,
            chapter_number=chapter,
            final=False,
            content=chapter_text,
            source="generate_write",
        )
        return {
            "status": "ok",
            "project_dir": str(project),
            "chapter": chapter,
            "outline_file": str(outline_path),
            "chapter_file": str(chapter_path),
            "profile_binding_file": str(binding_path),
        }

    async def finalize(
        self,
        *,
        chapter: int,
        project_dir: str | None = None,
        dry_run: bool = False,
        api_host: str | None = None,
    ) -> dict[str, Any]:
        self._assert_profile_operation_allowed("finalize")
        project = self._resolve_project_dir(project_dir)
        binding_path = self._ensure_profile_binding(project)
        demo = self._create_novel_demo(project, dry_run, self._profile.resolve_api_host(api_host))
        demo.finalize_chapter(chapter_number=chapter)
        final_path = project / "chapters" / f"final_chapter_{chapter}.txt"
        if final_path.exists():
            self._append_chapter_version(
                project_dir=project,
                chapter_number=chapter,
                final=True,
                content=final_path.read_text(encoding="utf-8"),
                source="finalize_step4",
            )
        return {
            "status": "ok",
            "project_dir": str(project),
            "chapter": chapter,
            "final_file": str(final_path),
            "summary_file": str(project / "global_summary.txt"),
            "profile_binding_file": str(binding_path),
        }

    async def cover(
        self,
        *,
        prompt: str,
        output_name: str,
        aspect_ratio: str | None = None,
        style_type: str | None = None,
        style_weight: float | None = None,
        project_dir: str | None = None,
        dry_run: bool = False,
        api_host: str | None = None,
    ) -> dict[str, Any]:
        self._assert_profile_operation_allowed("cover")
        project = self._resolve_project_dir(project_dir)
        binding_path = self._ensure_profile_binding(project)
        demo = self._create_novel_demo(project, dry_run, self._profile.resolve_api_host(api_host))
        output = demo.generate_cover_image(
            prompt=prompt,
            output_name=output_name,
            aspect_ratio=self._profile.resolve_cover_aspect_ratio(aspect_ratio),
            style_type=self._profile.resolve_style_type(style_type),
            style_weight=self._profile.resolve_style_weight(style_weight),
        )
        return {
            "status": "ok",
            "project_dir": str(project),
            "file": str(output),
            "url": self._safe_relative_url(output),
            "profile_binding_file": str(binding_path),
        }

    async def illustrate(
        self,
        *,
        chapter: int,
        count: int,
        aspect_ratio: str | None = None,
        style_type: str | None = None,
        style_weight: float | None = None,
        project_dir: str | None = None,
        dry_run: bool = False,
        api_host: str | None = None,
    ) -> dict[str, Any]:
        self._assert_profile_operation_allowed("illustrate")
        project = self._resolve_project_dir(project_dir)
        binding_path = self._ensure_profile_binding(project)
        demo = self._create_novel_demo(project, dry_run, self._profile.resolve_api_host(api_host))
        paths = demo.generate_chapter_illustrations(
            chapter_number=chapter,
            count=count,
            aspect_ratio=self._profile.resolve_illustration_aspect_ratio(aspect_ratio),
            style_type=self._profile.resolve_style_type(style_type),
            style_weight=self._profile.resolve_style_weight(style_weight),
        )
        return {
            "status": "ok",
            "project_dir": str(project),
            "chapter": chapter,
            "files": [str(item) for item in paths],
            "urls": [self._safe_relative_url(item) for item in paths],
            "profile_binding_file": str(binding_path),
        }

    async def list_chapters(self, *, project_dir: str | None = None) -> dict[str, Any]:
        project = self._resolve_project_dir(project_dir)
        directory_path = project / "Novel_directory.txt"
        chapter_entries: list[dict[str, Any]] = []
        if directory_path.exists():
            try:
                chapter_entries = json.loads(directory_path.read_text(encoding="utf-8"))
            except Exception:
                chapter_entries = []

        chapters_dir = project / "chapters"
        for entry in chapter_entries:
            chapter_no = int(entry.get("chapter", 0))
            entry["draft_exists"] = (chapters_dir / f"chapter_{chapter_no}.txt").exists()
            entry["final_exists"] = (chapters_dir / f"final_chapter_{chapter_no}.txt").exists()
        return {"project_dir": str(project), "chapters": chapter_entries}

    async def get_chapter(
        self,
        *,
        chapter_number: int,
        project_dir: str | None = None,
        final: bool = False,
    ) -> dict[str, Any]:
        project = self._resolve_project_dir(project_dir)
        filename = f"final_chapter_{chapter_number}.txt" if final else f"chapter_{chapter_number}.txt"
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

    async def save_chapter(
        self,
        *,
        chapter_number: int,
        text: str,
        final: bool = False,
        project_dir: str | None = None,
        note: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        project = self._resolve_project_dir(project_dir)
        filename = f"final_chapter_{chapter_number}.txt" if final else f"chapter_{chapter_number}.txt"
        chapter_file = project / "chapters" / filename
        chapter_file.parent.mkdir(parents=True, exist_ok=True)
        chapter_file.write_text(text, encoding="utf-8")
        version = self._append_chapter_version(
            project_dir=project,
            chapter_number=chapter_number,
            final=final,
            content=text,
            source="manual_save",
            note=note,
            tags=tags,
        )
        version.pop("content", None)
        return {
            "status": "ok",
            "file": str(chapter_file),
            "version": self._build_version_summary(version, chapter_number=chapter_number, final=final),
        }

    async def rollback_chapter(
        self,
        *,
        chapter_number: int,
        version_id: str,
        project_dir: str | None = None,
        final: bool = False,
        note: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        project = self._resolve_project_dir(project_dir)
        source_version = self._get_version_by_id(project, chapter_number=chapter_number, final=final, version_id=version_id)
        if source_version is None:
            raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")

        source_content = str(source_version.get("content", ""))
        chapter_file = self._chapter_file_path(project, chapter_number=chapter_number, final=final)
        chapter_file.parent.mkdir(parents=True, exist_ok=True)
        chapter_file.write_text(source_content, encoding="utf-8")

        rollback_note = note or f"Rollback to {version_id[:12]}"
        rollback_tags = tags or ["rollback"]
        rollback_version = self._append_chapter_version(
            project_dir=project,
            chapter_number=chapter_number,
            final=final,
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
            "final": final,
            "file": str(chapter_file),
            "restored_from_version": self._build_version_summary(source_version, chapter_number=chapter_number, final=final),
            "version": self._build_version_summary(rollback_version, chapter_number=chapter_number, final=final),
            "text": source_content,
        }

    async def list_chapter_versions(
        self,
        *,
        chapter_number: int,
        project_dir: str | None = None,
        final: bool = False,
    ) -> dict[str, Any]:
        project = self._resolve_project_dir(project_dir)
        versions = self._read_chapter_versions(project, chapter_number=chapter_number, final=final)
        summaries = [self._build_version_summary(item, chapter_number=chapter_number, final=final) for item in versions]
        return {"project_dir": str(project), "chapter": chapter_number, "final": final, "versions": summaries}

    async def get_chapter_version(
        self,
        *,
        chapter_number: int,
        version_id: str,
        project_dir: str | None = None,
        final: bool = False,
    ) -> dict[str, Any]:
        project = self._resolve_project_dir(project_dir)
        version = self._get_version_by_id(project, chapter_number=chapter_number, final=final, version_id=version_id)
        if version is None:
            raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")
        return {
            "project_dir": str(project),
            "chapter": chapter_number,
            "final": final,
            "version_id": version_id,
            "created_at": version.get("created_at", ""),
            "source": version.get("source", ""),
            "note": self._normalize_version_note(version.get("note")),
            "tags": self._normalize_version_tags(version.get("tags")),
            "content": version.get("content", ""),
        }

    async def update_chapter_version(
        self,
        *,
        chapter_number: int,
        version_id: str,
        project_dir: str | None = None,
        final: bool = False,
        update_note: bool,
        note: str | None = None,
        update_tags: bool,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        if not update_note and not update_tags:
            raise HTTPException(status_code=400, detail="At least one field (note or tags) must be provided.")

        project = self._resolve_project_dir(project_dir)
        updated = self._update_chapter_version_metadata(
            project_dir=project,
            chapter_number=chapter_number,
            final=final,
            version_id=version_id,
            update_note=update_note,
            note=note,
            update_tags=update_tags,
            tags=tags,
        )
        if updated is None:
            raise HTTPException(status_code=404, detail=f"Version not found: {version_id}")
        return {
            "status": "ok",
            "project_dir": str(project),
            "chapter": chapter_number,
            "final": final,
            "version": self._build_version_summary(updated, chapter_number=chapter_number, final=final),
        }

    async def get_chapter_diff(
        self,
        *,
        chapter_number: int,
        from_version: str,
        to_version: str,
        project_dir: str | None = None,
        final: bool = False,
    ) -> dict[str, Any]:
        project = self._resolve_project_dir(project_dir)
        source = self._get_version_by_id(project, chapter_number=chapter_number, final=final, version_id=from_version)
        target = self._get_version_by_id(project, chapter_number=chapter_number, final=final, version_id=to_version)
        if source is None:
            raise HTTPException(status_code=404, detail=f"from_version not found: {from_version}")
        if target is None:
            raise HTTPException(status_code=404, detail=f"to_version not found: {to_version}")
        diff_text = self._build_chapter_diff(
            source_text=str(source.get("content", "")),
            target_text=str(target.get("content", "")),
            from_label=f"{from_version[:8]}",
            to_label=f"{to_version[:8]}",
        )
        return {
            "project_dir": str(project),
            "chapter": chapter_number,
            "final": final,
            "from_version": from_version,
            "to_version": to_version,
            "diff": diff_text,
        }

    async def list_assets(self, *, project_dir: str | None = None) -> dict[str, Any]:
        project = self._resolve_project_dir(project_dir)
        return {"project_dir": str(project), "assets": self._list_novel_assets(project)}

    def _profile_binding_path(self, project: Path) -> Path:
        return project / ".mini-agent" / "novel_profile_binding.json"

    def _read_profile_binding(self, project: Path) -> dict[str, Any] | None:
        binding_path = self._profile_binding_path(project)
        if not binding_path.exists():
            return None
        try:
            payload = json.loads(binding_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def _ensure_profile_binding(self, project: Path) -> Path:
        profile_dir = project / ".mini-agent"
        profile_dir.mkdir(parents=True, exist_ok=True)
        memory_dir = profile_dir / "novel-memory" / self._profile.memory_namespace
        memory_dir.mkdir(parents=True, exist_ok=True)

        binding_path = self._profile_binding_path(project)
        now = datetime.now(timezone.utc).isoformat()
        expected = {
            "profile_id": self._profile.profile_id,
            "memory_namespace": self._profile.memory_namespace,
            "tool_profile_id": self._profile.tool_profile_id,
            "memory_dir": str(memory_dir),
            "updated_at": now,
        }

        if binding_path.exists():
            try:
                existing = json.loads(binding_path.read_text(encoding="utf-8"))
            except Exception as exc:
                raise HTTPException(
                    status_code=409,
                    detail=f"Novel profile binding file is invalid JSON: {binding_path}",
                ) from exc
            if not isinstance(existing, dict):
                raise HTTPException(
                    status_code=409,
                    detail=f"Novel profile binding file has invalid content: {binding_path}",
                )

            current_profile_id = str(existing.get("profile_id", "")).strip()
            if current_profile_id and current_profile_id != self._profile.profile_id:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Novel project already bound to profile '{current_profile_id}', "
                        f"cannot switch to '{self._profile.profile_id}' without migration."
                    ),
                )
            current_namespace = str(existing.get("memory_namespace", "")).strip()
            if current_namespace and current_namespace != self._profile.memory_namespace:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Novel project already bound to memory namespace '{current_namespace}', "
                        f"cannot switch to '{self._profile.memory_namespace}' without migration."
                    ),
                )
            merged = dict(existing)
            merged.update(expected)
            merged.setdefault("created_at", now)
            binding_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
            return binding_path

        payload = {
            **expected,
            "created_at": now,
            "profile": self._profile.to_public_payload(),
        }
        binding_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return binding_path

    def _assert_profile_operation_allowed(self, operation: str) -> None:
        try:
            self._profile.assert_operation_allowed(operation)
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
