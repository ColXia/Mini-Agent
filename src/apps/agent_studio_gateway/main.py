from __future__ import annotations

import difflib
import importlib.util
import json
import mimetypes
import os
import sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from mini_agent.agent import Agent
from mini_agent.agent_core.kernel import AgentKernelBuildOptions, build_agent_kernel
from mini_agent.application import (
    ChannelIngressUseCases,
    MainAgentSurfaceService,
    NovelAgentProfile,
    NovelServiceUseCases,
    RemoteConversationBindingService,
)
from mini_agent.interfaces import (
    ApiEnvelope,
    ChapterRollbackRequest,
    ChapterVersionMetaUpdateRequest,
    ChannelMessageRequest,
    ChannelMessageResponse,
    MainAgentRoutingDiagnostics,
    MainAgentRuntimeDiagnostics,
    MainAgentSessionApprovalRequest,
    MainAgentSessionApprovalResponse,
    MainAgentChatRequest,
    MainAgentChatResponse,
    MainAgentSessionCancelRequest,
    MainAgentSessionContextRequest,
    MainAgentSessionContextResponse,
    MainAgentSessionControlRequest,
    MainAgentSessionControlResponse,
    MainAgentSessionCreateRequest,
    MainAgentSessionDetail,
    MainAgentSessionForkRequest,
    MainAgentSessionMemoryRequest,
    MainAgentSessionMemoryResponse,
    MainAgentSessionMessage,
    MainAgentSessionSkillRequest,
    MainAgentSessionSkillResponse,
    MainAgentSessionModelSelectionRequest,
    MainAgentSessionModelSelectionResponse,
    MainAgentSessionMutationResponse,
    MainAgentSessionRenameRequest,
    MainAgentSessionRuntimePolicyRequest,
    MainAgentSessionRuntimePolicyResponse,
    MainAgentSessionShareRequest,
    MainAgentSessionSummary,
    NovelChapterSaveRequest,
    NovelCoverRequest,
    NovelFinalizeRequest,
    NovelIllustrateRequest,
    NovelSetupRequest,
    NovelWriteRequest,
    SystemHealthResponse,
    StudioModelListResponse,
)
from mini_agent.session import conversation_binding_store
from mini_agent.runtime.main_agent_runtime_manager import (
    MainAgentRuntimeManager,
    MainAgentRuntimeMode,
    MainAgentRuntimePolicy,
)
from mini_agent.runtime.session_lifecycle import resolve_session_lifecycle_policy
from mini_agent.tools.mcp_loader import cleanup_mcp_connections
from gateway.security.instance_lock import GatewayInstanceLock, GatewayInstanceLockError
from apps.agent_studio_gateway.studio_router import (
    _STUDIO_OPS_USE_CASES,
    _require_studio_auth,
    router as studio_router,
)
from subprograms.knowledge_base.gateway.router import router as knowledge_base_router
from subprograms.memory_manager.gateway.router import router as memory_manager_router

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_ROOT = REPO_ROOT / "workspace"
DEFAULT_NOVEL_PROJECT_DIR = WORKSPACE_ROOT / "mini-agent-novel-demo"
NOVEL_DEMO_FILE = REPO_ROOT / "examples" / "mini_agent_demo" / "minimax_novel_demo" / "novel_demo.py"
SESSION_TTL_SECONDS = 2 * 60 * 60
CHAT_STREAM_CHUNK_SIZE = 120
DEFAULT_STUDIO_UI_DIST = REPO_ROOT / "apps" / "agent_studio" / "dist"
STUDIO_GATEWAY_HOST = os.getenv("MINI_AGENT_STUDIO_HOST", "127.0.0.1").strip() or "127.0.0.1"
STUDIO_GATEWAY_PORT = int(os.getenv("MINI_AGENT_STUDIO_PORT", "8008"))
STUDIO_INSTANCE_LOCK_ENABLED = (
    os.getenv("MINI_AGENT_STUDIO_ENABLE_INSTANCE_LOCK", "1").strip().lower() in {"1", "true", "yes", "on"}
)
MAIN_AGENT_RUNTIME_MODE_RAW = os.getenv("MINI_AGENT_RUNTIME_MODE", "single_main").strip().lower()
MAIN_AGENT_MAIN_WORKSPACE_RAW = os.getenv("MINI_AGENT_MAIN_WORKSPACE", str(REPO_ROOT)).strip()
MAIN_AGENT_TEAM_MAX_AGENTS_RAW = os.getenv("MINI_AGENT_TEAM_MAX_AGENTS", "4").strip()
MAIN_AGENT_SESSION_RESET_MODE_RAW = os.getenv("MINI_AGENT_SESSION_RESET_MODE", "none").strip().lower()
MAIN_AGENT_SESSION_IDLE_SECONDS_RAW = os.getenv("MINI_AGENT_SESSION_IDLE_SECONDS", "1800").strip()
NOVEL_PROFILE_ID_RAW = os.getenv("MINI_AGENT_NOVEL_PROFILE_ID", "novel-default").strip()
NOVEL_PROFILE_API_HOST_RAW = os.getenv("MINI_AGENT_NOVEL_API_HOST", "https://api.minimaxi.com").strip()
NOVEL_PROFILE_STYLE_TYPE_RAW = os.getenv("MINI_AGENT_NOVEL_STYLE_TYPE", "漫画").strip()
NOVEL_PROFILE_STYLE_WEIGHT_RAW = os.getenv("MINI_AGENT_NOVEL_STYLE_WEIGHT", "1.0").strip()
NOVEL_PROFILE_COVER_ASPECT_RATIO_RAW = os.getenv("MINI_AGENT_NOVEL_COVER_ASPECT_RATIO", "1:1").strip()
NOVEL_PROFILE_ILLUSTRATION_ASPECT_RATIO_RAW = os.getenv("MINI_AGENT_NOVEL_ILLUSTRATION_ASPECT_RATIO", "16:9").strip()
NOVEL_PROFILE_MEMORY_NAMESPACE_RAW = os.getenv("MINI_AGENT_NOVEL_MEMORY_NAMESPACE", "novel-main").strip()
NOVEL_PROFILE_TOOL_PROFILE_ID_RAW = os.getenv("MINI_AGENT_NOVEL_TOOL_PROFILE_ID", "novel-default-tools").strip()
NOVEL_PROFILE_ENABLE_TEXT_TOOLS_RAW = os.getenv("MINI_AGENT_NOVEL_ENABLE_TEXT_TOOLS", "1").strip()
NOVEL_PROFILE_ENABLE_IMAGE_TOOLS_RAW = os.getenv("MINI_AGENT_NOVEL_ENABLE_IMAGE_TOOLS", "1").strip()
NOVEL_PROFILE_ENABLE_AUDIO_TOOLS_RAW = os.getenv("MINI_AGENT_NOVEL_ENABLE_AUDIO_TOOLS", "1").strip()
MAIN_AGENT_SESSION_STORE_DIR = Path(
    os.getenv(
        "MINI_AGENT_MAIN_SESSION_STORE_DIR",
        str(Path.home() / ".mini-agent" / "state" / "main_agent_runtime"),
    )
).expanduser()
_STUDIO_INSTANCE_LOCK: GatewayInstanceLock | None = None
_MAIN_AGENT_SURFACE_SERVICE: MainAgentSurfaceService | None = None
_MAIN_AGENT_USE_CASES: MainAgentSurfaceService | None = None
_NOVEL_USE_CASES: NovelServiceUseCases | None = None
_CHANNEL_INGRESS_USE_CASES: ChannelIngressUseCases | None = None

