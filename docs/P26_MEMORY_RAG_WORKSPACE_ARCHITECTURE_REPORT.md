# P26 Memory + RAG + Workspace Architecture Report

> Status: Proposed
> Date: 2026-04-10
> Scope: optimize Mini-Agent memory architecture for global memory, workspace task memory, RAG integration, and strong session/workspace coupling

## 1. Executive Summary

Your direction is broadly correct:

- keep the current lightweight RAG/KB system as the primary RAG path
- treat vectorization as a future enhancement, not a prerequisite
- strengthen the existing durable memory system instead of replacing it
- add a workspace-scoped `MemoriaEngine` layer for complex task execution
- make memory tightly integrated with `workspace` and `session`

But there are 3 important design corrections:

1. the current memory system is **not truly global yet**
2. `MemoriaEngine` must **not** become a second durable truth store
3. a workspace-level `MemoriaEngine` must be **session-aware / namespaced**, otherwise multi-session contamination is unavoidable

## 2. Current Reality In Mini-Agent

Today Mini-Agent already has one live durable memory path:

- `MemoryService`
  - workspace-scoped note/profile/session/consolidated retrieval facade
- durable files
  - `MEMORY.md`
  - `USER.md`
  - `memory/YYYY-MM-DD.md`
- runtime injection
  - workspace memory provider
  - consolidated memory provider
- write paths
  - `record_note`
  - `recall_notes`
  - `user_modeling`
  - automatic post-turn memory writeback
- retrieval and support paths
  - session transcript search
  - consolidation pipeline
  - Studio Ops memory APIs
  - gateway `/api/memory/*`

This means Mini-Agent already has a usable memory kernel.

## 3. Design Correction: What Is Wrong In The Current Mental Model

### 3.1 "Current memory is global"

This is the first design mismatch.

In code, current memory is still primarily **workspace-scoped**, because `MemoryService` resolves around the active workspace anchor. It feels global only because the main runtime often runs inside one long-lived primary workspace.

If you really want:

- user profile
- agent habits
- cross-workspace operational preferences

then that data must move to an explicit **global store**, not stay implicitly attached to whichever workspace happens to be active.

### 3.2 "Each workspace uses a second memory system"

This wording is dangerous.

If `MemoriaEngine` becomes a second memory system with equal status to the current durable memory stack, Mini-Agent will immediately have:

- one file-backed durable memory system
- one transient/workspace memory system

Without an ownership boundary, the two systems will drift.

So `MemoriaEngine` must not be described as a second durable memory system.
It should be described as:

- **workspace runtime task memory**
- session-aware
- promotable into durable memory
- but not itself the durable source of truth

### 3.3 "One workspace with multiple session threads"

This requirement is correct, but it changes the design.

If one workspace can have multiple sessions, then a single unpartitioned workspace `MemoriaEngine` is wrong, because:

- session A temporary task state can pollute session B
- unrelated investigations inside the same repository will bleed into each other
- retrieval quality will collapse as workspace complexity grows

The correct design is:

- one **physical Memoria store per workspace**
- multiple **logical namespaces inside it**

At minimum:

- `session:<session_id>` for isolated task memory
- `workspace:shared` for promoted workspace-level task facts

## 4. Optimized Architecture

Mini-Agent should move to a **four-plane memory architecture**.

### Plane G1: Global Durable Memory

Purpose:

- user profile
- user preferences
- agent operating habits
- cross-workspace learned conventions

Examples:

- user prefers Chinese replies
- user prefers concise technical summaries
- agent should default to TUI/CLI-first explanations

Storage:

- `~/.mini-agent/global/USER.md`
- `~/.mini-agent/global/AGENT.md`

Notes:

- this is the true cross-workspace layer
- this replaces the mistaken assumption that current root-level memory is already global

### Plane W1: Workspace Durable Memory

Purpose:

- project architecture facts
- long-lived workspace decisions
- repo/domain glossary
- recurring implementation rules
- workspace-local daily notes

