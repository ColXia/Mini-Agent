# API v1 Contract Skeleton

> **状态**: ✅ 活跃
> **最后更新**: 2026-04-06
> **版本**: v1.0 (P18 execution baseline)
> **文档索引**: [DOCS_INDEX.md](./DOCS_INDEX.md)

Updated: 2026-04-09

## 1. Scope

This file defines the first stable contract skeleton for hard refactor P18.

Rules:
1. Frontend consumes `/api/v1/*` only.
2. Router layer must use interface DTOs from `mini_agent/interfaces/*`.
3. No compatibility response shape should be preserved.

## 2. Endpoint Domains

1. System:
   - `GET /api/v1/system/health`
2. Main Agent:
   - `POST /api/v1/agent/chat`
   - `GET /api/v1/agent/chat/stream`
   - `GET /api/v1/agent/sessions`
   - `POST /api/v1/agent/sessions`
   - `GET /api/v1/agent/sessions/{session_id}`
   - `GET /api/v1/agent/sessions/{session_id}/messages`
   - `PATCH /api/v1/agent/sessions/{session_id}`
   - `DELETE /api/v1/agent/sessions/{session_id}`
   - `POST /api/v1/agent/sessions/{session_id}/share`
   - `POST /api/v1/agent/sessions/{session_id}/reset`
   - `POST /api/v1/agent/sessions/{session_id}/control`
3. Novel Subprogram:
   - removed in the v11.1 hard cut; `/api/v1/novel/*` is no longer part of the active contract
4. Channel Ingress:
   - `POST /api/v1/channel/message`
   - no longer performs feature-specific novel action dispatch
5. Ops:
   - `GET /api/v1/ops/providers`
   - `POST /api/v1/ops/providers`
   - `PUT /api/v1/ops/providers/{provider_id}`
   - `DELETE /api/v1/ops/providers/{provider_id}`
   - `GET /api/v1/ops/providers/{provider_id}/health`
   - `GET /api/v1/ops/memory/summary`
   - `GET /api/v1/ops/memory/search`
   - `GET /api/v1/ops/memory/daily/{day}`

## 2.1 Implementation Snapshot

| Endpoint | Status |
| --- | --- |
| `GET /api/v1/system/health` | Implemented |
| `POST /api/v1/agent/chat` | Implemented |
| `GET /api/v1/agent/chat/stream` | Implemented |
| `GET /api/v1/agent/sessions` | Implemented |
| `POST /api/v1/agent/sessions` | Implemented |
| `GET /api/v1/agent/sessions/{session_id}` | Implemented |
| `GET /api/v1/agent/sessions/{session_id}/messages` | Implemented |
| `PATCH /api/v1/agent/sessions/{session_id}` | Implemented |
| `DELETE /api/v1/agent/sessions/{session_id}` | Implemented |
| `POST /api/v1/agent/sessions/{session_id}/share` | Implemented |
| `POST /api/v1/agent/sessions/{session_id}/reset` | Implemented |
| `POST /api/v1/agent/sessions/{session_id}/control` | Implemented |
| `GET /api/v1/novel/config` | Removed in v11.1 hard cut |
| `POST /api/v1/novel/setup` | Removed in v11.1 hard cut |
| `POST /api/v1/novel/write` | Removed in v11.1 hard cut |
| `POST /api/v1/novel/finalize` | Removed in v11.1 hard cut |
| `POST /api/v1/novel/cover` | Removed in v11.1 hard cut |
| `POST /api/v1/novel/illustrate` | Removed in v11.1 hard cut |
| `GET /api/v1/novel/chapters` | Removed in v11.1 hard cut |
| `GET /api/v1/novel/chapter/{chapter_number}` | Removed in v11.1 hard cut |
| `PUT /api/v1/novel/chapter/{chapter_number}` | Removed in v11.1 hard cut |
| `GET /api/v1/novel/chapter/{chapter_number}/versions` | Removed in v11.1 hard cut |
| `GET /api/v1/novel/chapter/{chapter_number}/version/{version_id}` | Removed in v11.1 hard cut |
| `PATCH /api/v1/novel/chapter/{chapter_number}/version/{version_id}` | Removed in v11.1 hard cut |
| `POST /api/v1/novel/chapter/{chapter_number}/rollback` | Removed in v11.1 hard cut |
| `GET /api/v1/novel/chapter/{chapter_number}/diff` | Removed in v11.1 hard cut |
| `GET /api/v1/novel/assets` | Removed in v11.1 hard cut |
| `GET /api/v1/ops/providers` | Implemented |
| `POST /api/v1/ops/providers` | Implemented |
| `PUT /api/v1/ops/providers/{provider_id}` | Implemented |
| `DELETE /api/v1/ops/providers/{provider_id}` | Implemented |
| `GET /api/v1/ops/providers/{provider_id}/health` | Implemented |
| `GET /api/v1/ops/memory/summary` | Implemented |
| `GET /api/v1/ops/memory/search` | Implemented |
| `GET /api/v1/ops/memory/daily/{day}` | Implemented |
| `POST /api/v1/channel/message` | Implemented |

## 3. DTO Source of Truth

Interface DTO package:
- `mini_agent/interfaces/common.py`
- `mini_agent/interfaces/system.py`
- `mini_agent/interfaces/agent.py`
- `mini_agent/interfaces/novel.py`
- `mini_agent/interfaces/channel.py`
- `mini_agent/interfaces/ops.py`

## 4. Hard-Cut Policy

1. Old ad-hoc routes will be removed phase-by-phase after `/api/v1/*` replacement.
2. No long-term dual-route compatibility.
3. Any contract change must update this file and DTO definitions in the same slice.
4. Studio gateway legacy route set (`/api/health`, `/api/chat*`, `/api/sessions*`, `/api/novel/*`, `/api/studio/*`) has been hard-deleted on 2026-04-06.