# Ensure browser receives executable JS MIME type on Windows.
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("application/javascript", ".mjs")


def _resolve_studio_ui_dist_dir() -> Path | None:
    configured = os.getenv("MINI_AGENT_STUDIO_UI_DIST", "").strip()
    candidate = Path(configured).expanduser() if configured else DEFAULT_STUDIO_UI_DIST
    try:
        resolved = candidate.resolve()
    except Exception:
        return None
    if (resolved / "index.html").exists():
        return resolved
    return None


STUDIO_UI_DIST_DIR = _resolve_studio_ui_dist_dir()


_MAIN_AGENT_RUNTIME_MANAGER: MainAgentRuntimeManager | None = None

_NOVEL_DEMO_MODULE: ModuleType | None = None


def _load_novel_demo_module() -> ModuleType:
    global _NOVEL_DEMO_MODULE
    if _NOVEL_DEMO_MODULE is not None:
        return _NOVEL_DEMO_MODULE

    if not NOVEL_DEMO_FILE.exists():
        raise FileNotFoundError(f"Novel demo script not found: {NOVEL_DEMO_FILE}")

    spec = importlib.util.spec_from_file_location("mini_agent_novel_demo_module", NOVEL_DEMO_FILE)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load novel demo module from: {NOVEL_DEMO_FILE}")

    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    _NOVEL_DEMO_MODULE = module
    return module


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _safe_relative_url(path: Path) -> str:
    try:
        rel = path.resolve().relative_to(WORKSPACE_ROOT.resolve())
    except Exception as exc:  # pragma: no cover - defensive branch
        raise HTTPException(status_code=400, detail=f"Path is outside workspace root: {path}") from exc
    return f"/api/files/{rel.as_posix()}"


def _resolve_project_dir(project_dir: str | None) -> Path:
    if not project_dir:
        target = DEFAULT_NOVEL_PROJECT_DIR
    else:
        raw = Path(project_dir).expanduser()
        target = raw if raw.is_absolute() else WORKSPACE_ROOT / raw
    target = target.resolve()
    if not str(target).startswith(str(WORKSPACE_ROOT.resolve())):
        raise HTTPException(status_code=400, detail="Project directory must be inside workspace root.")
    return target


def _resolve_workspace_dir(workspace_dir: str | None) -> Path:
    if not workspace_dir:
        return REPO_ROOT
    raw = Path(workspace_dir).expanduser()
    return (raw if raw.is_absolute() else (REPO_ROOT / raw)).resolve()


def _chapter_file_path(project_dir: Path, chapter_number: int, final: bool) -> Path:
    name = f"final_chapter_{chapter_number}.txt" if final else f"chapter_{chapter_number}.txt"
    return project_dir / "chapters" / name


def _chapter_versions_file(project_dir: Path, chapter_number: int, final: bool) -> Path:
    kind = "final" if final else "draft"
    return project_dir / "chapters" / ".history" / f"chapter_{chapter_number}_{kind}.jsonl"


def _normalize_version_note(note: str | None) -> str:
    if note is None:
        return ""
    return note.strip()


def _normalize_version_tags(tags: list[str] | None) -> list[str]:
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


def _append_chapter_version(
    project_dir: Path,
    chapter_number: int,
    final: bool,
    content: str,
    source: str,
    note: str | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    versions_file = _chapter_versions_file(project_dir, chapter_number, final)
    versions_file.parent.mkdir(parents=True, exist_ok=True)
    item = {
        "version_id": uuid4().hex,
        "chapter": chapter_number,
        "final": final,
        "source": source,
        "content_length": len(content),
        "created_at": _to_utc_iso(datetime.now(timezone.utc)),
        "note": _normalize_version_note(note),
        "tags": _normalize_version_tags(tags),
        "content": content,
    }
    with versions_file.open("a", encoding="utf-8") as file_obj:
        file_obj.write(json.dumps(item, ensure_ascii=False) + "\n")
    return item


def _read_chapter_versions(project_dir: Path, chapter_number: int, final: bool) -> list[dict[str, Any]]:
    versions_file = _chapter_versions_file(project_dir, chapter_number, final)
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


def _write_chapter_versions(
    project_dir: Path,
    chapter_number: int,
    final: bool,
    versions: list[dict[str, Any]],
) -> None:
    versions_file = _chapter_versions_file(project_dir, chapter_number, final)
    versions_file.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(item, ensure_ascii=False) for item in versions]
    content = "\n".join(lines)
    if content:
        content += "\n"
    versions_file.write_text(content, encoding="utf-8")