Examples:

- this repo uses TUI/CLI as primary surfaces
- model switching is runtime-rebuilt per session
- QQ shared-session flow uses gateway-managed session control

Storage:

- existing workspace `MEMORY.md`
- existing workspace `memory/YYYY-MM-DD.md`

Notes:

- keep the existing file-backed system
- do not replace it
- strengthen it

### Plane W2: Workspace Runtime Task Memory (`MemoriaEngine`)

Purpose:

- active task decomposition state
- working memory for complex multi-step jobs
- transient task facts that are not yet stable enough for durable memory
- cross-turn task continuity inside the same workspace

Examples:

- current subgoal stack
- unresolved assumptions
- recent intermediate findings
- which files or modules are currently being compared
- temporary conclusions that may later be promoted

Storage model:

- one physical store per workspace
- namespaced by session and shared workspace scope

Suggested namespaces:

- `session:<session_id>`
- `workspace:shared`

Notes:

- this layer should be persisted for restart recovery
- but it is still not the primary durable truth
- promotion out of this layer must be explicit or policy-driven

### Plane K1: RAG / Knowledge Base

Purpose:

- grounded document retrieval
- manual or policy-triggered factual lookup
- external/project docs, references, imported knowledge

Current primary path:

- built-in lightweight hybrid store
- `BM25 + hash-vector cosine`
- explicit `knowledge_base_query`

Notes:

- keep this as the main RAG implementation for now
- vector DB / stronger embeddings remain future enhancements
- RAG stores source facts, not behavioral memory

## 5. Clear Ownership Rules

This is the most important part.

### Global Durable Memory owns:

- user profile
- user reply preferences
- cross-workspace agent behavior conventions

### Workspace Durable Memory owns:

- stable project knowledge
- stable repo decisions
- lessons learned specific to one workspace

### Workspace Runtime `MemoriaEngine` owns:

- active task memory
- intermediate working state
- transient cross-turn task continuity

### RAG owns:

- document chunks
- citations
- source-grounded facts

## 6. The Most Important Anti-Duplication Rule

Do **not** store raw RAG chunks as memory.

Instead:

- RAG retrieves source material
- the agent uses it
- if something becomes stable and reusable, write a distilled memory entry
- store citation/reference metadata if needed

Good:

- "Workspace uses event-driven session recovery; related gateway APIs already exist."

Bad:

- raw 700-character chunk copied from a design doc into `MEMORY.md`

This keeps memory small, interpretable, and reusable.

## 7. Retrieval Strategy Per Turn

Each turn should retrieve in this order:

### Tier 1: Always-small, high-value context

- global user profile
- global agent conventions

This should be tiny and stable.

### Tier 2: Workspace stable memory

- workspace durable notes
- consolidated workspace memory

### Tier 3: Runtime/session recovery memory

- active session recovery
- `MemoriaEngine` `session:<session_id>` retrieval
- optionally `workspace:shared` promoted task memory

### Tier 4: On-demand search memory

- session search
- RAG / KB retrieval

These should be conditional, not always injected.

## 8. Session / Workspace Integration Design

This is where Mini-Agent should borrow from the reference projects.

### Reference insight from Hermes

Hermes keeps a clean split between:

- persistent memory
- session search

That is the correct mental model for Mini-Agent too:

- memory = small, curated, stable
- session search = large, automatic, on-demand

Mini-Agent should keep that separation.

### Reference insight from extracted-src / Claude

The extracted-src code makes project identity stable:

- session history and project identity stay anchored to a stable project root
- mid-session directory changes do not redefine the session's project identity

Mini-Agent should adopt the same rule:

- a session belongs to exactly one workspace identity
- workspace memory and workspace `MemoriaEngine` are anchored to that stable workspace root
- ad-hoc cwd changes should not silently remap memory ownership

## 9. Recommended Storage Topology

### Global

- `~/.mini-agent/global/USER.md`
- `~/.mini-agent/global/AGENT.md`

