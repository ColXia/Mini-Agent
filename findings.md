# Findings

## 2026-04-12 P29.3e Local Skill Command Convergence

- `skill` was the last large local operator command family still duplicated in both TUI and CLI.
- The important boundary split in this slice is:
  - shared service owns local `skill` execution semantics
  - surfaces still own runtime reload orchestration and final operator timing
- That split matters because `skill` is not just formatting:
  - it reads catalog state
  - mutates workspace policy
  - installs/uninstalls/rolls back workspace assets
  - and may require hot runtime rebuilds that are surface-context dependent
- The TUI integration confirmed the seam is now strong enough for real stateful command families:
  - the old local `/skill` branch in `app.py` could be collapsed to one service call plus one surface-side result applicator
  - that is the clearest signal so far that P29.3 is reducing duplication structurally, not cosmetically
- A practical implementation lesson from this cut:
  - on Windows, very large one-shot file replacements can hit command-length limits before the code is even touched
  - using bounded marker-based replacement for large surface handlers is safer than trying to patch an entire huge branch in one command
- After this cut, the local command-convergence backlog is materially smaller:
  - shared locally now:
    - `skill`
    - `memory`
    - `context`
    - `kb`
    - `mcp`
    - `sandbox`
  - still surface-owned:
    - parts of `model`
    - remote/shared-session transport branches

## 2026-04-12 P29.3d Local Memory Command Convergence

- `memory` was the first genuinely heavyweight command family in the local command-convergence track:
  - it mixes read-only diagnostics
  - runtime selector resolution
  - workspace-durable mutations
  - runtime-memory mutations
- That made it a useful structural checkpoint:
  - if the shared execution seam could not carry `memory`, it would likely stop being useful for the remaining command backlog
- The most important refinement from this slice is that local command convergence does not have to start from the full surface handler:
  - the right first cut was to centralize the actual local execution semantics
  - keep remote/shared-session transport untouched
  - let TUI and CLI continue rendering the returned result in their own style
- This slice also exposed one practical lesson about technical debt in a large dirty tree:
  - focused architecture work can still surface unrelated latent failures
  - here the regression run uncovered a corrupted CLI banner string that broke module import before memory tests could even execute
  - fixing that immediately was the right move because a broken import path invalidates the readiness signal from the rest of the suite
- After this cut, the command-convergence backlog is much clearer:
  - shared locally now:
    - `memory`
    - `context`
    - `kb`
    - `mcp`
    - `sandbox`
  - still surface-owned:
    - `skill`
    - parts of `model`
    - remote/shared-session command transport

## 2026-04-12 P29.3c Local Context Command Convergence

- `context` is where the shared command execution seam first had to prove it could handle real local state mutation, not only status-style commands.
- The extraction was still worth doing before `memory` because `context` has a cleaner mutation model:
  - source inclusion/exclusion
  - budget normalization
  - reset to empty local policy
  - read-only rendering of prepared-context state
- The key lesson from this slice is that rendered defaults and stored state are not always the same thing:
  - operators expect `context reset` to clear stored local policy state
  - but they still benefit from seeing normalized default policy details in the UI
  - the shared service therefore must carry both concepts explicitly instead of conflating them
- This slice also clarified the next migration order:
  - now shared locally:
    - `kb`
    - `mcp`
    - `sandbox`
    - `context`
  - the next large command family is `memory`
  - `memory` should be treated as its own mini-phase because it has richer payloads and more varied operator-detail rendering than the earlier command families

## 2026-04-12 P29.3b Local KB Command Convergence

- After `mcp/sandbox`, `kb` was the right next command family because it sits in the middle:
  - not as trivial as read-only status output
  - not as entangled as `context` or `memory`
  - still duplicated across TUI and CLI
- The important boundary lesson here is that "shared execution" does not require identical final prose:
  - CLI still benefits from a short terminal-oriented KB status line
  - TUI still benefits from session-oriented feedback text
  - but validation, busy checks, action normalization, and toggle success semantics now come from one shared service
- This is a useful refinement of the P29.3 target:
  - command semantics should be shared
  - surface rendering can still differ when it genuinely serves the surface
  - the mistake would be re-embedding decision logic in each renderer
- With `kb` moved, the command backlog is now more clearly stratified:
  - already shared locally:
    - `kb`
    - `mcp`
    - `sandbox`
  - still surface-owned and more stateful:
    - `context`
    - `memory`
    - `skill`
    - parts of `model`
- That means the next extraction should stay selective:
  - `context` is likely the best next target
  - `memory` should probably come after `context`, because it has much richer payload and operator-detail shaping

## 2026-04-12 P29.3a Local Operator Command Service First Cut

- The next drift after session-boundary repair was command execution, not command syntax:
  - catalog/help/parsing were already shared
  - but local operator behavior still lived separately in TUI and CLI
- The safest first extraction was intentionally narrower than "all commands":
  - `mcp` and `sandbox` are cross-surface, high-value, and comparatively low-coupling
  - they provide a real command-execution seam without dragging session execution flow into the same cut
- The resulting boundary improvement is real even though only one command family moved:
  - TUI and CLI local `mcp` behavior now comes from one shared execution service
  - TUI and CLI local `sandbox status` behavior now comes from one shared execution service
  - surfaces now mainly render returned results instead of each re-deciding validation and summary/details shaping
- One useful parity detail surfaced during migration:
  - `mcp reload` in CLI implicitly depended on a pre-reload and post-reload snapshot cadence
  - the first shared-service version collapsed that to one post-reload probe
  - keeping the earlier cadence inside the shared service was the correct fix because the behavior belonged to command semantics, not to the CLI surface
- The next P29.3 step is now easier to choose:
  - the seam exists and is exercised
  - the next worthwhile candidates are the more stateful command families:
    - `kb`
    - then `context`
    - then `memory`
  - but they should be migrated in slices, not as one giant command rewrite

## 2026-04-12 P29.2b TUI Remote Session Service Convergence

- The next real session-boundary leak after P29.2a was not in gateway anymore; it was in TUI:
  - TUI still called raw `gateway_client` mutation/control endpoints directly
  - that meant transport-shape assumptions still lived in the surface layer even after gateway-side service extraction
- The clean repair was a client-side application seam, not more helpers inside `app.py`:
  - `RemoteSessionService` now provides typed list/detail/mutation/control methods over the gateway client
  - TUI remote session flows now consume DTOs instead of assuming raw dict payloads
- This matters structurally even though behavior is unchanged:
  - remote session mutation semantics are no longer embedded in TUI transport call sites
  - response-shape drift can now be tested once at the client-service seam
  - the TUI surface is closer to an adapter and less of a second application layer
- One implementation regression surfaced during the cut and confirmed the value of the seam:
  - remote `compact` still read `response.get("applied")` after the control path switched to a typed DTO
  - focused TUI regression caught it immediately
  - the fix was to finish the DTO transition instead of keeping mixed dict/model handling
- The next natural step is now clearer:
  - session read truth is shared
  - gateway mutation ownership is shared
  - TUI remote mutation ownership is shared
  - the next remaining large drift surface is command execution semantics across TUI/CLI/QQ, not another session transport patch

