"""Prepared turn-context orchestration service."""

from __future__ import annotations

from dataclasses import dataclass
import inspect
from pathlib import Path
from typing import Any

from mini_agent.agent_core.context.turn_context_curation import (
    curate_turn_context_items,
    summarize_turn_context_items,
)
from mini_agent.agent_core.context.turn_context_diagnostics import (
    update_prepared_context_diagnostics,
)
from mini_agent.agent_core.context.turn_context_policy import (
    context_policy_summary_line,
    provider_allowed_by_policy,
    resolve_turn_context_policy,
)
from mini_agent.agent_core.context.turn_context_types import (
    RuntimeTurnContext,
    coerce_runtime_turn_context,
    normalize_turn_context_items,
)
from mini_agent.schema import Message


@dataclass(frozen=True)
class PreparedTurnContextResult:
    """Prepared turn-context payload returned to the agent facade."""

    summary: dict[str, Any]
    diagnostics: dict[str, Any]
    context_message: Message | None = None
    runtime_turn_context: RuntimeTurnContext | None = None
    policy: dict[str, Any] | None = None


class AgentPreparedTurnContextService:
    """Own per-turn context provider orchestration and diagnostics."""

    def __init__(
        self,
        *,
        workspace_dir: str | Path,
        providers: list[Any] | None = None,
        default_max_items: int = 4,
        default_max_items_per_source: int = 1,
        default_max_total_chars: int = 2400,
        logger: Any | None = None,
        context_message_name_prefix: str = "__mini_agent_turn_context__",
    ) -> None:
        self.workspace_dir = Path(workspace_dir)
        self.providers = list(providers or [])
        self.default_max_items = max(1, int(default_max_items))
        self.default_max_items_per_source = max(1, int(default_max_items_per_source))
        self.default_max_total_chars = max(200, int(default_max_total_chars))
        self.logger = logger
        self.context_message_name_prefix = str(context_message_name_prefix or "").strip() or "__mini_agent_turn_context__"

    def _log_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        *,
        level: str = "info",
    ) -> None:
        logger = self.logger
        if logger is None or not hasattr(logger, "log_event"):
            return
        logger.log_event(event_type, payload, level=level)

    @staticmethod
    async def _describe_turn_context_provider(
        *,
        provider: Any,
        provider_name: str,
        runtime_turn_context: RuntimeTurnContext,
        agent: Any,
    ) -> dict[str, Any] | None:
        describe = getattr(provider, "describe_readiness", None)
        if describe is None:
            return None
        result = describe(
            turn_context=runtime_turn_context,
            agent=agent,
        )
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, dict):
            return None

        raw_status = str(result.get("status") or "").strip().lower()
        available = result.get("available")
        if raw_status:
            status = raw_status
        elif available is False:
            status = "unavailable"
        else:
            status = "ready"
        return {
            "provider": provider_name,
            "status": status,
            "reason": " ".join(str(result.get("reason") or "").split()),
            "item_count": max(0, int(result.get("item_count") or 0)),
            "available": bool(available) if available is not None else status not in {"unavailable", "disabled"},
        }

    async def prepare_turn_context(
        self,
        *,
        turn_context: Any | None = None,
        agent: Any,
        current_diagnostics: Any = None,
    ) -> PreparedTurnContextResult:
        if not self.providers:
            return PreparedTurnContextResult(
                summary=summarize_turn_context_items([]),
                diagnostics=dict(current_diagnostics) if isinstance(current_diagnostics, dict) else {},
            )

        runtime_turn_context = coerce_runtime_turn_context(
            turn_context,
            workspace_dir=self.workspace_dir,
        )
        policy = resolve_turn_context_policy(
            runtime_turn_context,
            default_max_items=self.default_max_items,
            default_max_items_per_source=self.default_max_items_per_source,
            default_max_total_chars=self.default_max_total_chars,
        )
        prepared_items: list[Any] = []
        provider_failures: list[dict[str, Any]] = []
        provider_statuses: list[dict[str, Any]] = []

        for provider in self.providers:
            provider_name = "turn_context_provider"
            if provider is not None:
                provider_name = str(getattr(provider, "name", "") or provider.__class__.__name__).strip() or provider_name
            allowed, filter_reason = provider_allowed_by_policy(provider_name, policy)
            if not allowed:
                provider_statuses.append(
                    {
                        "provider": provider_name,
                        "status": "filtered",
                        "reason": filter_reason,
                        "item_count": 0,
                    }
                )
                continue
            try:
                readiness = await self._describe_turn_context_provider(
                    provider=provider,
                    provider_name=provider_name,
                    runtime_turn_context=runtime_turn_context,
                    agent=agent,
                )
                if readiness is not None and not readiness.get("available", True):
                    provider_statuses.append(
                        {
                            "provider": provider_name,
                            "status": str(readiness.get("status") or "unavailable"),
                            "reason": str(readiness.get("reason") or ""),
                            "item_count": int(readiness.get("item_count") or 0),
                        }
                    )
                    continue
                result = provider.prepare(
                    turn_context=runtime_turn_context,
                    agent=agent,
                )
                if inspect.isawaitable(result):
                    result = await result
                normalized_items = normalize_turn_context_items(
                    result,
                    default_source=provider_name,
                )
                prepared_items.extend(normalized_items)
                provider_statuses.append(
                    {
                        "provider": provider_name,
                        "status": "used" if normalized_items else "no_match",
                        "reason": (
                            str(readiness.get("reason") or "")
                            if readiness is not None and readiness.get("reason")
                            else ("no relevant context for this turn" if not normalized_items else "")
                        ),
                        "item_count": len(normalized_items),
                    }
                )
            except Exception as exc:
                failure_payload = {
                    "provider": provider_name,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                provider_failures.append(failure_payload)
                provider_statuses.append(
                    {
                        "provider": provider_name,
                        "status": "failed",
                        "reason": failure_payload["error"],
                        "item_count": 0,
                    }
                )
                self._log_event(
                    "turn_context.provider_failed",
                    {
                        **failure_payload,
                        "session_id": runtime_turn_context.session_id,
                        "submission_id": runtime_turn_context.submission_id,
                    },
                    level="warning",
                )

        curated_items, curation_summary = curate_turn_context_items(
            prepared_items,
            max_items=int(policy.get("max_items") or self.default_max_items),
            max_items_per_source=int(
                policy.get("max_items_per_source") or self.default_max_items_per_source
            ),
            max_total_chars=int(policy.get("max_total_chars") or self.default_max_total_chars),
        )
        summary = summarize_turn_context_items(
            curated_items,
            failures=provider_failures,
            curation=curation_summary,
            provider_statuses=provider_statuses,
            policy=policy,
        )
        diagnostics = update_prepared_context_diagnostics(
            current_diagnostics,
            summary,
        )
        self._log_event(
            "turn_context.prepared",
            {
                **summary,
                "diagnostics": dict(diagnostics),
                "session_id": runtime_turn_context.session_id,
                "submission_id": runtime_turn_context.submission_id,
                "policy_summary": context_policy_summary_line(policy, include_default=True),
            },
        )

        context_message = None
        if curated_items:
            from mini_agent.agent_core.context.turn_context_diagnostics import (
                format_turn_context_block,
            )

            context_message = Message(
                role="system",
                content=format_turn_context_block(curated_items),
                name=f"{self.context_message_name_prefix}:{runtime_turn_context.submission_id}",
            )

        return PreparedTurnContextResult(
            summary=summary,
            diagnostics=diagnostics,
            context_message=context_message,
            runtime_turn_context=runtime_turn_context,
            policy=policy,
        )


__all__ = [
    "AgentPreparedTurnContextService",
    "PreparedTurnContextResult",
]
