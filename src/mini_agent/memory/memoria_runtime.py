"""Persisted workspace-scoped runtime task memory on top of MemoriaEngine."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any

from mini_agent.memory.engram import Engram
from mini_agent.memory.knowledge_base_grounding import knowledge_base_grounding_from_metadata
from mini_agent.memory.memoria_engine import MemoriaEngine
from mini_agent.memory.memory_files import resolve_workspace_root
from mini_agent.memory.promotion import (
    evaluate_durable_memory_promotion,
    evaluate_workspace_shared_runtime_promotion,
)


_SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(content, encoding="utf-8")
    tmp_path.replace(path)


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _safe_workspace_hash(anchor_dir: Path) -> str:
    return hashlib.sha1(str(anchor_dir).encode("utf-8")).hexdigest()[:16]


def _normalize_session_id(session_id: str) -> str:
    normalized = str(session_id or "").strip()
    if not _SESSION_ID_PATTERN.fullmatch(normalized):
        raise ValueError("session_id must match [A-Za-z0-9][A-Za-z0-9._-]{0,127}.")
    return normalized


@dataclass(frozen=True)
class RuntimeTaskMemoryHit:
    namespace: str
    engram_id: str
    layer: str
    content: str
    score: float
    metadata: dict[str, Any]


class WorkspaceMemoriaRuntime:
    """Workspace-scoped persisted runtime task memory with namespace isolation."""

    WORKSPACE_SHARED_NAMESPACE = "workspace:shared"

    def __init__(
        self,
        workspace_dir: str | Path,
        *,
        state_root: str | Path | None = None,
        max_working: int = 12,
        max_stm: int = 48,
        max_ltm: int = 128,
    ) -> None:
        self.workspace_dir = resolve_workspace_root(workspace_dir)
        self.anchor_dir = self.workspace_dir
        self.state_root = (
            Path(state_root).expanduser().resolve()
            if state_root is not None
            else (Path.home() / ".mini-agent" / "state" / "workspaces").resolve()
        )
        self.workspace_hash = _safe_workspace_hash(self.anchor_dir)
        self.workspace_state_dir = self.state_root / self.workspace_hash
        self.namespaces_dir = self.workspace_state_dir / "memoria"
        self.manifest_path = self.workspace_state_dir / "manifest.json"
        self.max_working = max(1, int(max_working))
        self.max_stm = max(1, int(max_stm))
        self.max_ltm = max(1, int(max_ltm))
        self._ensure_manifest()

    @staticmethod
    def session_namespace(session_id: str) -> str:
        return f"session:{_normalize_session_id(session_id)}"

    @classmethod
    def shared_namespace(cls) -> str:
        return cls.WORKSPACE_SHARED_NAMESPACE

    def save(
        self,
        *,
        namespace: str,
        content: str,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_content = _clean_text(content)
        if not normalized_content:
            raise ValueError("runtime task memory content cannot be empty.")

        engine = self._load_namespace(namespace)
        if engine.contains_content(normalized_content):
            existing = self._find_content(engine, normalized_content)
            return {
                "stored": False,
                "duplicate": True,
                "namespace": namespace,
                "engram_id": existing.get("engram_id"),
                "content": normalized_content,
            }

        engram = engine.save(
            normalized_content,
            importance=importance,
            metadata={} if metadata is None else dict(metadata),
        )
        self._save_namespace(namespace, engine)
        return {
            "stored": True,
            "duplicate": False,
            "namespace": namespace,
            "engram_id": engram.engram_id,
            "layer": engram.layer,
            "content": engram.content,
            "metadata": dict(engram.metadata),
        }

    def save_session_memory(
        self,
        session_id: str,
        *,
        content: str,
        importance: float = 0.5,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.save(
            namespace=self.session_namespace(session_id),
            content=content,
            importance=importance,
            metadata=metadata,
        )

    def save_workspace_shared_memory(
        self,
        *,
        content: str,
        importance: float = 0.6,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.save(
            namespace=self.shared_namespace(),
            content=content,
            importance=importance,
            metadata=metadata,
        )

    def retrieve(
        self,
        *,
        namespace: str,
        query: str,
        limit: int = 5,
        include_ltm: bool = True,
    ) -> list[RuntimeTaskMemoryHit]:
        engine = self._load_namespace(namespace)
        results = engine.retrieve(query, limit=limit, include_ltm=include_ltm)
        self._save_namespace(namespace, engine)
        return [
            RuntimeTaskMemoryHit(
                namespace=namespace,
                engram_id=result.engram_id,
                layer=result.layer,
                content=result.content,
                score=result.score,
                metadata=dict(result.metadata),
            )
            for result in results
        ]

    def retrieve_for_turn(
        self,
        *,
        session_id: str,
        query: str,
        session_limit: int = 3,
        shared_limit: int = 2,
        include_workspace_shared: bool = True,
    ) -> dict[str, Any]:
        session_namespace = self.session_namespace(session_id)
        session_hits = self.retrieve(
            namespace=session_namespace,
            query=query,
            limit=session_limit,
        )
        shared_hits: list[RuntimeTaskMemoryHit] = []
        if include_workspace_shared:
            shared_hits = self.retrieve(
                namespace=self.shared_namespace(),
                query=query,
                limit=shared_limit,
            )
        return {
            "session_namespace": session_namespace,
            "workspace_shared_namespace": self.shared_namespace(),
            "session_hits": [self._hit_to_dict(item) for item in session_hits],
            "shared_hits": [self._hit_to_dict(item) for item in shared_hits],
            "returned": len(session_hits) + len(shared_hits),
        }

    def namespace_stats(self, namespace: str) -> dict[str, int]:
        engine = self._load_namespace(namespace)
        return engine.stats()

    def list_namespace_entries(
        self,
        namespace: str,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        normalized_limit = max(1, int(limit))
        engine = self._load_namespace(namespace)
        items: list[dict[str, Any]] = []
        for layer in ("working", "stm", "ltm"):
            for engram in engine.list_layer(layer):
                items.append(
                    {
                        "engram_id": engram.engram_id,
                        "layer": engram.layer,
                        "content": engram.content,
                        "importance": engram.importance,
                        "updated_at": engram.updated_at.astimezone(timezone.utc).isoformat(),
                        "metadata": dict(engram.metadata),
                    }
                )
        items.sort(
            key=lambda item: (
                str(item.get("updated_at", "")),
                str(item.get("engram_id", "")),
            ),
            reverse=True,
        )
        return items[:normalized_limit]

    def list_workspace_shared_entries(
        self,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        return self.list_namespace_entries(self.shared_namespace(), limit=limit)

    def stats(self) -> dict[str, Any]:
        namespaces: dict[str, Any] = {}
        for file in sorted(self.namespaces_dir.glob("*.json")):
            namespace = self._namespace_from_path(file)
            if not namespace:
                continue
            engine = self._load_namespace(namespace)
            namespaces[namespace] = engine.stats()
        return {
            "workspace_dir": str(self.workspace_dir),
            "workspace_anchor_dir": str(self.anchor_dir),
            "workspace_hash": self.workspace_hash,
            "state_dir": str(self.workspace_state_dir),
            "namespace_count": len(namespaces),
            "namespaces": namespaces,
        }

    def clear_namespace(self, namespace: str) -> bool:
        path = self._namespace_path(namespace)
        existed = path.exists()
        if existed:
            path.unlink()
        return existed

    def clear_session_namespace(self, session_id: str) -> bool:
        return self.clear_namespace(self.session_namespace(session_id))

    def clear_workspace_shared_namespace(self) -> bool:
        return self.clear_namespace(self.shared_namespace())

    def snapshot_namespace_payload(self, namespace: str) -> dict[str, Any]:
        engine = self._load_namespace(namespace)
        stats = engine.stats()
        entry_count = sum(int(value or 0) for value in stats.values())
        if entry_count <= 0:
            return {}
        return {
            "engine": engine.to_payload(),
            "entry_count": entry_count,
            "stats": stats,
        }

    def snapshot_session_namespace_payload(self, session_id: str) -> dict[str, Any]:
        return self.snapshot_namespace_payload(self.session_namespace(session_id))

    def snapshot_workspace_shared_namespace_payload(self) -> dict[str, Any]:
        return self.snapshot_namespace_payload(self.shared_namespace())

    def restore_namespace_payload(
        self,
        namespace: str,
        payload: dict[str, Any] | None,
        *,
        replace: bool = True,
        merge: bool = False,
    ) -> dict[str, Any]:
        normalized = dict(payload) if isinstance(payload, dict) else {}
        engine_payload = normalized.get("engine")
        engine = MemoriaEngine.from_payload(engine_payload if isinstance(engine_payload, dict) else {})
        incoming_stats = engine.stats()
        incoming_entry_count = sum(int(value or 0) for value in incoming_stats.values())
        if replace:
            self.clear_namespace(namespace)
        if incoming_entry_count <= 0:
            return {
                "restored": False,
                "namespace": namespace,
                "entry_count": 0,
                "stats": incoming_stats,
            }
        if merge and not replace:
            existing_engine = self._load_namespace(namespace)
            merged_stats = self._merge_engines(existing_engine, engine)
            current_stats = existing_engine.stats()
            current_entry_count = sum(int(value or 0) for value in current_stats.values())
            if merged_stats["added_count"] > 0:
                self._save_namespace(namespace, existing_engine)
            return {
                "restored": merged_stats["added_count"] > 0,
                "namespace": namespace,
                "entry_count": current_entry_count,
                "stats": current_stats,
                "incoming_entry_count": incoming_entry_count,
                "added_count": merged_stats["added_count"],
                "duplicate_count": merged_stats["duplicate_count"],
                "merged": True,
            }
        self._save_namespace(namespace, engine)
        return {
            "restored": True,
            "namespace": namespace,
            "entry_count": incoming_entry_count,
            "stats": incoming_stats,
        }

    def restore_session_namespace_payload(
        self,
        session_id: str,
        payload: dict[str, Any] | None,
        *,
        replace: bool = True,
    ) -> dict[str, Any]:
        return self.restore_namespace_payload(
            self.session_namespace(session_id),
            payload,
            replace=replace,
        )

    def restore_workspace_shared_namespace_payload(
        self,
        payload: dict[str, Any] | None,
        *,
        replace: bool = False,
    ) -> dict[str, Any]:
        return self.restore_namespace_payload(
            self.shared_namespace(),
            payload,
            replace=replace,
            merge=not replace,
        )

    def promote_session_memory_to_workspace_shared(
        self,
        *,
        session_id: str,
        engram_id: str,
    ) -> dict[str, Any]:
        engram = self._get_engram(self.session_namespace(session_id), engram_id)
        if engram is None:
            raise FileNotFoundError(f"runtime task memory engram not found: {engram_id}")
        metadata = dict(engram.metadata)
        preferred_content = _clean_text(metadata.get("workspace_shared_candidate_text"))
        decision = evaluate_workspace_shared_runtime_promotion(
            preferred_content or engram.content,
        )
        if not decision.allowed:
            raise ValueError(
                "runtime task memory cannot be promoted to workspace-shared memory: "
                f"{decision.reason}"
            )
        saved = self.save_workspace_shared_memory(
            content=decision.normalized_text,
            importance=max(engram.importance, 0.6),
            metadata={
                **metadata,
                "promoted_from_namespace": self.session_namespace(session_id),
                "promoted_from_engram_id": engram.engram_id,
                "promoted_at": _utc_now_iso(),
                "promotion_reason": decision.reason or "workspace_shared_candidate",
            },
        )
        return {
            "promoted": True,
            "target_namespace": self.shared_namespace(),
            "target": "workspace_shared",
            **saved,
        }

    def promote_session_memory_to_workspace_note(
        self,
        *,
        session_id: str,
        engram_id: str,
        category: str = "runtime_promotion",
    ) -> dict[str, Any]:
        engram = self._get_engram(self.session_namespace(session_id), engram_id)
        if engram is None:
            raise FileNotFoundError(f"runtime task memory engram not found: {engram_id}")
        metadata = dict(engram.metadata)
        kb_grounding = knowledge_base_grounding_from_metadata(metadata)
        promotion = evaluate_durable_memory_promotion(engram.content)
        if not promotion.allowed:
            raise ValueError(f"runtime task memory cannot be promoted to workspace durable memory: {promotion.reason}")

        from mini_agent.memory.service import MemoryService

        memory = MemoryService(self.anchor_dir)
        effective_category = "kb_confirmed" if bool(kb_grounding.get("grounded")) else category
        memory.append_note(
            content=promotion.normalized_text,
            category=effective_category,
            scope="long_term",
            now=datetime.now(),
        )
        return {
            "promoted": True,
            "target": "workspace_note",
            "category": effective_category,
            "content": promotion.normalized_text,
            "memory_file": str(memory.long_term_file),
            "knowledge_base_grounding": kb_grounding if bool(kb_grounding.get("used")) else None,
        }

    def promote_session_memory_to_global_profile(
        self,
        *,
        session_id: str,
        engram_id: str,
    ) -> dict[str, Any]:
        engram = self._get_engram(self.session_namespace(session_id), engram_id)
        if engram is None:
            raise FileNotFoundError(f"runtime task memory engram not found: {engram_id}")
        promotion = evaluate_durable_memory_promotion(engram.content)
        if not promotion.allowed:
            raise ValueError(f"runtime task memory cannot be promoted to global durable memory: {promotion.reason}")

        from mini_agent.memory.service import MemoryService

        memory = MemoryService(self.anchor_dir)
        result = memory.add_profile_fact(fact=promotion.normalized_text)
        return {
            "promoted": bool(result.get("changed")),
            "target": "global_profile",
            "content": promotion.normalized_text,
            "user_file": memory.profile().get("user_file"),
        }

    def get_namespace_entry(
        self,
        namespace: str,
        *,
        engram_id: str,
    ) -> dict[str, Any] | None:
        engram = self._get_engram(namespace, engram_id)
        if engram is None:
            return None
        return self._engram_to_dict(namespace, engram)

    def get_workspace_shared_entry(self, *, engram_id: str) -> dict[str, Any] | None:
        return self.get_namespace_entry(self.shared_namespace(), engram_id=engram_id)

    def _ensure_manifest(self) -> None:
        self.workspace_state_dir.mkdir(parents=True, exist_ok=True)
        if self.manifest_path.exists():
            return
        _atomic_write_text(
            self.manifest_path,
            json.dumps(
                {
                    "workspace_dir": str(self.workspace_dir),
                    "workspace_anchor_dir": str(self.anchor_dir),
                    "workspace_hash": self.workspace_hash,
                    "updated_at": _utc_now_iso(),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    def _namespace_path(self, namespace: str) -> Path:
        if namespace == self.shared_namespace():
            filename = "workspace-shared.json"
        elif namespace.startswith("session:"):
            filename = f"session-{namespace.split(':', 1)[1]}.json"
        else:
            raise ValueError(f"unsupported runtime memory namespace: {namespace}")
        return self.namespaces_dir / filename

    def _namespace_from_path(self, path: Path) -> str | None:
        name = path.stem
        if name == "workspace-shared":
            return self.shared_namespace()
        if name.startswith("session-"):
            return self.session_namespace(name.removeprefix("session-"))
        return None

    def _load_namespace(self, namespace: str) -> MemoriaEngine:
        path = self._namespace_path(namespace)
        if not path.exists():
            return MemoriaEngine(
                max_working=self.max_working,
                max_stm=self.max_stm,
                max_ltm=self.max_ltm,
            )
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            payload = {}
        engine_payload = payload.get("engine") if isinstance(payload, dict) else {}
        return MemoriaEngine.from_payload(engine_payload if isinstance(engine_payload, dict) else {})

    def _save_namespace(self, namespace: str, engine: MemoriaEngine) -> None:
        path = self._namespace_path(namespace)
        _atomic_write_text(
            path,
            json.dumps(
                {
                    "namespace": namespace,
                    "workspace_anchor_dir": str(self.anchor_dir),
                    "updated_at": _utc_now_iso(),
                    "engine": engine.to_payload(),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

    def _get_engram(self, namespace: str, engram_id: str):
        engine = self._load_namespace(namespace)
        return engine.get_engram(engram_id)

    @staticmethod
    def _find_content(engine: MemoriaEngine, content: str) -> dict[str, Any]:
        for layer in ("working", "stm", "ltm"):
            for engram in engine.list_layer(layer):
                if engram.content == content:
                    return {
                        "engram_id": engram.engram_id,
                        "layer": engram.layer,
                        "metadata": dict(engram.metadata),
                    }
        return {}

    @staticmethod
    def _engram_to_dict(namespace: str, engram: Engram) -> dict[str, Any]:
        return {
            "namespace": namespace,
            "engram_id": engram.engram_id,
            "layer": engram.layer,
            "content": engram.content,
            "importance": engram.importance,
            "updated_at": engram.updated_at.astimezone(timezone.utc).isoformat(),
            "metadata": dict(engram.metadata),
        }

    @staticmethod
    def _copy_engram(engram: Engram, *, engram_id: str, sequence: int) -> Engram:
        return Engram(
            content=engram.content,
            layer=engram.layer,
            importance=engram.importance,
            metadata=dict(engram.metadata),
            engram_id=engram_id,
            created_at=engram.created_at,
            updated_at=engram.updated_at,
            access_count=engram.access_count,
            sequence=sequence,
        )

    @classmethod
    def _merge_engines(cls, target: MemoriaEngine, incoming: MemoriaEngine) -> dict[str, int]:
        existing_contents = {
            _clean_text(engram.content)
            for layer in ("working", "stm", "ltm")
            for engram in target.list_layer(layer)
        }
        existing_ids = {
            engram.engram_id
            for layer in ("working", "stm", "ltm")
            for engram in target.list_layer(layer)
        }
        next_sequence = max(
            int(getattr(target, "_save_sequence", 0) or 0),
            max(
                (
                    int(getattr(engram, "sequence", 0) or 0)
                    for layer in ("working", "stm", "ltm")
                    for engram in target.list_layer(layer)
                ),
                default=0,
            ),
        )
        added_count = 0
        duplicate_count = 0

        for layer in ("working", "stm", "ltm"):
            target_layer = getattr(target, "_layers")[layer]
            for engram in incoming.list_layer(layer):
                normalized_content = _clean_text(engram.content)
                if not normalized_content:
                    continue
                if normalized_content in existing_contents:
                    duplicate_count += 1
                    continue
                next_sequence += 1
                candidate_id = engram.engram_id
                if not candidate_id or candidate_id in existing_ids:
                    candidate_id = f"eng_{hashlib.sha1(f'{normalized_content}:{next_sequence}'.encode('utf-8')).hexdigest()[:16]}"
                copied = cls._copy_engram(
                    engram,
                    engram_id=candidate_id,
                    sequence=max(next_sequence, int(getattr(engram, "sequence", 0) or 0)),
                )
                next_sequence = max(next_sequence, int(copied.sequence or 0))
                target_layer.append(copied)
                existing_contents.add(normalized_content)
                existing_ids.add(candidate_id)
                added_count += 1

        setattr(target, "_save_sequence", max(int(getattr(target, "_save_sequence", 0) or 0), next_sequence))
        target._enforce_limits()
        return {
            "added_count": added_count,
            "duplicate_count": duplicate_count,
        }

    @staticmethod
    def _hit_to_dict(hit: RuntimeTaskMemoryHit) -> dict[str, Any]:
        return {
            "namespace": hit.namespace,
            "engram_id": hit.engram_id,
            "layer": hit.layer,
            "content": hit.content,
            "score": hit.score,
            "metadata": dict(hit.metadata),
        }


__all__ = [
    "RuntimeTaskMemoryHit",
    "WorkspaceMemoriaRuntime",
]