## 2026-04-12 P29 Session Boundary Audit

- The latest session bug was not a one-off implementation mistake; it exposed a structural ownership problem:
  - session state is currently split across TUI, runtime manager, legacy core session store, channel-side session stores, and an orphaned conversation-binding store
  - there is no single canonical session aggregate
- The most important boundary failure is in the terminal surfaces:
  - TUI is simultaneously a view layer, a session projection, a local runtime host, and a gateway client
  - it decides local-vs-gateway execution by inspecting attached runtime handles instead of talking to one application service
- The runtime center is also overloaded:
  - `MainAgentRuntimeManager` owns session persistence, lifecycle, transcript state, recovery, model selection, approvals, memory, skills, MCP, DTO assembly, and snapshot import/export
  - it also imports presentation-formatting helpers, so domain/runtime and response rendering are coupled
- The command system is only partially unified:
  - catalog + parsing are shared
  - execution semantics still live separately in TUI, CLI, and QQ
  - this is why command behavior is still vulnerable to per-surface drift
- The tree also still contains parallel and stale abstractions that blur the active architecture:
  - legacy `mini_agent/core/session.py`
  - orphaned `mini_agent/session/binding.py`
  - parallel QQ/channel implementations (`apps/qqbot_channel` vs `channels/qqbot`)
  - older Python-side channel abstractions under `src/gateway/channels/base.py`
- The immediate conclusion is clear:
  - more session-facing features should not be added on top of the current structure
  - the next step should be a boundary-first hard refactor centered on canonical session ownership and shared command execution

## 2026-04-12 P29 Hard-Refactor Planning

- The audit has now been translated into a concrete hard-refactor plan:
  - target boundary model
  - phase ordering
  - first implementation slice
  - acceptance bundle
- The chosen first cut is intentionally conservative:
  - build a shared session projection seam first
  - do not start by deleting modules or changing behavior blindly
  - make session truth explicit before centralizing more behavior
- The current recommended order is:
  - shared session projection
  - session application service
  - shared command execution service
  - terminal runtime-host split
  - runtime-manager decomposition
  - channel-path consolidation
  - persistence/DTO hardening

## 2026-04-12 P29.1a Shared Session Projection Seam

- The first implementation cut is now landed, not only planned:
  - a shared session projection seam exists under `src/mini_agent/session/projection.py`
  - runtime DTO read-model assembly now flows through that seam
  - TUI session display/read semantics now flow through that seam as well
- The boundary benefit is immediate:
  - runtime summary/detail logic no longer duplicates DTO field assembly separately from the emerging session read model
  - TUI no longer derives its main session-display semantics purely from ad hoc field inspection
  - transport and terminal projections are now explicit, named boundaries instead of implicit object-shape coupling
- One real implementation mistake surfaced and was fixed inside the slice:
  - persisted-record recovery briefly mixed projection objects back into raw recovery computation
  - this dropped pending approvals from restarted shared-session recovery payloads
  - the fix confirms why the seam matters: projection and raw-domain inputs must stay separate until mapping time
- The next P29 cut can now move with less risk:
  - extract a shared session application service
  - stop gateway/TUI from touching runtime/session internals directly

## 2026-04-12 P29.2a Session Application Service Extraction

- The next boundary cut is also now landed:
  - `src/mini_agent/application/session_service.py` exists as a real shared application seam
  - it owns session CRUD/detail/control wrappers plus a managed chat-turn lease
- The most important repair in this slice is ownership, not line movement:
  - gateway use cases no longer import `MainAgentSessionState`
  - gateway use cases no longer lock `session.lock` directly
  - turn scaffolding now belongs to the shared service:
    - lock
    - bind surface
    - apply pending selections
    - mark start/finish
    - record initial user message
- This reduces a specific class of drift:
  - `run_chat` and `stream_chat_events` no longer maintain their own parallel lock/lifecycle choreography
  - approval/activity/delegation logic still lives in gateway for now, but it now runs inside a shared session execution boundary instead of owning that boundary
- The next clean boundary target is clearer now:
  - move more command/session operation semantics out of gateway/TUI into shared services
  - continue shrinking `MainAgentGatewayUseCases` toward routing/orchestration only

## 2026-04-11 Stage Transition: Sandbox Deferred, Demo Baseline Active

- The latest sandbox work closed the practical gap for the current project stage:
  - Windows single-host local use now has a real restricted-token launch path
  - low integrity, admin-group disabling, UI restrictions, process count caps, and memory caps are all in place
  - TUI / CLI / gateway can all report the effective sandbox state
- That means the remaining sandbox ideas are enhancements, not current blockers:
  - CPU quota / runtime timeout at the job-object level
  - non-Windows native sandbox backend parity
- The right next move is therefore not "keep hardening sandbox forever":
  - return to the top-level demo-baseline goal
  - use readiness scripts and operator acceptance checks to decide the next implementation slice
  - only reopen sandbox work if a real demo/use failure points back to it

## 2026-04-11 P24 Demo Acceptance Audit

- The next meaningful demo audit did not expose a broad product failure; it exposed one narrow readiness-contract bug:
  - `scripts/tui_interaction_walkthrough.py` waited only for an assistant message entry to appear
  - but TUI assistant replies are streamed through an initial placeholder message
  - that made the walkthrough race against streaming completion and fail with `assistant echo mismatch`
- The correct fix was in the walkthrough contract, not the runtime:
  - wait for the final assistant content
  - and ensure `streaming=false` before asserting the multiline echo result
- After that fix, the acceptance picture became much clearer:
  - command catalog / unified entry preflight is green
  - scripted TUI / shared-session / channel-ingress readiness is green
  - targeted readiness regression is green
  - real headless model invocation is green
- That means the main local/runtime demo path is not the current weak point.
- The most valuable remaining unknown is now external rather than local:
  - a live QQ-origin task / takeover / continue roundtrip on the real bot path still needs explicit acceptance

## 2026-04-11 Real Runtime Stack vs Gateway Test Isolation

- A real local-demo condition surfaced a test-environment gap that normal idle-worktree runs would miss:
  - if the gateway runtime stack is already running on `127.0.0.1:8008`
  - FastAPI `TestClient(app)` startup for gateway suites fails inside the lifespan instance lock
  - that failure is not a product outage; it is a collision between real process locking and in-process API tests
- The clean fix is to isolate pytest from runtime instance-locking instead of weakening the runtime:
  - tests now default `MINI_AGENT_STUDIO_ENABLE_INSTANCE_LOCK=0` in `tests/conftest.py`
  - runtime stack / CLI startup paths still keep instance locking enabled for real operator use
- This matters for demo work specifically:
  - full regression can now run on the same machine while the live QQ/gateway demo stack is up
  - readiness validation no longer requires tearing down the real stack first

## 2026-04-11 Windows Sandbox Resource Caps And Persistence Recovery

- Sandbox status visibility exposed one real integration risk:
  - the new persistence path saved `sandbox_diagnostics`
  - but `_MainAgentRuntimePersistence.save_session()` called `_build_sandbox_diagnostics_for_session(...)` as if it were a class method
  - persistence exceptions are intentionally swallowed in the runtime write path
  - so the failure mode was silent metadata loss instead of an obvious crash
