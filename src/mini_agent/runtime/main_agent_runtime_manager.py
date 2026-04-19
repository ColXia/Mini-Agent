"""Runtime manager for single-host main-agent session lifecycle."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any, Callable

from mini_agent.runtime.handlers.main_agent_runtime_public_api_mixin import (
    MainAgentRuntimePublicApiMixin,
)
from mini_agent.runtime.handlers.session_agent_runtime_handler import (
    BuildAgentFn,
    BuildSelectedAgentFn,
)
from mini_agent.runtime.orchestration.main_agent_runtime_assembly_mixin import (
    MainAgentRuntimeAssemblyMixin,
)
from mini_agent.runtime.orchestration.session_runtime_policy_coordinator import (
    MainAgentRuntimePolicy,
)
from mini_agent.session.store_records import MainAgentSessionState


class MainAgentRuntimeManager(MainAgentRuntimePublicApiMixin, MainAgentRuntimeAssemblyMixin):
    """In-process manager enforcing main-agent runtime/session policies."""

    def __init__(
        self,
        *,
        ttl_seconds: int,
        build_agent: BuildAgentFn,
        build_agent_with_selection: BuildSelectedAgentFn | None = None,
        policy: MainAgentRuntimePolicy | None = None,
        storage_dir: Path | None = None,
        load_runtime_config: Callable[[], Any],
        resolve_agent_model_identity: Callable[[], tuple[str, str, str] | None] | None = None,
    ):
        self._ttl_seconds = int(ttl_seconds)
        self._build_agent = build_agent
        self._build_agent_with_selection = build_agent_with_selection
        self._policy = policy or MainAgentRuntimePolicy()
        self._load_runtime_config = load_runtime_config
        self._resolve_agent_model_identity = resolve_agent_model_identity
        self._sessions: dict[str, MainAgentSessionState] = {}
        self._store_lock = asyncio.Lock()
        self._initialize_runtime_core(storage_dir)
        self._initialize_runtime_support_services()
        self._initialize_session_model_services()
        self._initialize_session_runtime_services()
        self._initialize_session_boundary_services()


