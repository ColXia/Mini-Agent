# P25 Memory Core Consolidation Plan

> Status: Active
> Started: 2026-04-09
> Principle: Reuse and consolidate existing memory modules; do not build a parallel memory stack.

## Status Update (2026-04-09)

Completed in code:

- unified workspace-scoped `MemoryService`
- turn-context providers rewired to the unified memory path
- Studio Ops memory use cases rewired to the unified memory path
- `memory_manager` router rewired to the unified memory path
- `memory_manager` router mounted into gateway at `/api/memory/*`
- automatic post-turn memory writeback wired into `Agent.run_turn`
- focused regression coverage for unified memory service and automation behavior
- `MemoriaEngine` runtime role evaluated and explicitly kept as a lower-level primitive for now

Still active:

- keep automatic writeback conservative while improving real-use coverage
- evaluate future promotion criteria for `MemoriaEngine` only when a real runtime contract is needed

## Goal

Turn the existing memory slices into one coherent memory core that can support future:

- RAG integration
- explicit tools
- skills
- memory automation
- MCP-aware runtime context

The target is a strong but lean memory kernel, not a new compatibility layer.

## Current Inventory

The project already has these memory capabilities implemented:

- markdown note memory: `MEMORY.md` + `memory/YYYY-MM-DD.md`
- user/profile memory: `USER.md`
- session transcript search: SQLite + FTS5/LIKE fallback
- consolidated memory retrieval: relevance search over consolidated memory
- two-phase consolidation pipeline
- baseline STM/LTM engine: `MemoriaEngine`
- memory-manager router and Studio Ops memory endpoints

## Remaining Problems

- some memory features are runtime-active, while others are still operator-facing or baseline-only
- memory surfaces are now functional in both Studio Ops and gateway, but the long-term surface split should remain intentional and minimal
- automatic writeback is now landed, but its heuristics still need real-use tuning
- docs still partially refer to old `memory_tool.py` terminology

## P25 Milestones

### P25.1 Memory inventory and plan sync

- status: completed
- record the real code-level memory status in active docs
- mark which memory paths are runtime-active, weakly wired, or dormant
- set the rule that future memory work must extend existing modules first

### P25.2 Unified memory service

- status: completed
- add one workspace-scoped `MemoryService`
- consolidate note memory, profile memory, session search, and consolidated retrieval behind one API
- keep storage formats unchanged

### P25.3 Runtime and operator wiring

- status: completed
- switch turn-context providers to the unified memory service
- switch Studio Ops memory flows to the unified memory service
- switch memory-manager router to the unified memory service

### P25.4 Strengthening follow-ups

- status: in progress
- mount `memory_manager` into gateway through the existing router path, without building a duplicate API
- add stronger automatic memory writeback policy on top of the existing profile/note layers
- evaluate whether `MemoriaEngine` should become a real runtime subsystem or remain a low-level primitive

## Execution Rules

- No duplicate memory implementation.
- No compatibility shell.
- Prefer direct rewiring over wrapper-on-wrapper design.
- Every memory enhancement must identify the existing module it extends.

## First Delivery Slice

1. [x] add `MemoryService`
2. [x] rewire turn-context providers
3. [x] rewire Studio Ops memory endpoints
4. [x] rewire memory-manager router
5. [x] add focused tests

## Current Strengthening Slice

1. [x] wire automatic post-turn memory writeback into `Agent.run_turn`
2. [x] suppress duplicate auto-write only when explicit memory tools succeeded
3. [x] backfill memory automatically when explicit memory tools failed
4. [x] mount `memory_manager` into gateway at `/api/memory/*`
5. [x] evaluate promotion path for `MemoriaEngine`

## P25.9 Decision

- Decision: keep `MemoriaEngine` as a lower-level primitive in P25
- Rationale:
  - current live memory stack already has one coherent durable path centered on `MemoryService`
  - current `MemoriaEngine` is in-memory only and has no persistence/runtime/operator contract
  - force-mounting it now would create a second memory subsystem and duplicate retrieval semantics
- Reference:
  - `docs/P25_MEMORIA_RUNTIME_ASSESSMENT.md`
