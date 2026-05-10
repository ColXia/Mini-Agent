"""Agent-owned main model binding service over the provider/model pool."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Callable

from mini_agent.config_bootstrap import load_local_env_files
from mini_agent.model_manager.agent_model_binding import (
    AgentModelBindingRecord,
    AgentModelBindingStore,
)
from mini_agent.model_manager.bootstrap import bootstrap_llm_settings_from_config
from mini_agent.model_manager.model_registry_service import ModelRegistryService
from mini_agent.model_manager.runtime import (
    get_model_route_diagnostics_snapshot,
    resolve_pinned_llm_candidate,
    resolve_routed_llm_settings,
    resolve_session_model_selection_identity,
)
from mini_agent.utils.text import safe_text


def _safe_text(value: Any) -> str:
    return safe_text(value)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _selection_provider_id(*, provider_source: str | None, provider_id: str | None) -> str | None:
    normalized_source = _safe_text(provider_source).lower()
    normalized_provider_id = _safe_text(provider_id)
    if not normalized_provider_id:
        return None
    if normalized_source == "preset" and normalized_provider_id.startswith("preset-"):
        return normalized_provider_id.removeprefix("preset-")
    return normalized_provider_id


class AgentModelService:
    """Persist and resolve the agent-owned main model binding."""

    def __init__(
        self,
        *,
        binding_state_path: Path | None = None,
        catalog_path: Path | None = None,
        load_runtime_config: Callable[[], Any] | None = None,
        default_agent_id: str = "main-agent",
    ) -> None:
        self._binding_state_path = (
            binding_state_path.expanduser().resolve()
            if binding_state_path is not None
            else (Path.home() / ".mini-agent" / "agent_model_binding.json").resolve()
        )
        self._catalog_path = catalog_path.expanduser().resolve() if catalog_path is not None else None
        self._load_runtime_config = load_runtime_config
        self._default_agent_id = _safe_text(default_agent_id) or "main-agent"

    def list_model_bindings(self, agent_id: str | None = None) -> list[dict[str, Any]]:
        current = self.get_model_binding(agent_id)
        current_source = _safe_text(current.get("provider_source")).lower()
        current_provider_id = _safe_text(current.get("provider_id"))
        current_model_id = _safe_text(current.get("model_id"))

        items = [deepcopy(item) for item in self._registry_service().list_registry()]
        for provider in items:
            provider_source = _safe_text(provider.get("source")).lower()
            provider_id = _safe_text(provider.get("provider_id"))
            for model in list(provider.get("models") or []):
                if not isinstance(model, dict):
                    continue
                model["is_current_binding"] = bool(
                    current_source
                    and current_provider_id
                    and current_model_id
                    and provider_source == current_source
                    and provider_id == current_provider_id
                    and _safe_text(model.get("model_id")) == current_model_id
                )
        if items:
            return items

        if current_source == "bootstrap" and current_model_id:
            return [
                {
                    "source": "bootstrap",
                    "provider_id": current_provider_id or "bootstrap-config",
                    "provider_name": current.get("provider_name") or "Bootstrap Config",
                    "api_type": current.get("provider"),
                    "api_base": current.get("api_base"),
                    "provider_family": current.get("provider"),
                    "provider_variant": None,
                    "default_model_id": current_model_id,
                    "default_model_strategy": "runtime_bootstrap",
                    "default_model_confidence": None,
                    "models": [
                        {
                            "model_id": current_model_id,
                            "display_name": current.get("display_name") or current_model_id,
                            "is_default": True,
                            "is_current_binding": True,
                            "context_window": current.get("context_window"),
                            "learned_token_limit": current.get("learned_token_limit"),
                            "supports_tools": current.get("supports_tools"),
                            "supports_tools_truth": current.get("supports_tools_truth"),
                            "supports_tools_confidence": current.get("supports_tools_confidence"),
                            "supports_tools_source": current.get("supports_tools_source"),
                            "supports_thinking": current.get("supports_thinking"),
                            "supports_thinking_truth": current.get("supports_thinking_truth"),
                            "supports_thinking_confidence": current.get("supports_thinking_confidence"),
                            "supports_thinking_source": current.get("supports_thinking_source"),
                        }
                    ],
                    "enabled": True,
                    "priority": current.get("priority") or 0,
                }
            ]
        return []

    def get_model_binding(self, agent_id: str | None = None) -> dict[str, Any]:
        resolved = self._resolve_binding(agent_id)
        return dict(resolved)

    def update_model_binding(
        self,
        *,
        agent_id: str | None = None,
        provider_source: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> dict[str, Any]:
        resolved_agent_id = self._resolved_agent_id(agent_id)
        normalized_provider_id = _safe_text(provider_id)
        normalized_model_id = _safe_text(model_id)
        identity = resolve_session_model_selection_identity(
            provider_source=provider_source,
            provider_id=normalized_provider_id,
            model_id=normalized_model_id or None,
            catalog_path=self._catalog_path,
        )
        validated = resolve_pinned_llm_candidate(
            provider_source=identity[0],
            provider_id=identity[1],
            model_id=identity[2],
            catalog_path=self._catalog_path,
        )
        store = self._load_store()
        previous = store.bindings.get(resolved_agent_id)
        switch_generation = max(0, int(getattr(previous, "switch_generation", 0) or 0)) + 1
        store.bindings[resolved_agent_id] = AgentModelBindingRecord(
            agent_id=resolved_agent_id,
            provider_source=identity[0],
            provider_id=identity[1],
            model_id=identity[2],
            binding_kind="explicit",
            bound_at=_utc_now_iso(),
            switch_generation=switch_generation,
        )
        self._save_store(store)
        return self._binding_payload(
            agent_id=resolved_agent_id,
            binding_kind="explicit",
            candidate=validated,
            bound_at=store.bindings[resolved_agent_id].bound_at,
            switch_generation=switch_generation,
            configured_binding=store.bindings[resolved_agent_id],
        )

    def list_model_capabilities(self, agent_id: str | None = None) -> dict[str, Any]:
        binding = self.get_model_binding(agent_id)
        return {
            "agent_id": binding.get("agent_id"),
            "binding_kind": binding.get("binding_kind"),
            "provider_source": binding.get("provider_source"),
            "provider_id": binding.get("provider_id"),
            "model_id": binding.get("model_id"),
            "context_window": binding.get("context_window"),
            "learned_token_limit": binding.get("learned_token_limit"),
            "token_limit": binding.get("token_limit"),
            "supports_tools": binding.get("supports_tools"),
            "supports_tools_truth": binding.get("supports_tools_truth"),
            "supports_tools_confidence": binding.get("supports_tools_confidence"),
            "supports_tools_source": binding.get("supports_tools_source"),
            "supports_thinking": binding.get("supports_thinking"),
            "supports_thinking_truth": binding.get("supports_thinking_truth"),
            "supports_thinking_confidence": binding.get("supports_thinking_confidence"),
            "supports_thinking_source": binding.get("supports_thinking_source"),
        }

    def get_model_binding_diagnostics(self, agent_id: str | None = None) -> dict[str, Any]:
        resolved = self._resolve_binding(agent_id)
        return {
            "agent_id": resolved.get("agent_id"),
            "current_binding": dict(resolved),
            "configured_binding": deepcopy(resolved.get("configured_binding")),
            "configured_binding_error": resolved.get("configured_binding_error"),
            "latest_route": deepcopy(resolved.get("route_diagnostics")),
        }

    def explicit_model_identity(self, agent_id: str | None = None) -> tuple[str, str, str] | None:
        record = self._load_store().bindings.get(self._resolved_agent_id(agent_id))
        if record is None:
            return None
        try:
            identity = resolve_session_model_selection_identity(
                provider_source=record.provider_source,
                provider_id=record.provider_id,
                model_id=record.model_id,
                catalog_path=self._catalog_path,
            )
            resolve_pinned_llm_candidate(
                provider_source=identity[0],
                provider_id=identity[1],
                model_id=identity[2],
                catalog_path=self._catalog_path,
            )
            return identity
        except Exception:
            return None

    def _resolve_binding(self, agent_id: str | None = None) -> dict[str, Any]:
        resolved_agent_id = self._resolved_agent_id(agent_id)
        configured_binding = self._load_store().bindings.get(resolved_agent_id)
        configured_error: str | None = None

        if configured_binding is not None:
            try:
                candidate = resolve_pinned_llm_candidate(
                    provider_source=configured_binding.provider_source,
                    provider_id=configured_binding.provider_id,
                    model_id=configured_binding.model_id,
                    catalog_path=self._catalog_path,
                )
                return self._binding_payload(
                    agent_id=resolved_agent_id,
                    binding_kind="explicit",
                    candidate=candidate,
                    bound_at=configured_binding.bound_at,
                    switch_generation=configured_binding.switch_generation,
                    configured_binding=configured_binding,
                )
            except Exception as exc:
                configured_error = str(exc)

        candidate = resolve_routed_llm_settings(
            bootstrap_llm=self._bootstrap_llm(),
            catalog_path=self._catalog_path,
        )
        return self._binding_payload(
            agent_id=resolved_agent_id,
            binding_kind="automatic",
            candidate=candidate,
            bound_at=None,
            switch_generation=0,
            configured_binding=configured_binding,
            configured_binding_error=configured_error,
        )

    def _binding_payload(
        self,
        *,
        agent_id: str,
        binding_kind: str,
        candidate: Any,
        bound_at: str | None,
        switch_generation: int,
        configured_binding: AgentModelBindingRecord | None,
        configured_binding_error: str | None = None,
    ) -> dict[str, Any]:
        provider_source = _safe_text(getattr(candidate, "provider_source", "")).lower() or None
        provider_id = _selection_provider_id(
            provider_source=provider_source,
            provider_id=getattr(candidate, "provider_id", None),
        )
        model_id = _safe_text(getattr(candidate, "model", "")) or None
        return {
            "agent_id": agent_id,
            "binding_kind": binding_kind,
            "provider": str(getattr(getattr(candidate, "provider", None), "value", getattr(candidate, "provider", "")) or ""),
            "provider_source": provider_source,
            "provider_id": provider_id,
            "runtime_provider_id": _safe_text(getattr(candidate, "provider_id", "")) or None,
            "provider_name": _safe_text(getattr(candidate, "provider_name", "")) or None,
            "model_id": model_id,
            "display_name": model_id,
            "api_base": _safe_text(getattr(candidate, "api_base", "")) or None,
            "mapping_mode": _safe_text(getattr(candidate, "mapping_mode", "")) or None,
            "priority": getattr(candidate, "priority", None),
            "context_window": getattr(candidate, "context_window", None),
            "learned_token_limit": getattr(candidate, "learned_token_limit", None),
            "token_limit": getattr(candidate, "token_limit", None),
            "supports_tools": getattr(candidate, "supports_tools", None),
            "supports_tools_truth": getattr(candidate, "supports_tools_truth", None),
            "supports_tools_confidence": getattr(candidate, "supports_tools_confidence", None),
            "supports_tools_source": getattr(candidate, "supports_tools_source", None),
            "supports_thinking": getattr(candidate, "supports_thinking", None),
            "supports_thinking_truth": getattr(candidate, "supports_thinking_truth", None),
            "supports_thinking_confidence": getattr(candidate, "supports_thinking_confidence", None),
            "supports_thinking_source": getattr(candidate, "supports_thinking_source", None),
            "bound_at": bound_at,
            "switch_generation": max(0, int(switch_generation or 0)),
            "configured_binding": configured_binding.model_dump() if configured_binding is not None else None,
            "configured_binding_error": _safe_text(configured_binding_error) or None,
            "route_diagnostics": deepcopy(
                getattr(candidate, "route_diagnostics", None) or get_model_route_diagnostics_snapshot()
            ),
        }

    def _bootstrap_llm(self) -> Any | None:
        if self._load_runtime_config is None:
            return None
        try:
            return bootstrap_llm_settings_from_config(self._load_runtime_config())
        except Exception:
            return None

    def _load_store(self) -> AgentModelBindingStore:
        load_local_env_files()
        if not self._binding_state_path.exists():
            return AgentModelBindingStore()
        try:
            payload = json.loads(self._binding_state_path.read_text(encoding="utf-8"))
        except Exception:
            return AgentModelBindingStore()
        try:
            return AgentModelBindingStore.model_validate(payload)
        except Exception:
            return AgentModelBindingStore()

    def _save_store(self, store: AgentModelBindingStore) -> None:
        self._binding_state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = self._binding_state_path.with_suffix(self._binding_state_path.suffix + ".tmp")
        tmp_path.write_text(
            json.dumps(store.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        tmp_path.replace(self._binding_state_path)

    def _registry_service(self) -> ModelRegistryService:
        return ModelRegistryService(catalog_path=self._catalog_path)

    def _resolved_agent_id(self, agent_id: str | None = None) -> str:
        return _safe_text(agent_id) or self._default_agent_id


__all__ = ["AgentModelService"]