### Workspace durable

- `<workspace>/MEMORY.md`
- `<workspace>/memory/YYYY-MM-DD.md`

### Workspace runtime Memoria

Suggested:

- `~/.mini-agent/state/workspaces/<workspace_hash>/memoria.sqlite`

or

- `~/.mini-agent/state/workspaces/<workspace_hash>/memoria.jsonl`

with logical namespaces inside:

- `session:<session_id>`
- `workspace:shared`

This is better than storing transient Memoria state directly inside the repo.

## 10. Recommended Service Topology

Do not create unrelated parallel services.

Instead, evolve the current `MemoryService` into the top-level orchestrator.

Suggested structure:

- `GlobalMemoryStore`
- `WorkspaceMemoryStore`
- `SessionSearchStore`
- `WorkspaceMemoriaRuntime`
- `KnowledgeBaseConnector`

All should still be reachable through one orchestrator facade.

That gives you:

- one runtime integration seam
- one operator API family
- one place to enforce ranking / dedupe / promotion policy

## 11. Promotion Rules

### Promote into Global Durable Memory when:

- the fact is about the user
- the preference is stable across workspaces
- the agent operating convention is globally reusable

### Promote into Workspace Durable Memory when:

- the fact is stable for this repo/workspace
- the decision is architectural or procedural
- the lesson is likely to matter again in this workspace

### Keep only in `MemoriaEngine` when:

- the fact is task-local
- the conclusion is temporary
- the state is needed only for current multi-turn execution

### Keep only in RAG when:

- it is still source material
- it has not yet been distilled into a reusable memory

## 12. What Should Be Improved First

Before adding workspace `MemoriaEngine`, Mini-Agent should strengthen the current memory path in this order:

1. add a real global memory layer separate from workspace memory
2. add a `UserProfileTurnContextProvider` so `USER.md` is actually used automatically
3. add a workspace-filtered `SessionSearchTurnContextProvider`
4. add automatic or trigger-based consolidated-memory refresh

Only after that should `MemoriaEngine` enter the runtime.

Reason:

if you add `MemoriaEngine` before the durable/global/workspace boundaries are corrected, it will enter a confused topology and quickly become a second messy memory bucket.

## 13. Minimal Correct Runtime Shape For `MemoriaEngine`

When Mini-Agent is ready to add it, the first correct shape should be:

- persisted workspace runtime store
- session namespace isolation
- retrieval only through the existing turn-context seam
- promotion hooks into workspace/global durable memory
- no direct operator expectation that it is the same thing as `MEMORY.md`

In other words:

- `MemoriaEngine` should behave like runtime task memory
- not like a replacement for durable memory

## 14. Final Recommendation

The optimized version of your design is:

- keep current lightweight RAG as the main RAG implementation
- treat stronger vector search as a future enhancement
- split memory into:
  - global durable memory
  - workspace durable memory
  - workspace runtime task memory (`MemoriaEngine`)
  - on-demand session search
- keep RAG separate from memory ownership
- use one stable workspace identity per session
- let `MemoriaEngine` be workspace-scoped but session-namespaced
- use explicit promotion rules to move facts from runtime/task memory into durable memory

## 15. Bottom-Line Assessment Of Your Proposal

### Correct parts

- RAG stays lightweight-first
- durable memory should be enhanced rather than replaced
- `MemoriaEngine` is better used inside workspace/task scope than as a global memory engine
- session/workspace integration should be a first-class design goal

### Parts that need correction

- current memory is not truly global yet
- `MemoriaEngine` should not be treated as a second durable memory system
- one workspace with many sessions requires namespace isolation inside `MemoriaEngine`
- RAG results should not be copied into memory verbatim

### Final judgment

The design is good after correction.

The corrected architecture is strong, clear, and extensible, and it fits the current Mini-Agent codebase much better than either:

- making everything global, or
- force-promoting `MemoriaEngine` into the runtime too early.
