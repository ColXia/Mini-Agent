"""Phase 2 global consolidation (bounded baseline)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from mini_agent.memory.consolidation_phase1 import Phase1Artifact

_SECTION_BEGIN = "<!-- MINI_AGENT_CONSOLIDATED_MEMORY_BEGIN -->"
_SECTION_END = "<!-- MINI_AGENT_CONSOLIDATED_MEMORY_END -->"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class Phase2Result:
    """Result of one phase-2 consolidation run."""

    processed_artifacts: int
    selected_artifact_ids: list[str]
    added: list[str]
    retained: list[str]
    removed: list[str]
    output_items: list[str]
    watermark_size: int


class Phase2Consolidator:
    """Merge phase-1 raw memory artifacts into consolidated memory section."""

    def __init__(self, base_dir: Path, memory_file: Path):
        self.base_dir = base_dir.expanduser().resolve()
        self.memory_file = memory_file.expanduser().resolve()
        self.state_dir = self.base_dir / "consolidation"
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.watermark_path = self.state_dir / "watermarks.json"
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)

    def consolidate(self, artifacts: list[Phase1Artifact], *, top_n: int = 40) -> Phase2Result:
        watermark = self._read_watermark()
        processed_ids = set(watermark.get("processed_artifact_ids", []))

        fresh_artifacts = [artifact for artifact in artifacts if artifact.artifact_id not in processed_ids]
        fresh_artifacts.sort(key=lambda item: item.extracted_at, reverse=True)
        existing_items = self._read_existing_items()

        if not fresh_artifacts:
            return Phase2Result(
                processed_artifacts=0,
                selected_artifact_ids=[],
                added=[],
                retained=list(existing_items),
                removed=[],
                output_items=list(existing_items),
                watermark_size=len(processed_ids),
            )

        ranked = self._rank_memory_candidates(fresh_artifacts, existing_items=existing_items)
        target_items = [item for item, _ in ranked[: max(1, int(top_n))]]

        added = [item for item in target_items if item not in existing_items]
        retained = [item for item in target_items if item in existing_items]
        removed = [item for item in existing_items if item not in target_items]

        self._write_memory_section(target_items)

        next_ids = list(processed_ids | {artifact.artifact_id for artifact in fresh_artifacts})
        next_ids.sort()
        # Keep watermark bounded.
        next_ids = next_ids[-5000:]
        self._write_watermark(next_ids)

        return Phase2Result(
            processed_artifacts=len(fresh_artifacts),
            selected_artifact_ids=[artifact.artifact_id for artifact in fresh_artifacts],
            added=added,
            retained=retained,
            removed=removed,
            output_items=target_items,
            watermark_size=len(next_ids),
        )

    def _rank_memory_candidates(
        self,
        artifacts: list[Phase1Artifact],
        *,
        existing_items: list[str],
    ) -> list[tuple[str, float]]:
        scores: dict[str, float] = {item: 0.5 for item in existing_items}
        for artifact_rank, artifact in enumerate(artifacts):
            freshness_bonus = max(0.1, 2.0 - (artifact_rank * 0.05))
            density_bonus = max(0.1, min(2.0, artifact.source_message_count / 20.0))
            for line in artifact.raw_memory:
                item = line.strip()
                if not item:
                    continue
                scores[item] = scores.get(item, 0.0) + freshness_bonus + density_bonus
        ranked = sorted(scores.items(), key=lambda pair: (-pair[1], pair[0]))
        return ranked

    def _read_existing_items(self) -> list[str]:
        if not self.memory_file.exists():
            return []
        text = self.memory_file.read_text(encoding="utf-8")
        if _SECTION_BEGIN not in text or _SECTION_END not in text:
            return []
        start = text.index(_SECTION_BEGIN) + len(_SECTION_BEGIN)
        end = text.index(_SECTION_END, start)
        body = text[start:end]
        items = []
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("- "):
                candidate = stripped[2:].strip()
                if candidate.startswith("last_updated_utc:"):
                    continue
                items.append(candidate)
        return items

    def _write_memory_section(self, items: list[str]) -> None:
        if self.memory_file.exists():
            text = self.memory_file.read_text(encoding="utf-8")
        else:
            text = "# Long-Term Memory\n\n"

        section_lines = [_SECTION_BEGIN, "## Consolidated Memory"]
        if items:
            section_lines.extend(f"- {item}" for item in items)
        else:
            section_lines.append("- (no consolidated items)")
        section_lines.append(f"last_updated_utc: {_utc_now_iso()}")
        section_lines.append(_SECTION_END)
        section = "\n".join(section_lines)

        if _SECTION_BEGIN in text and _SECTION_END in text:
            begin_index = text.index(_SECTION_BEGIN)
            end_index = text.index(_SECTION_END, begin_index) + len(_SECTION_END)
            new_text = f"{text[:begin_index].rstrip()}\n\n{section}\n{text[end_index:].lstrip()}"
        else:
            new_text = f"{text.rstrip()}\n\n{section}\n"

        self.memory_file.write_text(new_text, encoding="utf-8")

    def _read_watermark(self) -> dict[str, object]:
        if not self.watermark_path.exists():
            return {"processed_artifact_ids": []}
        try:
            payload = json.loads(self.watermark_path.read_text(encoding="utf-8"))
        except Exception:
            return {"processed_artifact_ids": []}
        if not isinstance(payload, dict):
            return {"processed_artifact_ids": []}
        raw_ids = payload.get("processed_artifact_ids", [])
        ids = [str(item) for item in raw_ids if str(item).strip()] if isinstance(raw_ids, list) else []
        return {"processed_artifact_ids": ids}

    def _write_watermark(self, artifact_ids: list[str]) -> None:
        payload = {
            "updated_at": _utc_now_iso(),
            "processed_artifact_ids": artifact_ids,
        }
        self.watermark_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
