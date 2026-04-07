"""ACP (Agent Client Protocol) bridge for Mini-Agent."""

from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4

from acp import (
    PROTOCOL_VERSION,
    InitializeResponse,
    NewSessionResponse,
    PromptResponse,
    run_agent,
    start_tool_call,
    text_block,
    tool_content,
    update_agent_message,
    update_agent_thought,
    update_tool_call,
)
from acp.schema import AgentCapabilities, Implementation

from mini_agent.agent import Agent, PlannerExecutorHooks, StepPlan
from mini_agent.config import Config
from mini_agent.llm import LLMClient
from mini_agent.logger import create_agent_logger
from mini_agent.model_manager.failover import FailoverLLMClient
from mini_agent.model_manager.runtime import resolve_routed_llm_candidates
from mini_agent.retry import RetryConfig as RetryConfigBase
from mini_agent.runtime.tooling import (
    add_workspace_tools,
    initialize_shared_tools,
    resolve_runtime_policy,
)
from mini_agent.schema import Message

logger = logging.getLogger(__name__)


class ACPSessionStatus(str, Enum):
    NEW = "new"
    RUNNING = "running"
    CANCELLED = "cancelled"
    CLOSED = "closed"
    EXPIRED = "expired"


@dataclass
class SessionState:
    agent: Agent
    status: ACPSessionStatus = ACPSessionStatus.NEW
    cancel_requested: bool = False
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    last_activity_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def transition(self, status: ACPSessionStatus) -> None:
        now = datetime.now(timezone.utc)
        self.status = status
        self.updated_at = now
        self.last_activity_at = now


class MiniMaxACPAgent:
    """Minimal ACP adapter wrapping the existing Agent runtime."""

    def __init__(
        self,
        config: Config,
        llm: LLMClient,
        base_tools: list,
        system_prompt: str,
        policy_engine=None,
    ):
        self._conn: Any | None = None
        self._config = config
        self._llm = llm
        self._base_tools = base_tools
        self._system_prompt = system_prompt
        self._policy_engine = policy_engine or resolve_runtime_policy(config)
        self._sessions: dict[str, SessionState] = {}
        self._session_ttl_seconds = self._load_session_ttl_seconds()

    @staticmethod
    def _load_session_ttl_seconds() -> int:
        raw = os.getenv("MINI_AGENT_ACP_SESSION_TTL_SECONDS", "3600")
        try:
            parsed = int(raw)
            return max(1, parsed)
        except Exception:
            return 3600

    def on_connect(self, conn: Any) -> None:
        """ACP callback: store client connection for streaming updates."""
        self._conn = conn

    def _resolve_workspace(self, cwd: str | None) -> Path:
        workspace = Path(cwd or self._config.agent.workspace_dir).expanduser()
        if not workspace.is_absolute():
            workspace = workspace.resolve()
        return workspace

    def _create_session_state(self, session_id: str, cwd: str | None) -> SessionState:
        workspace = self._resolve_workspace(cwd)
        tools = list(self._base_tools)
        add_workspace_tools(tools, self._config, workspace, policy_engine=self._policy_engine)
        agent = Agent(
            llm_client=self._llm,
            system_prompt=self._system_prompt,
            tools=tools,
            max_steps=self._config.agent.max_steps,
            max_tool_calls_per_step=self._config.agent.max_tool_calls_per_step,
            workspace_dir=str(workspace),
            logger=create_agent_logger(self._config),
            console_output=False,
        )
        state = SessionState(agent=agent)
        state.transition(ACPSessionStatus.NEW)
        self._sessions[session_id] = state
        return state

    def _expire_sessions(self) -> None:
        now = datetime.now(timezone.utc)
        for state in self._sessions.values():
            if state.status in {ACPSessionStatus.RUNNING, ACPSessionStatus.CLOSED, ACPSessionStatus.EXPIRED}:
                continue
            idle_seconds = (now - state.last_activity_at).total_seconds()
            if idle_seconds > self._session_ttl_seconds:
                state.transition(ACPSessionStatus.EXPIRED)

    def get_session_status(self, session_id: str) -> ACPSessionStatus | None:
        state = self._sessions.get(session_id)
        if state is None:
            return None
        return state.status

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: Any | None = None,
        client_info: Any | None = None,
        **kwargs,
    ) -> InitializeResponse:  # noqa: ARG002
        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_capabilities=AgentCapabilities(loadSession=False),
            agent_info=Implementation(name="mini-agent", title="Mini-Agent", version="0.1.0"),
        )

    async def new_session(self, cwd: str | None = None, **kwargs) -> NewSessionResponse:  # noqa: ARG002
        session_id = f"sess-{len(self._sessions)}-{uuid4().hex[:8]}"
        self._create_session_state(session_id=session_id, cwd=cwd)
        return NewSessionResponse(session_id=session_id)

    async def prompt(self, prompt: list[Any], session_id: str, **kwargs) -> PromptResponse:  # noqa: ARG002
        self._expire_sessions()
        state = self._sessions.get(session_id)
        if not state or state.status in {ACPSessionStatus.CLOSED, ACPSessionStatus.EXPIRED}:
            logger.warning(f"Session '{session_id}' unavailable, auto-creating new session")
            state = self._create_session_state(
                session_id=session_id,
                cwd=str(self._resolve_workspace(None)),
            )
        state.cancel_requested = False
        state.transition(ACPSessionStatus.RUNNING)
        user_text = "\n".join(
            block.get("text", "") if isinstance(block, dict) else getattr(block, "text", "")
            for block in (prompt or [])
        )
        state.agent.messages.append(Message(role="user", content=user_text))
        stop_reason = await self._run_turn(state, session_id)
        if stop_reason == "cancelled":
            state.transition(ACPSessionStatus.CANCELLED)
        elif stop_reason in {"refusal", "max_turn_requests"}:
            state.transition(ACPSessionStatus.CLOSED)
        elif state.status == ACPSessionStatus.RUNNING:
            state.transition(ACPSessionStatus.NEW)
        return PromptResponse(stop_reason=stop_reason)

    async def cancel(self, session_id: str, **kwargs) -> None:  # noqa: ARG002
        state = self._sessions.get(session_id)
        if state and state.status not in {ACPSessionStatus.CLOSED, ACPSessionStatus.EXPIRED}:
            state.cancel_requested = True
            if state.agent.cancel_event is not None:
                state.agent.cancel_event.set()
            state.transition(ACPSessionStatus.CANCELLED)

    async def _run_turn(self, state: SessionState, session_id: str) -> str:
        agent = state.agent
        cancel_event = asyncio.Event()
        if state.cancel_requested:
            cancel_event.set()

        async def on_step_plan(step_plan: StepPlan) -> None:
            if step_plan.response_thinking:
                await self._send(session_id, update_agent_thought(text_block(step_plan.response_thinking)))
            if step_plan.response_content:
                await self._send(session_id, update_agent_message(text_block(step_plan.response_content)))

        async def on_tool_call_start(step: int, tool_call) -> None:  # noqa: ANN001,ARG001
            args = tool_call.function.arguments
            name = tool_call.function.name
            args_preview = (
                ", ".join(f"{key}={repr(value)[:50]}" for key, value in list(args.items())[:2])
                if isinstance(args, dict)
                else ""
            )
            label = f"[Tool] {name}({args_preview})" if args_preview else f"[Tool] {name}()"
            await self._send(session_id, start_tool_call(tool_call.id, label, kind="execute", raw_input=args))

        async def on_tool_call_result(step: int, tool_call, result) -> None:  # noqa: ANN001,ARG001
            status = "completed" if result.success else "failed"
            if result.success:
                text = f"[OK] {result.content}"
            else:
                error_text = result.error or "Tool execution failed"
                if str(error_text).startswith("Unknown tool:"):
                    text = f"[ERROR] {error_text}"
                elif str(error_text).startswith("Tool execution failed:"):
                    text = f"[ERROR] Tool error: {error_text}"
                else:
                    text = f"[ERROR] {error_text}"
            await self._send(
                session_id,
                update_tool_call(
                    tool_call.id,
                    status=status,
                    content=[tool_content(text_block(text))],
                    raw_output=text,
                ),
            )

        hooks = PlannerExecutorHooks(
            on_step_plan=on_step_plan,
            on_tool_call_start=on_tool_call_start,
            on_tool_call_result=on_tool_call_result,
        )

        try:
            turn_result = await agent.run_turn(
                cancel_event=cancel_event,
                hooks=hooks,
                start_new_run=True,
            )
        except Exception as exc:
            logger.exception("ACP turn execution failed")
            await self._send(session_id, update_agent_message(text_block(f"Error: {exc}")))
            return "refusal"
        return turn_result.stop_reason.value

    async def _send(self, session_id: str, update: Any) -> None:
        if self._conn is None:
            return
        await self._conn.session_update(session_id=session_id, update=update)


