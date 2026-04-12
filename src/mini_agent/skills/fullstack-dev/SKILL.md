---
name: fullstack-dev
description: Handle end-to-end features spanning UI, backend, API contracts, persistence, and runtime behavior.
metadata:
  trigger_keywords:
    - 全栈
    - 前后端
    - 接口
    - API
    - 后端
    - 数据流
    - integration
---

# Fullstack Dev

Build the smallest valuable vertical slice first, then harden it.

## Core Rules

1. Inspect the existing architecture before introducing a new subsystem.
2. Reuse current runtime, storage, session, workspace, and command seams whenever possible.
3. Define the API or message contract before coding both sides.
4. Keep the local run path short: one obvious command if possible.
5. Validate the real user flow, not only isolated units.

## Preferred Workflow

1. Audit the current stack:
   - entrypoints
   - backend/runtime modules
   - frontend or TUI/CLI surfaces
   - persistence and session model
2. Choose one end-to-end slice that proves the feature works.
3. Lock the contract:
   - request shape
   - response shape
   - state transitions
   - error cases
4. Implement the backend/runtime seam first when the contract is unclear.
5. Wire the user-facing surface second.
6. Add focused validation for the integrated flow.

## Architecture Expectations

- Keep business logic out of thin transport handlers.
- Keep data contracts explicit and testable.
- Avoid duplicate caches, registries, or shadow configuration sources.
- Prefer composition over introducing another top-level subsystem.

## Skill Composition

- Load `frontend-dev` when the user-facing web UI needs serious attention.
- Load `webapp-testing` when the browser flow should be verified through Playwright.
- Load `mcp-builder` when the task involves adding or extending MCP servers.

## Acceptance Bar

Do not stop at "code exists". Confirm that:

- the main flow is actually reachable
- the surface and backend agree on the same contract
- obvious failure paths are handled
- startup/run instructions remain simple

If the task is only frontend polish, use `frontend-dev` alone instead of this skill.
