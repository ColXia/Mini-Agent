"""Runtime wiring for novel subprogram use cases."""

from __future__ import annotations

import difflib
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

from fastapi import HTTPException

from .profile import NovelAgentProfile
from .service import NovelServiceUseCases


_NOVEL_DEMO_MODULES: dict[Path, ModuleType] = {}
_NOVEL_USE_CASES: dict[tuple[Path, Path], NovelServiceUseCases] = {}


def reset_novel_runtime_state() -> None:
    _NOVEL_DEMO_MODULES.clear()
    _NOVEL_USE_CASES.clear()


def get_novel_use_cases(*, repo_root: Path, workspace_root: Path) -> NovelServiceUseCases:
    resolved_repo_root = repo_root.resolve()
    resolved_workspace_root = workspace_root.resolve()
    cache_key = (resolved_repo_root, resolved_workspace_root)
    cached = _NOVEL_USE_CASES.get(cache_key)
    if cached is not None:
        return cached

    default_project_dir = resolved_workspace_root / "mini-agent-novel-demo"
    novel_demo_file = (
        resolved_repo_root / "examples" / "mini_agent_demo" / "minimax_novel_demo" / "novel_demo.py"
    )

    def load_novel_demo_module() -> ModuleType:
        cached_module = _NOVEL_DEMO_MODULES.get(novel_demo_file)
        if cached_module is not None:
            return cached_module
        if not novel_demo_file.exists():
            raise FileNotFoundError(f"Novel demo script not found: {novel_demo_file}")

        spec = importlib.util.spec_from_file_location("mini_agent_novel_demo_module", novel_demo_file)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"Cannot load novel demo module from: {novel_demo_file}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        _NOVEL_DEMO_MODULES[novel_demo_file] = module
        return module

    def to_utc_iso(value: datetime) -> str:
        return value.astimezone(timezone.utc).isoformat()

    def safe_relative_url(path: Path) -> str:
        try:
            rel = path.resolve().relative_to(resolved_workspace_root)
        except Exception as exc:  # pragma: no cover - defensive branch
            raise HTTPException(status_code=400, detail=f"Path is outside workspace root: {path}") from exc
        return f"/api/files/{rel.as_posix()}"

    def resolve_project_dir(project_dir: str | None) -> Path:
        if not project_dir:
            target = default_project_dir
        else:
            raw = Path(project_dir).expanduser()
            target = raw if raw.is_absolute() else resolved_workspace_root / raw
        target = target.resolve()
        if not str(target).startswith(str(resolved_workspace_root)):
            raise HTTPException(status_code=400, detail="Project directory must be inside workspace root.")
        return target

    def chapter_file_path(project_dir: Path, chapter_number: int, final: bool) -> Path:
        name = f"final_chapter_{chapter_number}.txt" if final else f"chapter_{chapter_number}.txt"
        return project_dir / "chapters" / name

    def chapter_versions_file(project_dir: Path, chapter_number: int, final: bool) -> Path:
        kind = "final" if final else "draft"
        return project_dir / "chapters" / ".history" / f"chapter_{chapter_number}_{kind}.jsonl"

    def normalize_version_note(note: str | None) -> str:
        if note is None:
            return ""
        return note.strip()

    def normalize_version_tags(tags: list[str] | None) -> list[str]:
        if not tags:
            return []
        normalized: list[str] = []
        for item in tags:
            value = str(item).strip()
            if not value:
                continue
            if value not in normalized:
                normalized.append(value)
        return normalized

    def append_chapter_version(
        project_dir: Path,
        chapter_number: int,
        final: bool,
        content: str,
        source: str,
        note: str | None = None,
        tags: list[str] | None = None,
    ) -> dict[str, Any]:
        versions_file = chapter_versions_file(project_dir, chapter_number, final)
        versions_file.parent.mkdir(parents=True, exist_ok=True)
        item = {
            "version_id": uuid4().hex,
            "chapter": chapter_number,
            "final": final,
            "source": source,
            "content_length": len(content),
            "created_at": to_utc_iso(datetime.now(timezone.utc)),
            "note": normalize_version_note(note),
            "tags": normalize_version_tags(tags),
            "content": content,
        }
        with versions_file.open("a", encoding="utf-8") as file_obj:
            file_obj.write(json.dumps(item, ensure_ascii=False) + "\n")
        return item

    def read_chapter_versions(project_dir: Path, chapter_number: int, final: bool) -> list[dict[str, Any]]:
        versions_file = chapter_versions_file(project_dir, chapter_number, final)
        if not versions_file.exists():
            return []

        versions: list[dict[str, Any]] = []
        for line in versions_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                versions.append(parsed)
        return versions

    def write_chapter_versions(
        project_dir: Path,
        chapter_number: int,
        final: bool,
        versions: list[dict[str, Any]],
    ) -> None:
        versions_file = chapter_versions_file(project_dir, chapter_number, final)
        versions_file.parent.mkdir(parents=True, exist_ok=True)
        lines = [json.dumps(item, ensure_ascii=False) for item in versions]
        content = "\n".join(lines)
        if content:
            content += "\n"
        versions_file.write_text(content, encoding="utf-8")

    def get_version_by_id(
        project_dir: Path,
        chapter_number: int,
        final: bool,
        version_id: str,
    ) -> dict[str, Any] | None:
        for item in reversed(read_chapter_versions(project_dir, chapter_number, final)):
            if item.get("version_id") == version_id:
                return item
        return None

    def build_version_summary(item: dict[str, Any], chapter_number: int, final: bool) -> dict[str, Any]:
        return {
            "version_id": str(item.get("version_id", "")),
            "chapter": int(item.get("chapter", chapter_number)),
            "final": bool(item.get("final", final)),
            "source": str(item.get("source", "")),
            "content_length": int(item.get("content_length", len(str(item.get("content", ""))))),
            "created_at": str(item.get("created_at", "")),
            "note": normalize_version_note(item.get("note")),
            "tags": normalize_version_tags(item.get("tags")),
        }

    def update_chapter_version_metadata(
        project_dir: Path,
        chapter_number: int,
        final: bool,
        version_id: str,
        update_note: bool,
        note: str | None,
        update_tags: bool,
        tags: list[str] | None,
    ) -> dict[str, Any] | None:
        versions = read_chapter_versions(project_dir, chapter_number, final)
        if not versions:
            return None

        updated_item: dict[str, Any] | None = None
        for item in versions:
            if item.get("version_id") != version_id:
                continue
            if update_note:
                item["note"] = normalize_version_note(note)
            if update_tags:
                item["tags"] = normalize_version_tags(tags)
            updated_item = item
            break

        if updated_item is None:
            return None
        write_chapter_versions(project_dir, chapter_number, final, versions)
        return updated_item

    def build_chapter_diff(
        source_text: str,
        target_text: str,
        from_label: str,
        to_label: str,
    ) -> str:
        diff_lines = difflib.unified_diff(
            source_text.splitlines(),
            target_text.splitlines(),
            fromfile=from_label,
            tofile=to_label,
            lineterm="",
        )
        return "\n".join(diff_lines)

    def create_novel_demo(project_dir: Path, dry_run: bool, api_host: str | None = None) -> Any:
        module = load_novel_demo_module()
        demo_config = getattr(module, "DemoConfig")
        minimax_novel_demo = getattr(module, "MiniMaxNovelDemo")

        config_path = project_dir / "project_config.json"
        if config_path.exists():
            config = demo_config.load(config_path)
        else:
            config = demo_config(
                topic="Agent story sandbox",
                genre="Sci-fi",
                num_chapters=8,
                words_per_chapter=1800,
            )

        env_api_host = os.getenv("MINIMAX_API_HOST")
        host = (api_host or env_api_host or "https://api.minimaxi.com").rstrip("/")
        return minimax_novel_demo(
            project_dir=project_dir,
            config=config,
            api_key=os.getenv("MINIMAX_API_KEY"),
            api_host=host,
            dry_run=dry_run,
        )

    def list_novel_assets(project_dir: Path) -> list[dict[str, str]]:
        asset_dirs = {
            "covers": project_dir / "covers",
            "illustrations": project_dir / "illustrations",
            "audio": project_dir / "audio",
        }
        assets: list[dict[str, str]] = []
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
                        "url": safe_relative_url(path),
                    }
                )
        return assets

    use_cases = NovelServiceUseCases(
        resolve_project_dir=resolve_project_dir,
        load_novel_demo_module=load_novel_demo_module,
        create_novel_demo=create_novel_demo,
        append_chapter_version=append_chapter_version,
        list_novel_assets=list_novel_assets,
        chapter_file_path=chapter_file_path,
        get_version_by_id=get_version_by_id,
        build_version_summary=build_version_summary,
        update_chapter_version_metadata=update_chapter_version_metadata,
        read_chapter_versions=read_chapter_versions,
        build_chapter_diff=build_chapter_diff,
        normalize_version_note=normalize_version_note,
        normalize_version_tags=normalize_version_tags,
        safe_relative_url=safe_relative_url,
        profile=NovelAgentProfile.from_env(os.environ),
    )
    _NOVEL_USE_CASES[cache_key] = use_cases
    return use_cases
