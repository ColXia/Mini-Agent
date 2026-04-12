from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from dotenv import dotenv_values

from mini_agent.agent import PlannerExecutorHooks
from mini_agent.agent_core.kernel import AgentKernelBuildOptions, build_agent_kernel


REPO_ROOT = Path(__file__).resolve().parents[1]
OFFICIAL_PRESET_ENV_KEYS = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY",
    "MINIMAX_API_KEY",
)
PLACEHOLDER_KEYS = {
    "YOUR_API_KEY_HERE",
    "YOUR_OPENAI_API_KEY_HERE",
    "YOUR_ANTHROPIC_API_KEY_HERE",
    "YOUR_GEMINI_API_KEY_HERE",
    "YOUR_MINIMAX_API_KEY_HERE",
    "your_api_key",
    "your-api-key",
    "sk-cp-xxxxx",
    "sk-...",
    "sk-ant-...",
}
DEFAULT_CASES: list[tuple[str, str]] = [
    (
        "frontend-dev",
        "帮我重做这个 React 管理后台页面布局和交互。现在先不要改代码、不要执行 bash、不要联网，只判断你会调用什么能力以及你的实施思路。",
    ),
    (
        "fullstack-dev",
        "给这个项目做一个前后端打通的设置页和保存接口。现在先不要改代码、不要执行 bash、不要联网，只判断你会调用什么能力以及你的实施思路。",
    ),
    (
        "buddy-sings",
        "给 nyonyo 做一段简短的欢迎歌曲。现在先不要实际生成音频，只判断你会调用什么能力以及你的实施思路。",
    ),
    (
        "minimax-music-playlist",
        "给这个 demo 设计一个三首曲子的背景音乐播放列表。现在先不要实际生成音频，只判断你会调用什么能力以及你的实施思路。",
    ),
]


