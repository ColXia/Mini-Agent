"""P23 runtime baseline benchmark for gateway main-agent path.

Measures lightweight p50/p95 latency for chat and stream paths with an
in-memory dummy agent and writes a markdown report plus JSON artifact.
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import statistics
import sys
import time
from types import SimpleNamespace
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mini_agent.application.use_cases.agent_interaction_application_service import (  # noqa: E402
    AgentInteractionApplicationService,
)
from mini_agent.application.use_cases.session_task_service import SessionTaskService  # noqa: E402
from mini_agent.application.user_services.service_assembly import (  # noqa: E402
    resolve_runtime_backed_user_service_ports,
)
from mini_agent.config import AgentConfig, Config, LLMConfig, ToolsConfig  # noqa: E402
from mini_agent.interfaces.agent import MainAgentChatRequest  # noqa: E402
from mini_agent.runtime.main_agent_runtime_manager import MainAgentRuntimeManager  # noqa: E402


class _BenchAgent:
    def __init__(self) -> None:
        self.messages = [SimpleNamespace(role="system", content="system")]
        self.api_total_tokens = 0

    def add_user_message(self, content: str) -> None:
        self.messages.append(SimpleNamespace(role="user", content=content))

    async def run(self, *, cancel_event: asyncio.Event | None = None) -> str:
        _ = cancel_event
        text = f"bench:{self.messages[-1].content}"
        self.messages.append(SimpleNamespace(role="assistant", content=text))
        self.api_total_tokens += 3
        return text


def _pctl(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(0, math.ceil((p / 100.0) * len(ordered)) - 1)
    return ordered[min(rank, len(ordered) - 1)]


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"count": 0.0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    return {
        "count": float(len(values)),
        "mean_ms": round(statistics.fmean(values), 3),
        "p50_ms": round(_pctl(values, 50), 3),
        "p95_ms": round(_pctl(values, 95), 3),
        "max_ms": round(max(values), 3),
    }


def _to_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _sse_event(event: str, data: dict[str, Any]) -> str:
    return f"event: {event}\ndata: {data}\n\n"


def _format_bootstrap_error(exc: Exception):
    raise RuntimeError(str(exc))


def _test_runtime_config() -> Config:
    return Config(
        llm=LLMConfig(
            api_key="sk-test",
            api_base="https://api.example.com/v1",
            model="gpt-5.4",
            provider="openai",
        ),
        agent=AgentConfig(
            max_steps=8,
            max_tool_calls_per_step=2,
            system_prompt_path="system_prompt.md",
        ),
        tools=ToolsConfig(
            enable_file_tools=False,
            enable_bash=False,
            enable_note=False,
            enable_skills=False,
            enable_mcp=False,
        ),
    )


def _resolve_workspace_dir(workspace_dir: str | None) -> Path:
    return Path(workspace_dir or ".").resolve()


def _build_interaction_service(*, runtime: MainAgentRuntimeManager) -> AgentInteractionApplicationService:
    ports = resolve_runtime_backed_user_service_ports(runtime_manager=runtime)
    session_task_service = SessionTaskService(
        runtime_manager=ports.session_task_runtime,
        session_agent_runtime=ports.session_agent_runtime,
    )
    return AgentInteractionApplicationService(
        session_task_service=session_task_service,
        resolve_workspace_dir=_resolve_workspace_dir,
        to_utc_iso=_to_utc_iso,
        sse_event=_sse_event,
        format_bootstrap_error=_format_bootstrap_error,
        stream_chunk_size=64,
    )


async def _run_benchmark(workspace: Path, runs: int) -> dict[str, Any]:
    async def _build_agent(_workspace: Path):
        return _BenchAgent()

    runtime = MainAgentRuntimeManager(
        ttl_seconds=3600,
        build_agent=_build_agent,
        load_runtime_config=_test_runtime_config,
    )
    interaction_service = _build_interaction_service(runtime=runtime)

    chat_ms: list[float] = []
    stream_ms: list[float] = []

    for i in range(runs):
        start = time.perf_counter()
        _ = await interaction_service.submit_message(
            MainAgentChatRequest(
                message=f"benchmark-chat-{i}",
                session_id="bench-chat",
                workspace_dir=str(workspace),
            )
        )
        chat_ms.append((time.perf_counter() - start) * 1000.0)

    for i in range(runs):
        start = time.perf_counter()
        async for _ in interaction_service.stream_message(
            message=f"benchmark-stream-{i}",
            session_id="bench-chat",
            workspace_dir=str(workspace),
            dry_run=False,
        ):
            pass
        stream_ms.append((time.perf_counter() - start) * 1000.0)

    return {
        "runs": runs,
        "chat": _summary(chat_ms),
        "stream": _summary(stream_ms),
        "captured_at_utc": _to_utc_iso(datetime.now(timezone.utc)),
    }


def _render_markdown(summary: dict[str, Any]) -> str:
    chat = summary["chat"]
    stream = summary["stream"]
    return "\n".join(
        [
            "# P23 Runtime Baseline",
            "",
            f"- captured_at_utc: {summary['captured_at_utc']}",
            f"- runs: {summary['runs']}",
            "",
            "## Chat Path",
            "",
            f"- mean_ms: {chat['mean_ms']}",
            f"- p50_ms: {chat['p50_ms']}",
            f"- p95_ms: {chat['p95_ms']}",
            f"- max_ms: {chat['max_ms']}",
            "",
            "## Stream Path",
            "",
            f"- mean_ms: {stream['mean_ms']}",
            f"- p50_ms: {stream['p50_ms']}",
            f"- p95_ms: {stream['p95_ms']}",
            f"- max_ms: {stream['max_ms']}",
            "",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run P23 runtime p95 baseline benchmark.")
    parser.add_argument(
        "--workspace",
        type=str,
        default=".",
        help="Workspace directory used for benchmark context.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=50,
        help="Number of iterations per path (chat/stream).",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="workspace/perf",
        help="Directory for markdown/json artifacts.",
    )
    args = parser.parse_args()

    workspace = Path(args.workspace).expanduser().resolve()
    runs = max(10, int(args.runs))
    output_dir = Path(args.output_dir).expanduser().resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    summary = asyncio.run(_run_benchmark(workspace, runs))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    md_path = output_dir / f"p23_runtime_baseline_{stamp}.md"
    json_path = output_dir / f"p23_runtime_baseline_{stamp}.json"
    md_path.write_text(_render_markdown(summary), encoding="utf-8")
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[p23-baseline] markdown={md_path}")
    print(f"[p23-baseline] json={json_path}")
    print(
        "[p23-baseline] p95(chat_ms)={chat} p95(stream_ms)={stream}".format(
            chat=summary["chat"]["p95_ms"],
            stream=summary["stream"]["p95_ms"],
        )
    )


if __name__ == "__main__":
    main()
