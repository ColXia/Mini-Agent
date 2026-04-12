# P18 Route Deletion Backlog

> **状态**: ✅ 活跃
> **最后更新**: 2026-04-06
> **文档索引**: [DOCS_INDEX.md](./DOCS_INDEX.md)

Updated: 2026-04-06

This file tracks legacy ad-hoc routes that must be removed during hard refactor.

## 1. Legacy -> V1 Mapping

| Legacy Route | Replacement | Status |
| --- | --- | --- |
| `GET /api/health` | `GET /api/v1/system/health` | Deleted (hard cut, 2026-04-06) |
| `POST /api/chat` | `POST /api/v1/agent/chat` | Deleted (hard cut, 2026-04-06) |
| `GET /api/chat/stream` | `GET /api/v1/agent/chat/stream` | Deleted (hard cut, 2026-04-06) |
| `GET /api/sessions` | `GET /api/v1/agent/sessions` | Deleted (hard cut, 2026-04-06) |
| `DELETE /api/sessions/{session_id}` | `DELETE /api/v1/agent/sessions/{session_id}` | Deleted (hard cut, 2026-04-06) |
| `POST /api/sessions/{session_id}/reset` | `POST /api/v1/agent/sessions/{session_id}/reset` | Deleted (hard cut, 2026-04-06) |
| `POST /api/novel/*` | `POST /api/v1/novel/*` | Deleted (hard cut, 2026-04-06) |
| `GET /api/studio/*` | `GET/POST /api/v1/ops/*` | Deleted (hard cut, 2026-04-06) |

## 2. Deletion Rule

1. A legacy route is deleted only after frontend/client has switched to v1 contract.
2. No compatibility wrappers are added in this process.
3. Deletion and replacement test update must be completed in the same slice.