def _get_version_by_id(project_dir: Path, chapter_number: int, final: bool, version_id: str) -> dict[str, Any] | None:
    for item in reversed(_read_chapter_versions(project_dir, chapter_number, final)):
        if item.get("version_id") == version_id:
            return item
    return None


def _build_version_summary(item: dict[str, Any], chapter_number: int, final: bool) -> dict[str, Any]:
    return {
        "version_id": str(item.get("version_id", "")),
        "chapter": int(item.get("chapter", chapter_number)),
        "final": bool(item.get("final", final)),
        "source": str(item.get("source", "")),
        "content_length": int(item.get("content_length", len(str(item.get("content", ""))))),
        "created_at": str(item.get("created_at", "")),
        "note": _normalize_version_note(item.get("note")),
        "tags": _normalize_version_tags(item.get("tags")),
    }


def _update_chapter_version_metadata(
    project_dir: Path,
    chapter_number: int,
    final: bool,
    version_id: str,
    update_note: bool,
    note: str | None,
    update_tags: bool,
    tags: list[str] | None,
) -> dict[str, Any] | None:
    versions = _read_chapter_versions(project_dir, chapter_number, final)
    if not versions:
        return None

    updated_item: dict[str, Any] | None = None
    for item in versions:
        if item.get("version_id") != version_id:
            continue
        if update_note:
            item["note"] = _normalize_version_note(note)
        if update_tags:
            item["tags"] = _normalize_version_tags(tags)
        updated_item = item
        break

    if updated_item is None:
        return None
    _write_chapter_versions(project_dir, chapter_number, final, versions)
    return updated_item


def _build_chapter_diff(
    source_text: str,
    target_text: str,
    from_label: str,
    to_label: str,
) -> str:
    source_lines = source_text.splitlines()
    target_lines = target_text.splitlines()
    diff_lines = difflib.unified_diff(
        source_lines,
        target_lines,
        fromfile=from_label,
        tofile=to_label,
        lineterm="",
    )
    return "\n".join(diff_lines)


def _sse_event(event: str, data: dict[str, Any]) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    return f"event: {event}\ndata: {payload}\n\n"


def _format_agent_bootstrap_error(exc: Exception) -> HTTPException:
    raw = str(exc).strip() or exc.__class__.__name__
    if "API Key" in raw or "api key" in raw.lower():
        detail = (
            "Mini-Agent bootstrap failed: valid API key not detected. "
            "Check OPENAI_API_KEY / ANTHROPIC_API_KEY / GEMINI_API_KEY / MINIMAX_API_KEY "
            "or local .env.local fallback."
        )
    elif "Configuration file not found" in raw:
        detail = (
            "Mini-Agent bootstrap failed: configuration assets were not found. "
            "Expected config.yaml in src/mini_agent/config/, ~/.mini-agent/config/, "
            "or the installed package config directory."
        )
    else:
        detail = f"Mini-Agent bootstrap failed: {raw}"
    return HTTPException(status_code=503, detail=detail)


async def _build_agent(workspace_dir: Path) -> Agent:
    return await build_agent_kernel(
        workspace_dir=workspace_dir,
        options=AgentKernelBuildOptions(
            console_output=False,
            allow_interactive_setup=False,
            session_store_dir=MAIN_AGENT_SESSION_STORE_DIR,
        ),
    )


async def _build_agent_with_selection(
    workspace_dir: Path,
    provider_source: str | None,
    provider_id: str | None,
    model_id: str | None,
) -> Agent:
    return await build_agent_kernel(
        workspace_dir=workspace_dir,
        options=AgentKernelBuildOptions(
            requested_provider_source=provider_source,
            requested_provider_id=provider_id,
            requested_model=model_id,
            console_output=False,
            allow_interactive_setup=False,
            session_store_dir=MAIN_AGENT_SESSION_STORE_DIR,
        ),
    )


def _parse_main_agent_runtime_policy() -> MainAgentRuntimePolicy:
    if MAIN_AGENT_RUNTIME_MODE_RAW == MainAgentRuntimeMode.TEAM.value:
        mode = MainAgentRuntimeMode.TEAM
    else:
        mode = MainAgentRuntimeMode.SINGLE_MAIN

    raw_workspace = MAIN_AGENT_MAIN_WORKSPACE_RAW or str(REPO_ROOT)
    workspace_path = Path(raw_workspace).expanduser()
    main_workspace_dir = (
        workspace_path if workspace_path.is_absolute() else (REPO_ROOT / workspace_path)
    ).resolve()

    try:
        team_max_agents = int(MAIN_AGENT_TEAM_MAX_AGENTS_RAW or "4")
    except ValueError:
        team_max_agents = 4
    team_max_agents = max(1, team_max_agents)

    session_lifecycle = resolve_session_lifecycle_policy(
        reset_mode_raw=MAIN_AGENT_SESSION_RESET_MODE_RAW,
        idle_seconds_raw=MAIN_AGENT_SESSION_IDLE_SECONDS_RAW,
    )

    if mode == MainAgentRuntimeMode.SINGLE_MAIN:
        return MainAgentRuntimePolicy(
            mode=mode,
            main_workspace_dir=main_workspace_dir,
            max_active_sessions=1,
            reserved_team_slots=team_max_agents,
            workspace_application_required=True,
            session_lifecycle=session_lifecycle,
        )

    return MainAgentRuntimePolicy(
        mode=mode,
        main_workspace_dir=main_workspace_dir,
        max_active_sessions=team_max_agents,
        reserved_team_slots=team_max_agents,
        workspace_application_required=True,
        session_lifecycle=session_lifecycle,
    )