- The clean fix was to keep persistence self-sufficient:
  - collect diagnostics directly from the live agent when possible
  - fall back to the session-cached diagnostics
  - normalize the payload in place before writing metadata
- After that regression was repaired, the next useful Windows hardening step proved safe:
  - conservative job-object active-process cap
  - conservative per-process memory cap
- The implementation tradeoff is intentional:
  - defaults are strong enough to add a real boundary
  - but still high enough for ordinary coding flows (`32` processes, `2048 MB` per process)
  - both caps remain operator-configurable and can be disabled explicitly
- The important proof here is runtime proof, not just config plumbing:
  - the live Windows job object now reports both `JOB_OBJECT_LIMIT_ACTIVE_PROCESS` and `JOB_OBJECT_LIMIT_PROCESS_MEMORY`
  - restart/session snapshot/gateway persistence remains green after the diagnostics write-path fix

## 2026-04-11 Windows Low-Integrity Restricted Launch Finalization

- The native restricted-launch path was already real, but its integrity boundary still depended on the caller token baseline.
- A small Windows-native validation spike narrowed the correct implementation:
  - explicitly set `TokenIntegrityLevel` to `WinLowLabelSid`
  - do not force-write `TokenMandatoryPolicy` when the current privilege context rejects that operation
- The live host behavior is now clearer:
  - the restricted token already inherits mandatory policy `3`
  - `3` corresponds to `NO_WRITE_UP | NEW_PROCESS_MIN`
  - that value should be surfaced honestly, not syntheticly tightened by a failing write attempt
- The result is a better-defined Windows baseline without over-claiming isolation:
  - restricted token
  - disabled high-privilege groups
  - low integrity
  - job kill-on-close / exception / UI restrictions
- The most important proof for this slice is runtime proof, not just metadata:
  - the Windows-only native-launch regression now opens the child token and verifies the launched process really carries `WinLowLabelSid`

## 2026-04-11 Windows Token / Job Restriction Tightening

- After native launch was real, the next meaningful hardening was not a whole new backend but stronger defaults inside that same backend.
- Two safe tightening points proved practical in the current environment:
  - disable a curated set of high-privilege builtin groups when creating the restricted token
  - add job-object exception/UI restrictions that do not interfere with ordinary hidden CLI execution
- The selected restriction shape is intentionally conservative:
  - builtin admin/power/back-operator style groups are downgraded
  - clipboard, desktop, global-atoms, exit-windows, and system-parameter UI actions are restricted
  - `DIE_ON_UNHANDLED_EXCEPTION` is enabled on the job object
- One thing was explicitly not added:
  - no aggressive child-process-count cap yet, because normal PowerShell-hosted tool usage still needs child processes for common commands
- A small implementation gap surfaced during testing:
  - the backend metadata exposed the new flags
  - but `SandboxManager.select_initial()` did not forward them initially
  - that drift is now fixed so runtime reporting matches the real restriction state again

## 2026-04-11 Windows Native Restricted-Process Launch

- The earlier Windows sandbox backend was only half-real:
  - policy selection chose `windows_restricted_token`
  - command validation and transform ran
  - but child processes still launched through the normal asyncio subprocess path
- A small local pywin32 spike proved the real path was viable in the current environment:
  - `CreateRestrictedToken`
  - `CreateProcessAsUser`
  - `AssignProcessToJobObject`
  - inherited stdio pipes
- That made the clean implementation path much narrower:
  - keep policy/transform as preflight
  - add one native Windows process adapter compatible with the current `BashTool` interface
  - route only the Windows restricted backend through it
- One subtle runtime issue surfaced immediately:
  - the native launcher originally treated `env` as the full environment
  - that dropped baseline values such as `PATH` / `SystemRoot` in direct launcher calls
  - the correct behavior is base-environment + override merge, which is now in place
- The resulting boundary is now more honest:
  - Windows restricted backend no longer means "annotated normal subprocess"
  - it now means the shell child is actually launched under a restricted token and job object
  - it is still a baseline guardrail, not a full AppContainer-grade isolation boundary
- End-to-end validation matters here more than pure unit coverage:
  - direct sandbox launch was verified
  - `BashTool` native branch selection was verified
  - `SandboxManager + BashTool` real execution was verified on Windows

## 2026-04-11 Sandbox Auto-Edit Mutation Tiering

- The previous approval tightening solved the safety mismatch, but it flattened too many operations into one bucket:
  - ordinary workspace code edits
  - durable memory writes
  - skill lifecycle changes
  - shell execution
- `auto-edit` works better as a middle mode when it is tiered instead of uniformly strict:
  - allow ordinary `write_file` / `edit_file`
  - keep long-lived or environment-shaping mutations on approval
- This keeps the trust model cleaner:
  - workspace file changes are bounded by the existing workspace path guardrails
  - durable/system mutations remain explicit operator decisions
  - `full-auto` is still the only mode that fully bypasses approval
- One implementation detail mattered:
  - `tool_exclude` deny rules must stay ahead of the `auto-edit` allow rules
  - otherwise explicit exclusions would silently stop working for `write_file` / `edit_file`

## 2026-04-11 Sandbox Default-Mutation Approval Tightening

- The previous sandbox hardening slice closed the big boundary gaps, but one default-trust mismatch remained:
  - `auto-edit` still auto-allowed `WRITE` and `EDIT`
  - that meant the default profile could mutate workspace state without operator confirmation even after file-boundary hardening
- The clean fix was to tighten the approval baseline instead of adding another special-case layer:
  - keep read-only tools on the existing default-allow path
  - keep `full-auto` as the explicit autonomous mode
  - move `auto-edit` mutations back behind the existing approval loop
- Security-audit wording had also drifted behind reality:
  - `elevated_exec=require_approval` no longer means "approval plumbing missing"
  - it now means elevated shell commands are gated by the live approval flow
- The result is a more coherent runtime trust model:
  - read-only remains low-friction
  - workspace mutation is explicit by default
  - full autonomy still exists, but only under `full-auto`

## 2026-04-11 Sandbox Hardening Re-Audit

- The current sandbox stack is real but baseline-level:
  - shell execution already goes through runtime policy plus sandbox transform
  - TUI/CLI/gateway approval plumbing already exists and is exercised by tests
  - Windows workspace sandbox currently selects a `windows_restricted_token`-style backend
- The main security gaps are not abstract; they are concrete integration seams:
  - file tools accept absolute paths and therefore bypass the intended workspace boundary
  - `elevated_exec=require_approval` currently returns a blocking error string instead of entering the live approval loop
  - network policy primitives exist, but runtime tooling does not currently pass configured policy into `SandboxManager`
- The current runtime split is important:
  - Windows workspace mode selects the Windows sandbox backend
  - non-Windows and unrestricted mode both fall back to passthrough
- The right next slice is therefore hardening, not reinvention:
  - reuse the current approval loop
  - tighten file-tool path resolution
  - plumb network policy from config into the existing sandbox manager
- The hardening slice is now landed:
  - file tools use one canonical workspace-root resolver and reject paths outside the workspace
  - elevated shell commands under `require_approval` now route through the live approval loop instead of failing before approval can happen
  - network policy is now configurable from `SecurityConfig` and reaches the runtime sandbox manager

