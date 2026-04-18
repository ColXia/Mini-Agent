from __future__ import annotations

from mini_agent.transport.remote_memory_client import RemoteMemoryClient


class _DummyGatewayClient:
    def get_ops_memory_summary_sync(self, *, workspace_dir: str | None = None):
        return {
            "workspace_dir": workspace_dir or "D:/file/Mini-Agent",
            "memory_root": "D:/file/Mini-Agent",
            "long_term_file": "D:/file/Mini-Agent/MEMORY.md",
            "daily_dir": "D:/file/Mini-Agent/memory",
            "daily_files": ["2026-04-18.md"],
            "notes_count": 2,
            "categories": ["fact", "decision"],
        }

    def search_ops_memory_sync(self, *, query: str = "", limit: int = 20, workspace_dir: str | None = None):
        return {
            "workspace_dir": workspace_dir or "D:/file/Mini-Agent",
            "query": query,
            "limit": limit,
            "total": 1,
            "items": [
                {
                    "timestamp": "2026-04-18T08:00:00Z",
                    "category": "fact",
                    "content": "remember this",
                    "path": "memory/2026-04-18.md",
                }
            ],
        }

    def get_ops_memory_daily_sync(self, *, day: str, workspace_dir: str | None = None):
        return {
            "workspace_dir": workspace_dir or "D:/file/Mini-Agent",
            "day": day,
            "path": "D:/file/Mini-Agent/memory/2026-04-18.md",
            "note_count": 1,
            "content": "daily note",
            "items": [
                {
                    "timestamp": "2026-04-18T08:00:00Z",
                    "category": "fact",
                    "content": "remember this",
                    "path": "memory/2026-04-18.md",
                }
            ],
        }


def test_remote_memory_client_shapes_gateway_payloads_into_typed_models() -> None:
    service = RemoteMemoryClient(memory_transport=_DummyGatewayClient())

    summary = service.get_ops_memory_summary_sync(workspace_dir="D:/file/Mini-Agent")
    search = service.search_ops_memory_sync(query="remember", limit=10, workspace_dir="D:/file/Mini-Agent")
    daily = service.get_ops_memory_daily_sync(day="2026-04-18", workspace_dir="D:/file/Mini-Agent")

    assert summary.notes_count == 2
    assert search.total == 1
    assert daily.path.endswith("2026-04-18.md")
