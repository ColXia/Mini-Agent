# Development Index (Published)

> **鐘舵€?*: 鉁?娲昏穬
> **鏈€鍚庢洿鏂?*: 2026-04-12
> **缁存姢鑰?*: Mini-Agent Core Refactor
> **鏂囨。绱㈠紩**: [DOCS_INDEX.md](./DOCS_INDEX.md)

> Note (P18 hard refactor): entries under old phases may reference deleted legacy modules for historical traceability only.
> Current runtime architecture is single-host v1 (`src/apps/agent_studio_gateway/main.py` + `/api/v1/*`).
> Stage normalization (2026-04-07): P18 closeout baseline frozen; P19 kickoff + Stage-C docs + ops alerting + adoption tracking/target-bands/delta slices landed.
> Phase update (2026-04-12): terminal-first remains the active implementation focus, and the product entrance model is explicitly `CLI / TUI / DesktopUI / Remote Interaction`; current remote delivery is `QQ` only, while any non-QQ adapter remains future-only and out of the active repo.
> Session boundary update (2026-04-14 P32.34): `src/mini_agent/session/store.py` and `tests/test_session_store_persistence.py` were removed. Live session ownership is now `src/mini_agent/runtime/session_state.py` + `src/mini_agent/runtime/session_runtime_persistence.py`, while `mini_agent.session` is limited to persistence/projection/conversation-binding owners.
> Surface cleanup update (2026-04-14 P32.35): browser `WebUI / OpenWebUI` were hard-removed from the active codebase; canonical entrances are now only `CLI / TUI / DesktopUI / Remote Interaction`.
> Remote lock update (2026-04-14 P32.60): `QQ` is the only active remote adapter path. Legacy `WeChat` / old channel trees were removed from the active repo so future work cannot drift back into "QQ as a fifth entrance" or fake multi-channel parity.
> Current execution anchor (2026-04-16): `docs/P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md`.

