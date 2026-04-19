from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from apps.agent_studio_gateway.composition import GatewayComposition, GatewayCompositionSettings
from apps.agent_studio_gateway.main_agent_router import create_main_agent_router
from apps.agent_studio_gateway.ops_auth import require_ops_auth
from apps.agent_studio_gateway.ops_router import OpsRouterDependencies, create_ops_router
from mini_agent.application.use_cases import MemoryOperationsUseCases, ProviderOperationsUseCases
from subprograms.knowledge_base.gateway.router import router as knowledge_base_router
from subprograms.memory_manager.gateway.router import router as memory_manager_router

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKSPACE_ROOT = REPO_ROOT / "workspace"
SESSION_TTL_SECONDS = 2 * 60 * 60
CHAT_STREAM_CHUNK_SIZE = 120
STUDIO_GATEWAY_HOST = os.getenv("MINI_AGENT_STUDIO_HOST", "127.0.0.1").strip() or "127.0.0.1"
STUDIO_GATEWAY_PORT = int(os.getenv("MINI_AGENT_STUDIO_PORT", "8008"))
STUDIO_INSTANCE_LOCK_ENABLED = (
    os.getenv("MINI_AGENT_STUDIO_ENABLE_INSTANCE_LOCK", "1").strip().lower() in {"1", "true", "yes", "on"}
)
MAIN_AGENT_SESSION_STORE_DIR = Path(
    os.getenv(
        "MINI_AGENT_MAIN_SESSION_STORE_DIR",
        str(Path.home() / ".mini-agent" / "state" / "main_agent_runtime"),
    )
).expanduser()

GATEWAY_SETTINGS = GatewayCompositionSettings(
    repo_root=REPO_ROOT,
    workspace_root=WORKSPACE_ROOT,
    session_ttl_seconds=SESSION_TTL_SECONDS,
    chat_stream_chunk_size=CHAT_STREAM_CHUNK_SIZE,
    studio_gateway_host=STUDIO_GATEWAY_HOST,
    studio_gateway_port=STUDIO_GATEWAY_PORT,
    studio_instance_lock_enabled=STUDIO_INSTANCE_LOCK_ENABLED,
    session_store_dir=MAIN_AGENT_SESSION_STORE_DIR,
)
GATEWAY_COMPOSITION = GatewayComposition(
    settings=GATEWAY_SETTINGS,
    require_ops_auth=require_ops_auth,
)
GATEWAY_PROVIDER_OPERATIONS_USE_CASES = ProviderOperationsUseCases(
    repo_root=REPO_ROOT,
    workspace_root=WORKSPACE_ROOT,
)
GATEWAY_MEMORY_OPERATIONS_USE_CASES = MemoryOperationsUseCases(
    repo_root=REPO_ROOT,
    workspace_root=WORKSPACE_ROOT,
)


def _get_provider_operations_use_cases() -> ProviderOperationsUseCases:
    return GATEWAY_PROVIDER_OPERATIONS_USE_CASES


def _get_memory_operations_use_cases() -> MemoryOperationsUseCases:
    return GATEWAY_MEMORY_OPERATIONS_USE_CASES


def _list_main_agent_models():
    return GATEWAY_PROVIDER_OPERATIONS_USE_CASES.list_models(catalog_path=None)


app = FastAPI(
    title="Mini-Agent Gateway",
    version="0.1.0",
    lifespan=GATEWAY_COMPOSITION.lifespan,
)
app.include_router(
    create_ops_router(
        OpsRouterDependencies(
            get_memory_operations_use_cases=_get_memory_operations_use_cases,
            get_provider_operations_use_cases=_get_provider_operations_use_cases,
            require_ops_auth=require_ops_auth,
        )
    )
)
app.include_router(knowledge_base_router)
app.include_router(memory_manager_router)
app.include_router(
    create_main_agent_router(
        GATEWAY_COMPOSITION.build_main_agent_router_dependencies(
            list_models=_list_main_agent_models,
        )
    )
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
WORKSPACE_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/api/files", StaticFiles(directory=str(WORKSPACE_ROOT.resolve()), check_dir=True), name="workspace-files")


@app.get("/", include_in_schema=False)
async def gateway_root() -> dict[str, object]:
    return {
        "service": "mini-agent-gateway",
        "status": "ok",
        "entrances": ["cli", "tui", "desktop", "remote"],
        "removed_surfaces": ["webui", "openwebui"],
        "message": "Browser WebUI/OpenWebUI were removed. Use CLI, TUI, Desktop, or remote adapters.",
    }


if __name__ == "__main__":
    uvicorn.run("apps.agent_studio_gateway.main:app", host="127.0.0.1", port=8008, reload=False)