async def run_acp_server(config: Config | None = None) -> None:
    """Run Mini-Agent as an ACP-compatible stdio server."""
    config = config or Config.load()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    policy_engine = resolve_runtime_policy(config)
    base_tools, skill_loader = await initialize_shared_tools(config, policy_engine=policy_engine)
    prompt_path = Config.find_config_file(config.agent.system_prompt_path)
    if prompt_path and prompt_path.exists():
        system_prompt = prompt_path.read_text(encoding="utf-8")
    else:
        system_prompt = "You are a helpful AI assistant."
    if skill_loader:
        meta = skill_loader.get_skills_metadata_prompt()
        if meta:
            system_prompt = f"{system_prompt.rstrip()}\n\n{meta}"
    rcfg = config.llm.retry
    llm_routes = resolve_routed_llm_candidates(config, requested_model=config.llm.model)
    llm = FailoverLLMClient(
        routes=llm_routes,
        retry_config=RetryConfigBase(
            enabled=rcfg.enabled,
            max_retries=rcfg.max_retries,
            initial_delay=rcfg.initial_delay,
            max_delay=rcfg.max_delay,
            exponential_base=rcfg.exponential_base,
        ),
    )

    agent = MiniMaxACPAgent(
        config=config,
        llm=llm,
        base_tools=base_tools,
        system_prompt=system_prompt,
        policy_engine=policy_engine,
    )
    logger.info("Mini-Agent ACP server running")
    await run_agent(agent)


def main() -> None:
    asyncio.run(run_acp_server())


__all__ = ["ACPSessionStatus", "MiniMaxACPAgent", "run_acp_server", "main"]