## 1. Navigation
- Refactor plan: `docs/REFACTOR_TASKS.md`
- Current execution anchor: `docs/P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md`
- Framework skeleton lock: `docs/FRAMEWORK_SKELETON.md`
- Dev habit and mistake ledger: `docs/MINIAGENT_DEV_HABIT_LEDGER.md`
- API v1 contract skeleton: `docs/API_V1_CONTRACT_SKELETON.md`
- Archived P18 route deletion backlog: `docs/archive/P18_ROUTE_DELETION_BACKLOG.md`
- Archived P18 closeout baseline evidence: `docs/archive/P18_CLOSEOUT_BASELINE_2026-04-07.md`
- Archived P18 hard-refactor execution plan: `docs/archive/P18_HARD_REFACTOR_EXECUTION_PLAN.md`
- Archived P19 rollout prep contract: `docs/archive/P19_AGENT_TEAM_ROLLOUT_CONTRACT.md`
- Archived P19 operator runbook: `docs/archive/P19_TEAM_MODE_OPERATOR_RUNBOOK.md`
- Archived P19 rollout announcement: `docs/archive/P19_TEAM_MODE_ROLLOUT_ANNOUNCEMENT.md`
- Archived P19 support FAQ: `docs/archive/P19_TEAM_MODE_SUPPORT_FAQ.md`
- Archived P19 ops alert policy: `docs/archive/P19_TEAM_MODE_ALERT_POLICY.md`
- Archived P19 Stage-C adoption tracking: `docs/archive/P19_STAGEC_ADOPTION_TRACKING.md`
- Archived P19 canary cadence: `docs/archive/P19_TEAM_MODE_CANARY_CADENCE.md`
- Archived P19 weekly readiness template: `docs/archive/P19_WEEKLY_RELEASE_READINESS_TEMPLATE.md`
- Archived GitHub upload scope (2026-04-07): `docs/archive/GITHUB_UPLOAD_SCOPE_2026-04-07.md`
- Archived cross-device handoff (2026-04-07): `docs/archive/CROSS_DEVICE_HANDOFF_2026-04-07.md`
- Archived anti-duplication system inventory (2026-04-07): `docs/archive/ANTI_DUPLICATION_REPORT_2026-04-07.md`
- Terminal real-use readiness gate (2026-04-08): `docs/P23_TERMINAL_REAL_USE_READINESS.md`
- Real-use command acceptance checklist (2026-04-10): `docs/P24_REAL_USE_COMMAND_ACCEPTANCE_CHECKLIST.md`
- Memory core consolidation plan (2026-04-09): `docs/P25_MEMORY_CORE_TASK_PLAN.md`
- Memoria runtime assessment (2026-04-10): `docs/P25_MEMORIA_RUNTIME_ASSESSMENT.md`
- Memory + RAG + workspace architecture report (2026-04-10): `docs/P26_MEMORY_RAG_WORKSPACE_ARCHITECTURE_REPORT.md`
- Memory runtime implementation plan (2026-04-10): `docs/P26_MEMORY_RUNTIME_TASK_PLAN.md`
- Session boundary audit (2026-04-12): `docs/P29_SESSION_BOUNDARY_AUDIT_2026-04-12.md`
- Session hard-refactor plan (2026-04-12): `docs/P29_SESSION_HARD_REFACTOR_PLAN.md`
- Surface/session architecture correction (2026-04-12): `docs/P30_SURFACE_SESSION_ARCHITECTURE_CORRECTION_2026-04-12.md`
- Surface/session executable refactor task plan (2026-04-12): `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
- Session truth boundary map (2026-04-13): `docs/P30_SESSION_TRUTH_BOUNDARY_MAP_2026-04-13.md`
- DesktopUI(PySide6) decision + task plan (2026-04-13): `docs/P31_DESKTOPUI_PYSIDE6_TASK_PLAN_2026-04-13.md`
- Remote interaction hard-lock (2026-04-14): `docs/P32_REMOTE_INTERACTION_ARCHITECTURE_LOCK_2026-04-14.md`
- Repo hygiene + structure alignment plan (2026-04-16): `docs/P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md`
- LLM runtime upgrade plan (2026-04-14): `docs/P33_LLM_RUNTIME_UPGRADE_PLAN_2026-04-14.md`
- Runtime truth + provider governance plan (2026-04-15): `docs/P33B_RUNTIME_TRUTH_AND_PROVIDER_GOVERNANCE_PLAN_2026-04-15.md`
- Agent-core refactor plan (2026-04-15): `docs/P34_AGENT_CORE_REFACTOR_PLAN_2026-04-15.md`
- Session/runtime contract consolidation plan (2026-04-15): `docs/P36_SESSION_RUNTIME_CONTRACT_CONSOLIDATION_PLAN_2026-04-15.md`
- TUI surface orchestration convergence plan (2026-04-15): `docs/P37_TUI_SURFACE_ORCHESTRATION_CONVERGENCE_PLAN_2026-04-15.md`
- Post-P36 runtime/surface evaluation (2026-04-15): `docs/POST_P36_RUNTIME_SURFACE_EVALUATION_2026-04-15.md`
- Post-P37 TUI/surface evaluation (2026-04-16): `docs/POST_P37_TUI_SURFACE_EVALUATION_2026-04-16.md`
- Architecture execution guardrails (2026-04-17): `docs/ARCHITECTURE_EXECUTION_GUARDRAILS_2026-04-17.md`
- v11.1 agent/workspace execution architecture (2026-04-17): `docs/V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md`
- v11.1 agent kernel contract design (2026-04-17): `docs/V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md`
- v11.1 run/attachment/checkpoint/journal design (2026-04-17): `docs/V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md`
- v11.1 run control and agent lifecycle design (2026-04-17): `docs/V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md`
- v11.1 model block design record (2026-04-17): `docs/V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md`
- v11.1 user surface architecture (2026-04-17): `docs/V11_1_USER_SURFACE_ARCHITECTURE_2026-04-17.md`
- v11.1 user service to kernel interface design (2026-04-17): `docs/V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md`
- v11.1 module ownership and migration direction (2026-04-17): `docs/V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md`
- v11.1 transport DTO and read-model contract (2026-04-17): `docs/V11_1_TRANSPORT_DTO_AND_READ_MODEL_CONTRACT_2026-04-17.md`
- v11.1 architecture migration execution order (2026-04-17): `docs/V11_1_ARCHITECTURE_MIGRATION_EXECUTION_ORDER_2026-04-17.md`
- v11.1 concrete module tree (2026-04-17): `docs/V11_1_CONCRETE_MODULE_TREE_2026-04-17.md`
- Historical transformation plan (source-study only): `docs/TRANSFORMATION_PLAN.md`
- Transformation plan (mini guardrails): `docs/TRANSFORMATION_PLAN_LITE_ADDENDUM.md`
- OSS mapping index: `docs/OSS_REFERENCE_INDEX.md`
- Archived external OSS index bridge: `docs/archive/EXTERNAL_OSS_INDEX.md`
- Runtime boundary notes: `docs/RUNTIME_FLOW.md`

## 2. Current Phase Status
- Execution note (2026-04-16): the current daily execution anchor is `P32b` repo hygiene and structure alignment. Older lines below remain important architecture references, but they are not the current execution anchor unless explicitly restated.
- `P0`: done
- `P1`: done
- `P2`: done
- `P3`: done (session kernel persistence + retention + migration landed)
- `P4`: done (ACP states + gateway lock/auth + conversation binding landed)
- `P5`: done (MCP modular split + policy/resources + profile sync + atomic writes)
- `P6`: done (runtime policy + execution/access modes + security audit command)
- `P7`: done (plugin capability boundaries + markdown memory split + hybrid retrieval)
- `P8`: done (structured run events + replay logs + doctor + startup self-check)
- `P9`: done (retention/rotation + observability APIs + deep doctor probe + export/guardrails)
- `P10`: done (schema/export/auth + durability + ops/metrics/throughput controls landed and rechecked)
- `P11`: done (agent execution policy and step-state refactor kickoff landed)
- `P12`: done (memory core baseline completed with lean architecture)
- `P13`: done (model-manager minimal path landed: T1.1-T1.6)
- `P14`: done (T2.1-T2.7 landed)
- `P15`: done (T3.1-T3.7 landed)
- `P16`: done (T4.1-T4.4 landed)
- `P17+`: done (T5.1/T5.2/T5.3 hardening + deployment follow-up validations completed on 2026-04-07)
- `P18`: done (hard refactor completed; baseline frozen for single-host v1 on 2026-04-07)
- `P19`: done (rollout preparation baseline completed on 2026-04-07; documentation and operator guardrails landed)
- `P20`: done (historical positioning work completed; browser adapters were later removed in P32.35)
- `P21`: done (terminal interaction refactor and unified terminal entry landed)
- `P24`: maintained baseline (TUI-first real-use refinement remains part of the product baseline, but it is not the current execution anchor)
- `P25`: maintained baseline (memory-core consolidation and shared memory service wiring are landed and remain the maintained reference)
- `P26`: maintained baseline (runtime memory boundary correction is landed and remains the maintained reference)
- `P29`: maintained reference line (session boundary audit is complete and remains a boundary reference rather than the current execution line)
- `P30`: maintained architecture foundation (surface/session correction locked the four-entrance model and remains the base architecture reference)
- `P31`: maintained direction line (`DesktopUI(PySide6)` remains the canonical graphical mainline)
- `P32`: active (second-pass repo hygiene / structure alignment / commit slicing is now tracked in `docs/P32B_REPO_HYGIENE_AND_STRUCTURE_ALIGNMENT_PLAN_2026-04-16.md`)
- `P33`: done (runtime/provider/config baseline upgrade completed)
- `P33b`: done (runtime truth and provider governance completed)
- `P34`: done (agent-core refactor completed)
- `P35`: done (core seam lock completed before P36; tracked through the P36 execution note and progress log)
- `P36`: done (session/runtime contract consolidation completed)
- `P37`: done (TUI surface orchestration convergence completed)

Latest stage sync:
- `2026-04-11`: Windows sandbox hardening is paused at the current sufficient-for-demo baseline.
- `2026-04-11`: active execution focus returns to P24 demo-baseline acceptance across `TUI / CLI / QQ / gateway`.
- `2026-04-12`: session work is temporarily re-anchored to P29 boundary repair after the latest unification bug exposed multi-owner session semantics and surface/runtime coupling.
- `2026-04-12`: architecture is now explicitly corrected at P30: sessions are core truth, while the four user entrances are `CLI / TUI / DesktopUI / Remote Interaction`; the active remote adapter is `QQ`, and any future adapters still belong under the remote entrance as thin adapters; execution should proceed from `docs/P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`.
- `2026-04-13`: framework skeleton is explicitly locked in `docs/FRAMEWORK_SKELETON.md`; future implementation should treat it as the repo/layer ownership guardrail before adding more surface or remote behavior.
- `2026-04-13`: the third graphical mainline is frozen as `DesktopUI(PySide6)`; the next desktop implementation order is `thin application seam first -> reuse existing gateway transport -> build DesktopUI shell`.
- `2026-04-15`: `P33 / P33b` runtime/model/provider lines are materially complete; later work should build on the registry/runtime/config truth already landed.
- `2026-04-15`: `P34` agent-core refactor is materially complete; later core work should start from a fresh problem statement rather than reopening the same seam line.
- `2026-04-15`: `P36` session/runtime contract consolidation is materially complete.
- `2026-04-16`: `P37` TUI surface orchestration convergence is materially complete.
- `2026-04-16`: active execution focus moves to `P32b` repo hygiene, commit slicing, and active-doc alignment.
- `2026-04-17`: architecture execution is explicitly tightened again: surfaces must stay presentation-only plus local ephemeral UI state, while shared interaction/runtime corrections belong in `application/` or `runtime/`; use `docs/ARCHITECTURE_EXECUTION_GUARDRAILS_2026-04-17.md` as the current boundary checklist.
- `2026-04-17`: `v11.1` architecture discussion baseline is now captured in `docs/V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md`; use it as the current agent/workspace/session/tool/skill/memory boundary discussion anchor before opening a new core redesign slice.
- `2026-04-17`: the first kernel-contract discussion group is now captured in `docs/V11_1_AGENT_KERNEL_CONTRACT_DESIGN_2026-04-17.md`; treat `AgentProfile / AgentInstance / Run / Attachment / CapabilitySnapshot / Checkpoint / ExecutionJournal` as the maintained kernel truth model for later service and runtime redesign.
- `2026-04-17`: the second kernel-design slice is now captured in `docs/V11_1_RUN_ATTACHMENT_CHECKPOINT_JOURNAL_DESIGN_2026-04-17.md`; treat `Run.status + Run.phase`, attachment references, checkpoint write points, and journal separation as the maintained execution-truth contract.
- `2026-04-17`: the third kernel-design slice is now captured in `docs/V11_1_RUN_CONTROL_AND_AGENT_LIFECYCLE_DESIGN_2026-04-17.md`; treat run-owned control state, first-class approval waits, interrupt-vs-cancel separation, and agent-instance lifecycle as the maintained control-plane baseline.
- `2026-04-17`: the main agent-facing model boundary is now captured separately in `docs/V11_1_MODEL_BLOCK_DESIGN_RECORD_2026-04-17.md`; treat model supply as `ModelPool + AgentModelService`, not as workspace/session-owned state.
- `2026-04-17`: the corrected user-side topology is now captured in `docs/V11_1_USER_SURFACE_ARCHITECTURE_2026-04-17.md`; treat `TUI / Desktop / Remote Interaction` as the primary user surfaces and `CLI` as the command-carrier form of the shared command subsystem.
- `2026-04-17`: the user-service/application/runtime-port interface direction is now captured in `docs/V11_1_USER_SERVICE_TO_KERNEL_INTERFACE_DESIGN_2026-04-17.md`; treat explicit user services as the stable surface contract and treat current session-centric application/runtime ports as transitional compatibility structures.
- `2026-04-17`: the physical ownership and migration direction is now captured in `docs/V11_1_MODULE_OWNERSHIP_AND_MIGRATION_DIRECTION_2026-04-17.md`; treat physical module placement as part of the architecture contract so future implementation keeps logical and repository structure aligned.
- `2026-04-17`: the transport/DTO/read-model boundary is now captured in `docs/V11_1_TRANSPORT_DTO_AND_READ_MODEL_CONTRACT_2026-04-17.md`; treat truth objects, internal projections, interface DTOs, and raw transport payloads as four distinct shapes with explicit conversion boundaries.
- `2026-04-17`: the staged migration order is now captured in `docs/V11_1_ARCHITECTURE_MIGRATION_EXECUTION_ORDER_2026-04-17.md`; use it to sequence future code migration so truth movement, service introduction, compatibility retention, and cleanup happen in the correct order.
- `2026-04-17`: the concrete target tree is now captured in `docs/V11_1_CONCRETE_MODULE_TREE_2026-04-17.md`; use it as the file-level landing map for Stage 1-3 implementation so new code stops drifting into transitional owners.
- `2026-04-18`: the surface DTO-read boundary is tightened again: TUI/desktop surface paths now route DTO-to-payload conversion through `mini_agent.interfaces.surface_payload_adapter`, and `tests/test_surface_payload_boundary_hygiene.py` guards against new direct `.model_dump()` transport serialization inside surface modules.
- `2026-04-18`: gateway workspace/model routes now consume `WorkspaceUserService` and `ModelUserService` directly instead of routing those entrypoints through `MainAgentSurfaceService`; shared HTTP DTO normalization for those services lives in `src/mini_agent/application/facades/service_response_dto_adapter.py`.
- `2026-04-18`: gateway session mutation/control routes now consume `SessionTaskService`, `AgentUserService`, and `ModelUserService` directly; `MainAgentSurfaceService` remains on the chat/session-read side while the gateway transport layer now owns request-binding adaptation for the migrated mutation endpoints.
- `2026-04-18`: gateway session list/create/default/detail/message routes now consume `SessionTaskService` directly, with explicit router-owned `resolve_workspace_dir` and `validate_workspace` handling; `MainAgentSurfaceService` is narrowed further toward chat/stream orchestration and transitional diagnostics only.
- `2026-04-18`: `GatewayComposition` no longer assembles the legacy `SessionApplicationService`; gateway runtime composition now exposes explicit user services only, while legacy session-facade compatibility remains isolated under `mini_agent.application.legacy`.
- `2026-04-18`: the gateway router no longer depends on a whole `MainAgentSurfaceService` object for chat/routing endpoints; transport dependencies are now explicit callables for `run_main_agent_chat`, `stream_main_agent_chat`, and routing diagnostics, which keeps the router ready for later chat-service extraction without another transport contract rewrite.

## 3. Active Plan: P22 Core Agent Minimal (Started 2026-04-07)

Goal: keep Mini-Agent lightweight, while landing the minimum core capabilities required by terminal-first agent products (extracted-src/codex/gemini-cli/opencode style), without pursuing full parity.

Scope (current implementation focus):
- [x] P22.1 Wire `code_agent` submission loop into real runtime path (TUI + CLI + headless landed).
- [x] P22.2 Add minimal task lifecycle (`queued/running/completed/cancelled`) and `/tasks` visibility in terminal UX (TUI landed).
- [x] P22.3 Make interrupt robust at runtime boundaries (turn-level + tool-level best-effort hard stop; foreground `bash` interrupt landed).
- [x] P22.4 Ensure model switch takes effect deterministically (invalidate/rebuild active agent sessions).
- [x] P22.5 Add one minimal workflow orchestration entry (`research -> implement -> verify`) using existing coordinator baseline (TUI/CLI `/workflow` landed).
- [x] P22.6 Integrate unified `agent-core` kernel bootstrap (shared build path for CLI/TUI/Gateway; remove duplicate bootstrap wiring).

Delivery principles:
- Minimal viable architecture, no compatibility shell.
- Test-first for each milestone (unit + focused integration).
- TUI/CLI first; browser WebUI/OpenWebUI are removed.

## 4. Active Plan: P23 Agent-Core Hard Wiring (Started 2026-04-07)

Goal: keep Mini-Agent lightweight while turning existing `agent_core` modules into real runtime capabilities through direct wiring, with no compatibility shell.

Primary docs:
- `docs/P23_AGENT_CORE_DETAILED_PLAN.md`
- `docs/P23_AGENT_CORE_TASK_PLAN.md`

Milestones:
- [x] P23.1 Wire `agent_core.session.lifecycle` into gateway runtime manager and diagnostics.
- [x] P23.2 Align CLI/TUI session reuse/reset semantics with the same lifecycle policy.
- [x] P23.3 Wire minimal delegation path into main runtime.
- [x] P23.4 Wire routing resolver into main runtime.
- [x] P23.5 Stability/performance convergence and regression hardening.

## 5. Current Operating Mode (2026-04-08)

Goal: treat TUI as the primary daily-use surface and drive the next iteration loop from real usage findings, not speculative UI work.

Current execution rules:
- TUI/CLI first; browser WebUI/OpenWebUI are removed.
- Prefer validating changes through real TUI interaction before adding more abstraction.
- Keep internal runtime noise out of the main chat view unless it directly helps the operator.
- Every TUI polish change should leave behind one of: focused test, scripted checklist, or walkthrough evidence.

Evidence already landed:
- terminal gate: `python scripts/terminal_readiness_gate.py`
- live headless smoke: `python scripts/terminal_readiness_gate.py --run-live-headless`
- scripted TUI checklist: `python scripts/tui_manual_checklist.py`
- prompt_toolkit walkthrough: `python scripts/tui_interaction_walkthrough.py`

## 6. Active Plan: P25 Memory Core Consolidation (Started 2026-04-09)

Goal: consolidate the already-landed memory slices into one coherent memory core that can support future RAG, tools, skills, memory automation, and MCP-aware runtime context without introducing a second parallel memory stack.

Primary doc:
- `docs/P25_MEMORY_CORE_TASK_PLAN.md`

Current code-level inventory:
- markdown note memory is already landed and runtime-usable
- user/profile memory is already landed via `USER.md`
- session transcript search is already landed via SQLite/FTS5
- consolidated memory retrieval and two-phase consolidation are already landed
- `MemoriaEngine` exists as a baseline primitive but is not yet the main runtime memory orchestrator
- `memory_manager` router is now mounted into gateway, while Studio Ops keeps its own memory operator surface

Completed integration slice:
- [x] P25.1 Add one unified `MemoryService` entry point
- [x] P25.2 Rewire turn-context providers to the unified memory service
- [x] P25.3 Rewire Studio Ops memory flows to the unified memory service
- [x] P25.4 Rewire memory-manager router to the unified memory service
- [x] P25.5 Add focused tests and verify no behavioral regression on existing memory paths

Current strengthening slice:
- [x] P25.6 Add conservative automatic post-turn memory writeback in the shared `Agent.run_turn` path
- [x] P25.7 Suppress duplicate auto-write only when explicit memory tools succeeded, and backfill automatically when they failed
- [x] P25.8 Mount the existing `memory_manager` router into gateway at `/api/memory/*`, while keeping Studio Ops memory under `/api/v1/ops/memory/*`
- [x] P25.9 Evaluate `MemoriaEngine` and keep it as a lower-level primitive for now; do not create a second runtime memory subsystem during P25

## 7. Active Plan: P26 Memory Runtime Architecture (Started 2026-04-10)

Goal: turn the P26 architecture report into a real runtime path for global durable memory, workspace durable memory, future session-aware task memory, and explicit RAG ownership.

Primary docs:
- `docs/P26_MEMORY_RAG_WORKSPACE_ARCHITECTURE_REPORT.md`
- `docs/P26_MEMORY_RUNTIME_TASK_PLAN.md`

Current implementation state:
- [x] P26.1 Correct the global-vs-workspace durable memory boundary
- [x] P26.2 Add a real `user_profile` turn-context provider backed by global durable memory
- [x] P26.3 Add workspace-aware session-search turn-context retrieval
- [x] P26.4 Add consolidated-memory refresh / promotion policy
- [x] P26.5 Add persisted workspace runtime `MemoriaEngine` with session namespaces
- [x] P26.6 Add operator-facing memory diagnostics and `/memory` controls across gateway/TUI/CLI
- [x] P26.7 Harden `reset/delete/clear` semantics so session runtime task memory is cleared consistently across gateway/TUI/CLI
- [x] P26.8 Add snapshot/import/export parity for session-scoped runtime task memory across gateway/TUI share flows
- [x] P26.9 Add merge-safe snapshot/import/export portability for workspace-shared runtime task memory
- [x] P26.10 Add workspace-shared candidate/promotion policy and `/memory promote shared`
- [x] P26.11 Add retrieval gating so workspace-shared runtime memory remains supplemental

## 15. P12+ Deep Transformation (Planned)

See `docs/TRANSFORMATION_PLAN.md` for the complete transformation plan.
Execution guardrails are enforced by `docs/TRANSFORMATION_PLAN_LITE_ADDENDUM.md` (small/fast/strong only).
Mini principle in execution: capability strong, architecture lean (not capability reduction).

### P12: Memory Core (P0 in transformation plan)
- [x] T0.1: Memoria STM/LTM engine (mini baseline)
  - `mini_agent/memory/engram.py`
  - `mini_agent/memory/memoria_engine.py`
  - tests: `tests/test_memory_core_baseline.py`
- [x] T0.2: GEMINI.md hierarchical file system (discovery + safe append baseline)
  - `mini_agent/memory/memory_files.py`
  - tests: `tests/test_memory_core_baseline.py`
- [x] T0.3: MemoryTool self-save (runtime path integration)
  - `mini_agent/tools/note_tool.py` (hierarchical memory anchor + topic tag self-save)
  - tests: `tests/test_note_tool.py`
- [x] T0.4: FTS5 session search (router + health diagnostics baseline)
  - `mini_agent/memory/session_search.py`
  - `mini_agent/session/persistence.py`
  - `mini_agent/session/store.py`
  - `gateway/routers/sessions.py`
  - `gateway/routers/observability.py`
  - tests: `tests/test_session_search.py`, `tests/test_session_store_persistence.py`, `tests/test_gateway_routers.py`
- [x] T0.5: Two-phase memory consolidation baseline (bounded phase1/phase2 + scheduler)
  - phase1: `mini_agent/memory/consolidation_phase1.py`
  - phase2: `mini_agent/memory/consolidation_phase2.py`
  - scheduler: `mini_agent/memory/consolidation_scheduler.py`
  - facade: `mini_agent/memory/consolidation.py`
  - CLI entry: `mini-agent consolidate-memory`
  - tests: `tests/test_memory_consolidation.py`
- [x] T0.6: Relevance memory retrieval
  - relevance ranker: `mini_agent/memory/relevance.py`
  - persistence/store integration:
    - `mini_agent/session/persistence.py`
    - `mini_agent/session/store.py`
  - gateway endpoint: `GET /api/sessions/memory/relevance`
  - router: `gateway/routers/sessions.py`
  - tests:
    - `tests/test_memory_relevance.py`
    - `tests/test_session_store_persistence.py`
    - `tests/test_gateway_routers.py`
- [x] T0.7: User modeling (Honcho)
  - provider abstraction: `mini_agent/memory/memory_provider.py`
  - builtin provider: `mini_agent/memory/builtin_memory.py`
  - tool surface: `mini_agent/tools/user_modeling.py`
  - runtime wiring: `mini_agent/runtime/tooling.py`
  - tests:
    - `tests/test_user_modeling.py`
    - `tests/test_note_tool.py`

### P13: Model Manager (P1 in transformation plan)
- [x] T1.1: Custom Provider configuration
  - provider schema + normalization:
    - `mini_agent/model_manager/provider.py`
    - `mini_agent/model_manager/__init__.py`
  - tests: `tests/test_provider_config.py`
- [x] T1.2: Proxy routing
  - model mapper + route selector:
    - `mini_agent/model_manager/model_mapper.py`
    - `mini_agent/model_manager/runtime.py`
  - runtime wiring:
    - `mini_agent/cli_interactive.py`
    - `gateway/routers/chat.py`
    - `mini_agent/acp/__init__.py`
  - tests:
    - `tests/test_model_mapper.py`
    - `tests/test_model_routing_runtime.py`
- [x] T1.3: Circuit breaker
  - three-state breaker core:
    - `mini_agent/model_manager/circuit_breaker.py`
  - exported model-manager interfaces:
    - `mini_agent/model_manager/__init__.py`
  - tests:
    - `tests/test_circuit_breaker.py`
- [x] T1.4: Health monitoring
  - provider health monitor + runtime state hooks:
    - `mini_agent/model_manager/health_monitor.py`
    - `mini_agent/model_manager/runtime.py`
  - dashboard APIs:
    - `gateway/routers/model_manager.py`
    - `gateway/core/app.py`
    - `gateway/routers/__init__.py`
  - tests:
    - `tests/test_health_monitor.py`
    - `tests/test_model_manager_router.py`
- [x] T1.5: Failover
  - error classification + failover executor:
    - `mini_agent/model_manager/error_classifier.py`
    - `mini_agent/model_manager/failover.py`
  - routing candidate chain + breaker-aware fallback:
    - `mini_agent/model_manager/model_mapper.py`
    - `mini_agent/model_manager/runtime.py`
  - runtime wiring:
    - `mini_agent/cli_interactive.py`
    - `gateway/routers/chat.py`
    - `mini_agent/acp/__init__.py`
  - tests:
    - `tests/test_model_failover.py`
    - `tests/test_error_classifier.py`
    - `tests/test_model_routing_runtime.py`
- [x] T1.6: Request rectifier
  - request rectifier + protocol converters:
    - `mini_agent/model_manager/rectifier.py`
  - llm client request-stage integration:
    - `mini_agent/llm/openai_client.py`
    - `mini_agent/llm/anthropic_client.py`
  - model-manager exports:
    - `mini_agent/model_manager/__init__.py`
  - tests:
    - `tests/test_request_rectifier.py`

### P14: Code Agent (P2 in transformation plan)
- [x] T2.1: Agent event loop
  - submission loop + event channel:
    - `mini_agent/agent_core/execution/agent_loop.py`
  - turn context snapshot:
    - `mini_agent/agent_core/context/loop_context.py`
  - scheduler state machine baseline:
    - `mini_agent/agent_core/execution/scheduler.py`
  - package exports:
    - `mini_agent/agent_core/execution/__init__.py`
  - tests:
    - `tests/test_agent_core_execution_loop.py`
- [x] T2.2: Windows sandbox
  - network policy and domain extraction baseline:
    - `mini_agent/agent_core/execution/sandbox/network.py`
  - restricted-token command transform and policy validation:
    - `mini_agent/agent_core/execution/sandbox/windows.py`
  - backend selection manager and exports:
    - `mini_agent/agent_core/execution/sandbox/manager.py`
    - `mini_agent/agent_core/execution/sandbox/__init__.py`
    - `mini_agent/agent_core/execution/__init__.py`
  - tests:
    - `tests/test_agent_core_execution_sandbox.py`
- [x] T2.3: Tool system (DeclarativeTool)
  - declarative contract attributes:
    - `mini_agent/agent_core/execution/tools/attributes.py`
  - invocation model + schema validation:
    - `mini_agent/agent_core/execution/tools/invocation.py`
  - schema-first builder and registry:
    - `mini_agent/agent_core/execution/tools/builder.py`
  - runtime adapter path:
    - `mini_agent/agent_core/execution/tools/runtime_adapter.py`
  - package exports:
    - `mini_agent/agent_core/execution/tools/__init__.py`
    - `mini_agent/agent_core/execution/__init__.py`
  - tests:
    - `tests/test_agent_core_execution_tools.py`
- [x] T2.4: Multi-agent coordination
  - coordinator pipeline and worker contract baseline:
    - `mini_agent/agent_core/execution/coordinator.py`
  - package exports:
    - `mini_agent/agent_core/execution/__init__.py`
  - tests:
    - `tests/test_agent_core_execution_coordinator.py`
- [x] T2.5: Context management
  - layered context compaction:
    - `mini_agent/agent_core/context/context_compaction.py`
  - tool output masking:
    - `mini_agent/agent_core/execution/output_masking.py`
  - package exports:
    - `mini_agent/agent_core/execution/__init__.py`
  - tests:
    - `tests/test_agent_core_context_compaction.py`
- [x] T2.6: MCP client
  - execution MCP client manager:
    - `mini_agent/agent_core/execution/mcp_client.py`
  - MCP declarative wrapper helpers:
    - `mini_agent/agent_core/execution/mcp_tools.py`
  - package exports:
    - `mini_agent/agent_core/execution/__init__.py`
  - tests:
    - `tests/test_agent_core_execution_mcp_client.py`
- [x] T2.7: Permission system
  - permission policy model:
    - `mini_agent/agent_core/execution/permissions/policy.py`
  - approval cache and escalation engine:
    - `mini_agent/agent_core/execution/permissions/approval.py`
    - `mini_agent/agent_core/execution/permissions/__init__.py`
  - package exports:
    - `mini_agent/agent_core/execution/__init__.py`
  - tests:
    - `tests/test_agent_core_execution_permissions.py`

### P15: Agent Core (P3 in transformation plan)
- [x] T3.1: 8-level routing
  - route table and priority resolver:
    - `mini_agent/agent_core/routing.py`
  - package exports:
    - `mini_agent/agent_core/__init__.py`
  - tests:
    - `tests/test_agent_core_routing.py`
- [x] T3.2: Skills platform
  - skills loader + tiers:
    - `mini_agent/agent_core/skills/loader.py`
  - source registry:
    - `mini_agent/agent_core/skills/registry.py`
  - eligibility checks:
    - `mini_agent/agent_core/skills/eligibility.py`
  - package exports:
    - `mini_agent/agent_core/skills/__init__.py`
    - `mini_agent/agent_core/__init__.py`
  - runtime bridge wiring:
    - `mini_agent/tools/skill_tool.py`
  - tests:
    - `tests/test_agent_core_skills.py`
- [x] T3.3: Cron jobs
  - scheduler core:
    - `mini_agent/agent_core/cron/scheduler.py`
  - isolated execution:
    - `mini_agent/agent_core/cron/isolated_run.py`
  - delivery router:
    - `mini_agent/agent_core/cron/delivery.py`
  - package exports:
    - `mini_agent/agent_core/cron/__init__.py`
    - `mini_agent/agent_core/__init__.py`
  - tests:
    - `tests/test_agent_core_cron.py`
- [x] T3.4: Sub-agent delegation
  - delegation manager and contracts:
    - `mini_agent/agent_core/delegation.py`
  - package exports:
    - `mini_agent/agent_core/__init__.py`
  - tests:
    - `tests/test_agent_core_delegation.py`
- [x] T3.5: Session management
  - session-key model and index:
    - `mini_agent/agent_core/session/session_key.py`
  - lifecycle reset policy:
    - `mini_agent/agent_core/session/lifecycle.py`
  - lineage graph and cycle guard:
    - `mini_agent/agent_core/session/lineage.py`
  - package exports:
    - `mini_agent/agent_core/session/__init__.py`
    - `mini_agent/agent_core/__init__.py`
  - tests:
    - `tests/test_agent_core_session.py`
- [x] T3.6: Browser control
  - chrome lifecycle manager:
    - `mini_agent/agent_core/browser/chrome.py`
  - CDP client and navigation guard:
    - `mini_agent/agent_core/browser/cdp.py`
  - agent browser tool interface:
    - `mini_agent/agent_core/browser/tool.py`
  - package exports:
    - `mini_agent/agent_core/browser/__init__.py`
    - `mini_agent/agent_core/__init__.py`
  - tests:
    - `tests/test_agent_core_browser.py`
- [x] T3.7: DM pairing security
  - pairing store baseline:
    - `mini_agent/agent_core/security/pairing.py`
  - dm/group access policy baseline:
    - `mini_agent/agent_core/security/policy.py`
  - package exports:
    - `mini_agent/agent_core/security/__init__.py`
    - `mini_agent/agent_core/__init__.py`
  - tests:
    - `tests/test_agent_core_security_pairing.py`

### P16: Tools & Subprograms (P4 in transformation plan)
- [x] T4.1: Docling integration
  - tool baseline:
    - `mini_agent/tools/docling_parse.py`
    - `mini_agent/tools/__init__.py`
  - document parser subprogram baseline:
    - `subprograms/document_parser/manifest.json`
    - `subprograms/document_parser/main.py`
    - `subprograms/document_parser/gateway/router.py`
  - tests:
    - `tests/test_docling_parse_tool.py`
    - `tests/test_document_parser_router.py`
- [x] T4.2: Knowledge-base integration
  - tool baseline:
    - `mini_agent/tools/knowledge_base.py`
    - `mini_agent/tools/__init__.py`
  - knowledge-base subprogram baseline:
    - `subprograms/knowledge_base/manifest.json`
    - `subprograms/knowledge_base/main.py`
    - `subprograms/knowledge_base/gateway/router.py`
  - tests:
    - `tests/test_knowledge_base_tool.py`
    - `tests/test_knowledge_base_router.py`
- [x] T4.3: Web search tool
  - tool baseline:
    - `mini_agent/tools/web_search.py`
    - `mini_agent/tools/__init__.py`
  - tests:
    - `tests/test_web_search_tool.py`
- [x] T4.4: Memory manager subprogram
  - subprogram baseline:
    - `subprograms/memory_manager/manifest.json`
    - `subprograms/memory_manager/main.py`
    - `subprograms/memory_manager/gateway/router.py`
  - tests:
    - `tests/test_memory_manager_router.py`

### P17: Historical Frontend & Integration Record (P5 in transformation plan)
> Historical note (P32.35): browser `WebUI / OpenWebUI` and the React `agent_studio` frontend were hard-removed on 2026-04-14.
> Keep these entries only as implementation history. Do not use them as active build targets.

- [x] T5.1: Historical Open WebUI adapter slice
  - landed earlier as an OpenAI-compatible browser adapter experiment
  - fully removed from the active codebase in P32.35
  - current replacement policy:
    - no browser adapter path
    - canonical entrances are only `CLI / TUI / DesktopUI / Remote Interaction`
- [x] T5.2: Historical Agent Studio frontend slice
  - the browser frontend and static-host path were removed in P32.35
  - the maintained gateway code under `src/apps/agent_studio_gateway/` now serves API composition only
  - currently maintained files from that slice:
    - `src/apps/agent_studio_gateway/main.py`
    - `src/apps/agent_studio_gateway/composition.py`
    - `src/apps/agent_studio_gateway/main_agent_router.py`
    - `src/apps/agent_studio_gateway/ops_router.py`
  - maintained verification:
    - `tests/test_agent_studio_gateway_ops_router.py`
    - `tests/test_agent_studio_gateway_api_v1.py`
- [x] T5.3: Historical remote-channel completion
  - shared channel contract update:
    - legacy TypeScript channel package formerly lived under `src/channels/types/`
  - QQ channel completion:
    - historical package baseline later consolidated into the maintained runtime app under `src/apps/qqbot_channel/`
  - removed legacy channel trees in `P32.60`:
    - `src/channels/types/`
    - `src/channels/wechat/`
    - `src/mini_agent/channels/`
    - `src/gateway/channels/`
    - `scripts/qq_wechat_smoke.py`
  - channel run scripts at that stage:
    - `scripts/archive/run_qqbot_channel.ps1`
    - `scripts/archive/run_wechat_channel.ps1`
  - current maintained local entry:
    - `uv run mini-agent stack up`
    - `scripts/start_runtime_stack.ps1`
  - tests:
    - `tests/test_gateway_routers.py` (conversation binding sender split coverage)
  - hardening slice still maintained:
    - `src/apps/qqbot_channel/bot.mjs`
    - `src/apps/qqbot_channel/gateway_io.mjs`
    - `src/apps/qqbot_channel/guardrails.mjs`
    - `src/apps/qqbot_channel/smoke_runner.mjs`
    - `src/apps/qqbot_channel/.env.example`
  - active validations:
    - `npm run check --prefix src/apps/qqbot_channel`
    - `npm run smoke --prefix src/apps/qqbot_channel`
    - `python scripts/test_stable.py`

## 3. P2 Execution Index

### P2.1 Critical structural fixes
- [x] Restore canonical session implementation
  - `mini_agent/session/store.py`
- [x] Unify session import path to one source of truth
  - canonical module: `mini_agent.session`
- [x] Fix gateway tool initialization duplication
  - `gateway/routers/chat.py`
- [x] Remove compatibility shims after refactor
  - deleted `gateway/core/session.py`
  - ACP now uses only `run_agent` + snake_case protocol methods

### P2.2 Test and baseline completion
- [x] Add stable test command script
  - `scripts/test_stable.py`
- [x] Add gateway router/session tests
  - `tests/test_gateway_routers.py`
- [x] Add MCP example config compatibility validation
  - `tests/test_mcp.py`

## 4. P3 Execution Index

### P3.1 Session persistence kernel
- [x] Add persistence backend package
  - `mini_agent/session/persistence.py`
  - `mini_agent/session/__init__.py`
- [x] Expand canonical session store APIs
  - resume/list/delete/reset/history/checkpoint
  - `mini_agent/session/store.py`
- [x] Add retention and cleanup support
  - `POST /api/sessions/cleanup`
  - `gateway/routers/sessions.py`
- [x] Add in-memory to new storage migration path
  - `SessionStore.set_storage_dir(..., migrate_existing=True)`

## 5. P4 Execution Index

### P4.1 ACP and Gateway control-plane hardening
- [x] Introduce ACP explicit session state machine
  - `mini_agent/acp/__init__.py`
  - states: `new/running/cancelled/closed/expired`
- [x] Add gateway single-instance lock and conflict error path
  - `gateway/security/instance_lock.py`
  - `gateway/core/app.py`
- [x] Add token auth mode for non-local access
  - `gateway/security/auth.py`
  - `gateway/core/app.py`, `src/apps/agent_studio_gateway/main.py`
- [x] Add conversation-to-session binding model
  - `mini_agent/session/binding.py`
  - `gateway/routers/chat.py`

## 6. P5 Execution Index

### P5.1 MCP modularization and config safety
- [x] Split MCP loader implementation modules
  - `mini_agent/tools/mcp/discovery.py`
  - `mini_agent/tools/mcp/registry.py`
  - `mini_agent/tools/mcp/executor.py`
  - `mini_agent/tools/mcp/lifecycle.py`
- [x] Add server-level policy gate and timeout wiring
  - `allow/exclude/trust/enable_resources`
  - `mini_agent/tools/mcp/types.py`
- [x] Add resource discovery/read entry tools
  - `<server>_list_resources`
  - `<server>_read_resource`
- [x] Add MCP profile sync and atomic write helpers
  - `mini_agent/tools/mcp_profile_sync.py`
- [x] Keep public loader entry stable via facade
  - `mini_agent/tools/mcp_loader.py`

## 7. Next Work Queue
1. Keep execution anchored on the four-entrance model:
   - `CLI / TUI / DesktopUI / Remote Interaction`
   - browser `WebUI / OpenWebUI` must not be revived
2. Continue runtime validation from maintained gates only:
   - `studio_ops_smoke`
   - terminal readiness / shared-session walkthroughs
   - stable tests

## 8. P6 Execution Index

### P6.1 Runtime safety and policy layer
- [x] Add three-layer runtime policy model
  - `mini_agent/security/policy.py`
  - layers: sandbox/tool/elevated
- [x] Add runtime execution/access modes (`plan` / `build`, `default` / `full-access`)
  - config: `src/mini_agent/config.py` + `src/mini_agent/config/config*.yaml`
  - runtime wiring: `mini_agent/runtime/tooling.py`, `mini_agent/tools/bash_tool.py`
  - CLI wiring: `mini_agent/cli.py`, `mini_agent/cli_interactive.py`
- [x] Add security audit command and risk report
  - command: `mini-agent security-audit`
  - implementation: `mini_agent/security/audit.py`
  - tests: `tests/test_security_audit.py`, `tests/test_security_policy.py`

## 9. P7 Execution Index

### P7.1 Plugin and memory evolution
- [x] Add plugin capability registry boundaries
  - `mini_agent/plugins/registry.py`
  - domains: `provider/channel/tool/hook`
  - tests: `tests/test_plugin_registry.py`
- [x] Move note memory to markdown split model
  - `mini_agent/tools/note_tool.py`
  - storage: `MEMORY.md` + `memory/YYYY-MM-DD.md`
  - runtime wiring: `mini_agent/runtime/tooling.py`
- [x] Add hybrid memory retrieval
  - keyword ranking by default
  - optional embedding ranking via pluggable embedding provider
  - tests: `tests/test_note_tool.py`, `tests/test_session_integration.py`, `tests/test_integration.py`

## 10. Verification Commands
```bash
uv run pytest tests/test_interaction_surface.py tests/test_agent_studio_gateway_api_v1.py tests/test_agent_studio_gateway_ops_router.py tests/test_p19_runtime_matrix.py -q
uv run pytest tests/test_agent_core_execution_loop.py tests/test_agent_core_execution_permissions.py tests/test_agent_core_execution_sandbox.py tests/test_agent_core_execution_tools.py -q
uv run pytest tests/test_memory_automation.py tests/test_session_integration.py tests/test_memoria_runtime.py -q
uv run pytest tests/test_release_promotion_checklist.py tests/test_p19_rollout_reporting.py -q
uv run python scripts/ci/studio_ops_smoke.py --base-url http://127.0.0.1:8008 --token <ops-token> --expect-auth
uv run python scripts/terminal_readiness_gate.py
npm run check --prefix src/apps/qqbot_channel
```

## 11. P8 Execution Index

### P8.1 Observability and operations
- [x] Add structured run events and replayable logs
  - `mini_agent/logger.py` (`*.events.jsonl` journal + replay formatter)
  - `mini_agent/agent_core/engine.py` (step/tool/run lifecycle event emission)
  - command: `mini-agent replay-log --file <events.jsonl>`
- [x] Add `doctor` diagnostics command
  - implementation: `mini_agent/ops/doctor.py`
  - CLI wiring: `mini_agent/cli.py`
  - tests: `tests/test_doctor.py`
- [x] Add startup self-check gates
  - gateway startup gate: `mini_agent/cli.py`
  - CLI startup gate: `mini_agent/cli_interactive.py`
  - coverage: `tests/test_doctor.py`

## 12. P9 Execution Index

### P9.1 Run-event retention and rotation
- [x] Add retention policy configuration
  - `src/mini_agent/config.py`
  - `src/mini_agent/config/config.yaml`, `src/mini_agent/config/config-example.yaml`
  - keys: `observability.log_dir`, `event_log_*`
- [x] Add run-log pruning implementation and command
  - `mini_agent/logger.py` (`EventLogRetentionPolicy`, `prune_logs`)
  - `mini_agent/cli.py` (`mini-agent prune-logs`)
- [x] Wire logger retention across runtime entry points
  - `mini_agent/cli_interactive.py`
  - `gateway/routers/chat.py`
  - `mini_agent/acp/__init__.py`
- [x] Add retention test coverage
  - `tests/test_logger_retention.py`

### P9.2 Gateway observability API surfaces
- [x] Add observability router and endpoint set
  - `gateway/routers/observability.py`
  - health/run listing/event page/replay API endpoints
- [x] Wire observability router into gateway app
  - `gateway/routers/__init__.py`
  - `gateway/core/app.py`
- [x] Add gateway router test coverage for observability endpoints
  - `tests/test_gateway_routers.py`

### P9.3 Doctor deep MCP probe and remediation
- [x] Add optional deep MCP handshake probe path
  - flag: `mini-agent doctor --mcp-handshake`
  - implementation: `mini_agent/ops/doctor.py`
  - runtime probe signal: `mini_agent/tools/mcp/registry.py` (`last_error`)
- [x] Add actionable remediation hints in doctor report output
  - formatter includes `Hint:` lines for warn/fail findings
  - CLI wiring: `mini_agent/cli.py`
- [x] Add test coverage for deep-probe/hint behavior
  - `tests/test_doctor.py`

### P9.4 Export interfaces and endpoint guardrails
- [x] Add run-event export endpoint for analysis pipelines
  - `GET /api/observability/runs/{run_id}/export`
  - formats: `jsonl`, `json`, `csv`
  - implementation: `gateway/routers/observability.py`
- [x] Add observability auth/rate-limit guardrails
  - implementation: `gateway/security/observability.py`
  - envs: `MINI_AGENT_OBSERVABILITY_TOKEN`, `MINI_AGENT_OBSERVABILITY_AUTH_STRICT`
  - envs: `MINI_AGENT_OBSERVABILITY_RATE_LIMIT_PER_MIN`, `MINI_AGENT_OBSERVABILITY_RATE_LIMIT_WINDOW_SECONDS`
- [x] Add filtering enhancements for large event archives
  - runs: `run_id_prefix`, `updated_after`
  - events/replay/export: `event_type`, `level`, `contains`
  - implementation: `gateway/routers/observability.py`
- [x] Add test coverage for export + guardrail paths
  - `tests/test_gateway_routers.py`
  - `tests/test_gateway_security.py`

## 13. P10 Execution Index

### P10.1 Event schema versioning and compatibility checks
- [x] Add schema version to event journal records
  - `mini_agent/logger.py` (`schema_version`)
- [x] Add compatibility check helpers for downstream consumers
  - `mini_agent/logger.py` (`check_event_schema_compatibility`)
- [x] Add compatibility gates in CLI and gateway observability APIs
  - CLI: `mini_agent/cli.py` (`replay-log --expected-schema-version`)
  - Gateway: `gateway/routers/observability.py` (`expected_schema_version`)
- [x] Add schema compatibility coverage
  - `tests/test_event_schema.py`
  - `tests/test_logger_events.py`
  - `tests/test_gateway_routers.py`

### P10.2 Async export jobs and large-archive delivery
- [x] Add async export-job endpoint set
  - `POST /api/observability/exports`
  - `GET /api/observability/exports/{job_id}`
  - `GET /api/observability/exports/{job_id}/download`
  - implementation: `gateway/routers/observability.py`
- [x] Add chunked delivery path for large sync exports (`jsonl`/`csv`)
  - implementation: `gateway/routers/observability.py`
- [x] Add export job lifecycle coverage
  - tests: `tests/test_gateway_routers.py`

### P10.3 Observability auth policy convergence
- [x] Integrate observability guard with gateway token state
  - gateway state wiring: `gateway/core/app.py`
  - observability policy resolver: `gateway/security/observability.py`
- [x] Add profile-driven auth mode for observability endpoints
  - env: `MINI_AGENT_OBSERVABILITY_AUTH_PROFILE`
  - values: `inherit_gateway` / `observability_only` / `gateway_only`
- [x] Add security coverage for inheritance/profile behavior
  - tests: `tests/test_gateway_security.py`

### P10.4 Legacy schema migration tooling
- [x] Add event-log migration helpers in logger layer
  - `AgentLogger.list_event_log_files(...)`
  - `AgentLogger.migrate_event_schema_file(...)`
  - implementation: `mini_agent/logger.py`
- [x] Add CLI migration command
  - `mini-agent migrate-event-logs`
  - flags: `--path`, `--dry-run`, `--no-backup`, `--target-schema-version`, `--no-recursive`
  - implementation: `mini_agent/cli.py`
- [x] Add migration test coverage
  - tests: `tests/test_event_schema.py`

### P10.5 Export durability across restarts
- [x] Add filesystem-backed export job metadata
  - metadata dir: `<log_dir>/exports/jobs`
  - implementation: `gateway/routers/observability.py`
- [x] Add lazy reload of persisted jobs in status/download APIs
  - `GET /api/observability/exports/{job_id}`
  - `GET /api/observability/exports/{job_id}/download`
- [x] Define restart behavior for in-flight jobs
  - persisted `queued/running` jobs are marked `failed` after reload
- [x] Add persistence recovery test coverage
  - tests: `tests/test_gateway_routers.py`

### P10.6 Export control-plane cancel API
- [x] Add explicit export job cancel endpoint
  - `POST /api/observability/exports/{job_id}/cancel`
  - implementation: `gateway/routers/observability.py`
- [x] Add deterministic cancel transitions
  - queued jobs cancel immediately to `cancelled`
  - running jobs set `cancel_requested` and terminate to `cancelled`
- [x] Add cancel behavior coverage
  - tests: `tests/test_gateway_routers.py`

### P10.7 Export metrics history
- [x] Add queue/runtime aggregate metrics endpoint
  - `GET /api/observability/exports/metrics`
  - dimensions include queue depth/failure ratio/avg duration
- [x] Add time-bucketed metrics history endpoint
  - `GET /api/observability/exports/metrics/history`
  - implementation: `gateway/routers/observability.py`
- [x] Add metrics endpoint test coverage
  - tests: `tests/test_gateway_routers.py`

### P10.8 Throughput controls and restart replay
- [x] Add export queue concurrency and backpressure controls
  - envs: `MINI_AGENT_OBSERVABILITY_EXPORT_MAX_CONCURRENCY`, `MINI_AGENT_OBSERVABILITY_EXPORT_MAX_QUEUE`
  - behavior: bounded running workers + queue full `429`
- [x] Add restart replay mode for persisted queued jobs
  - env: `MINI_AGENT_OBSERVABILITY_EXPORT_REPLAY_ON_RESTART`
  - behavior: replay queued/running persisted jobs as queued when enabled
- [x] Add throughput/restart replay coverage
  - tests: `tests/test_gateway_routers.py`

### P10.9 Export metadata compaction and checksum
- [x] Add compact export metadata persistence format
  - compact JSON write (`sort_keys` + no indentation)
  - implementation: `gateway/routers/observability.py`
- [x] Add snapshot index with checksum map
  - file: `<log_dir>/exports/jobs/snapshot.json`
  - fields include per-job `checksum_sha256`
- [x] Add snapshot-first restore with integrity gate
  - checksum mismatch blocks loading tampered metadata
- [x] Add checksum and tamper coverage
  - tests: `tests/test_gateway_routers.py`

## 14. P11 Execution Index

### P11.1 Agent execution policy and tool budget kickoff
- [x] Add explicit execution policy model in Agent runtime
  - `mini_agent/agent_core/engine.py`
  - models: `AgentExecutionPolicy`, `StepExecutionState`
- [x] Add per-step tool-call budget with truncation telemetry
  - policy knob: `max_tool_calls_per_step`
  - events: `step.tool_calls_truncated`, `step.completed`
  - implementation: `mini_agent/agent_core/engine.py`
- [x] Wire policy config through runtime entry points
  - config schema + YAML: `src/mini_agent/config.py`, `src/mini_agent/config/config.yaml`, `src/mini_agent/config/config-example.yaml`
  - runtime wiring: `mini_agent/cli_interactive.py`, `gateway/routers/chat.py`, `mini_agent/acp/__init__.py`
- [x] Add deterministic unit coverage for budget behavior
  - tests: `tests/test_agent_core_execution_policy.py`
  - includes Agent loop and ACP turn path

### P11.2 Agent run-loop planner/executor split
- [x] Split `Agent.run` into planner/executor/state transition phases
  - planner: `_plan_step(...)`
  - executor: `_execute_tool_calls(...)`
  - transition contract: `StepPlan`, `StepOutcome`, `StepTransition`
  - implementation: `mini_agent/agent_core/engine.py`
- [x] Normalize step timing finalization through one path
  - helper: `_finalize_step_timing(...)`
  - implementation: `mini_agent/agent_core/engine.py`
- [x] Add transition-level test coverage
  - planner failure transition
  - executor complete transition
  - tests: `tests/test_agent_core_execution_policy.py`

### P11.3 Step failure envelope and metrics wiring
- [x] Add structured step failure envelope
  - model: `StepFailureEnvelope` (`error_type`, `recoverable`, `retryable`)
  - event: `step.failed`
  - implementation: `mini_agent/agent_core/engine.py`
- [x] Add run-level metrics aggregation payload
  - model: `RunExecutionMetrics`
  - terminal events include `metrics` payload (`run.completed` / `run.failed` / `run.cancelled` / `run.max_steps`)
  - implementation: `mini_agent/agent_core/engine.py`
- [x] Add failure envelope + metrics coverage
  - tests: `tests/test_agent_core_execution_policy.py`

### P11.4 Policy surfaces in inspection APIs
- [x] Expose run policy in session inspection endpoints
  - `/api/sessions` includes `max_steps`, `max_tool_calls_per_step`
  - `/api/sessions/{session_id}/history` includes `max_steps`, `max_tool_calls_per_step`
  - implementation: `mini_agent/session/store.py`, `mini_agent/session/persistence.py`, `gateway/routers/sessions.py`
- [x] Expose run policy in chat response surfaces
  - `POST /api/chat` response includes policy fields
  - `GET /api/chat/stream` done event includes policy fields
  - implementation: `gateway/routers/chat.py`
- [x] Add policy-surface coverage
  - tests: `tests/test_gateway_routers.py`, `tests/test_session_store_persistence.py`

### P11.5 Shared planner/executor facade for ACP/Gateway parity
- [x] Extract shared planner/executor run-loop facade in Agent runtime
  - shared loop: `_run_planner_executor_loop(...)`
  - facade entry: `run_turn(...)`
  - contracts: `PlannerExecutorHooks`, `TurnExecutionResult`, `TurnStopReason`
  - implementation: `mini_agent/agent_core/engine.py`
- [x] Migrate ACP turn execution to shared facade (remove duplicated run loop)
  - ACP callbacks wired via `on_step_plan`, `on_tool_call_start`, `on_tool_call_result`
  - ACP session agent now runs with `console_output=False` to avoid stdio noise
  - implementation: `mini_agent/acp/__init__.py`
- [x] Add facade behavior coverage
  - hook + stop reason tests: `tests/test_agent_core_execution_policy.py`
  - ACP integration coverage remains passing: `tests/test_acp.py`

### P11.6 Step-failure trend aggregation endpoint
- [x] Add dashboard-facing step-failure trend endpoint
  - endpoint: `GET /api/observability/failures/step-trends`
  - params: `bucket_minutes`, `limit`, `top_error_types`, `run_id_prefix`, `since_utc`
  - aggregation dimensions: `total/planner/executor/recoverable/retryable/unique_runs`
  - top breakdown: `top_error_types`
  - implementation: `gateway/routers/observability.py`
- [x] Add router coverage for trend endpoint and invalid `since_utc` guard
  - tests: `tests/test_gateway_routers.py`

### P11.7 Policy-drift detector in session diagnostics
- [x] Add configured-vs-runtime policy drift detector in session core
  - diagnostics fields: `configured_max_steps`, `configured_max_tool_calls_per_step`, `policy_drift`, `policy_drift_fields`
  - implementation: `mini_agent/session/store.py`
- [x] Persist configured policy snapshot for inactive-session diagnostics
  - metadata key: `configured_execution_policy`
  - implementation: `mini_agent/session/persistence.py`
- [x] Add store-level drift diagnostics coverage
  - tests: `tests/test_session_store_persistence.py`

### P11.8 Policy-drift fields exposed in session inspection APIs
- [x] Extend session summary/history models with drift diagnostics flags
  - `/api/sessions`
  - `/api/sessions/{session_id}/history`
  - implementation: `gateway/routers/sessions.py`
- [x] Add gateway router drift diagnostics coverage
  - tests: `tests/test_gateway_routers.py`

### P11.9 Step-failure trend phase/error_type filters
- [x] Add targeted trend filters for SRE dashboards
  - endpoint: `GET /api/observability/failures/step-trends`
  - new query params: `phase`, `error_type`
  - `error_type` filter is case-insensitive
  - implementation: `gateway/routers/observability.py`
- [x] Add router coverage for phase/error_type filtering behavior
  - tests: `tests/test_gateway_routers.py`

### P11.10 Policy-drift fields exposed in chat response surfaces
- [x] Extend `POST /api/chat` response with drift diagnostics fields
  - `configured_max_steps`, `configured_max_tool_calls_per_step`, `policy_drift`, `policy_drift_fields`
  - implementation: `gateway/routers/chat.py`
- [x] Extend `GET /api/chat/stream` done payload with drift diagnostics fields
  - dry-run emits null/false defaults for drift fields
  - implementation: `gateway/routers/chat.py`
- [x] Add gateway router coverage for chat drift diagnostics fields
  - tests: `tests/test_gateway_routers.py`

### P11.11 Drift-focused counters in observability health diagnostics
- [x] Extend observability health response with drift counters
  - endpoint: `GET /api/observability/health`
  - fields: `policy_drift_active_sessions`, `policy_drift_sessions`, `policy_drift_ratio`
  - implementation: `gateway/routers/observability.py`
- [x] Add health counter coverage for drift-session scenarios
  - tests: `tests/test_gateway_routers.py`

### P11.12 Session listing filter for policy drift
- [x] Add `policy_drift` filtering to session listing API
  - endpoint: `GET /api/sessions`
  - query param: `policy_drift` (`true`/`false`)
  - implementation: `gateway/routers/sessions.py`
- [x] Add gateway router coverage for drift filter behavior
  - tests: `tests/test_gateway_routers.py`

### P11.13 Drift triage summary surfaces and trend context
- [x] Add drift summary fields to run/session listings for faster triage
  - run listing fields: `policy_drift_active_sessions`, `policy_drift_sessions`, `policy_drift_ratio`
  - session listing fields: `policy_drift_field_count`, `policy_drift_summary`
  - implementation: `gateway/routers/observability.py`, `gateway/routers/sessions.py`
- [x] Add trend response context counters for dashboard filtering visibility
  - endpoint: `GET /api/observability/failures/step-trends`
  - fields: `matched_failures`, `filtered_out_failures`
  - implementation: `gateway/routers/observability.py`
- [x] Add health diagnostics drilldown field for top drifted sessions
  - endpoint: `GET /api/observability/health`
  - field: `top_policy_drift_session_ids`
  - implementation: `gateway/routers/observability.py`
- [x] Add gateway router coverage for P11.13 fields
  - tests: `tests/test_gateway_routers.py`
