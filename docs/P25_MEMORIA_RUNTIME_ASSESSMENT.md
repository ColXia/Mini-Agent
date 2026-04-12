# P25 Memoria Runtime Assessment

> Status: Decided
> Date: 2026-04-10
> Decision: Keep `MemoriaEngine` as a lower-level primitive for now

## Goal

Decide whether `mini_agent/memory/memoria_engine.py` should be promoted into the live Mini-Agent runtime during P25 memory-core consolidation.

## Short Answer

Not in P25.

`MemoriaEngine` should remain a lower-level primitive for now and should not be wired into runtime yet.

## Current Reality

The live memory path is already built around durable, runtime-visible components:

- `MemoryService`
  - unified entry for notes, profile, session search, and consolidated retrieval
- note/profile durability
  - `MEMORY.md`
  - `USER.md`
  - `memory/YYYY-MM-DD.md`
- runtime retrieval
  - `WorkspaceMemoryContextProvider`
  - `ConsolidatedMemoryTurnContextProvider`
- operator/runtime tools
  - `record_note`
  - `user_modeling`
  - automatic post-turn memory writeback
- search and consolidation
  - session transcript search
  - consolidated memory relevance retrieval
  - two-phase consolidation pipeline

By contrast, the current `MemoriaEngine` is still only:

- in-memory
- process-local
- non-persistent
- not wired into `Agent`, gateway, TUI, CLI, or turn-context providers
- covered only by baseline unit tests

## Why Not Promote It Now

### 1. It would duplicate the existing memory stack

Mini-Agent already has one real memory path:

- durable files
- retrieval through `MemoryService`
- prompt injection through turn-context providers
- operator surfaces through TUI/CLI/gateway

If `MemoriaEngine` were wired in today, Mini-Agent would immediately have two memory systems:

- durable runtime memory
- transient `MemoriaEngine` memory

That would create divergence without a reconciliation model.

### 2. Its current implementation is weaker than the live runtime path

The current `MemoriaEngine` implementation provides:

- lexical token overlap scoring
- simple recency/importance scoring
- in-memory layer demotion

It does not currently provide:

- persistence
- session/workspace restore
- ingestion from real transcript/tool/runtime events
- stronger retrieval than the already-landed consolidated-memory and session-search path

So promoting it now would increase complexity more than capability.

### 3. There is no runtime contract yet

To become a real runtime subsystem, `MemoriaEngine` would need explicit answers for:

- what gets ingested
- when it gets ingested
- where it is stored
- how it is queried
- how operators inspect or control it
- how it coexists with `MEMORY.md`, `USER.md`, session search, and consolidated memory

Those contracts do not exist yet.

## Decision

For P25:

- keep `MemoriaEngine` as a lower-level primitive
- do not wire it directly into runtime
- do not create a second memory store around it
- keep the live memory kernel centered on `MemoryService` and the existing durable memory surfaces

## What Promotion Would Require Later

`MemoriaEngine` should only be promoted after all of the following exist:

### 1. One persisted store contract

- workspace-scoped or session-scoped persistence
- deterministic restore across restart
- explicit serialization format

### 2. One ingestion policy

- transcript events
- tool outcomes
- operator commands
- memory automation outputs

Ingestion must be explicit and bounded, not passive "save everything".

### 3. One retrieval bridge

- retrieval must feed the existing turn-context seam
- it must not bypass the current prepared-context curation path

### 4. One observability surface

- stats
- recent promoted memories
- layer counts / usage
- failure and drift visibility

### 5. One coexistence rule with current durable memory

Examples:

- `MemoriaEngine` as ephemeral pre-consolidation working memory only
- durable facts still written through note/profile memory
- promotion to durable memory only through explicit consolidation

## Recommended Future Shape

If Mini-Agent later needs `MemoriaEngine`, the cleanest role is:

- ephemeral working/short-term memory buffer inside one runtime session
- never the primary durable memory source
- durable memory still remains:
  - `MEMORY.md`
  - `USER.md`
  - daily memory
  - consolidated memory

That keeps the architecture single-path:

- transient memory helps local runtime reasoning
- durable memory remains file-backed and operator-visible

## P25 Conclusion

P25 should end with:

- one coherent durable memory kernel
- one shared retrieval and operator surface
- no parallel runtime memory subsystem

On that basis, `MemoriaEngine` remains intentionally unmounted.