def _main_agent_runtime_manager() -> MainAgentRuntimeManager:
    global _MAIN_AGENT_RUNTIME_MANAGER
    if _MAIN_AGENT_RUNTIME_MANAGER is None:
        _MAIN_AGENT_RUNTIME_MANAGER = MainAgentRuntimeManager(
            ttl_seconds=SESSION_TTL_SECONDS,
            build_agent=_build_agent,
            build_agent_with_selection=_build_agent_with_selection,
            policy=_parse_main_agent_runtime_policy(),
            storage_dir=MAIN_AGENT_SESSION_STORE_DIR,
        )
    return _MAIN_AGENT_RUNTIME_MANAGER


def _parse_novel_style_weight(value: str, default: float = 1.0) -> float:
    raw = (value or "").strip()
    if not raw:
        return default
    try:
        parsed = float(raw)
    except ValueError:
        return default
    if parsed < 0:
        return default
    return parsed


def _parse_env_flag(value: str, default: bool) -> bool:
    raw = (value or "").strip().lower()
    if not raw:
        return default
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off"}:
        return False
    return default


def _parse_novel_agent_profile() -> NovelAgentProfile:
    return NovelAgentProfile(
        profile_id=NOVEL_PROFILE_ID_RAW or "novel-default",
        api_host=(NOVEL_PROFILE_API_HOST_RAW or "https://api.minimaxi.com").rstrip("/"),
        default_style_type=NOVEL_PROFILE_STYLE_TYPE_RAW or "漫画",
        default_style_weight=_parse_novel_style_weight(NOVEL_PROFILE_STYLE_WEIGHT_RAW, default=1.0),
        default_cover_aspect_ratio=NOVEL_PROFILE_COVER_ASPECT_RATIO_RAW or "1:1",
        default_illustration_aspect_ratio=NOVEL_PROFILE_ILLUSTRATION_ASPECT_RATIO_RAW or "16:9",
        memory_namespace=NOVEL_PROFILE_MEMORY_NAMESPACE_RAW or "novel-main",
        tool_profile_id=NOVEL_PROFILE_TOOL_PROFILE_ID_RAW or "novel-default-tools",
        enable_text_tools=_parse_env_flag(NOVEL_PROFILE_ENABLE_TEXT_TOOLS_RAW, True),
        enable_image_tools=_parse_env_flag(NOVEL_PROFILE_ENABLE_IMAGE_TOOLS_RAW, True),
        enable_audio_tools=_parse_env_flag(NOVEL_PROFILE_ENABLE_AUDIO_TOOLS_RAW, True),
    )


def _main_agent_surface_service() -> MainAgentSurfaceService:
    global _MAIN_AGENT_SURFACE_SERVICE, _MAIN_AGENT_USE_CASES
    if _MAIN_AGENT_USE_CASES is not None:
        _MAIN_AGENT_SURFACE_SERVICE = _MAIN_AGENT_USE_CASES
        return _MAIN_AGENT_SURFACE_SERVICE
    if _MAIN_AGENT_SURFACE_SERVICE is None:
        _MAIN_AGENT_SURFACE_SERVICE = MainAgentSurfaceService(
            runtime_manager=_main_agent_runtime_manager(),
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            sse_event=_sse_event,
            format_bootstrap_error=_format_agent_bootstrap_error,
            stream_chunk_size=CHAT_STREAM_CHUNK_SIZE,
        )
        _MAIN_AGENT_USE_CASES = _MAIN_AGENT_SURFACE_SERVICE
    return _MAIN_AGENT_SURFACE_SERVICE


def _novel_use_cases() -> NovelServiceUseCases:
    global _NOVEL_USE_CASES
    if _NOVEL_USE_CASES is None:
        _NOVEL_USE_CASES = NovelServiceUseCases(
            resolve_project_dir=_resolve_project_dir,
            load_novel_demo_module=_load_novel_demo_module,
            create_novel_demo=_create_novel_demo,
            append_chapter_version=_append_chapter_version,
            list_novel_assets=_list_novel_assets,
            chapter_file_path=_chapter_file_path,
            get_version_by_id=_get_version_by_id,
            build_version_summary=_build_version_summary,
            update_chapter_version_metadata=_update_chapter_version_metadata,
            read_chapter_versions=_read_chapter_versions,
            build_chapter_diff=_build_chapter_diff,
            normalize_version_note=_normalize_version_note,
            normalize_version_tags=_normalize_version_tags,
            safe_relative_url=_safe_relative_url,
            profile=_parse_novel_agent_profile(),
        )
    return _NOVEL_USE_CASES


def _channel_ingress_use_cases() -> ChannelIngressUseCases:
    global _CHANNEL_INGRESS_USE_CASES
    if _CHANNEL_INGRESS_USE_CASES is None:
        _CHANNEL_INGRESS_USE_CASES = ChannelIngressUseCases(
            run_main_agent_chat=_run_main_agent_chat,
            novel_use_cases=_novel_use_cases(),
            resolve_workspace_dir=_resolve_workspace_dir,
            to_utc_iso=_to_utc_iso,
            remote_binding_service=RemoteConversationBindingService(
                binding_store=conversation_binding_store,
            ),
        )
    return _CHANNEL_INGRESS_USE_CASES


def _create_novel_demo(project_dir: Path, dry_run: bool, api_host: str | None = None) -> Any:
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
                    "url": _safe_relative_url(path),
                }
            )
    return assets


async def _startup_instance_lock() -> None:
    global _STUDIO_INSTANCE_LOCK
    if not STUDIO_INSTANCE_LOCK_ENABLED:
        return
    lock = GatewayInstanceLock(host=STUDIO_GATEWAY_HOST, port=STUDIO_GATEWAY_PORT)
    try:
        lock.acquire()
    except GatewayInstanceLockError as exc:
        raise RuntimeError(str(exc)) from exc
    _STUDIO_INSTANCE_LOCK = lock


