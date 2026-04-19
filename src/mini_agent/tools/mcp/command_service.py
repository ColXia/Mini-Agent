"""Shared operator-facing MCP command semantics across local and runtime surfaces."""

from __future__ import annotations

import inspect
from dataclasses import dataclass
from typing import Any, Awaitable, Callable

from mini_agent.runtime.handlers.session_agent_control_handler import SessionControlErrorService


def _safe_text(value: object) -> str:
    return " ".join(str(value or "").split())


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


@dataclass(slots=True)
class McpReloadOutcome:
    rebuilt_runtime: bool = False
    active_model_label: str | None = None


def format_cli_mcp_reload_success(outcome: McpReloadOutcome) -> str:
    """Return the canonical CLI success line for a local MCP reload."""

    model_label = _safe_text(outcome.active_model_label)
    if outcome.rebuilt_runtime and model_label:
        return f"Reloaded MCP bindings; current CLI agent reloaded on {model_label}"
    return "Reloaded MCP bindings"


def build_mcp_reload_warm_prefix(session_label: str) -> str:
    """Return the canonical warm-reload prefix for local surface runtime rebuilds."""

    label = _safe_text(session_label)
    return f"MCP bindings reloaded for {label}" if label else "MCP bindings reloaded"


@dataclass(frozen=True, slots=True)
class McpCommandError(Exception):
    detail: str
    status_code: int = 400

    def __str__(self) -> str:
        return self.detail


@dataclass(frozen=True, slots=True)
class McpCommandResult:
    action: str
    summary: str
    details: str
    snapshot: Any
    applied: bool
    reload_outcome: McpReloadOutcome


@dataclass(slots=True)
class McpCommandService:
    load_config: Callable[[], Any]
    snapshot_loader: Callable[[Any], Any]
    status_formatter: Callable[[Any], str]
    server_list_formatter: Callable[[Any], str]

    @staticmethod
    def normalize_action(action: str) -> str:
        normalized = _safe_text(action).lower().replace("-", "_")
        if normalized.startswith("mcp_"):
            normalized = normalized[4:]
        return normalized

    def validate_action(self, action: str) -> str:
        normalized = self.normalize_action(action)
        if normalized not in {"status", "list", "reload"}:
            raise McpCommandError(f"Unsupported MCP action: {action}")
        return normalized

    async def execute(
        self,
        *,
        action: str,
        busy: bool = False,
        cleanup_connections: Callable[[], Awaitable[None] | None] | None = None,
        reload_callback: Callable[[], Awaitable[McpReloadOutcome | tuple[bool, str] | dict[str, Any] | None] | McpReloadOutcome | tuple[bool, str] | dict[str, Any] | None]
        | None = None,
    ) -> McpCommandResult:
        normalized = self.validate_action(action)
        if busy and normalized == "reload":
            raise McpCommandError(
                detail=SessionControlErrorService.busy_detail(),
                status_code=409,
            )

        try:
            config = self.load_config()
        except Exception as exc:
            raise McpCommandError(
                detail=f"Failed to load config for MCP inspection: {exc}",
                status_code=500,
            ) from exc

        reload_outcome = McpReloadOutcome()
        if normalized == "reload":
            try:
                self.snapshot_loader(config)
                if cleanup_connections is not None:
                    await _maybe_await(cleanup_connections())
                if reload_callback is not None:
                    raw_outcome = await _maybe_await(reload_callback())
                    reload_outcome = self.normalize_reload_outcome(raw_outcome)
            except Exception as exc:
                raise McpCommandError(
                    detail=f"MCP reload failed: {exc}",
                    status_code=500,
                ) from exc

        snapshot = self.snapshot_loader(config)
        summary, details = self._build_output(normalized, snapshot=snapshot)
        return McpCommandResult(
            action=normalized,
            summary=summary,
            details=details,
            snapshot=snapshot,
            applied=normalized == "reload",
            reload_outcome=reload_outcome,
        )

    def _build_output(self, action: str, *, snapshot: Any) -> tuple[str, str]:
        status_details = self.status_formatter(snapshot)
        if action == "status":
            return (
                f"{int(getattr(snapshot, 'active_total', 0) or 0)} active server(s) | "
                f"{int(getattr(snapshot, 'tool_total', 0) or 0)} tool(s)",
                status_details,
            )
        list_details = f"{status_details}\n\n{self.server_list_formatter(snapshot)}"
        if action == "list":
            return (
                f"{int(getattr(snapshot, 'configured_total', 0) or 0)} configured server(s) | "
                f"{int(getattr(snapshot, 'active_total', 0) or 0)} active",
                list_details,
            )
        return (
            f"reloaded MCP | {int(getattr(snapshot, 'active_total', 0) or 0)} active server(s) | "
            f"{int(getattr(snapshot, 'tool_total', 0) or 0)} tool(s)",
            list_details,
        )

    @staticmethod
    def normalize_reload_outcome(raw: Any) -> McpReloadOutcome:
        if isinstance(raw, McpReloadOutcome):
            return raw
        if isinstance(raw, tuple) and raw:
            rebuilt = bool(raw[0])
            active_model_label = _safe_text(raw[1]) if len(raw) > 1 else ""
            return McpReloadOutcome(
                rebuilt_runtime=rebuilt,
                active_model_label=active_model_label or None,
            )
        if isinstance(raw, dict):
            return McpReloadOutcome(
                rebuilt_runtime=bool(raw.get("rebuilt_runtime")),
                active_model_label=_safe_text(raw.get("active_model_label")) or None,
            )
        return McpReloadOutcome()


__all__ = [
    "build_mcp_reload_warm_prefix",
    "format_cli_mcp_reload_success",
    "McpCommandError",
    "McpCommandResult",
    "McpCommandService",
    "McpReloadOutcome",
]
