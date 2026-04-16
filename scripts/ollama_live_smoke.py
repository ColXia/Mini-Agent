"""Live smoke for the maintained Ollama local provider path.

Checks:
- preset discovery resolves a local Ollama route
- one real streamed prompt completes through `preset-ollama`
- optional tool call smoke executes through the full agent loop
"""
# ruff: noqa: E402

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from mini_agent.agent_core.kernel import AgentKernelBuildOptions, build_agent_kernel
from mini_agent.cli_interactive import create_submission_loop_for_agent, run_prompt_via_submission_loop
from mini_agent.model_manager.model_discovery import ModelDiscoveryService, ProviderType
from mini_agent.model_manager.preset_providers import PresetProvider, get_preset_provider_config
from mini_agent.tools.mcp_loader import cleanup_mcp_connections


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


async def _run_one_turn(
    *,
    workspace: Path,
    model_id: str,
    prompt: str,
    session_id: str,
) -> dict[str, Any]:
    agent = await build_agent_kernel(
        workspace_dir=workspace,
        options=AgentKernelBuildOptions(
            requested_provider_source="preset",
            requested_provider_id="ollama",
            requested_model=model_id,
            allow_interactive_setup=False,
            suppress_background_output=True,
            console_output=False,
        ),
    )

    event_counts: dict[str, int] = {}
    text_deltas: list[str] = []
    tool_events: list[dict[str, Any]] = []

    async def _on_event(event_type: str, payload: dict[str, Any]) -> None:
        event_counts[event_type] = event_counts.get(event_type, 0) + 1
        if event_type == "loop.llm_event":
            llm_event_type = _safe_text(payload.get("llm_event_type"))
            if llm_event_type:
                key = f"llm:{llm_event_type}"
                event_counts[key] = event_counts.get(key, 0) + 1
            delta = str(payload.get("delta") or "")
            if delta:
                text_deltas.append(delta)
            if llm_event_type == "tool_call":
                tool_events.append(
                    {
                        "event_type": event_type,
                        "tool_name": _safe_text(payload.get("tool_name")),
                        "tool_call_id": _safe_text(payload.get("tool_call_id")),
                    }
                )
        elif event_type == "loop.activity":
            label = _safe_text(payload.get("label"))
            if label in {"thinking", "shell"}:
                tool_events.append(
                    {
                        "event_type": event_type,
                        "label": label,
                        "detail": _safe_text(payload.get("detail")),
                        "preview": _safe_text(payload.get("preview")),
                        "output_summary": _safe_text(payload.get("output_summary")),
                    }
                )

    loop, bus = await create_submission_loop_for_agent(agent=agent, session_id=session_id)
    try:
        payload = await run_prompt_via_submission_loop(
            loop=loop,
            bus=bus,
            agent=agent,
            prompt=prompt,
            metadata={"surface": "headless", "mode": "ollama_live_smoke"},
            start_new_run=True,
            approval_resolver=lambda _payload: True,
            event_handler=_on_event,
        )
        return {
            "route_provider_id": _safe_text(getattr(getattr(agent, "runtime_route", None), "provider_id", None)),
            "route_model": _safe_text(getattr(getattr(agent, "runtime_route", None), "model", None)),
            "state": _safe_text(payload.get("state")),
            "stop_reason": _safe_text(payload.get("stop_reason")),
            "message": payload.get("message"),
            "error": payload.get("error"),
            "event_counts": event_counts,
            "text_preview": "".join(text_deltas)[:240],
            "tool_events": tool_events[:12],
        }
    finally:
        await loop.stop()