async def _shutdown_cleanup() -> None:
    global _STUDIO_INSTANCE_LOCK, _MAIN_AGENT_SURFACE_SERVICE, _MAIN_AGENT_USE_CASES, _NOVEL_USE_CASES, _CHANNEL_INGRESS_USE_CASES
    try:
        await cleanup_mcp_connections()
    finally:
        try:
            if _MAIN_AGENT_RUNTIME_MANAGER is not None:
                await _MAIN_AGENT_RUNTIME_MANAGER.clear()
            _MAIN_AGENT_SURFACE_SERVICE = None
            _MAIN_AGENT_USE_CASES = None
            _NOVEL_USE_CASES = None
            _CHANNEL_INGRESS_USE_CASES = None
        finally:
            if _STUDIO_INSTANCE_LOCK is not None:
                _STUDIO_INSTANCE_LOCK.release()
                _STUDIO_INSTANCE_LOCK = None


@asynccontextmanager
async def _app_lifespan(_: FastAPI):
    await _startup_instance_lock()
    try:
        yield
    finally:
        await _shutdown_cleanup()


app = FastAPI(
    title="Mini-Agent Studio Gateway",
    version="0.1.0",
    lifespan=_app_lifespan,
)
app.include_router(studio_router)
app.include_router(knowledge_base_router)
app.include_router(memory_manager_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/api/files", StaticFiles(directory=str(WORKSPACE_ROOT), check_dir=True), name="workspace-files")
if STUDIO_UI_DIST_DIR is not None and (STUDIO_UI_DIST_DIR / "assets").exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(STUDIO_UI_DIST_DIR / "assets"), check_dir=True),
        name="studio-assets",
    )


async def _build_health_response() -> SystemHealthResponse:
    runtime = await _main_agent_runtime_manager().get_runtime_diagnostics()
    return SystemHealthResponse(
        status="ok",
        now_utc=_to_utc_iso(datetime.now(timezone.utc)),
        workspace_root=str(WORKSPACE_ROOT),
        runtime=runtime.__dict__,
    )


async def _run_main_agent_chat(request: MainAgentChatRequest) -> MainAgentChatResponse:
    return await _main_agent_surface_service().run_chat(request)


async def _run_channel_message(request: ChannelMessageRequest) -> ChannelMessageResponse:
    return await _channel_ingress_use_cases().handle_message(request)


@app.get("/api/v1/system/health", response_model=ApiEnvelope[SystemHealthResponse])
async def v1_health() -> ApiEnvelope[SystemHealthResponse]:
    return ApiEnvelope[SystemHealthResponse](ok=True, data=await _build_health_response())


@app.get(
    "/api/v1/ops/diagnostics/runtime",
    response_model=MainAgentRuntimeDiagnostics,
    dependencies=[Depends(_require_studio_auth)],
)
async def v1_ops_runtime_diagnostics() -> MainAgentRuntimeDiagnostics:
    runtime = await _main_agent_runtime_manager().get_runtime_diagnostics()
    return MainAgentRuntimeDiagnostics(**runtime.__dict__)


@app.get(
    "/api/v1/ops/diagnostics/routing",
    response_model=MainAgentRoutingDiagnostics,
    dependencies=[Depends(_require_studio_auth)],
)
async def v1_ops_routing_diagnostics() -> MainAgentRoutingDiagnostics:
    return await _main_agent_surface_service().get_routing_diagnostics()


@app.post("/api/v1/agent/chat", response_model=ApiEnvelope[MainAgentChatResponse])
async def v1_agent_chat(request: MainAgentChatRequest) -> ApiEnvelope[MainAgentChatResponse]:
    return ApiEnvelope[MainAgentChatResponse](ok=True, data=await _run_main_agent_chat(request))


@app.post("/api/v1/channel/message", response_model=ApiEnvelope[ChannelMessageResponse])
async def v1_channel_message(request: ChannelMessageRequest) -> ApiEnvelope[ChannelMessageResponse]:
    return ApiEnvelope[ChannelMessageResponse](ok=True, data=await _run_channel_message(request))


async def _list_main_agent_sessions(
    *,
    workspace_dir: str | None = None,
    shared_only: bool = False,
) -> list[MainAgentSessionSummary]:
    return await _main_agent_surface_service().list_sessions(
        workspace_dir=workspace_dir,
        shared_only=shared_only,
    )


async def _create_main_agent_session(request: MainAgentSessionCreateRequest) -> MainAgentSessionDetail:
    return await _main_agent_surface_service().create_session(request)


async def _create_main_agent_derived_session(
    session_id: str,
    request: MainAgentSessionForkRequest,
) -> MainAgentSessionDetail:
    return await _main_agent_surface_service().create_derived_session(session_id, request)


async def _get_main_agent_session_detail(session_id: str, recent_limit: int = 50) -> MainAgentSessionDetail:
    return await _main_agent_surface_service().get_session_detail(session_id, recent_limit=recent_limit)


async def _get_main_agent_session_messages(session_id: str, limit: int = 10) -> list[MainAgentSessionMessage]:
    return await _main_agent_surface_service().get_session_messages(session_id, limit=limit)


def _list_main_agent_models() -> StudioModelListResponse:
    return _STUDIO_OPS_USE_CASES.list_models(catalog_path=None)


async def _delete_main_agent_session(session_id: str) -> MainAgentSessionMutationResponse:
    return await _main_agent_surface_service().delete_session(session_id)


async def _rename_main_agent_session(
    session_id: str,
    request: MainAgentSessionRenameRequest,
) -> MainAgentSessionMutationResponse:
    return await _main_agent_surface_service().rename_session(session_id, request)


async def _share_main_agent_session(
    session_id: str,
    request: MainAgentSessionShareRequest,
) -> MainAgentSessionMutationResponse:
    return await _main_agent_surface_service().set_session_shared(session_id, request)


async def _reset_main_agent_session(session_id: str) -> MainAgentSessionMutationResponse:
    return await _main_agent_surface_service().reset_session(session_id)


async def _cancel_main_agent_session(
    session_id: str,
    request: MainAgentSessionCancelRequest,
) -> MainAgentSessionMutationResponse:
    return await _main_agent_surface_service().cancel_session(session_id, request)


