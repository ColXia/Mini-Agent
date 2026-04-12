"""Phase 1 memory extraction (bounded baseline)."""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from mini_agent.memory.promotion import evaluate_durable_memory_promotion


_SENTENCE_SPLIT = re.compile(r"[\r\n]+|(?<=[.!?。！？])\s+")
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _utc_now_iso() -> str:
    return _utc_now().isoformat()


def _normalize_sentence(text: str) -> str:
    compact = " ".join(text.strip().split())
    return compact


def _safe_slug(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", value.strip())
    normalized = normalized.strip("-")
    return normalized or "session"


@dataclass(frozen=True)
class Phase1Artifact:
    """Output payload for one session extraction."""

    artifact_id: str
    session_id: str
    workspace_dir: str
    session_updated_at: str
    extracted_at: str
    rollout_slug: str
    rollout_summary: str
    raw_memory: list[str]
    source_message_count: int


class Phase1Extractor:
    """Extract bounded structured memory from one session transcript."""

    def extract(
        self,
        *,
        session_id: str,
        workspace_dir: str,
        session_updated_at: str,
        messages: list[dict[str, Any]],
        max_raw_memory_items: int = 12,
    ) -> Phase1Artifact:
        ranked_sentences = self._rank_message_sentences(messages)
        selected = [item[0] for item in ranked_sentences[: max(1, int(max_raw_memory_items))]]

        if not selected:
            selected = ["No significant memory extracted from this session."]

        summary = self._build_summary(selected)
        extracted_at = _utc_now_iso()
        slug = _safe_slug(session_id)
        artifact_id = f"p1_{slug}_{int(_utc_now().timestamp())}"
        return Phase1Artifact(
            artifact_id=artifact_id,
            session_id=session_id,
            workspace_dir=workspace_dir,
            session_updated_at=session_updated_at,
            extracted_at=extracted_at,
            rollout_slug=slug,
            rollout_summary=summary,
            raw_memory=selected,
            source_message_count=len(messages),
        )

    def _rank_message_sentences(self, messages: list[dict[str, Any]]) -> list[tuple[str, float]]:
        ranked: list[tuple[str, float]] = []
        seen: set[str] = set()

        for index, payload in enumerate(messages):
            if not isinstance(payload, dict):
                continue
            role = str(payload.get("role", "assistant")).strip().lower()
            tool_name = str(payload.get("name", "")).strip().lower()
            content = str(payload.get("content", "")).strip()
            if not content:
                continue
            for sentence in _SENTENCE_SPLIT.split(content):
                normalized = _normalize_sentence(sentence)
                if len(normalized) < 8:
                    continue
                promotion = evaluate_durable_memory_promotion(
                    normalized,
                    role=role,
                    tool_name=tool_name,
                )
                if not promotion.allowed:
                    continue
                normalized = promotion.normalized_text
                signature = normalized.lower()
                if signature in seen:
                    continue
                seen.add(signature)

                tokens = _TOKEN_PATTERN.findall(normalized)
                if not tokens:
                    continue
                lexical = min(8.0, len(tokens) / 4.0)
                role_bonus = 1.5 if role == "user" else 1.0 if role == "assistant" else 0.6
                recency_bonus = (index + 1) / max(1, len(messages))
                score = lexical + role_bonus + recency_bonus
                ranked.append((normalized, score))

        ranked.sort(key=lambda item: (-item[1], item[0]))
        return ranked

    def _build_summary(self, selected: list[str]) -> str:
        preview = selected[:3]
        return " | ".join(preview)


class Phase1ArtifactStore:
    """Persist phase-1 artifacts to json files."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir.expanduser().resolve()
        self.phase1_dir = self.base_dir / "consolidation" / "phase1"
        self.phase1_dir.mkdir(parents=True, exist_ok=True)

    def save(self, artifact: Phase1Artifact) -> Path:
        path = self.phase1_dir / f"{artifact.artifact_id}.json"
        payload = asdict(artifact)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    def load(self, path: Path) -> Phase1Artifact:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Phase1Artifact(
            artifact_id=str(payload.get("artifact_id", "")),
            session_id=str(payload.get("session_id", "")),
            workspace_dir=str(payload.get("workspace_dir", "")),
            session_updated_at=str(payload.get("session_updated_at", "")),
            extracted_at=str(payload.get("extracted_at", "")),
            rollout_slug=str(payload.get("rollout_slug", "")),
            rollout_summary=str(payload.get("rollout_summary", "")),
            raw_memory=[str(item) for item in payload.get("raw_memory", []) if str(item).strip()],
            source_message_count=int(payload.get("source_message_count", 0)),
        )

    def list_artifacts(self) -> list[Phase1Artifact]:
        artifacts: list[Phase1Artifact] = []
        for file in sorted(self.phase1_dir.glob("p1_*.json")):
            if not file.is_file():
                continue
            try:
                artifacts.append(self.load(file))
            except Exception:
                continue
        artifacts.sort(key=lambda item: item.extracted_at, reverse=True)
        return artifacts