## 2026-04-10 P26 Reset/Delete Semantics Re-Audit

- The current P26 memory architecture is much closer to the target than the operator behavior suggests:
  - global durable memory is now separated correctly
  - workspace-aware session search is already anchored correctly
  - persisted runtime task memory already exists and is namespaced by `session:<id>`
- The next blocking gap is not another memory feature but semantic consistency:
  - `reset/delete/clear` does not fully clear session-scoped runtime task memory
  - gateway reset uses a weaker `_reset_agent_messages()` than local TUI reset
  - local TUI clear likely leaves enough restored state behind for stale context to reappear later
- This means current operator intent and runtime reality are still mismatched:
  - users think they started from a clean session
  - runtime task memory may still influence later turns through prepared-context retrieval
- The right next slice is therefore cleanup semantics, not more retrieval:
  - add namespace deletion to `WorkspaceMemoriaRuntime`
  - wire it through gateway reset/delete/lifecycle reset
  - align TUI and CLI local clear behavior to the same contract
  - then verify with focused regression instead of jumping to a larger storage refactor
- The slice is now landed and verified:
  - session runtime-memory cleanup is explicit instead of implicit
  - gateway, TUI, and CLI now agree on the core meaning of a session reset
  - `workspace:shared` remains untouched by session reset, preserving the intended workspace/session boundary

## 2026-04-10 P26 Snapshot / Import / Export Runtime-Memory Parity

- The next continuity gap after reset/delete hardening was snapshot-based migration:
  - restart persistence was already correct
  - but share/unshare/import/export still dropped session runtime task memory because only transcript and diagnostics traveled
- The right fix was an explicit payload seam, not overloading diagnostics:
  - diagnostics remain operator-facing summaries
  - `runtime_task_memory_payload` now carries the actual session-scoped `MemoriaEngine` payload for migration
- Import semantics had one subtle but important requirement:
  - the payload must be restored under the effective destination session id chosen by the runtime
  - it cannot stay tied to the original source session id from the snapshot producer
- TUI share had one additional cleanup requirement:
  - once migration succeeds and the session id changes, the old local runtime namespace must be removed
  - otherwise local orphan task memory would accumulate silently
- The parity slice is now landed and verified:
  - gateway export includes session runtime task memory
  - gateway import restores it
  - local share/unshare preserve it
  - diagnostics and payload semantics are now cleanly separated

## 2026-04-10 P26 Workspace-Shared Runtime-Memory Portability

- `workspace:shared` needed a different portability contract from `session:<id>`:
  - it is workspace-owned, not session-owned
  - so session snapshot transport is useful, but session snapshot overwrite would be wrong
- The clean fix was an explicit payload plus merge-safe restore:
  - `workspace_shared_runtime_memory_payload` now carries portable workspace-shared runtime memory
  - restore semantics merge by normalized content instead of replacing the target namespace
- This preserves both sides of the architecture:
  - portability now exists for share/unshare/import/export flows
  - session reset/delete semantics remain unchanged and do not touch `workspace:shared`
- The important safety rule is now explicit:
  - `workspace:shared` can travel with a session snapshot as a carrier
  - but that snapshot is not authoritative over the destination workspace's existing shared runtime state
- The slice is now landed and verified:
  - gateway import/export carries workspace-shared runtime memory explicitly
  - TUI share/unshare carries it too
  - existing target workspace-shared facts survive restore because the restore path is merge-safe

## 2026-04-10 P26 Workspace-Shared Boundary / Promotion Policy

- `workspace:shared` needed to become explicit without becoming automatic:
  - automatic writeback should remain session-scoped
  - workspace-shared promotion should remain operator-driven
- The clean compromise was:
  - annotate session runtime writeback with `workspace_shared_candidate`
  - allow explicit `/memory promote shared <selector>`
  - prefer the distilled candidate text over the raw session-summary envelope during promotion
- This keeps the boundary honest:
  - `session:<id>` is still the default runtime task-memory sink
  - `workspace:shared` is a curated shared runtime layer, not another silent transcript mirror

## 2026-04-10 P26 Workspace-Shared Retrieval Boundary

- After portability and promotion cleanup, retrieval became the next real boundary risk:
  - if `workspace:shared` always participates, it can compete with current-task session memory too often
- The right fix was to make shared retrieval supplemental:
  - query `session:<id>` first
  - include `workspace:shared` when the query itself is workspace/runtime-scoped, or when session hits are sparse
- This makes the runtime-memory hierarchy much clearer in practice:
  - session memory answers “what matters to this active thread?”
  - workspace-shared memory answers “what workspace-level runtime conventions help when session memory is missing or the question is broader?”

## 2026-04-10 Memory Operator Ergonomics

- The first Phase 5 memory command surface was functional but still too operator-hostile for real use:
  - promotions required the raw `engram_id`
  - runtime previews were visible, but they were not index-addressable
  - KB-to-memory confirmation still lacked one explicit manual save path
- The clean follow-up was to keep one shared seam instead of inventing separate local and remote flows:
  - runtime manager resolves selector forms like `latest` and `1`
  - TUI/CLI reuse the same selector semantics locally
  - gateway shared sessions inherit the same behavior through the existing `/api/v1/agent/sessions/{session_id}/memory` route
- The extra real-use convenience slice is worth landing early:
  - `list` is a better operator verb than forcing people to remember that `runtime` also doubles as a selector preview
  - QQ should not be documentation-only here; it can reuse the same gateway seam and stay behaviorally aligned with TUI
- The right manual-confirmation contract is explicit and distilled:
  - `save note` writes workspace durable memory
  - `save profile` writes global durable profile memory
  - raw KB payloads still go through the same durable-memory promotion guardrails and are rejected if they are not distilled
- The KB/manual-save boundary is now clearer in storage too:
  - if the latest prepared context included `knowledge_base`, a manual note save is categorized as `kb_confirmed`
  - otherwise it is treated as a generic `operator_note`

## 2026-04-08

- The repository already contains QQ channel groundwork:
  - `src/apps/qqbot_channel/bot.mjs`
  - `src/channels/qqbot/src/channel.ts`
  - `src/gateway/channels/base.py`
- Existing channel/gateway contracts already model:
  - `channel_type`
  - `conversation_id`
  - `session_id`
  - `reply`
- Existing QQ bridge currently forwards one inbound QQ message to `POST /api/v1/channel/message`, stores `sessionId` per conversation, and immediately replies with gateway output.
- Current QQ flow appears request/response oriented; it does not yet model:
  - TUI takeover
  - source-aware reply suppression after TUI takes over
  - `/continue` recent-context pull
  - live agent activity mirroring into TUI for channel-origin sessions
- Existing terminal session model is TUI-local today; the new feature should reuse runtime/gateway sessions rather than building a second remote-session system.
- The cleanest first landing slice is backend-first:
  - persist remote binding on runtime sessions
  - expose session detail/recent-messages/takeover APIs
  - let QQ `/continue` consume those APIs
  - let TUI adopt the same contract in the next slice