async def _run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    import os

    os.environ["MINI_AGENT_OLLAMA_ENABLED"] = "1"
    if args.protocol:
        os.environ["MINI_AGENT_OLLAMA_PROTOCOL"] = args.protocol

    try:
        discovery = await ModelDiscoveryService().discover_models(
            ProviderType.OLLAMA,
            "ollama",
            api_base=args.host,
            use_cache=False,
        )
        preset = get_preset_provider_config(PresetProvider.OLLAMA, use_latest_model=True)
        if preset is None:
            raise RuntimeError("preset-ollama is unavailable after local discovery")

        model_id = _safe_text(args.model) or _safe_text(preset.get("model"))
        if not model_id:
            raise RuntimeError("no Ollama model available for smoke")

        workspace = args.workspace.resolve()
        workspace.mkdir(parents=True, exist_ok=True)

        basic = await _run_one_turn(
            workspace=workspace,
            model_id=model_id,
            prompt=args.prompt,
            session_id="ollama-live-smoke-basic",
        )

        tool_smoke: dict[str, Any] | None = None
        if not args.skip_tool_smoke:
            tool_smoke = await _run_one_turn(
                workspace=workspace,
                model_id=model_id,
                prompt=args.tool_prompt,
                session_id="ollama-live-smoke-tool",
            )

        available_models = [str(item.id) for item in discovery.available_models]
        report = {
            "host": args.host,
            "protocol": _safe_text(args.protocol) or "anthropic",
            "discovery": {
                "error": discovery.error,
                "source": discovery.discovery_source,
                "available_models": available_models,
                "recommended_model": _safe_text(preset.get("model")),
            },
            "selected_model": model_id,
            "basic_smoke": basic,
            "tool_smoke": tool_smoke,
        }
        return report
    finally:
        await cleanup_mcp_connections()


def _is_success(report: dict[str, Any]) -> bool:
    basic = report.get("basic_smoke") or {}
    if basic.get("state") != "completed" or basic.get("stop_reason") not in {"", "end_turn"}:
        return False
    if _safe_text(basic.get("route_provider_id")) != "preset-ollama":
        return False
    if int((basic.get("event_counts") or {}).get("llm:text_delta", 0)) <= 0:
        return False

    tool_smoke = report.get("tool_smoke")
    if tool_smoke is None:
        return True
    if tool_smoke.get("state") != "completed" or tool_smoke.get("stop_reason") not in {"", "end_turn"}:
        return False
    tool_event_count = int((tool_smoke.get("event_counts") or {}).get("llm:tool_call", 0))
    return tool_event_count > 0


def _collect_warnings(report: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    basic = report.get("basic_smoke") or {}
    if _safe_text(basic.get("message")) == "":
        warnings.append("basic smoke completed without a final assistant text message")

    tool_smoke = report.get("tool_smoke") or {}
    if tool_smoke:
        if _safe_text(tool_smoke.get("message")) == "":
            warnings.append(
                "tool smoke completed without a final assistant text message; "
                "tool routing worked, but finalization quality may differ on this model/protocol path"
            )
        text_delta_count = int((tool_smoke.get("event_counts") or {}).get("llm:text_delta", 0))
        if text_delta_count <= 0:
            warnings.append(
                "tool smoke emitted no final text deltas; the model appears to end the turn using thinking/tool flow only"
            )
    return warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run live Ollama local-provider smoke checks.")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=REPO_ROOT,
        help="Workspace used to build the smoke agent.",
    )
    parser.add_argument(
        "--host",
        default="http://localhost:11434",
        help="Ollama host base URL.",
    )
    parser.add_argument(
        "--protocol",
        choices=["anthropic", "openai"],
        default="anthropic",
        help="Mini-Agent runtime protocol family for Ollama.",
    )
    parser.add_argument(
        "--model",
        default="",
        help="Override smoke model id. Defaults to the preset recommendation.",
    )
    parser.add_argument(
        "--prompt",
        default="Reply with exactly OLLAMA_SMOKE_OK and nothing else.",
        help="Prompt for the basic smoke run.",
    )
    parser.add_argument(
        "--tool-prompt",
        default="Use the bash tool to run exactly: echo OLLAMA_TOOL_SMOKE . After the tool returns, reply with exactly TOOL_OK.",
        help="Prompt for the optional tool smoke run.",
    )
    parser.add_argument(
        "--skip-tool-smoke",
        action="store_true",
        help="Skip the tool-call smoke run.",
    )
    args = parser.parse_args()

    try:
        report = asyncio.run(_run_smoke(args))
    except Exception as exc:  # noqa: BLE001
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 1

    report["ok"] = _is_success(report)
    report["warnings"] = _collect_warnings(report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