def _is_valid_key(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if text in PLACEHOLDER_KEYS:
        return False
    if text.endswith("..."):
        return False
    if (text.startswith("${") and text.endswith("}")) or (text.startswith("$") and len(text) > 1):
        return False
    return True


def _available_key_sources() -> list[tuple[str, str]]:
    found: list[tuple[str, str]] = []
    for env_key in OFFICIAL_PRESET_ENV_KEYS:
        if _is_valid_key(os.getenv(env_key)):
            found.append(("env", env_key))

    env_local = REPO_ROOT / ".env.local"
    if env_local.exists():
        values = dotenv_values(env_local)
        for env_key in OFFICIAL_PRESET_ENV_KEYS:
            if _is_valid_key(values.get(env_key)):
                found.append((".env.local", env_key))
    return found


def _safe_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _tool_name_from_call(tool_call: Any) -> str:
    function = getattr(tool_call, "function", None)
    return _safe_text(getattr(function, "name", None))


def _tool_arguments_from_call(tool_call: Any) -> dict[str, Any]:
    function = getattr(tool_call, "function", None)
    args = getattr(function, "arguments", None)
    return dict(args) if isinstance(args, dict) else {}


async def _run_case(
    *,
    expected_skill: str,
    prompt: str,
    workspace_root: Path,
) -> dict[str, Any]:
    from mini_agent.tools.mcp_loader import cleanup_mcp_connections

    case_slug = expected_skill.replace("/", "-").strip() or "probe"
    workspace = Path(
        tempfile.mkdtemp(
            prefix=f"{case_slug}-",
            dir=str(workspace_root),
        )
    ).resolve()

    agent = await build_agent_kernel(
        workspace_dir=workspace,
        options=AgentKernelBuildOptions(
            console_output=False,
            allow_interactive_setup=False,
            suppress_background_output=True,
        ),
    )
    agent.console_output = False
    agent.max_steps = min(int(getattr(agent, "max_steps", 6) or 6), 6)

    planned_tool_names: list[str] = []
    started_tool_names: list[str] = []
    completed_tool_calls: list[dict[str, Any]] = []
    cleanup_error: str | None = None

    async def _on_step_plan(plan) -> None:  # noqa: ANN001
        for tool_call in list(getattr(plan, "planned_tool_calls", []) or []):
            planned_tool_names.append(_tool_name_from_call(tool_call))

    async def _on_tool_start(step: int, tool_call) -> None:  # noqa: ANN001
        _ = step
        started_tool_names.append(_tool_name_from_call(tool_call))

    async def _on_tool_result(step: int, tool_call, result) -> None:  # noqa: ANN001
        _ = step
        completed_tool_calls.append(
            {
                "name": _tool_name_from_call(tool_call),
                "arguments": _tool_arguments_from_call(tool_call),
                "success": bool(getattr(result, "success", False)),
            }
        )

    payload: dict[str, Any]
    try:
        agent.add_user_message(prompt)
        result = await agent.run_turn(
            hooks=PlannerExecutorHooks(
                on_step_plan=_on_step_plan,
                on_tool_call_start=_on_tool_start,
                on_tool_call_result=_on_tool_result,
            ),
        )
        get_skill_calls = [item for item in completed_tool_calls if item["name"] == "get_skill"]
        loaded_skills = [
            _safe_text(item.get("arguments", {}).get("skill_name"))
            for item in get_skill_calls
            if _safe_text(item.get("arguments", {}).get("skill_name"))
        ]
        route = getattr(agent, "runtime_route", None)
        payload = {
            "expected_skill": expected_skill,
            "prompt": prompt,
            "stop_reason": getattr(getattr(result, "stop_reason", None), "value", str(getattr(result, "stop_reason", ""))),
            "message_preview": _safe_text(getattr(result, "message", ""))[:240],
            "model": _safe_text(getattr(getattr(agent, "llm", None), "model", None))
            or _safe_text(getattr(getattr(agent, "llm_client", None), "model", None))
            or "unknown",
            "provider_id": _safe_text(getattr(route, "provider_id", None)) or "unknown",
            "planned_tool_names": planned_tool_names,
            "started_tool_names": started_tool_names,
            "tool_calls": completed_tool_calls,
            "called_get_skill": bool(get_skill_calls),
            "loaded_skills": loaded_skills,
            "matched_expected_skill": expected_skill in loaded_skills,
        }
    except asyncio.CancelledError as exc:
        payload = {
            "expected_skill": expected_skill,
            "prompt": prompt,
            "error": f"cancelled: {exc}",
            "planned_tool_names": planned_tool_names,
            "started_tool_names": started_tool_names,
            "tool_calls": completed_tool_calls,
            "called_get_skill": any(item.get("name") == "get_skill" for item in completed_tool_calls),
            "loaded_skills": [
                _safe_text(item.get("arguments", {}).get("skill_name"))
                for item in completed_tool_calls
                if item.get("name") == "get_skill" and _safe_text(item.get("arguments", {}).get("skill_name"))
            ],
            "matched_expected_skill": False,
        }
    except Exception as exc:
        payload = {
            "expected_skill": expected_skill,
            "prompt": prompt,
            "error": f"{type(exc).__name__}: {exc}",
            "planned_tool_names": planned_tool_names,
            "started_tool_names": started_tool_names,
            "tool_calls": completed_tool_calls,
            "called_get_skill": any(item.get("name") == "get_skill" for item in completed_tool_calls),
            "loaded_skills": [
                _safe_text(item.get("arguments", {}).get("skill_name"))
                for item in completed_tool_calls
                if item.get("name") == "get_skill" and _safe_text(item.get("arguments", {}).get("skill_name"))
            ],
            "matched_expected_skill": False,
        }
    finally:
        llm_client = getattr(agent, "llm", None)
        close_method = getattr(llm_client, "close", None)
        if callable(close_method):
            try:
                result = close_method()
                if hasattr(result, "__await__"):
                    await result
            except asyncio.CancelledError as exc:
                cleanup_error = cleanup_error or f"llm cleanup cancelled: {exc}"
            except Exception as exc:
                cleanup_error = cleanup_error or f"llm cleanup {type(exc).__name__}: {exc}"
        try:
            await cleanup_mcp_connections()
        except asyncio.CancelledError as exc:
            cleanup_error = f"cleanup cancelled: {exc}"
        except Exception as exc:
            cleanup_error = f"cleanup {type(exc).__name__}: {exc}"
    if cleanup_error:
        payload["cleanup_error"] = cleanup_error
    return payload


def _run_all_cases(args: argparse.Namespace) -> dict[str, Any]:
    key_sources = _available_key_sources()
    if not key_sources:
        return {
            "ok": False,
            "skipped": True,
            "reason": "no valid provider key found in env or .env.local",
            "results": [],
        }

    workspace_root = Path(args.workspace).expanduser().resolve()
    workspace_root.mkdir(parents=True, exist_ok=True)

    cases = list(DEFAULT_CASES)
    if args.prompt:
        expected_skill = str(args.expected_skill or "").strip() or "unknown"
        cases = [(expected_skill, str(args.prompt).strip())]

    results: list[dict[str, Any]] = []
    for expected_skill, prompt in cases:
        results.append(
            asyncio.run(
                _run_case(
                    expected_skill=expected_skill,
                    prompt=prompt,
                    workspace_root=workspace_root,
                )
            )
        )

    called_count = sum(1 for item in results if item.get("called_get_skill"))
    matched_count = sum(1 for item in results if item.get("matched_expected_skill"))
    return {
        "ok": True,
        "skipped": False,
        "key_sources": key_sources,
        "results": results,
        "summary": {
            "cases": len(results),
            "called_get_skill": called_count,
            "matched_expected_skill": matched_count,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe whether a live Mini-Agent turn actively calls get_skill.")
    parser.add_argument(
        "--workspace",
        default=str((REPO_ROOT / "workspace" / "skill-live-probe").resolve()),
        help="Workspace root for probe runs.",
    )
    parser.add_argument(
        "--prompt",
        default=None,
        help="Optional single prompt override.",
    )
    parser.add_argument(
        "--expected-skill",
        default=None,
        help="Expected skill for --prompt mode.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = _run_all_cases(args)
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    try:
        print(text)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(text.encode("utf-8", errors="replace"))
        sys.stdout.buffer.write(b"\n")
    if payload.get("skipped"):
        return 0
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