- The backend-first slice has now landed:
  - runtime sessions carry remote binding and active-surface metadata
  - shared transcript snapshots are queryable from gateway APIs
  - QQ Bot can call `/continue` without creating a parallel context path
- The TUI slice has now landed too:
  - TUI polls gateway shared sessions in the background
  - remote QQ sessions appear in Threads with source/peer metadata
  - TUI can take over a remote session and continue on the same shared `session_id`
  - remote prompts are routed through gateway instead of creating a local parallel session

## Design Direction

- Treat QQ and TUI as two surfaces over one shared session.
- TUI becomes the visual operations console for remote-origin sessions.
- Session metadata needs at least:
  - origin surface
  - reply target
  - current active surface / handoff state
  - recent message history fetch for `/continue`

## 2026-04-09

- Current TUI local sessions already persist into `.mini-agent/tui_sessions.json`, but remote/gateway sessions are excluded from that file on purpose.
- Current gateway shared sessions are fully in-memory inside `MainAgentRuntimeManager`; that is the main reason sessions disappear after gateway restart.
- The clean split for this phase is:
  - local TUI session: private, persisted only in local TUI state
  - shared gateway session: discoverable remotely, persisted by gateway runtime
- The clean handoff model is explicit migration, not dual ownership:
  - local TUI session is shared by exporting a snapshot into gateway
  - after share, TUI marks that session as gateway-managed and stops treating the local copy as authoritative
- Reusing `mini_agent.session.persistence.SessionPersistence` is feasible if we:
  - mark gateway-owned records with a runtime-specific discriminator
  - store shared transcript metadata alongside the existing persisted agent-message record
  - filter list/restore operations so unrelated session-store entries do not leak into gateway session APIs
- Existing shared-session APIs already cover list/detail/messages/takeover/reset/delete.
- What is missing for this phase is one new capability:
  - import/upsert a shared session snapshot from TUI so a local session can be promoted into gateway management.
- The implementation landed with this shape:
  - gateway exposes `POST /api/v1/agent/sessions/import`
  - gateway exposes `GET /api/v1/agent/sessions/{session_id}/snapshot`
  - TUI exposes `/session share`
  - gateway shared sessions persist metadata + transcript and can be listed/restored after restart
- `unshare` now works by:
  - exporting the full shared-session snapshot from gateway
  - converting that snapshot into a local TUI session
  - deleting the gateway copy afterward
- Safety rule:
  - only TUI-origin shared sessions can be unshared
  - if another surface currently owns the thread, TUI should take over first
- Persisted shared sessions are restored lazily:
  - list/detail/messages work directly from persistence
  - mutation or chat flows restore the agent state on demand
- To avoid test pollution while still giving the real gateway restart persistence:
  - generic runtime-manager instances default to an isolated temp persistence directory
  - the real gateway wires a fixed store at `~/.mini-agent/state/main_agent_runtime` unless overridden
- `scripts/terminal_readiness_gate.py` passed in normal mode, but the first `--run-live-headless` attempt showed a gate-ordering weakness:
  - `p23_runtime_baseline` was scheduled before the live smoke result became available to the operator
  - in long chains, the benchmark could consume the budget and prevent the real-provider smoke from being observed promptly
- The real headless path itself is healthy:
  - `uv run mini-agent --mode headless --prompt "Reply with exactly: READY" --output-format json --workspace ...`
  - returned `ok=true` and `output=READY`
- The clean fix is to make the gate prioritize user-value first:
  - run `headless_live_smoke` before targeted/full regression and benchmark steps when `--run-live-headless` is enabled
  - add `--skip-baseline` for quick real-use validation
  - reduce the default benchmark run count in live mode from `50` to `20` unless explicitly overridden
- Shared-session `/cancel` previously had a hidden semantic gap:
  - TUI local cancel worked
  - gateway shared sessions had no cancel endpoint
  - `MainAgentGatewayUseCases._run_agent_once(...)` did not pass a session-level `cancel_event` into `agent.run_turn(...)`
  - because chat execution holds `session.lock` for the whole turn, a cancel API cannot rely on taking that lock without risking deadlock-like behavior
- The correct fix shape is:
  - store a per-session `cancel_event` on the runtime session state
  - create it at `mark_turn_started(...)` and clear it at `mark_turn_finished(...)`
  - let the cancel API set that event without waiting on the running turn lock
  - route remote TUI and QQ `/cancel` through the same gateway endpoint

## 2026-04-09 Agent-Core Next Slice

- Current `agent-core` recovery baseline is stronger than it first appears:
  - TUI local sessions already persist interrupted task metadata and can resume pending tasks after restart.
  - shared gateway sessions already persist transcript + metadata and can be restored lazily.
- The next real gap is more specific:
  - recovery is mostly turn-level, not execution-state-level
  - tool progress is rendered as activity lines, but there is not yet one durable, structured “latest tool state” surface that survives interruption cleanly
- Current tool observability is split across:
  - transient loop bus events in `code_agent.agent_loop`
  - transcript activity items in TUI/gateway rendering
  - coarse `running_state` strings on session/task objects
- A good next slice should therefore avoid overbuilding “full checkpoint replay” and instead tighten:
  - structured per-turn tool state snapshots
  - clearer persistence of interrupted work status for resume/review
  - one shared payload shape that CLI/TUI/gateway can all consume consistently

## 2026-04-09 Agent-Core Tool-State / Recovery Validation

- The new structured payload shape is now validated end-to-end across the local agent path:
  - `loop.activity` is the streaming surface for plan/tool/approval progress
  - `loop.turn.completed` is the durable per-turn summary surface
- Two summary fields must stay distinct:
  - `running_state` is the latest overall turn state and may legitimately end at `step N: preparing final response`
  - `last_tool_activity_summary` is the tool-specific summary surface and should not be overwritten by later non-tool progress
- The current preview heuristic is intentionally user-facing rather than schema-exact:
  - for common single-key tool calls like `text`, `command`, `path`, `pattern`, or `url`, the summary prefers a compact readable preview over raw JSON
  - if richer structure is needed later, it should be added as a separate field rather than making the operator summary harder to scan
- TUI restart recovery is now materially more useful without attempting full execution replay:
  - persisted session state includes last running state and pending approval snapshot
  - resumed local turns can inject that recovery context back into the next turn as hidden system guidance
- Focused regression for this slice is green:
  - `tests/test_code_agent_loop.py`
  - `tests/test_cli_submission_loop.py`
  - `tests/test_tui_app.py`

## 2026-04-09 Agent-Core Turn-Context Integration Seam

- The next durable core seam for future integrations is now explicit:
  - `RAG`, `memory`, `skills`, and `MCP` side-context should enter the model through one turn-scoped provider interface
  - providers prepare ephemeral context for the current turn only; they should not directly mutate long-lived conversation history
- This makes a clean separation in the core:
  - persistent transcript remains the source of user/assistant/tool history
  - prepared runtime context is temporary and is removed after the turn completes
- The first concrete provider now exists and proves the seam is real, not abstract:
  - workspace memory retrieval can prepare relevant snippets from markdown memory notes
  - the injected memory context is available to the model during planning, then cleaned up afterward
