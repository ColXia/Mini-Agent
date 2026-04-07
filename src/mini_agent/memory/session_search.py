"""Session transcript search index with FTS5-first backend."""

from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9_\u4e00-\u9fff]+")


def _tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN_PATTERN.findall(text) if token]


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return str(value)


def _build_snippet(content: str, query: str, *, radius: int = 48) -> str:
    text = content.strip()
    if not text:
        return ""
    query_lower = query.lower().strip()
    if not query_lower:
        return text[: max(16, radius * 2)]
    lower = text.lower()
    idx = lower.find(query_lower)
    if idx < 0:
        tokens = _tokenize(query_lower)
        for token in tokens:
            idx = lower.find(token.lower())
            if idx >= 0:
                break
    if idx < 0:
        return text[: max(16, radius * 2)]
    start = max(0, idx - radius)
    end = min(len(text), idx + len(query_lower) + radius)
    snippet = text[start:end]
    if start > 0:
        snippet = f"...{snippet}"
    if end < len(text):
        snippet = f"{snippet}..."
    return snippet


class SessionSearchIndex:
    """Session search index with FTS5 backend and LIKE fallback."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir.expanduser().resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.base_dir / "session_search.sqlite3"
        self.backend = "fts5"
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS session_meta (
                    session_id TEXT PRIMARY KEY,
                    workspace_dir TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    message_count INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS message_store (
                    session_id TEXT NOT NULL,
                    message_index INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (session_id, message_index)
                )
                """
            )
            try:
                conn.execute(
                    """
                    CREATE VIRTUAL TABLE IF NOT EXISTS message_fts USING fts5(
                        session_id UNINDEXED,
                        message_index UNINDEXED,
                        role,
                        content,
                        updated_at UNINDEXED
                    )
                    """
                )
                self.backend = "fts5"
            except sqlite3.OperationalError:
                self.backend = "like"
            conn.commit()

    def upsert_session(
        self,
        *,
        session_id: str,
        workspace_dir: str,
        updated_at: str,
        messages: list[dict[str, Any]],
    ) -> None:
        rows: list[tuple[str, int, str, str, str]] = []
        for idx, payload in enumerate(messages):
            if not isinstance(payload, dict):
                continue
            role = _coerce_text(payload.get("role", "assistant")).strip() or "assistant"
            content = _coerce_text(payload.get("content", "")).strip()
            if not content:
                continue
            rows.append((session_id, idx, role, content, updated_at))

        with self._connect() as conn:
            conn.execute("DELETE FROM message_store WHERE session_id = ?", (session_id,))
            if self.backend == "fts5":
                conn.execute("DELETE FROM message_fts WHERE session_id = ?", (session_id,))
            for row in rows:
                conn.execute(
                    """
                    INSERT INTO message_store (session_id, message_index, role, content, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    row,
                )
                if self.backend == "fts5":
                    conn.execute(
                        """
                        INSERT INTO message_fts (session_id, message_index, role, content, updated_at)
                        VALUES (?, ?, ?, ?, ?)
                        """,
                        row,
                    )
            conn.execute(
                """
                INSERT INTO session_meta (session_id, workspace_dir, updated_at, message_count)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                    workspace_dir = excluded.workspace_dir,
                    updated_at = excluded.updated_at,
                    message_count = excluded.message_count
                """,
                (session_id, workspace_dir, updated_at, len(rows)),
            )
            conn.commit()

    def delete_session(self, session_id: str) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM session_meta WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM message_store WHERE session_id = ?", (session_id,))
            if self.backend == "fts5":
                conn.execute("DELETE FROM message_fts WHERE session_id = ?", (session_id,))
            conn.commit()

    def search(
        self,
        *,
        query: str,
        limit: int = 20,
        session_id: str | None = None,
    ) -> list[dict[str, Any]]:
        normalized_query = query.strip()
        if not normalized_query:
            raise ValueError("query must not be empty.")
        max_limit = max(1, min(int(limit), 200))

        with self._connect() as conn:
            if self.backend == "fts5":
                match_query = self._to_match_query(normalized_query)
                if session_id:
                    rows = conn.execute(
                        """
                        SELECT session_id, message_index, role, content, updated_at, bm25(message_fts) AS rank
                        FROM message_fts
                        WHERE message_fts MATCH ? AND session_id = ?
                        ORDER BY rank ASC, message_index ASC
                        LIMIT ?
                        """,
                        (match_query, session_id, max_limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT session_id, message_index, role, content, updated_at, bm25(message_fts) AS rank
                        FROM message_fts
                        WHERE message_fts MATCH ?
                        ORDER BY rank ASC, message_index ASC
                        LIMIT ?
                        """,
                        (match_query, max_limit),
                    ).fetchall()
            else:
                like = f"%{normalized_query.lower()}%"
                if session_id:
                    rows = conn.execute(
                        """
                        SELECT session_id, message_index, role, content, updated_at, 0.0 AS rank
                        FROM message_store
                        WHERE session_id = ? AND lower(content) LIKE ?
                        ORDER BY updated_at DESC, message_index DESC
                        LIMIT ?
                        """,
                        (session_id, like, max_limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT session_id, message_index, role, content, updated_at, 0.0 AS rank
                        FROM message_store
                        WHERE lower(content) LIKE ?
                        ORDER BY updated_at DESC, message_index DESC
                        LIMIT ?
                        """,
                        (like, max_limit),
                    ).fetchall()

        results: list[dict[str, Any]] = []
        for row in rows:
            content = _coerce_text(row["content"])
            results.append(
                {
                    "session_id": _coerce_text(row["session_id"]),
                    "message_index": int(row["message_index"]),
                    "role": _coerce_text(row["role"]),
                    "content": content,
                    "snippet": _build_snippet(content, normalized_query),
                    "updated_at": _coerce_text(row["updated_at"]),
                    "score": float(row["rank"]),
                }
            )
        return results

    def stats(self) -> dict[str, Any]:
        with self._connect() as conn:
            indexed_sessions = int(
                conn.execute("SELECT COUNT(1) AS n FROM session_meta").fetchone()["n"]
            )
            indexed_messages = int(
                conn.execute("SELECT COUNT(1) AS n FROM message_store").fetchone()["n"]
            )
        return {
            "backend": self.backend,
            "indexed_sessions": indexed_sessions,
            "indexed_messages": indexed_messages,
            "db_path": str(self.db_path),
        }

    def _to_match_query(self, query: str) -> str:
        tokens = [token.lower() for token in _tokenize(query)]
        if not tokens:
            escaped = query.replace('"', '""').strip()
            if not escaped:
                raise ValueError("query must not be empty.")
            return f'"{escaped}"'
        return " AND ".join(f'"{token}"' for token in tokens)
