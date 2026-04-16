"""Unit tests for novel service use-cases and profile defaults."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from mini_agent.novel import NovelAgentProfile, NovelServiceUseCases


class _DemoStub:
    def __init__(self, project_dir: Path, calls: list[dict[str, Any]]) -> None:
        self._project_dir = project_dir
        self._calls = calls

    def setup_project(self) -> None:
        return

    def write_chapter(self, chapter_number: int, guidance: str) -> tuple[Path, Path]:
        outline = self._project_dir / "outline.txt"
        chapter = self._project_dir / "chapters" / f"chapter_{chapter_number}.txt"
        outline.parent.mkdir(parents=True, exist_ok=True)
        chapter.parent.mkdir(parents=True, exist_ok=True)
        outline.write_text(guidance, encoding="utf-8")
        chapter.write_text("chapter", encoding="utf-8")
        return outline, chapter

    def finalize_chapter(self, chapter_number: int) -> None:
        final_path = self._project_dir / "chapters" / f"final_chapter_{chapter_number}.txt"
        final_path.parent.mkdir(parents=True, exist_ok=True)
        final_path.write_text("final", encoding="utf-8")

    def generate_cover_image(
        self,
        *,
        prompt: str,
        output_name: str,
        aspect_ratio: str,
        style_type: str,
        style_weight: float,
    ) -> Path:
        self._calls.append(
            {
                "op": "cover",
                "prompt": prompt,
                "output_name": output_name,
                "aspect_ratio": aspect_ratio,
                "style_type": style_type,
                "style_weight": style_weight,
            }
        )
        path = self._project_dir / "covers" / output_name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("cover", encoding="utf-8")
        return path

    def generate_chapter_illustrations(
        self,
        *,
        chapter_number: int,
        count: int,
        aspect_ratio: str,
        style_type: str,
        style_weight: float,
    ) -> list[Path]:
        self._calls.append(
            {
                "op": "illustrate",
                "chapter_number": chapter_number,
                "count": count,
                "aspect_ratio": aspect_ratio,
                "style_type": style_type,
                "style_weight": style_weight,
            }
        )
        output_dir = self._project_dir / "illustrations"
        output_dir.mkdir(parents=True, exist_ok=True)
        paths: list[Path] = []
        for index in range(1, count + 1):
            path = output_dir / f"chapter_{chapter_number}_{index}.png"
            path.write_text("illustration", encoding="utf-8")
            paths.append(path)
        return paths


def _build_use_cases(tmp_root: Path, profile: NovelAgentProfile, calls: list[dict[str, Any]]) -> NovelServiceUseCases:
    def _resolve_project_dir(project_dir: str | None) -> Path:
        target = tmp_root / (project_dir or "novel-test")
        target.mkdir(parents=True, exist_ok=True)
        return target.resolve()

    def _create_novel_demo(project_dir: Path, dry_run: bool, api_host: str | None) -> _DemoStub:
        calls.append({"op": "create", "project_dir": str(project_dir), "dry_run": dry_run, "api_host": api_host})
        return _DemoStub(project_dir=project_dir, calls=calls)

    return NovelServiceUseCases(
        resolve_project_dir=_resolve_project_dir,
        load_novel_demo_module=lambda: SimpleNamespace(),
        create_novel_demo=_create_novel_demo,
        append_chapter_version=lambda **_: {},
        list_novel_assets=lambda _project_dir: [],
        chapter_file_path=lambda project_dir, chapter_number, final: (
            project_dir / "chapters" / (f"final_chapter_{chapter_number}.txt" if final else f"chapter_{chapter_number}.txt")
        ),
        get_version_by_id=lambda *_: None,
        build_version_summary=lambda item, _chapter_number, _final: item,
        update_chapter_version_metadata=lambda **_: None,
        read_chapter_versions=lambda *_: [],
        build_chapter_diff=lambda source_text, target_text, _from_label, _to_label: f"{source_text}->{target_text}",
        normalize_version_note=lambda note: (note or "").strip(),
        normalize_version_tags=lambda tags: [str(item).strip() for item in (tags or []) if str(item).strip()],
        safe_relative_url=lambda path: f"/api/files/{path.name}",
        profile=profile,
    )


def _profile(
    *,
    profile_id: str,
    enable_text_tools: bool = True,
    enable_image_tools: bool = True,
    enable_audio_tools: bool = True,
    memory_namespace: str = "novel-main",
) -> NovelAgentProfile:
    return NovelAgentProfile(
        profile_id=profile_id,
        api_host="https://novel-profile-host",
        default_style_type="profile-default-style",
        default_style_weight=0.9,
        default_cover_aspect_ratio="1:1",
        default_illustration_aspect_ratio="16:9",
        memory_namespace=memory_namespace,
        tool_profile_id=f"{profile_id}-tools",
        enable_text_tools=enable_text_tools,
        enable_image_tools=enable_image_tools,
        enable_audio_tools=enable_audio_tools,
    )


def test_cover_uses_profile_defaults(tmp_path: Path) -> None:
    async def _run() -> None:
        calls: list[dict[str, Any]] = []
        profile = _profile(profile_id="novel-profile-a")
        profile = NovelAgentProfile(
            **{
                **profile.to_public_payload(),
                "default_style_type": "line-art",
                "default_style_weight": 0.66,
                "default_cover_aspect_ratio": "3:4",
                "default_illustration_aspect_ratio": "21:9",
            }
        )
        use_cases = _build_use_cases(tmp_path, profile, calls)

        result = await use_cases.cover(
            prompt="city skyline",
            output_name="cover-a.png",
            project_dir="book-a",
            aspect_ratio=None,
            style_type=None,
            style_weight=None,
            api_host=None,
            dry_run=True,
        )
        assert result["status"] == "ok"

        create_call = next(item for item in calls if item["op"] == "create")
        assert create_call["api_host"] == "https://novel-profile-host"
        cover_call = next(item for item in calls if item["op"] == "cover")
        assert cover_call["aspect_ratio"] == "3:4"
        assert cover_call["style_type"] == "line-art"
        assert cover_call["style_weight"] == 0.66

    asyncio.run(_run())


def test_illustrate_allows_request_overrides(tmp_path: Path) -> None:
    async def _run() -> None:
        calls: list[dict[str, Any]] = []
        profile = _profile(profile_id="novel-profile-b")
        profile = NovelAgentProfile(**{**profile.to_public_payload(), "default_illustration_aspect_ratio": "4:3"})
        use_cases = _build_use_cases(tmp_path, profile, calls)

        result = await use_cases.illustrate(
            chapter=2,
            count=2,
            aspect_ratio="16:9",
            style_type="anime",
            style_weight=1.25,
            project_dir="book-b",
            api_host="https://override-host",
            dry_run=False,
        )
        assert result["status"] == "ok"
        assert result["chapter"] == 2
        assert len(result["files"]) == 2

        create_call = next(item for item in calls if item["op"] == "create")
        assert create_call["api_host"] == "https://override-host"
        illustrate_call = next(item for item in calls if item["op"] == "illustrate")
        assert illustrate_call["aspect_ratio"] == "16:9"
        assert illustrate_call["style_type"] == "anime"
        assert illustrate_call["style_weight"] == 1.25

    asyncio.run(_run())


def test_cover_blocked_when_image_tools_disabled(tmp_path: Path) -> None:
    async def _run() -> None:
        calls: list[dict[str, Any]] = []
        use_cases = _build_use_cases(
            tmp_path,
            _profile(profile_id="novel-profile-c", enable_image_tools=False),
            calls,
        )
        with pytest.raises(Exception) as exc_info:
            await use_cases.cover(
                prompt="blocked cover",
                output_name="cover.png",
                project_dir="book-c",
                aspect_ratio=None,
                style_type=None,
                style_weight=None,
                api_host=None,
                dry_run=True,
            )
        exc = exc_info.value
        assert getattr(exc, "status_code", None) == 403
        assert "blocks image operation" in str(getattr(exc, "detail", "")).lower()

    asyncio.run(_run())


def test_profile_binding_rejects_cross_profile_reuse(tmp_path: Path) -> None:
    async def _run() -> None:
        calls_a: list[dict[str, Any]] = []
        use_cases_a = _build_use_cases(tmp_path, _profile(profile_id="novel-profile-owner"), calls_a)
        first = await use_cases_a.cover(
            prompt="bind profile",
            output_name="cover-a.png",
            project_dir="book-shared",
            aspect_ratio=None,
            style_type=None,
            style_weight=None,
            api_host=None,
            dry_run=True,
        )
        binding_file = Path(first["profile_binding_file"])
        assert binding_file.exists()

        calls_b: list[dict[str, Any]] = []
        use_cases_b = _build_use_cases(tmp_path, _profile(profile_id="novel-profile-other"), calls_b)
        with pytest.raises(Exception) as exc_info:
            await use_cases_b.cover(
                prompt="reuse profile",
                output_name="cover-b.png",
                project_dir="book-shared",
                aspect_ratio=None,
                style_type=None,
                style_weight=None,
                api_host=None,
                dry_run=True,
            )
        exc = exc_info.value
        assert getattr(exc, "status_code", None) == 409
        assert "already bound to profile" in str(getattr(exc, "detail", "")).lower()

    asyncio.run(_run())