- The local and remote execution paths now share the same concept:
  - submission-loop turns pass structured `turn_context`
  - gateway direct-turn execution also passes structured `turn_context`
  - `loop.turn.completed` exposes a compact `prepared_context` summary for future TUI/QQ/gateway surfacing
- One implementation hazard was confirmed and fixed:
  - placing the shared turn-context module under `agent_core` introduced an import cycle through `agent_core.__init__`
  - moving it to top-level `mini_agent.turn_context` removed the cycle and kept the seam reusable

## 2026-04-09 Agent-Core Knowledge-Base Turn Context

- The lightweight knowledge-base path is now best treated as another provider on the same turn-context seam, not as a separate agent-core subsystem.
- Reuse was the right choice here:
  - `mini_agent.rag.HybridSearchStore` already provides persistent retrieval
  - `mini_agent.rag.rewrite_query(...)` already covers lightweight follow-up disambiguation
  - a second retriever would only duplicate ranking, storage, and query-rewrite logic
- The provider contract is now clear:
  - if the store file is missing, return no prepared context instead of creating side effects
  - if the store exists and returns hits, inject one ephemeral `TurnContextItem`
  - include compact citation/source information so later TUI/CLI surfaces can expose prepared-context provenance
- Knowledge-base selection should remain per-turn and metadata-driven:
  - `turn_context.metadata["knowledge_base_id"]` is the primary selector
  - default falls back to `default` so local usage stays lightweight
- Store path resolution needed one deliberate compatibility rule:
  - current knowledge-base router semantics are still cwd-relative for `workspace/rag/light_hybrid_store.json`
  - turn-context providers also need to support workspace-relative future usage
  - the practical fix is dual resolution with fallback, not a new path contract
- Focused regression for this slice is green:
  - `tests/test_agent_turn_context.py`
  - `tests/test_code_agent_loop.py`
  - `tests/test_agent_execution_policy.py`
  - `tests/test_main_agent_gateway_use_cases.py`
  - `tests/test_tui_app.py`
  - `tests/test_agent_core_kernel.py`
  - `tests/test_cli_submission_loop.py`

## 2026-04-09 Agent-Core Operator-Facing Prepared Context

- The `prepared_context` payload was already present in `loop.turn.completed`, but until now it was effectively dead data for operators.
- The right fix was to reuse existing operator surfaces instead of inventing another event stream:
  - CLI can print one compact `[context]` block at turn completion
  - TUI can reuse the existing collapsible command-entry rendering for internal runtime notes
- One important UI rule emerged:
  - prepared-context visibility is useful in the main operator view
  - but it should not become the latest visible thread preview, otherwise `Threads` gets noisy and stops representing user/assistant flow
  - hiding the synthetic `/context` transcript entry from thread previews while keeping it in the main chat strikes the right balance
- Status panel semantics now have a clearer role:
  - `Run/task/approve` describe what is happening now
  - `ctx` describes what supporting runtime context was most recently prepared for the session
- This keeps future integrations aligned:
  - memory / knowledge-base / skills / MCP providers can all surface through the same `prepared_context` operator summary path
  - TUI and CLI do not need provider-specific rendering every time a new context source is added

## 2026-04-09 Agent-Core Additional Provider Types

- The next provider slice was best served by reuse, not expansion:
  - richer memory should come from `mini_agent.memory.relevance.ConsolidatedMemoryRelevanceRetriever`
  - skills should come from `mini_agent.agent_core.skills.AgentSkillLoader`
  - MCP capability hints should come from live registered MCP connections rather than a second config-only catalog
- This keeps the seam honest:
  - one turn-context interface
  - one operator-facing `prepared_context` surface
  - no side-channel provider-specific transcript or status plumbing
- The practical provider split is now clearer:
  - `WorkspaceMemoryContextProvider` handles note-level markdown memory snippets
  - `ConsolidatedMemoryTurnContextProvider` handles ranked long-lived consolidated memory facts
  - `KnowledgeBaseTurnContextProvider` handles document/RAG retrieval
  - `SkillCatalogTurnContextProvider` handles task-relevant skill hints
  - `MCPToolCatalogTurnContextProvider` handles currently available MCP capability hints
- One new implementation hazard also showed up:
  - skills discovery path can silently drift if tool bootstrap and turn-context bootstrap resolve builtin skills from different roots
  - the fix was to share builtin-skills resolution in `runtime/tooling.py` instead of letting each caller guess
- The resulting runtime shape is a good foundation for the next stage:

## 2026-04-10 Consolidated-Memory Refresh / Promotion

- The previous consolidation pipeline had a real workspace-boundary flaw:
  - it read from the shared session store but wrote into one workspace `MEMORY.md`
  - without workspace scoping, different repositories could leak into the same consolidated durable memory
- The lowest-cost correct fix was not a second service:
  - keep `MemoryConsolidationPipeline`
  - namespace its scheduler/artifact state per workspace anchor
  - filter phase-1 source sessions by stable workspace anchor before extraction
- The right ownership seam for refresh is `MemoryService`, not the scheduler:
  - `MemoryService.consolidated_refresh_status()` can answer whether the consolidated section is missing or behind workspace session history
  - `MemoryService.refresh_consolidated_memory()` can reuse the existing pipeline instead of inventing another consolidation path
- On-demand refresh from the consolidated-memory turn-context provider is a good lightweight default:
  - it keeps refresh conservative
  - it avoids always-on background work
  - it makes prepared context more likely to reflect recent same-workspace history
- Promotion policy needed one explicit anti-RAG guardrail:
  - raw tool payloads should not be promoted into durable consolidated memory
  - KB-style JSON/source/citation payloads should not be promoted verbatim
  - distilled assistant/user conclusions remain promotable and are the right durable-memory unit

## 2026-04-10 Persisted Runtime Task Memory

- `MemoriaEngine` became viable only after the durable-memory boundaries were corrected:
  - global durable memory already had a real owner
  - workspace durable memory already had a real owner
  - consolidated memory already had refresh/promotion policy
- The clean promotion path was not to replace `MemoryService`:
  - keep `MemoriaEngine` as the runtime task-memory primitive
  - wrap it in a workspace-scoped persisted runtime store
  - feed retrieval back through the existing turn-context seam
- Namespace isolation is mandatory:
  - `session:<session_id>` prevents sibling task contamination inside one repo
  - `workspace:shared` gives one explicit place for promoted workspace-scoped runtime facts
- Minimal viable ingestion is one compact per-turn summary, not full transcript mirroring:
  - it keeps runtime memory bounded
  - it avoids creating a second session-history system
  - it still gives restart continuity and same-session task recall
- Promotion out of runtime task memory should stay explicit:

## 2026-04-10 Operator-Facing Memory Diagnostics

- The clean operator surface was one shared diagnostics payload, not parallel per-surface formatting logic:
  - runtime manager now owns the canonical `memory_diagnostics` snapshot for shared sessions
  - TUI, CLI, and gateway all consume that same shape
- Shared-session memory actions needed a dedicated endpoint instead of overloading context/model controls:
  - `POST /api/v1/agent/sessions/{session_id}/memory`
  - actions: `status`, `show`, `runtime`, `refresh`, `promote_note`, `promote_profile`
