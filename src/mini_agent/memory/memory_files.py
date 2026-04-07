"""Memory file discovery and lightweight write helpers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MemoryFileLayout:
    """Resolved memory file layout from one workspace anchor."""

    anchor_dir: Path
    gemini_file: Path | None
    memory_file: Path | None


def discover_memory_layout(start_dir: str | Path) -> MemoryFileLayout:
    """Discover GEMINI.md and MEMORY.md by walking from cwd to root."""
    current = Path(start_dir).expanduser().resolve()
    gemini_file: Path | None = None
    memory_file: Path | None = None

    for candidate_dir in [current, *current.parents]:
        gemini_candidate = candidate_dir / "GEMINI.md"
        memory_candidate = candidate_dir / "MEMORY.md"
        if gemini_file is None and gemini_candidate.exists():
            gemini_file = gemini_candidate
        if memory_file is None and memory_candidate.exists():
            memory_file = memory_candidate
        if gemini_file is not None and memory_file is not None:
            break

    if gemini_file is not None:
        anchor_dir = gemini_file.parent
    elif memory_file is not None:
        anchor_dir = memory_file.parent
    else:
        anchor_dir = current

    return MemoryFileLayout(
        anchor_dir=anchor_dir,
        gemini_file=gemini_file,
        memory_file=memory_file,
    )


def ensure_memory_file(memory_file: str | Path, *, title: str = "# MEMORY") -> Path:
    """Create memory file if missing and keep a tiny canonical header."""
    target = Path(memory_file).expanduser().resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(f"{title}\n\n", encoding="utf-8")
    return target


def append_memory_note(
    memory_file: str | Path,
    *,
    heading: str,
    content: str,
    timestamp_utc: str | None = None,
) -> Path:
    """Append one note block to MEMORY.md."""
    target = ensure_memory_file(memory_file)
    normalized_heading = heading.strip() or "Untitled"
    normalized_content = content.strip()
    stamp = timestamp_utc or _utc_now_iso()
    block = (
        f"## {normalized_heading}\n"
        f"- at: {stamp}\n"
        f"{normalized_content}\n\n"
    )
    with target.open("a", encoding="utf-8") as handle:
        handle.write(block)
    return target
