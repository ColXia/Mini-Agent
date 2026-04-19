"""Native knowledge-base tools backed by the built-in lightweight RAG store."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from mini_agent.rag.lightweight_hybrid import HybridSearchStore
from mini_agent.rag.knowledge_base_runtime import resolve_knowledge_base_store_path
from mini_agent.tools.base import Tool, ToolResult


def _truncate_text(value: str, *, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


class KnowledgeBaseQueryTool(Tool):
    """Explicit knowledge-base retrieval tool for agent runtime use."""

    def __init__(
        self,
        *,
        workspace_dir: str | Path = ".",
        store_path: str | Path | None = None,
        embedding_provider: Any | Callable[[str], list[float]] | None = None,
        default_top_k: int = 5,
        max_top_k: int = 10,
        max_hit_chars: int = 260,
    ) -> None:
        self.workspace_dir = Path(workspace_dir).expanduser().resolve()
        self.store_path = Path(store_path).expanduser() if store_path is not None else None
        self.embedding_provider = embedding_provider
        self.default_top_k = max(1, int(default_top_k))
        self.max_top_k = max(self.default_top_k, int(max_top_k))
        self.max_hit_chars = max(80, int(max_hit_chars))

    @property
    def name(self) -> str:
        return "knowledge_base_query"

    @property
    def description(self) -> str:
        return (
            "Search the built-in knowledge base / RAG store for relevant project or document context. "
            "Use this when the answer should be grounded in README/spec/API/design/manual/ingested docs "
            "instead of guessing. Prefer concrete query terms from the user's request, such as feature names, "
            "component names, file names, API names, or decision keywords."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "The search query to run against the knowledge base. "
                        "Use concrete nouns from the request, such as doc titles, component names, API names, "
                        "feature names, or architecture terms."
                    ),
                },
                "knowledge_base_id": {
                    "type": "string",
                    "description": "Optional knowledge-base namespace. Defaults to 'default'.",
                },
                "top_k": {
                    "type": "integer",
                    "minimum": 1,
                    "maximum": self.max_top_k,
                    "default": self.default_top_k,
                    "description": "Maximum number of matching chunks to return.",
                },
            },
            "required": ["query"],
            "additionalProperties": False,
        }

    async def execute(
        self,
        query: str,
        knowledge_base_id: str | None = None,
        top_k: int = 5,
    ) -> ToolResult:
        normalized_query = str(query or "").strip()
        if not normalized_query:
            return ToolResult(success=False, error="query must not be empty.")

        resolved_store = resolve_knowledge_base_store_path(
            workspace_dir=self.workspace_dir,
            store_path=self.store_path,
            must_exist=False,
        )
        if resolved_store is None:
            return ToolResult(success=False, error="knowledge-base store path could not be resolved.")

        kb_id = str(knowledge_base_id or "default").strip() or "default"
        bounded_top_k = max(1, min(int(top_k), self.max_top_k))

        if not resolved_store.exists():
            return ToolResult(
                success=True,
                content=(
                    "Knowledge base is not available yet.\n"
                    f"- knowledge_base_id: {kb_id}\n"
                    f"- store_path: {resolved_store}"
                ),
            )

        try:
            store = HybridSearchStore(
                resolved_store,
                embedding_provider=self.embedding_provider,
            )
            result = store.query(
                query=normalized_query,
                knowledge_base_id=kb_id,
                top_k=bounded_top_k,
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(success=False, error=f"{type(exc).__name__}: {exc}")

        if not result.hits:
            return ToolResult(
                success=True,
                content=(
                    "Knowledge base search returned no matches.\n"
                    f"- knowledge_base_id: {kb_id}\n"
                    f"- query: {normalized_query}\n"
                    f"- store_path: {resolved_store}"
                ),
            )

        lines = [
            "Knowledge base results:",
            f"- knowledge_base_id: {kb_id}",
            f"- query: {normalized_query}",
            f"- store_path: {resolved_store}",
            f"- hits: {len(result.hits)}",
        ]
        for index, hit in enumerate(result.hits, start=1):
            citation = hit.citation or {}
            citation_label = (
                citation.get("source_path")
                or citation.get("url")
                or citation.get("title")
                or citation.get("source_id")
                or hit.document_name
            )
            lines.extend(
                [
                    f"{index}. [{hit.document_name}] {_truncate_text(hit.content, limit=self.max_hit_chars)}",
                    (
                        f"   citation: {citation_label} | "
                        f"score={hit.score:.4f} | bm25={hit.bm25_score:.4f} | vector={hit.vector_score:.4f}"
                    ),
                ]
            )

        return ToolResult(success=True, content="\n".join(lines))


__all__ = ["KnowledgeBaseQueryTool"]
