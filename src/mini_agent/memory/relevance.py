"""Relevance retrieval on top of consolidated memory."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Callable, Literal


_SECTION_BEGIN = "<!-- MINI_AGENT_CONSOLIDATED_MEMORY_BEGIN -->"
_SECTION_END = "<!-- MINI_AGENT_CONSOLIDATED_MEMORY_END -->"
_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")

DriftStatus = Literal["aligned", "possibly_stale", "unverified"]
SupportLookup = Callable[[str, int], list[dict[str, Any]]]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _parse_utc(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except Exception:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _utc_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).isoformat()


def _tokenize(text: str) -> list[str]:
    tokens = [token.lower() for token in _TOKEN_PATTERN.findall(text)]
    deduped: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        if token in seen:
            continue
        seen.add(token)
        deduped.append(token)
    return deduped


def _bounded_int(value: int, *, min_value: int, max_value: int) -> int:
    return max(min_value, min(int(value), max_value))


@dataclass(frozen=True)
class ConsolidatedMemorySnapshot:
    items: list[str]
    memory_last_updated_utc: str | None
    memory_file_mtime_utc: str | None


@dataclass(frozen=True)
class RelevanceMemoryHit:
    content: str
    score: float
    lexical_score: float
    freshness_score: float
    drift_penalty: float
    memory_item_index: int
    drift_status: DriftStatus
    drift_reason: str
    support_last_seen_utc: str | None = None


@dataclass(frozen=True)
class DriftAssessment:
    status: DriftStatus
    reason: str
    support_last_seen_utc: str | None


class ConsolidatedMemoryRelevanceRetriever:
    """Rank consolidated memory items by side-query relevance and freshness."""

    def __init__(self, memory_file: Path | str):
        self.memory_file = Path(memory_file).expanduser().resolve()

    def search(
        self,
        *,
        query: str,
        top_k: int = 5,
        stale_after_days: int = 30,
        support_lookup: SupportLookup | None = None,
    ) -> dict[str, Any]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty.")

        bounded_top_k = _bounded_int(int(top_k), min_value=1, max_value=50)
        bounded_stale_days = _bounded_int(int(stale_after_days), min_value=1, max_value=3650)
        snapshot = self.load_snapshot()

        payload: dict[str, Any] = {
            "query": normalized_query,
            "top_k": bounded_top_k,
            "stale_after_days": bounded_stale_days,
            "memory_file": str(self.memory_file),
            "memory_file_mtime_utc": snapshot.memory_file_mtime_utc,
            "memory_last_updated_utc": snapshot.memory_last_updated_utc,
            "item_count": len(snapshot.items),
            "returned": 0,
            "hits": [],
        }
        if not snapshot.items:
            return payload

        now = _utc_now()
        query_tokens = _tokenize(normalized_query)
        freshness_reference = snapshot.memory_last_updated_utc or snapshot.memory_file_mtime_utc
        freshness_score = self._score_freshness(
            freshness_reference_utc=freshness_reference,
            now_utc=now,
            stale_after_days=bounded_stale_days,
        )

        ranked: list[RelevanceMemoryHit] = []
        for index, item in enumerate(snapshot.items):
            lexical_score = self._score_lexical(item=item, query=normalized_query, query_tokens=query_tokens)
            if lexical_score <= 0.0:
                continue

            drift = self._assess_drift(
                item=item,
                now_utc=now,
                stale_after_days=bounded_stale_days,
                fallback_timestamp_utc=freshness_reference,
                support_lookup=support_lookup,
            )
            drift_penalty = {
                "aligned": 0.0,
                "unverified": 0.2,
                "possibly_stale": 0.75,
            }[drift.status]
            position_bonus = 0.5 / (1.0 + float(index))
            total = (lexical_score * 2.0) + freshness_score + position_bonus - drift_penalty

            ranked.append(
                RelevanceMemoryHit(
                    content=item,
                    score=round(total, 6),
                    lexical_score=round(lexical_score, 6),
                    freshness_score=round(freshness_score, 6),
                    drift_penalty=round(drift_penalty, 6),
                    memory_item_index=index,
                    drift_status=drift.status,
                    drift_reason=drift.reason,
                    support_last_seen_utc=drift.support_last_seen_utc,
                )
            )

        ranked.sort(
            key=lambda item: (-item.score, item.memory_item_index, item.content),
        )
        hits = [asdict(item) for item in ranked[:bounded_top_k]]
        payload["returned"] = len(hits)
        payload["hits"] = hits
        return payload

    def load_snapshot(self) -> ConsolidatedMemorySnapshot:
        mtime_utc = None
        if self.memory_file.exists():
            mtime = datetime.fromtimestamp(self.memory_file.stat().st_mtime, tz=timezone.utc)
            mtime_utc = _utc_iso(mtime)
        if not self.memory_file.exists():
            return ConsolidatedMemorySnapshot(
                items=[],
                memory_last_updated_utc=None,
                memory_file_mtime_utc=mtime_utc,
            )

        text = self.memory_file.read_text(encoding="utf-8")
        if _SECTION_BEGIN not in text or _SECTION_END not in text:
            return ConsolidatedMemorySnapshot(
                items=[],
                memory_last_updated_utc=None,
                memory_file_mtime_utc=mtime_utc,
            )

        begin_index = text.index(_SECTION_BEGIN) + len(_SECTION_BEGIN)
        end_index = text.index(_SECTION_END, begin_index)
        body = text[begin_index:end_index]

        items: list[str] = []
        seen: set[str] = set()
        memory_last_updated_utc: str | None = None
        for line in body.splitlines():
            stripped = line.strip()
            if not stripped:
                continue

            if stripped.startswith("last_updated_utc:"):
                memory_last_updated_utc = stripped.split(":", 1)[1].strip() or None
                continue

            if not stripped.startswith("- "):
                continue

            candidate = stripped[2:].strip()
            if not candidate:
                continue
            if candidate.startswith("last_updated_utc:"):
                memory_last_updated_utc = candidate.split(":", 1)[1].strip() or None
                continue
            if candidate == "(no consolidated items)":
                continue
            if candidate in seen:
                continue
            seen.add(candidate)
            items.append(candidate)

        return ConsolidatedMemorySnapshot(
            items=items,
            memory_last_updated_utc=memory_last_updated_utc,
            memory_file_mtime_utc=mtime_utc,
        )

    def _score_lexical(self, *, item: str, query: str, query_tokens: list[str]) -> float:
        lowered_item = item.lower()
        lowered_query = query.lower()

        score = 0.0
        if lowered_query in lowered_item:
            score += 4.0

        if not query_tokens:
            return score

        item_tokens = set(_tokenize(lowered_item))
        overlap = len(item_tokens & set(query_tokens))
        if overlap <= 0 and score <= 0.0:
            return 0.0

        score += overlap * 1.5
        score += float(overlap) / float(max(1, len(query_tokens)))
        return score

    def _score_freshness(
        self,
        *,
        freshness_reference_utc: str | None,
        now_utc: datetime,
        stale_after_days: int,
    ) -> float:
        parsed = _parse_utc(freshness_reference_utc)
        if parsed is None:
            return 0.4
        age_days = max(0.0, (now_utc - parsed).total_seconds() / 86400.0)
        decay = 1.0 / (1.0 + (age_days / float(max(1, stale_after_days))))
        return 1.5 * decay

    def _assess_drift(
        self,
        *,
        item: str,
        now_utc: datetime,
        stale_after_days: int,
        fallback_timestamp_utc: str | None,
        support_lookup: SupportLookup | None,
    ) -> DriftAssessment:
        if support_lookup is None:
            return DriftAssessment(
                status="unverified",
                reason="No side-query support source available.",
                support_last_seen_utc=None,
            )

        side_query = self._build_side_query(item)
        if not side_query:
            return DriftAssessment(
                status="unverified",
                reason="Memory item has insufficient tokens for side-query validation.",
                support_last_seen_utc=None,
            )

        try:
            hits = support_lookup(side_query, 5)
        except Exception as exc:
            return DriftAssessment(
                status="unverified",
                reason=f"Side-query validation failed: {exc}",
                support_last_seen_utc=None,
            )

        if not isinstance(hits, list) or not hits:
            fallback_time = _parse_utc(fallback_timestamp_utc)
            if fallback_time is None:
                return DriftAssessment(
                    status="unverified",
                    reason="No supporting transcript hit found.",
                    support_last_seen_utc=None,
                )
            age_days = max(0.0, (now_utc - fallback_time).total_seconds() / 86400.0)
            if age_days > stale_after_days:
                return DriftAssessment(
                    status="possibly_stale",
                    reason=f"No supporting transcript hit and memory is {int(age_days)} days old.",
                    support_last_seen_utc=None,
                )
            return DriftAssessment(
                status="unverified",
                reason="No supporting transcript hit found.",
                support_last_seen_utc=None,
            )

        latest_seen = self._latest_hit_timestamp(hits)
        if latest_seen is None:
            return DriftAssessment(
                status="unverified",
                reason="Supporting transcript hits have no valid timestamp.",
                support_last_seen_utc=None,
            )

        age_days = max(0.0, (now_utc - latest_seen).total_seconds() / 86400.0)
        if age_days > stale_after_days:
            return DriftAssessment(
                status="possibly_stale",
                reason=f"Latest supporting transcript is {int(age_days)} days old.",
                support_last_seen_utc=_utc_iso(latest_seen),
            )

        return DriftAssessment(
            status="aligned",
            reason="Supporting transcript evidence is recent.",
            support_last_seen_utc=_utc_iso(latest_seen),
        )

    def _build_side_query(self, item: str) -> str:
        tokens = _tokenize(item)
        if not tokens:
            return ""
        ranked_tokens = sorted(tokens, key=lambda token: (-len(token), token))
        chosen: list[str] = []
        for token in ranked_tokens:
            if len(chosen) >= 4:
                break
            if len(token) <= 1:
                continue
            if token in chosen:
                continue
            chosen.append(token)
        return " ".join(chosen)

    def _latest_hit_timestamp(self, hits: list[dict[str, Any]]) -> datetime | None:
        latest: datetime | None = None
        for hit in hits:
            if not isinstance(hit, dict):
                continue
            parsed = _parse_utc(hit.get("updated_at"))
            if parsed is None:
                continue
            if latest is None or parsed > latest:
                latest = parsed
        return latest