- Status/show inspection should stay lightweight and non-noisy:
  - they do not append transcript command entries on the gateway side
  - mutating actions (`refresh`, `promote_*`) do append compact command records for auditability
- The best TUI status treatment is compact, not verbose:
  - one `memory` summary line in the right sidebar
  - detailed inspection remains command-driven via `/memory ...`
  - workspace durable note promotion is valid for stable workspace facts
  - global profile promotion is valid only when the caller explicitly chooses that semantic target
  - future RAG / memory / MCP upgrades can improve provider quality without changing the core injection seam
  - CLI/TUI operator surfaces already receive the new providers automatically through the existing `prepared_context` summary path

## 2026-04-09 Agent-Core Provider Quality Controls

- Once multiple providers were attached simultaneously, the next real risk was no longer missing context but noisy context:
  - duplicated facts could arrive from memory and knowledge-base together
  - lower-value provider output could crowd out higher-value retrieval
  - a naive append-only strategy would make prompt cost and operator summaries drift upward over time
- The right fix was to keep quality control centralized:
  - providers still prepare their own candidate context independently
  - one shared curation step now decides what actually gets injected into the turn
  - CLI/TUI continue reading the same `prepared_context` payload, so operator surfaces stay stable
- The current curation contract is intentionally lightweight:
  - dedupe by normalized content across providers
  - prefer the higher-priority source when duplicates collide
  - enforce shared item and character budgets before injecting the synthetic system context block
- This preserves the main seam:
  - providers stay simple and reusable
  - the agent runtime owns prompt-budget and cross-provider tradeoffs
  - future provider-specific tuning can be added without changing transcript semantics or UI contracts

## 2026-04-09 Agent-Core Provider Readiness And Operator Policy

- After curation, the next practical gap was observability and control:
  - operators still could not tell whether a provider was unavailable, filtered, or simply had no relevant match
  - there was no user-facing way to constrain sources for a turn without editing code
- The clean extension was to keep everything on the same seam:
  - providers can optionally expose readiness
  - agent runtime records provider statuses on the existing `prepared_context` payload
  - CLI/TUI reuse the same payload and do not need a second provider-status event stream
- The resulting provider-state model is now much clearer in practice:
  - `used`: provider contributed prepared context
  - `no_match`: provider was available but found nothing relevant for this turn
  - `filtered`: operator policy excluded it
  - `unavailable`: backing source was not ready (missing notes/store/connections/skills)
  - `failed`: provider execution raised
- Operator control now exists without breaking the runtime contract:
  - `prepared_context_policy` travels as turn metadata
  - TUI persists it per session
  - CLI and TUI both expose lightweight `/context` commands for include/exclude/budget/reset
- One subtle bug surfaced during implementation:
  - a raw policy dict and a metadata-wrapped policy dict were being interpreted differently
  - the fix was to normalize both through one policy parser so UI state, runtime state, and tests all agree

## 2026-04-10 P25.9 Memoria Role Evaluation

- The current live memory stack is already real and coherent without `MemoriaEngine`:
  - `MemoryService` unifies notes, user profile, session search, and consolidated retrieval
  - turn-context providers already surface workspace memory and consolidated memory into runtime turns
  - note/profile tools and automatic memory writeback already mutate durable memory files used by the runtime
- The current `MemoriaEngine` is not a runtime subsystem yet:
  - it is in-memory only
  - it has no persistence contract
  - it has no session/workspace scoping contract
  - it has no tool, gateway, or turn-context integration
  - its retrieval is simple lexical/recentness scoring, not a stronger production path than the already-landed retrieval stack
- Forcing `MemoriaEngine` into runtime now would create a duplicate memory path:
  - runtime memory facts already come from `MEMORY.md`, `USER.md`, session search, and consolidated memory
  - adding a second live memory store would immediately introduce divergence and reconciliation problems
- The correct P25 decision is:
  - keep `MemoriaEngine` as a lower-level primitive for now
  - do not wire it into runtime until it has one explicit persistence + ingestion + retrieval + operator contract
- If it is promoted later, the minimum acceptable shape should be:
  - one persisted workspace/session-backed store
  - one explicit ingestion policy from transcript/tool/runtime events
  - one retrieval bridge into the existing turn-context seam
  - one observability surface so operators can see what it is doing

## 2026-04-10 Memory + RAG + Workspace Architecture Adjustment

- The user's target direction is broadly correct, but one assumption needed correction:
  - current Mini-Agent memory is mainly workspace-scoped, not a true cross-workspace global memory layer yet
- The clean target shape is four-plane, not "one global memory plus one second memory system":
  - global durable memory
  - workspace durable memory
  - workspace runtime task memory (`MemoriaEngine`)
  - RAG / knowledge-base retrieval
- `MemoriaEngine` should not become a second durable truth store:
  - it should act as workspace runtime task memory only
  - promotion into durable memory should be explicit or policy-driven
- A single workspace-level `MemoriaEngine` without namespaces would be a design bug:
  - one workspace can have multiple concurrent sessions
  - therefore the right shape is one physical workspace store with logical namespaces such as `session:<id>` and `workspace:shared`
- RAG and memory must remain distinct:
  - RAG owns document chunks and citations
  - memory owns distilled reusable conclusions, preferences, and task knowledge
  - raw RAG hits should not be copied into durable memory verbatim
- Two reference patterns are worth carrying over:
  - Hermes cleanly separates persistent memory from session search
  - extracted-src/Claude anchors session/project identity to a stable project root rather than mutable cwd

## 2026-04-10 P26 Phase 1 Boundary Correction

- The cleanest first implementation slice was smaller than the whole P26 report:
  - do not start with `MemoriaEngine`
  - first correct the durable-memory ownership boundary
  - then make global user memory actually reachable from runtime turns
- `MemoryService` was the right top-level seam to evolve:
  - switching profile operations to true global scope gives an immediate architecture improvement
  - keeping workspace-note memory untouched avoids mixing concerns during the first landing
- The low-risk path was:
  - keep `BuiltinMemoryProvider` available for workspace scope
  - add an explicit global scope mode to it
  - make higher-level runtime callers (`MemoryService`, `UserModelingTool`) choose global scope intentionally
- The `user_profile` source priority already existed in `turn_context.py`, but there was no real provider behind it.
  - adding `UserProfileTurnContextProvider` closed that gap cleanly without changing the rest of the prepared-context machinery
- Test isolation mattered immediately:
  - without an overridable global-memory root, tests would leak into real `~/.mini-agent/global`
  - `MINI_AGENT_GLOBAL_MEMORY_ROOT` is now the isolation seam used by the new coverage
- One historical problem surfaced during this slice:
  - `tests/test_memory_automation.py` depended on broken non-ASCII literals and became syntactically unstable
  - rewriting it into deterministic ASCII tests plus extraction stubs was cleaner than preserving brittle encoding artifacts

## 2026-04-10 P26 Phase 2 Workspace-Aware Session Search

- The current session-search layer already stored `workspace_dir`, but that was not enough for stable project identity:
  - nested paths inside one repo would not naturally group together
  - exact cwd-based filtering would violate the intended "stable workspace root" rule