async def _control_main_agent_session(
    session_id: str,
    request: MainAgentSessionControlRequest,
) -> MainAgentSessionControlResponse:
    return await _main_agent_surface_service().control_session(session_id, request)


async def _update_main_agent_session_context(
    session_id: str,
    request: MainAgentSessionContextRequest,
) -> MainAgentSessionContextResponse:
    return await _main_agent_surface_service().update_session_context(session_id, request)


async def _manage_main_agent_session_memory(
    session_id: str,
    request: MainAgentSessionMemoryRequest,
) -> MainAgentSessionMemoryResponse:
    return await _main_agent_surface_service().manage_session_memory(session_id, request)


async def _manage_main_agent_session_skill(
    session_id: str,
    request: MainAgentSessionSkillRequest,
) -> MainAgentSessionSkillResponse:
    return await _main_agent_surface_service().manage_session_skills(session_id, request)


async def _update_main_agent_session_model(
    session_id: str,
    request: MainAgentSessionModelSelectionRequest,
) -> MainAgentSessionModelSelectionResponse:
    return await _main_agent_surface_service().update_session_model_selection(session_id, request)


async def _respond_main_agent_session_approval(
    session_id: str,
    request: MainAgentSessionApprovalRequest,
) -> MainAgentSessionApprovalResponse:
    return await _main_agent_surface_service().respond_to_approval(session_id, request)


async def _update_main_agent_session_runtime_policy(
    session_id: str,
    request: MainAgentSessionRuntimePolicyRequest,
) -> MainAgentSessionRuntimePolicyResponse:
    return await _main_agent_surface_service().update_session_runtime_policy(session_id, request)


@app.get("/api/v1/agent/sessions", response_model=ApiEnvelope[list[MainAgentSessionSummary]])
async def v1_list_sessions(
    workspace_dir: str | None = None,
    shared_only: bool = False,
) -> ApiEnvelope[list[MainAgentSessionSummary]]:
    return ApiEnvelope[list[MainAgentSessionSummary]](
        ok=True,
        data=await _list_main_agent_sessions(workspace_dir=workspace_dir, shared_only=shared_only),
    )


@app.post("/api/v1/agent/sessions", response_model=ApiEnvelope[MainAgentSessionDetail])
async def v1_create_session(
    request: MainAgentSessionCreateRequest,
) -> ApiEnvelope[MainAgentSessionDetail]:
    return ApiEnvelope[MainAgentSessionDetail](
        ok=True,
        data=await _create_main_agent_session(request),
    )


@app.get("/api/v1/agent/sessions/{session_id}", response_model=ApiEnvelope[MainAgentSessionDetail])
async def v1_get_session_detail(
    session_id: str,
    recent_limit: int = 50,
) -> ApiEnvelope[MainAgentSessionDetail]:
    return ApiEnvelope[MainAgentSessionDetail](
        ok=True,
        data=await _get_main_agent_session_detail(session_id, recent_limit=recent_limit),
    )


@app.get("/api/v1/agent/sessions/{session_id}/messages", response_model=ApiEnvelope[list[MainAgentSessionMessage]])
async def v1_get_session_messages(
    session_id: str,
    limit: int = 10,
) -> ApiEnvelope[list[MainAgentSessionMessage]]:
    return ApiEnvelope[list[MainAgentSessionMessage]](
        ok=True,
        data=await _get_main_agent_session_messages(session_id, limit=limit),
    )


@app.get("/api/v1/agent/models", response_model=ApiEnvelope[StudioModelListResponse])
async def v1_list_agent_models() -> ApiEnvelope[StudioModelListResponse]:
    return ApiEnvelope[StudioModelListResponse](ok=True, data=_list_main_agent_models())


@app.delete("/api/v1/agent/sessions/{session_id}", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
async def v1_delete_session(session_id: str) -> ApiEnvelope[MainAgentSessionMutationResponse]:
    return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=await _delete_main_agent_session(session_id))


