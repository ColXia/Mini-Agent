"""User modeling tool backed by built-in profile memory provider."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mini_agent.memory.builtin_memory import BuiltinMemoryProvider

from .base import Tool, ToolResult


class UserModelingTool(Tool):
    """Minimal global user-profile modeling tool surface."""

    def __init__(
        self,
        memory_root: str = "./workspace",
        provider: BuiltinMemoryProvider | None = None,
        global_root: str | Path | None = None,
    ):
        self.provider = provider or BuiltinMemoryProvider(
            memory_root,
            profile_scope="global",
            global_root=global_root,
        )

    @property
    def name(self) -> str:
        return "user_modeling"

    @property
    def description(self) -> str:
        return (
            "Global user profile memory tool with actions: profile, search, conclude, replace, remove. "
            "Use conclude to store stable cross-workspace user facts and preferences."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["profile", "search", "conclude", "replace", "remove"],
                    "description": "Operation to perform.",
                    "default": "profile",
                },
                "query": {
                    "type": "string",
                    "description": "Search query when action=search.",
                },
                "fact": {
                    "type": "string",
                    "description": "Fact text when action=conclude or replace.",
                },
                "match": {
                    "type": "string",
                    "description": "Substring matcher when action=replace or remove.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum returned matches when action=search.",
                    "default": 5,
                    "minimum": 1,
                    "maximum": 100,
                },
            },
        }

    async def execute(
        self,
        action: str = "profile",
        query: str | None = None,
        fact: str | None = None,
        match: str | None = None,
        limit: int = 5,
    ) -> ToolResult:
        try:
            normalized_action = action.strip().lower()
            if normalized_action == "profile":
                return self._execute_profile()
            if normalized_action == "search":
                return self._execute_search(query=query, limit=limit)
            if normalized_action == "conclude":
                return self._execute_conclude(fact=fact)
            if normalized_action == "replace":
                return self._execute_replace(match=match, fact=fact)
            if normalized_action == "remove":
                return self._execute_remove(match=match)
            return ToolResult(
                success=False,
                content="",
                error="Invalid action. Use one of: profile, search, conclude, replace, remove.",
            )
        except Exception as exc:
            return ToolResult(
                success=False,
                content="",
                error=f"User modeling failed: {exc}",
            )

    def _execute_profile(self) -> ToolResult:
        snapshot = self.provider.profile()
        facts = snapshot.get("facts", [])
        fact_count = int(snapshot.get("fact_count", 0))
        user_file = str(snapshot.get("user_file", ""))

        lines = [
            f"User Profile ({fact_count} facts)",
            f"scope: {snapshot.get('scope', 'global')}",
            f"user_file: {user_file}",
        ]
        if facts:
            for index, fact in enumerate(facts, start=1):
                lines.append(f"{index}. {fact}")
        else:
            lines.append("(no facts yet)")
        return ToolResult(success=True, content="\n".join(lines))

    def _execute_search(self, *, query: str | None, limit: int) -> ToolResult:
        if query is None or not query.strip():
            return ToolResult(success=False, content="", error="query is required for search action.")
        hits = self.provider.search(query=query, limit=max(1, min(int(limit), 100)))
        if not hits:
            return ToolResult(success=True, content=f"No profile facts matched query: {query.strip()}")

        lines = [f"Profile Search Results ({len(hits)})"]
        for index, hit in enumerate(hits, start=1):
            lines.append(
                f"{index}. {hit['fact']} (score={hit['score']}, index={hit['index']})"
            )
        return ToolResult(success=True, content="\n".join(lines))

    def _execute_conclude(self, *, fact: str | None) -> ToolResult:
        if fact is None or not fact.strip():
            return ToolResult(success=False, content="", error="fact is required for conclude action.")
        result = self.provider.add_fact(fact=fact)
        return ToolResult(
            success=True,
            content=(
                f"Profile conclude status={result['status']} "
                f"(fact_count={result['fact_count']}): {result['fact']}"
            ),
        )

    def _execute_replace(self, *, match: str | None, fact: str | None) -> ToolResult:
        if match is None or not match.strip():
            return ToolResult(success=False, content="", error="match is required for replace action.")
        if fact is None or not fact.strip():
            return ToolResult(success=False, content="", error="fact is required for replace action.")
        result = self.provider.replace_fact(match=match, fact=fact)
        return ToolResult(
            success=True,
            content=(
                f"Profile replace status={result['status']} "
                f"(replaced={result['replaced']}, fact_count={result['fact_count']})."
            ),
        )

    def _execute_remove(self, *, match: str | None) -> ToolResult:
        if match is None or not match.strip():
            return ToolResult(success=False, content="", error="match is required for remove action.")
        result = self.provider.remove_fact(match=match)
        return ToolResult(
            success=True,
            content=(
                f"Profile remove status={result['status']} "
                f"(removed={result['removed']}, fact_count={result['fact_count']})."
            ),
        )