- The correct low-cost fix was to persist `workspace_anchor_dir` in the session-search index:
  - compute it from `discover_memory_layout(...)`
  - backfill it for older rows on index startup
  - filter search queries by anchor, not raw cwd
- The session-search provider needed one practical retrieval heuristic:
  - full natural-language FTS queries are often too strict because the current FTS match builder uses `AND`
  - provider-level fallback to shorter keyword-focused candidates is enough for now and avoids rewriting the global index semantics in this slice
- The current session should be excluded by default in prepared-context retrieval:
  - current turn transcript is already present in live agent history
  - feeding it back through session-search mostly creates duplication and prompt waste
- Gateway-managed shared sessions use a different session store path than local default session search:
  - without explicit wiring, runtime providers would search the wrong store
  - adding `session_store_dir` to kernel bootstrap was the clean integration seam

## 2026-04-10 Explicit Memory / RAG Grounding Boundary

- The next RAG-memory risk was accidental writeback, not missing retrieval:
  - KB was already explicit as a tool
  - but runtime summaries and automatic daily-note writeback still had no first-class way to record or respect KB grounding
- The clean fix is explicit grounding metadata plus explicit confirmation:
  - KB-grounded turns now annotate runtime task memory with `query`, `knowledge_base_id`, `hits`, and compact refs
  - automatic workspace durable-note and daily-note writeback is suppressed for KB-grounded turns
  - explicit runtime-memory promotion into workspace durable notes now categorizes the result as `kb_confirmed`
- This keeps the architecture boundary honest:
  - RAG still owns source chunks and citations
  - runtime task memory is the bridge for temporary KB-grounded conclusions
  - durable memory receives only operator-confirmed distilled conclusions

## 2026-04-10 KB Grounding Operator Visibility Follow-Up

- After the storage/promotion boundary was fixed, the next risk shifted to operator ambiguity:
  - KB grounding metadata existed in runtime memory
  - but preview/detail rendering still depended on separate gateway/TUI/CLI formatting paths
  - that makes future drift likely even when the underlying memory payload is correct
- The right fix was one shared formatting seam, not more per-surface conditionals:
  - runtime-memory previews now flow through one shared formatter
  - shared-entry detail rendering now also flows through one shared formatter
  - KB-grounded runtime entries expose badges plus compact `kb / hits / query / refs` lines consistently
- This keeps the operator contract cleaner:
  - storage semantics stay separate from display semantics
  - KB visibility is now stable across local and remote surfaces
  - later memory-surface refinements can extend one seam instead of editing three outputs independently

## 2026-04-10 Session Runtime Entry Inspection Symmetry

- After `workspace:shared` became directly inspectable, the remaining operator asymmetry was session-local runtime memory:
  - operators could list session runtime entries
  - and they could promote them
  - but they still could not open one session entry in detail through the same command surface
- That asymmetry matters because session/workspace memory boundaries are part of the design itself:
  - if only shared entries are directly inspectable, the operator surface nudges people toward workspace-shared facts
  - while session-scoped runtime memory remains the primary active-task layer
- The clean fix was to extend the existing command seam instead of inventing a new noun:
  - keep `memory show brief|full` for diagnostics
  - add `memory show <selector>` for session-entry detail
  - route the same behavior through gateway, TUI, CLI, and QQ

## 2026-04-10 Durable-Memory Unified Command Surface

- Once runtime-memory inspection was symmetric, the next operator gap was outside runtime memory entirely:
  - `/memory` could inspect active/runtime state
  - but global profile facts and durable workspace notes still lived behind separate service APIs instead of the main operator command seam
- That split was starting to work against the architecture:
  - runtime memory and durable memory are different layers
  - but operators still need one coherent place to inspect both when confirming promotions or debugging memory behavior
- The low-friction fix was to extend the existing `/memory` family instead of adding another top-level command set:
  - `memory profile [query]`
  - `memory notes [query]`
  - `memory daily <YYYY-MM-DD>`
- One interface refinement was worth doing explicitly:
  - the gateway memory request already had `content`, but overloading it for search/day selectors would blur write vs read semantics
  - adding explicit `query` and `day` fields keeps the API clearer for later TUI/QQ/remote integrations

## 2026-04-10 Consolidated-Memory Operator Surface

- After durable-memory browsing landed, one memory layer was still operator-second-class:
  - consolidated memory already influenced turn-context preparation
  - refresh diagnostics were visible
  - but there was still no direct `/memory` inspection/search path for the consolidated layer itself
- That was becoming an observability gap:
  - operators could tell consolidated memory existed
  - but not easily inspect its current items or query it directly from the main command seam
- The right follow-up was read-only surface expansion, not more automation:
  - keep `/memory refresh` as the explicit refresh trigger
  - add `memory consolidated` for snapshot inspection
  - add `memory consolidated search <query>` for ranked lookup
- This keeps the layer boundaries clean:
  - runtime memory remains active-task state
  - durable memory remains human-edited/confirmed notes and profile facts
  - consolidated memory remains a derived retrieval layer, now with first-class operator visibility

## 2026-04-10 Cross-Layer Memory Overview / Export Surface

- Once runtime, durable, and consolidated layers were all individually inspectable, the next gap was operator context switching:
  - `/memory` had several precise read commands
  - but there was still no single cross-layer overview to answer "what does memory look like right now?"
  - and no explicit export surface from the same operator seam
- The clean follow-up was aggregation plus explicit export, not another hidden background workflow:
  - add `memory overview` for one operator-facing summary across runtime, durable, and consolidated layers
  - add `memory export [jsonl|markdown]` for explicit durable-note export
  - keep request semantics explicit by adding a dedicated `export_format` field instead of overloading `content`
- This keeps the seam coherent:
  - overview is human-oriented and cross-layer
  - export is explicit and payload-oriented
  - gateway, TUI, CLI, and QQ now reuse the same shared formatting path instead of inventing separate summaries

## 2026-04-10 KB Call-Decision Guidance + Low-Signal Memory Quality

- The current RAG/memory architecture did not need another retrieval path; it needed better decision quality at the existing seam:
  - doc-grounded requests should bias toward explicit KB use
  - but KB should still stay explicit rather than being passively injected into every turn
- The clean fix for KB behavior was guidance, not automation:
  - strengthen the `knowledge_base` tool description around README/spec/API/design/manual retrieval cases
  - strengthen the system prompt so the agent forms better KB queries and reaches for KB earlier on document-grounded asks
- The memory side had a different quality problem:
  - low-signal control chatter can pollute both durable auto-memory and runtime task memory
  - once stored, that noise competes with actually useful task memory during later retrieval
- The right first hardening step was one shared filter, not two drifting heuristics:
  - `clean_memory_text(...)` and `is_low_signal_control_turn(...)` now give automation and runtime writeback the same low-signal gate
  - skipped writes now expose an explicit `low_signal_control_turn` reason instead of silently disappearing
- A real-use integration test was worth adding now, before more automation expands:
  - personal workflow memory behavior is easy to misunderstand if only unit tests exist
  - `tests/test_memory_real_use_flow.py` now checks that workspace/session boundaries stay intact and KB-grounded facts still require explicit confirmation before durable promotion