@app.patch("/api/v1/agent/sessions/{session_id}", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
async def v1_rename_session(
    session_id: str,
    request: MainAgentSessionRenameRequest,
) -> ApiEnvelope[MainAgentSessionMutationResponse]:
    return ApiEnvelope[MainAgentSessionMutationResponse](
        ok=True,
        data=await _rename_main_agent_session(session_id, request),
    )


@app.post("/api/v1/agent/sessions/{session_id}/share", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
async def v1_share_session(
    session_id: str,
    request: MainAgentSessionShareRequest,
) -> ApiEnvelope[MainAgentSessionMutationResponse]:
    return ApiEnvelope[MainAgentSessionMutationResponse](
        ok=True,
        data=await _share_main_agent_session(session_id, request),
    )


@app.post("/api/v1/agent/sessions/{session_id}/fork", response_model=ApiEnvelope[MainAgentSessionDetail])
async def v1_fork_session(
    session_id: str,
    request: MainAgentSessionForkRequest,
) -> ApiEnvelope[MainAgentSessionDetail]:
    return ApiEnvelope[MainAgentSessionDetail](
        ok=True,
        data=await _create_main_agent_derived_session(session_id, request),
    )


@app.post("/api/v1/agent/sessions/{session_id}/reset", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
async def v1_reset_session(session_id: str) -> ApiEnvelope[MainAgentSessionMutationResponse]:
    return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=await _reset_main_agent_session(session_id))


@app.post("/api/v1/agent/sessions/{session_id}/cancel", response_model=ApiEnvelope[MainAgentSessionMutationResponse])
async def v1_cancel_session(
    session_id: str,
    request: MainAgentSessionCancelRequest,
) -> ApiEnvelope[MainAgentSessionMutationResponse]:
    return ApiEnvelope[MainAgentSessionMutationResponse](ok=True, data=await _cancel_main_agent_session(session_id, request))


@app.post("/api/v1/agent/sessions/{session_id}/control", response_model=ApiEnvelope[MainAgentSessionControlResponse])
async def v1_control_session(
    session_id: str,
    request: MainAgentSessionControlRequest,
) -> ApiEnvelope[MainAgentSessionControlResponse]:
    return ApiEnvelope[MainAgentSessionControlResponse](
        ok=True,
        data=await _control_main_agent_session(session_id, request),
    )


@app.post("/api/v1/agent/sessions/{session_id}/context", response_model=ApiEnvelope[MainAgentSessionContextResponse])
async def v1_update_session_context(
    session_id: str,
    request: MainAgentSessionContextRequest,
) -> ApiEnvelope[MainAgentSessionContextResponse]:
    return ApiEnvelope[MainAgentSessionContextResponse](
        ok=True,
        data=await _update_main_agent_session_context(session_id, request),
    )


@app.post("/api/v1/agent/sessions/{session_id}/memory", response_model=ApiEnvelope[MainAgentSessionMemoryResponse])
async def v1_manage_session_memory(
    session_id: str,
    request: MainAgentSessionMemoryRequest,
) -> ApiEnvelope[MainAgentSessionMemoryResponse]:
    return ApiEnvelope[MainAgentSessionMemoryResponse](
        ok=True,
        data=await _manage_main_agent_session_memory(session_id, request),
    )


@app.post("/api/v1/agent/sessions/{session_id}/skill", response_model=ApiEnvelope[MainAgentSessionSkillResponse])
async def v1_manage_session_skill(
    session_id: str,
    request: MainAgentSessionSkillRequest,
) -> ApiEnvelope[MainAgentSessionSkillResponse]:
    return ApiEnvelope[MainAgentSessionSkillResponse](
        ok=True,
        data=await _manage_main_agent_session_skill(session_id, request),
    )


@app.post(
    "/api/v1/agent/sessions/{session_id}/model",
    response_model=ApiEnvelope[MainAgentSessionModelSelectionResponse],
)
async def v1_update_session_model(
    session_id: str,
    request: MainAgentSessionModelSelectionRequest,
) -> ApiEnvelope[MainAgentSessionModelSelectionResponse]:
    return ApiEnvelope[MainAgentSessionModelSelectionResponse](
        ok=True,
        data=await _update_main_agent_session_model(session_id, request),
    )


@app.post("/api/v1/agent/sessions/{session_id}/policy", response_model=ApiEnvelope[MainAgentSessionRuntimePolicyResponse])
async def v1_update_session_runtime_policy(
    session_id: str,
    request: MainAgentSessionRuntimePolicyRequest,
) -> ApiEnvelope[MainAgentSessionRuntimePolicyResponse]:
    return ApiEnvelope[MainAgentSessionRuntimePolicyResponse](
        ok=True,
        data=await _update_main_agent_session_runtime_policy(session_id, request),
    )


@app.post("/api/v1/agent/sessions/{session_id}/approval", response_model=ApiEnvelope[MainAgentSessionApprovalResponse])
async def v1_respond_session_approval(
    session_id: str,
    request: MainAgentSessionApprovalRequest,
) -> ApiEnvelope[MainAgentSessionApprovalResponse]:
    return ApiEnvelope[MainAgentSessionApprovalResponse](
        ok=True,
        data=await _respond_main_agent_session_approval(session_id, request),
    )


async def chat_stream(
    message: str,
    session_id: str | None = None,
    session_title_hint: str | None = None,
    workspace_dir: str | None = None,
    dry_run: bool = False,
    surface: str | None = None,
    channel_type: str | None = None,
    conversation_id: str | None = None,
    sender_id: str | None = None,
) -> StreamingResponse:
    stream = _main_agent_surface_service().stream_chat_events(
        message=message,
        session_id=session_id,
        session_title_hint=session_title_hint,
        workspace_dir=workspace_dir,
        dry_run=dry_run,
        surface=surface,
        channel_type=channel_type,
        conversation_id=conversation_id,
        sender_id=sender_id,
    )

    return StreamingResponse(
        stream,
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@app.get("/api/v1/agent/chat/stream")
async def v1_chat_stream(
    message: str,
    session_id: str | None = None,
    session_title_hint: str | None = None,
    workspace_dir: str | None = None,
    dry_run: bool = False,
    surface: str | None = None,
    channel_type: str | None = None,
    conversation_id: str | None = None,
    sender_id: str | None = None,
) -> StreamingResponse:
    return await chat_stream(
        message=message,
        session_id=session_id,
        session_title_hint=session_title_hint,
        workspace_dir=workspace_dir,
        dry_run=dry_run,
        surface=surface,
        channel_type=channel_type,
        conversation_id=conversation_id,
        sender_id=sender_id,
    )


async def get_novel_config(project_dir: str | None = None) -> dict[str, Any]:
    return await _novel_use_cases().get_config(project_dir=project_dir)


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


async def novel_write(request: NovelWriteRequest) -> dict[str, Any]:
    return await _novel_use_cases().write(
        chapter=request.chapter,
        guidance=request.guidance,
        project_dir=request.project_dir,
        dry_run=request.dry_run,
        api_host=request.api_host,
    )


async def novel_finalize(request: NovelFinalizeRequest) -> dict[str, Any]:
    return await _novel_use_cases().finalize(
        chapter=request.chapter,
        project_dir=request.project_dir,
        dry_run=request.dry_run,
        api_host=request.api_host,
    )


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


async def list_novel_chapters(project_dir: str | None = None) -> dict[str, Any]:
    return await _novel_use_cases().list_chapters(project_dir=project_dir)


async def get_novel_chapter(chapter_number: int, project_dir: str | None = None, final: bool = False) -> dict[str, Any]:
    return await _novel_use_cases().get_chapter(
        chapter_number=chapter_number,
        project_dir=project_dir,
        final=final,
    )


async def save_novel_chapter(chapter_number: int, request: NovelChapterSaveRequest) -> dict[str, Any]:
    return await _novel_use_cases().save_chapter(
        chapter_number=chapter_number,
        text=request.text,
        final=request.final,
        project_dir=request.project_dir,
        note=request.note,
        tags=request.tags,
    )


async def rollback_novel_chapter(chapter_number: int, request: ChapterRollbackRequest) -> dict[str, Any]:
    return await _novel_use_cases().rollback_chapter(
        chapter_number=chapter_number,
        version_id=request.version_id,
        project_dir=request.project_dir,
        final=request.final,
        note=request.note,
        tags=request.tags,
    )


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


async def update_chapter_version(
    chapter_number: int,
    version_id: str,
    request: ChapterVersionMetaUpdateRequest,
) -> dict[str, Any]:
    update_note = "note" in request.model_fields_set
    update_tags = "tags" in request.model_fields_set
    return await _novel_use_cases().update_chapter_version(
        chapter_number=chapter_number,
        version_id=version_id,
        project_dir=request.project_dir,
        final=request.final,
        update_note=update_note,
        note=request.note,
        update_tags=update_tags,
        tags=request.tags,
    )


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


async def list_assets(project_dir: str | None = None) -> dict[str, Any]:
    return await _novel_use_cases().list_assets(project_dir=project_dir)


@app.get("/api/v1/novel/config")
async def v1_get_novel_config(project_dir: str | None = None) -> dict[str, Any]:
    return await get_novel_config(project_dir=project_dir)


@app.post("/api/v1/novel/setup")
async def v1_novel_setup(request: NovelSetupRequest) -> dict[str, Any]:
    return await novel_setup(request)


@app.post("/api/v1/novel/write")
async def v1_novel_write(request: NovelWriteRequest) -> dict[str, Any]:
    return await novel_write(request)


@app.post("/api/v1/novel/finalize")
async def v1_novel_finalize(request: NovelFinalizeRequest) -> dict[str, Any]:
    return await novel_finalize(request)


@app.post("/api/v1/novel/cover")
async def v1_novel_cover(request: NovelCoverRequest) -> dict[str, Any]:
    return await novel_cover(request)


@app.post("/api/v1/novel/illustrate")
async def v1_novel_illustrate(request: NovelIllustrateRequest) -> dict[str, Any]:
    return await novel_illustrate(request)


@app.get("/api/v1/novel/chapters")
async def v1_list_novel_chapters(project_dir: str | None = None) -> dict[str, Any]:
    return await list_novel_chapters(project_dir=project_dir)


@app.get("/api/v1/novel/chapter/{chapter_number}")
async def v1_get_novel_chapter(
    chapter_number: int,
    project_dir: str | None = None,
    final: bool = False,
) -> dict[str, Any]:
    return await get_novel_chapter(chapter_number=chapter_number, project_dir=project_dir, final=final)


@app.put("/api/v1/novel/chapter/{chapter_number}")
async def v1_save_novel_chapter(chapter_number: int, request: NovelChapterSaveRequest) -> dict[str, Any]:
    return await save_novel_chapter(chapter_number=chapter_number, request=request)


@app.post("/api/v1/novel/chapter/{chapter_number}/rollback")
async def v1_rollback_novel_chapter(chapter_number: int, request: ChapterRollbackRequest) -> dict[str, Any]:
    return await rollback_novel_chapter(chapter_number=chapter_number, request=request)


@app.get("/api/v1/novel/chapter/{chapter_number}/versions")
async def v1_list_chapter_versions(
    chapter_number: int,
    project_dir: str | None = None,
    final: bool = False,
) -> dict[str, Any]:
    return await list_chapter_versions(chapter_number=chapter_number, project_dir=project_dir, final=final)


@app.get("/api/v1/novel/chapter/{chapter_number}/version/{version_id}")
async def v1_get_chapter_version(
    chapter_number: int,
    version_id: str,
    project_dir: str | None = None,
    final: bool = False,
) -> dict[str, Any]:
    return await get_chapter_version(
        chapter_number=chapter_number,
        version_id=version_id,
        project_dir=project_dir,
        final=final,
    )


@app.patch("/api/v1/novel/chapter/{chapter_number}/version/{version_id}")
async def v1_update_chapter_version(
    chapter_number: int,
    version_id: str,
    request: ChapterVersionMetaUpdateRequest,
) -> dict[str, Any]:
    return await update_chapter_version(chapter_number=chapter_number, version_id=version_id, request=request)


@app.get("/api/v1/novel/chapter/{chapter_number}/diff")
async def v1_get_chapter_diff(
    chapter_number: int,
    from_version: str,
    to_version: str,
    project_dir: str | None = None,
    final: bool = False,
) -> dict[str, Any]:
    return await get_chapter_diff(
        chapter_number=chapter_number,
        from_version=from_version,
        to_version=to_version,
        project_dir=project_dir,
        final=final,
    )


@app.get("/api/v1/novel/assets")
async def v1_list_assets(project_dir: str | None = None) -> dict[str, Any]:
    return await list_assets(project_dir=project_dir)


if STUDIO_UI_DIST_DIR is not None:

    @app.get("/", include_in_schema=False)
    async def studio_ui_index() -> FileResponse:
        return FileResponse(STUDIO_UI_DIST_DIR / "index.html")


    @app.get("/{full_path:path}", include_in_schema=False)
    async def studio_ui_spa_fallback(full_path: str) -> FileResponse:
        if full_path.startswith("api/") or full_path == "api":
            raise HTTPException(status_code=404, detail="Not found.")

        candidate = (STUDIO_UI_DIST_DIR / full_path).resolve()
        if str(candidate).startswith(str(STUDIO_UI_DIST_DIR.resolve())) and candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(STUDIO_UI_DIST_DIR / "index.html")


else:

    @app.get("/", include_in_schema=False)
    async def studio_ui_not_built() -> dict[str, str]:
        return {
            "message": "Studio UI dist not found. Build frontend first: `cd apps/agent_studio && npm run build`.",
            "expected_dist": str(DEFAULT_STUDIO_UI_DIST),
        }


if __name__ == "__main__":
    uvicorn.run("apps.agent_studio_gateway.main:app", host="127.0.0.1", port=8008, reload=False)
