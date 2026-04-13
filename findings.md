# Findings

## 2026-04-13 P31.2 Thin Application Seam Hardening

- This slice confirmed that the right next move was not a large gateway rewrite.
- It was enough to correct the top application seam so a new desktop surface would not bind itself to transport-owned naming and orchestration.
- The key result is not new behavior.
- The key result is corrected ownership:
  - `MainAgentSurfaceService` is now the canonical top interaction service
  - surface-neutral chat flow types now exist for request/result/stream-event handling
  - gateway now consumes the shared service as transport, instead of being the only obvious semantic owner
- The implementation also showed that a small amount of compatibility aliasing is still useful here.
- Why:
  - tests and adjacent code still reference `MainAgentGatewayUseCases` and older gateway-shaped names
  - replacing all of that in one cut would create churn disproportionate to the seam correction itself
- This is one of the cases where a minimal alias is acceptable:
  - it preserves working behavior
  - but the canonical name and dependency direction are now changed
- The more important architectural win is that the next desktop slice can now target:
  - shared surface service semantics
  - local gateway transport
- instead of hard-binding to `gateway use cases` as if HTTP were the business boundary.

## 2026-04-13 P31 DesktopUI(PySide6) Decision Freeze

- The desktop-direction choice should be treated as an architecture decision, not just a UI preference.
- The important clarification is:
  - the user does not want browser-first work as the main daily-use graphical path
  - but also does not want the current TUI renderer awkwardly wrapped into a fake desktop shell
- That makes the right answer:
  - a separate `PySide6 DesktopUI`
  - on the same shared runtime/session/application truth
- The current codebase is actually in a better place for this than it first appears.
- Why:
  - `SessionApplicationService` is already mostly surface-neutral
  - recent `P30.5` work cleaned up interaction binding and session truth handling
  - the gateway already exposes a reasonably complete command/session/model transport surface
- But there is still one meaningful leak:
  - the top orchestration is still named and shaped as `MainAgentGatewayUseCases`
  - that is acceptable for HTTP delivery
  - but it is the wrong long-term service boundary for a new first-class desktop entrance
- So the real decision is not:
  - "rewrite gateway first"
- And it is not:
  - "start DesktopUI directly on the current gateway-owned orchestration shape"
- The correct middle path is:
  - first land one thin surface-neutral application seam
  - then reuse the existing gateway as the first DesktopUI transport/backend
- That keeps the execution path fast without locking the new desktop surface onto transport-owned semantics.

## 2026-04-13 P30.5 Near-Close And Remote Scope Correction

- It would be easy to keep shaving `P30.5` forever once the shared-binding work starts going well.
- But the latest audit suggests that would now be the wrong move.
- Why:
  - the active production binding path is already aligned
  - the runtime write path is aligned too
  - the low-level direct-call guardrail is also now patched
- At that point, continuing the same line by inertia would mostly be cosmetic refactor energy.
- A follow-up review initially pointed toward the remote-adapter side.
- But the user clarified an important product-scope rule:
  - `WeChat` is not part of the current actual implementation plan
  - it is future extension only
- That changes the right conclusion.
- The correct next move is not:
  - using `WeChat` as the next active refactor target
- The correct next move is:
  - freeze `P30.5` near its natural stop
  - keep the `Remote Interaction` architecture generic at the entrance level
  - but document active delivery scope as `QQ` only
  - leave `WeChat / Feishu` as future extension targets, not current execution commitments

## 2026-04-13 P30.5 Interaction-Surface Direct-Call Guardrail

- After the runtime live-state cut, the main production drift was already removed.
- But a smaller guardrail issue remained in the lowest shared helper:
  - `resolve_interaction_surface(...)`
- The mismatch was subtle:
  - `resolve_user_entrance(None, "qq")` already classifies the request as remote
  - but `resolve_interaction_surface(None, "qq")` still returned the legacy fallback surface shape
- That no longer broke the current application/runtime path because those paths now use shared interaction binding.
- Still, leaving the helper in that state would invite the same bug to reappear the next time someone reaches for the lower-level function directly.
- So this is not a big architecture slice.
- It is a preventive guardrail:
  - make the lower-level helper consistent with the remote meaning it already exposes
  - lock that with one direct test
- This kind of cleanup is worth doing after a convergence refactor:
  - first fix the real write path
  - then remove the remaining low-level footguns that could recreate the same drift later

## 2026-04-13 P30.5 Runtime Live-State Remote Binding Convergence

- The previous two `P30.5` cuts fixed the shared binding seam and the request-side precedence bug.
- But one lower-level drift point still remained:
  - some runtime state writes were still using older surface-only normalization
  - so the top of the stack could correctly understand a remote request as `qq`
  - while a deeper transcript/projection write could still fall back differently
- That kind of bug is easy to miss because the request contract already looks correct at the application boundary.
- The real question is:
  - does the runtime write the same truth it just resolved?
- In this case, the answer was "not always yet."
- The important fix was therefore not another adapter rewrite.
- It was to reuse the same shared interaction-binding seam in the place that actually mutates session truth:
  - projection surface binding
  - transcript message writes
  - activity transcript writes
- Two adjacent seams benefited from the same cleanup:
  - gateway execution metadata now resolves through shared interaction binding too
  - remote conversation binding lookup no longer relies on the older `surface=channel_type` shortcut
- This is a useful architecture lesson for the rest of the refactor:
  - boundary convergence is not finished when requests are normalized
  - it is finished when the write-path that persists session truth also uses the same normalization contract

## 2026-04-13 P30.5 Default-Surface Override Fix For Remote Bindings

- This follow-up mattered because the previous convergence cut removed duplication, but one precedence bug still remained.
- The bug was subtle:
  - `SessionSurfaceBinding.from_request(...)` accepted `default_surface`
  - and it applied that default before calling the shared resolver
- That changed the meaning of the resolver itself.
- The shared resolver was supposed to decide:
  - explicit surface first
  - channel type second
  - default surface last
- But with the old prefill behavior, `default_surface="tui"` could win too early.
- So a remote request like:
  - no explicit `surface`
  - `channel_type="qqbot"`
- could still end up looking like a TUI-originated request before the shared binding logic even ran.
- That is not merely duplication.
- It is a correctness bug because remote-origin context gets overwritten by a local fallback.
- The fix is small and honest:
  - stop pre-applying the default
  - pass the raw request values into the shared resolver
  - let the resolver keep the authoritative precedence order
- This is a good example of why small boundary follow-ups are worth doing:
  - the previous slice created the right seam
  - this slice made sure callers actually respect that seam's contract

## 2026-04-13 P30.5 Shared Interaction Binding Convergence

- This was a good next slice because it fixed a real semantic split without reopening a large refactor track.
- By this point, the architecture docs had already locked the four-entrance model.
- The remaining risk was quieter:
  - chat requests were already normalized through a shared interaction adapter
  - shared-session operations still built their bindings locally
  - the TUI gateway client had yet another lighter local normalization path
- That kind of duplication does not look dramatic in code review.
- But it creates exactly the sort of boundary drift that shows up later as:
  - alias mismatches
  - slightly different trimming rules
  - one entrance passing `qqbot` while another passes `qq`
  - one path inventing a default surface while another preserves `None`
- The right fix was not to redesign surface semantics.
- The right fix was to add one shared normalization seam and reuse it in the existing callers.
- The most important detail in this cut is what it did *not* do:
  - it did not force empty shared-session mutation requests into `"api"`
  - it kept the current meaning that missing `surface` stays unset unless a real source/default is available
- That matters because session mutation/control paths should not accidentally overwrite session activity provenance just because the caller omitted optional surface metadata.
- This is a healthy convergence slice:
  - small
  - boundary-focused
  - behavior-preserving
  - valuable because it removes a future source of entrance drift before it becomes another larger refactor

## 2026-04-13 P30.7ap Runtime Manager Re-Audit + Natural Stop Check

- This re-audit was important because successful refactors create a new kind of risk:
  - continuing to refactor after the architectural reason is gone
- The current runtime manager still has some long methods.
- But the meaning of those long methods has changed.
- The longest remaining blocks are now the staged initialization methods.
- Those are composition-root wiring.
- They are not the same problem as the earlier mixed-responsibility hotspots.
- The parameter-heavy operator methods also still occupy noticeable space, but on inspection they are mostly:
  - load session
  - delegate
  - return
- That is a good facade shape, even if the signature itself is long.
- The re-audit therefore suggests a different standard from the earlier `P30.7` stages:
  - do not keep extracting because the file is still non-trivial
  - only extract again when a real behavior seam starts drifting or mixing ownership
- The small dead-helper cleanup found during the audit supports that conclusion:
  - what remained to remove was mostly residue, not architecture
  - `_allocate_session_title_unlocked(...)` and the thin lineage wrapper remnants were cleanup, not new decomposition work
- So the honest state now is:
  - `P30.7` has materially improved the runtime boundary
  - the manager is now close enough to a real outer coordinator/composition root
  - the next useful engineering energy should probably move back to capability work unless a fresh runtime smell appears

## 2026-04-13 P30.7ao Lineage Registry Helper Extraction

- This was the smallest honest third cut after the hotspot audit.
- By this point, the manager no longer owned much shared state or much request interpretation.
- What remained in this area was one runtime-private rule cluster:
  - lineage root resolution
  - lineage registration/update
  - lineage removal
- That is exactly the kind of logic that does not need a large subsystem, but also should not stay inline in the outer coordinator forever.
- The helper extraction is useful because it improves ownership without breaking the current observation seam:
  - `runtime._session_lineage` still exists for tests/debugging
  - the mutation rules now live in a dedicated helper
- That is a good fit for this stage of `P30.7`:
  - small
  - behavior-preserving
  - no abstraction theater

## 2026-04-13 P30.7an Derived Session Creation Extraction

- This was the right second cut after model-selection request resolution.
- `create_derived_session(...)` was still a real manager hotspot because it assembled a full inherited payload inline.
- That included:
  - inheriting selected model identity
  - inheriting context and sandbox state
  - shaping child lineage metadata
- None of that is outer-coordinator work.
- It belongs with session creation and hydration semantics.
- Moving payload inheritance into the hydration builder and creation orchestration into the registry handler improved the package structure in a very clean way:
  - the manager still owns lock + parent-session lookup
  - registry/hydration now own how a derived session is shaped and created
- Fixing direct `create_session(...)` to reuse `allocate_session_id()` was also the right opportunistic cleanup here.
- It removed a real though low-probability inconsistency:
  - direct session creation now respects the same live/persisted collision guard as the rest of runtime session creation
- After this cut, derived-session creation looks much more like the rest of the runtime:
  - session truth stays centralized
  - the coordinator delegates
  - the session registry/hydration path owns the construction details

## 2026-04-13 P30.7am Model Selection Request Resolution Extraction

- This was the right next implementation cut because it matched the hotspot audit almost perfectly:
  - small surface
  - clear misplaced responsibility
  - low risk of collateral churn
- Before this slice, the runtime manager still behaved like a partial request interpreter for model selection.
- It was deciding:
  - whether `provider_source` was missing
  - how to infer it
  - and how to translate inference failures into `400` errors
- That is not coordinator work.
- It belongs with model-selection request semantics.
- Moving the logic into `RuntimeSessionModelSelectionHandler` improves the boundary in two ways:
  - the handler now owns the full request-resolution step before planning
  - `MainAgentRuntimeManager` now only:
    - loads the session
    - forwards the request
- Another good detail in this cut is that the existing monkeypatch seam stayed stable:
  - the runtime manager still injects the bound `resolve_session_model_selection_identity(...)` callback
  - so tests and runtime composition can continue to override the resolution behavior without teaching the manager to interpret the request again
- This is a healthy `P30.7` pattern to keep repeating:
  - do not invent a new abstraction if one handler already owns the nearby semantics
  - just move the remaining request meaning into that handler and thin the manager facade
- The next best follow-up remains `create_derived_session(...)`, because it is now the clearest remaining manager method that still assembles a non-trivial runtime payload inline

## 2026-04-13 P30.7al Runtime Hotspot Audit

- After the persistence and shared-state extractions, the right question changed.
- The question was no longer:
  - "what still makes the file look big?"
- The better question was:
  - "what remaining logic still makes the manager the wrong owner?"
- That distinction mattered immediately.
- The longest remaining methods by line count were the initialization stages.
- But those are now mostly honest composition-root wiring.
- They are long, yet not especially confused.
- That means they should not be the next target just because they rank high in a length table.
- The more useful hotspots are smaller but more meaningful:
  - `update_session_model_selection(...)` still performs provider-source inference and exact selection validation before delegating
  - `create_derived_session(...)` still assembles inherited snapshot payload state inline inside the manager
  - `_register_session_lineage_unlocked(...)` still owns the runtime-private lineage graph mutation rules
- Those three are better next-cut candidates because each one still represents a real ownership question:
  - model-selection request resolution belongs with model-selection semantics
  - derived-session creation belongs with session creation/registry orchestration
  - lineage graph mutation belongs with a lineage-specific runtime seam rather than the outer coordinator
- The audit also exposed one smaller but honest consistency problem:
  - `RuntimeSessionRegistryHandler.create_session(...)` uses `uuid4().hex` directly
  - while the runtime already has `allocate_session_id()` to avoid collisions against both live sessions and persisted records
  - collision probability is low, but this is still the wrong owner for identity generation rules
- So the outcome of the audit is not "the manager is still too large."
- The more accurate outcome is:
  - the manager has now reached the point where only behavior-shaped hotspots deserve further extraction
  - future `P30.7` work should be narrower and more evidence-driven than the earlier residue-removal cuts

## 2026-04-13 P30.7ak Session State Model Extraction

- This was the right follow-up to the persistence cut because it addressed a different kind of residual coupling.
- The persistence wrapper was manager-private.
- The session-state cluster was not.
- It was referenced across much of the runtime package, which meant the shared runtime session truth was still physically living inside the outer runtime facade.
- That is a subtle but important architectural drag:
  - even if behavior is correct
  - other runtime collaborators still look like they depend on the manager for their core shared types
- Moving the state cluster into `session_state.py` improves the shape of the package more than the raw line count suggests.
- It makes the runtime dependency graph more honest:
  - state models live in a neutral shared module
  - the manager depends on those models
  - the collaborators depend on those models
  - fewer modules conceptually depend on the manager just to talk about shared session state
- This slice also confirms a useful boundary rule for the remaining `P30.7` work:
  - once file-top residue is gone, the next cuts should be driven by true orchestration hotspots
  - not by adjacency or by a desire to keep splitting modules for its own sake
- In other words:
  - persistence and shared state were good extractions because they represented distinct shared responsibilities
  - future cuts now need to justify themselves in terms of ownership or behavior, not just file geography

## 2026-04-13 P30.7aj Runtime Persistence Extraction

- The latest `P30.7` audit was useful because it showed that the remaining runtime-manager file-top bulk was not one problem.
- It was at least two different problems:
  - a private persistence wrapper
  - a broadly referenced session-state type cluster
- Treating those as one refactor would have been the wrong move.
- The persistence wrapper was the better first cut because it already had a clean boundary:
  - write the live session record
  - write/read the shared transcript sidecar
  - manage metadata records
- It was also mostly manager-private.
- That matters because a good decomposition slice should reduce ownership confusion without forcing a cross-runtime import migration unless that migration is the point of the slice.
- This cut therefore improved architecture in a very honest way:
  - the outer runtime facade no longer embeds persistence implementation
  - persistence behavior did not need to change
  - the manager composition root still clearly owns when persistence is used, but not how the persistence wrapper works internally
- The next top-of-file hotspot is now clearer:
  - the `MainAgentSession*` dataclass cluster is still physically anchored in `main_agent_runtime_manager.py`
  - unlike persistence, that cluster is referenced by a broad set of runtime modules
  - so it should be treated as a separate follow-up slice, not casually bundled into the same change
- This is a good example of the current `P30.7` refactor rule:
  - prefer small extractions that remove real mixed responsibility
  - avoid combining unrelated cleanup categories just because they are adjacent in the file

## 2026-04-13 P30.5 TUI-CLI Model Use Request Convergence

- This slice is smaller than the earlier remote-command cuts, but still worth doing.
- By this point, the biggest architectural danger was no longer one huge duplicated command shell.
- The danger was smaller repetition surviving in multiple entrances because it looked harmless.
- `/model use` was one of those cases.
- Both terminal entrances still owned the same local questions:
  - is usage complete?
  - does the provider exist in the current catalog snapshot?
  - does the provider expose that model?
- Those questions are not very complicated.
- But that is exactly why they are easy to duplicate forever.
- The useful move here was not to redesign model selection.
- Runtime and gateway already own the actual selection decision.
- The useful move was only to centralize the request-resolution contract that both terminal entrances were already implementing.
- That gives two benefits:
  - one shared place now defines the catalog-facing `/model use` validation semantics
  - `TUI` and `CLI` can still present the result in surface-appropriate ways without re-deciding the same request validity logic
- This is a good example of the kind of convergence work that matters late in a refactor track:
  - not dramatic
  - not architectural theater
  - just removing the small duplicated branches that would otherwise keep reappearing

## 2026-04-13 P30.5 TUI Remote Memory Mutation Convergence

- This was the natural follow-up to the read-path convergence cut.
- The useful question was no longer:
  - "what business rule still belongs in `TUI`?"
- The useful question was:
  - "why do `promote` and `save` still own their own execution shell if the shared memory service already owns the real command semantics?"
- The answer was basically "historical leftover shape."
- That is exactly the right kind of thing to remove during a convergence pass.
- These branches still repeated:
  - execute
  - catch
  - unpack `result`
  - append feedback
  - set status
- But they were not earning that duplication with any special local meaning.
- So the right move stayed small and honest:
  - do not invent a new mutation framework
  - just route the last two branches through the helper that already proved itself on the read-heavy actions
- The second useful finding came from verification, not from the original code target.
- Once the broader `TUI` suite was run, it exposed a real boundary inconsistency:
  - remote approval forwarding still omitted remote binding metadata even though the request contract supports it
- That matters because once a session is remote and channel-bound, the surface should not arbitrarily drop binding context for one command family while forwarding it for others.
- So this slice ended up doing two healthy things:
  - finishing the memory mutation convergence
  - correcting a small but real remote approval boundary gap discovered by the broader regression sweep

## 2026-04-13 P30.5 TUI Remote Memory Read-Path Convergence

- `memory` was the right next hotspot after `context`.
- The problem here was less about duplicated command meaning and more about duplicated command shell mechanics.
- The `TUI` memory handler had many branches that all repeated the same five steps:
  - execute one memory action
  - catch an exception
  - unpack `result`
  - render the feedback
  - set the status
- That repetition matters because large command handlers do not only drift in business rules.
- They also drift in little things:
  - one branch forgets a metadata field
  - one branch phrases a failure slightly differently
  - one branch starts using a different result unpack rule
- The useful move here was not to invent another full command-planning system.
- The useful move was smaller:
  - add one execution/render helper
  - move the repeated read-heavy memory paths through it
- That gives us a good intermediate result:
  - the read-heavy remote memory surface is thinner now
  - the remaining mutation-heavy memory actions are easier to see as the next separate hotspot
- This is a healthy cut because it reduces structural thickness without forcing a premature redesign of the more stateful memory mutations.

## 2026-04-13 P30.5 TUI Remote Context Request Convergence

- This was a particularly worthwhile cut because it removed a subtle but important kind of drift.
- The drift was not in validation output.
- `TUI` was already asking the shared command service to validate `context include/exclude/budget/reset`.
- The drift was in what happened next:
  - after validation succeeded
  - `TUI` went back to raw `args`
  - and rebuilt the remote request shape itself
- That is exactly the kind of half-shared command flow that looks fine for a while and then becomes a maintenance trap.
- The right move here was not to push more logic into `TUI`.
- The right move was to let the shared command service expose the structured remote-request intent directly.
- Then `TUI` could just forward it.
- That produces a much healthier split:
  - shared command execution owns more of the command meaning
  - `TUI` owns less re-parsing
  - remote binding metadata is forwarded consistently
- This slice is valuable because it reduces a kind of drift that is easy to miss in reviews:
  - duplicated parse logic that only exists after validation has already happened once

## 2026-04-13 P30.5 TUI Remote Control Dispatch Convergence

- After the busy-conflict cut, the remaining remote control smell was smaller but still worth fixing.
- The issue was no longer "who decides busy."
- The issue was "why are remote `mcp` and remote context-control still assembling nearly the same control request in parallel?"
- That kind of duplication is quieter than duplicated business rules, but it still matters.
- It creates three risks:
  - one path starts forwarding a different binding payload than the other
  - one path handles gateway failure detail differently
  - one path forgets to sync session detail after a successful remote mutation
- In fact, that first inconsistency was already real:
  - remote context-control was not sending the same binding payload style as remote `mcp`
- So this cut was the right size:
  - not a new subsystem
  - not a broad control-framework rewrite
  - just one shared remote dispatch seam inside `TUI`
- That gives a cleaner entrance shape:
  - request assembly is less duplicated
  - gateway error rendering is less duplicated
  - remote control binding metadata is more consistent
- This is a good follow-up cut because it reduces drift pressure without pretending the whole command surface is now "finished."

## 2026-04-13 P30.5 TUI Remote Control Conflict Convergence

- This slice is smaller than remote `skill` or remote approval, but still worth doing.
- The problem was not that `TUI` owned all remote control semantics.
- The problem was that it still owned one very specific kind of semantic fork:
  - remote busy-conflict decisions for `compact`
  - remote busy-conflict decisions for `drop_memories`
  - remote busy-conflict decisions for `mcp reload`
- Those are easy branches to leave in a surface because they look harmless.
- But they are exactly the kind of branches that make one entrance slowly drift from the canonical runtime behavior.
- The shared control path already had the authoritative rule:
  - session busy should be rejected there
  - and the user should get the shared conflict detail there
- So the useful move here was not a bigger redesign.
- It was to stop `TUI` from answering that question first for remote sessions.
- This slice also improved test truthfulness:
  - the fake gateway now knows how to surface shared busy conflicts for remote control actions
  - so the tests verify gateway-authoritative control conflicts instead of verifying the old local precheck
- The result is healthy:
  - `TUI` remote control handling is thinner
  - shared control conflict wording is more authoritative
  - there is still more `mcp` convergence left, but the worst remote busy fork is gone

## 2026-04-13 P30.5 TUI Remote Approval Convergence

- Remote approval was the right next target after remote `skill`.
- The issue was not just duplicated lines.
- The issue was duplicated authority:
  - `TUI` was still deciding whether approval existed
  - whether restart loss should block direct approval
  - whether one pending approval should auto-pick a token
  - and whether multiple approvals should require a token
- Those are not surface concerns.
- Those are approval-resolution rules.
- And the shared runtime already owns them.
- So the right move here was the same principle as the QQ approval cut:
  - do not redesign approval APIs
  - do not introduce a new abstraction layer
  - just stop letting the surface re-implement shared approval semantics
- This slice also needed one testing correction:
  - the fake gateway in `test_tui_app.py` was still modeling the old TUI-precheck world for restart loss
  - that would have let stale local behavior look correct in tests even after the architecture moved on
- Fixing the fake gateway matters because otherwise we would be "testing the old bug as the contract."
- The result of this cut is clear:
  - remote `TUI` approval now behaves more like a surface over shared runtime decisions
  - local approval still works the same way
  - the next `P30.5` hotspot is now remote control behavior, especially MCP/context-control

## 2026-04-13 P30.5 TUI Remote Skill Convergence

- The audit was right to target `TUI` first.
- The remote `skill` path in `TUI` really was a second command shell in practice:
  - per-action argument validation
  - per-action usage handling
  - per-action response fallback text
  - per-action status wording
  all lived in one long branch tree
- That kind of structure is not just ugly.
- It is dangerous because every new skill action encourages one more local branch in the entrance layer.
- The useful move here was not a new abstraction shared across the whole app.
- The useful move was smaller and more honest:
  - add one normalized remote command plan
  - centralize remote usage / unknown-action handling
  - centralize remote response fallback rendering
  - keep gateway interaction exactly where it already belongs
- That gives us a better boundary:
  - `TUI` still owns operator-facing display behavior
  - but it owns far less action-by-action command meaning
- This slice also exposed a small correctness risk:
  - remote `skill uninstall` and `skill rollback` were not included in the same mutation-sync path as the other mutating skill actions
- That was easy to miss because it was not a crash.
- It was a consistency hole.
- Locking it now is worthwhile because these are exactly the kinds of tiny drift bugs that slowly make one entrance feel "special."
- So the architectural result of this slice is good:
  - `TUI` remote `skill` is no longer the biggest low-hanging command-shell duplication in the surface
  - the next `P30.5` cuts can now move to remote approval, then remote MCP/context-control

## 2026-04-13 P30.5 Shared Entrance Command Convergence Audit

- The good news is that the project is no longer missing a shared command foundation.
- It already exists in two important pieces:
  - [router.py](d:\file\Mini-Agent\src\mini_agent\commands\router.py)
  - [execution.py](d:\file\Mini-Agent\src\mini_agent\commands\execution.py)
- That matters because it changes the nature of the problem.
- We are not looking at a system with no shared command seam.
- We are looking at a system where some entrances already use that seam better than others.
- `CLI` is not perfect, but it is meaningfully closer to the target:
  - it already dispatches several command families through shared helpers
  - `kb`, `mcp`, `model`, `skill`, and compaction-related flows are visibly converging
- `QQ` also stopped being the main boundary risk after the `P30.4` work.
- The remaining adapter logic there is now mostly:
  - binding hints
  - display formatting
  - channel protocol behavior
- So continuing to shave QQ edges would no longer attack the highest-value problem.
- The highest-value problem has moved to `TUI`.
- More specifically, it has moved to the `TUI` remote-session command path.
- The architectural smell is not just "a few duplicated lines."
- The smell is that `TUI` still behaves like it owns a second command execution shell when operating against gateway-backed sessions.
- The clearest hotspots are:
  - approval resolution
  - context control
  - context command orchestration
  - memory command orchestration
  - MCP command orchestration
  - skill command orchestration
  - model command orchestration
- There is one important nuance:
  - some `TUI` model behavior is legitimately surface-specific, such as cursor movement, filter state, and apply-next/apply-prev operator affordances
  - but `show/list/use` semantics should not keep drifting separately
- So the correct `P30.5` direction is now clear:
  - do not restart from QQ
  - do not invent a brand-new shared command subsystem
  - instead, thin the `TUI` remote command shell until it becomes a true surface over shared semantics
- The safest first implementation cut is:
  - remote `skill` convergence in `TUI`
- After that, the next best cuts are:
  - remote approval convergence
  - remote MCP/context-control convergence

## 2026-04-13 P30.4 QQ Tail Cleanup + Closure Check

- After the last command-thinning cuts, the remaining QQ issues were no longer serious boundary violations.
- They were small tail problems:
  - `/status` could double-reply when probing for a shared session and then falling back to local status
  - `/cancel` still kept a QQ-local conflict wording branch
- These are important to fix, but they do not justify another large `P30.4` refactor.
- The right finish here is tiny and disciplined:
  - allow silent binding checks for read-only status probing
  - let shared conflict wording remain authoritative for cancel failures
- After that cleanup, the remaining QQ logic is mostly:
  - conversation binding hints
  - local display formatting
  - channel protocol handling
- That matches the frozen remote-adapter contract.
- So the architectural conclusion is straightforward:
  - `P30.4` is ready to close
  - further work should move to shared entrance convergence instead of continuing to shave tiny adapter-local edges

## 2026-04-13 P30.4 QQ Runtime Policy + MCP Command Thinning

- After the approval cut, the remaining QQ adapter semantics were smaller but still visible in two places:
  - runtime policy commands
  - session control commands
- The runtime-policy issue was mostly structural:
  - `/plan`
  - `/build`
  - `/default`
  - `/full_access`
  were all routed through one handler, but the handler still derived the payload by branching on the command name.
- That is not a severe boundary violation, but it is still the adapter deciding command meaning in code instead of declaring it at dispatch time.
- The cleaner boundary is:
  - dispatch declares the intended policy payload
  - the handler only forwards that payload and renders the response
- The MCP issue was similar but lighter:
  - `/mcp` legitimately remains a subcommand router in QQ
  - but it did not need to keep a QQ-only `reload + 409 busy` wording branch
- The shared session-control path already knows whether a session is busy and already returns the canonical conflict message.
- So the useful tightening here was not to invent a new shared subsystem.
- It was to:
  - move more meaning into entry metadata
  - keep `/mcp` as a thin router
  - and let shared error detail stay authoritative
- This is a good `P30.4` cut because it improves entrance clarity without pretending every tiny command translation must disappear.

## 2026-04-13 P30.4 QQ Approval Command Thinning

- After the `/memory` and `/context` cut, the strongest remaining QQ adapter-owned semantic hotspot was `/approve` / `/deny`.
- The problem was not transport formatting.
- The problem was that QQ was still acting like a partial approval resolver:
  - fetch session detail
  - inspect live pending approvals
  - inspect restart-recovery pending approvals
  - auto-pick a token when only one approval exists
  - and locally tell the user which token to choose when multiple approvals exist
- That is exactly the kind of logic the adapter should not own, because approval resolution semantics must stay identical across entrances.
- The good news was that the correct shared seam already existed:
  - `session_interrupt_handler.py` already owns
    - no-pending conflict behavior
    - restart-lost approval conflict behavior
    - implicit single-token resolution
    - multi-token conflict messaging
- So the right move here was not to invent a new abstraction.
- The right move was to delete QQ's duplicate logic and let the shared approval path speak for itself.
- This is a healthy `P30.4` cut because it removes duplicated business semantics without touching remote binding behavior that legitimately belongs to the adapter.

## 2026-04-13 P30.4 QQ Memory + Context Command Thinning

- After thinning `/skill`, the next architectural pressure point was the pair of large QQ handlers:
  - `/memory`
  - `/context`
- Both had the same smell:
  - lots of action-specific branching
  - lots of argument-shape handling
  - and only part of that logic truly needed to remain at the adapter boundary
- The right split here is not "move everything out."
- Some local responsibility is still real:
  - `context show`
  - `context stats`
  need local read-model formatting in the QQ surface
- But the update and mutation paths did not need so much adapter-owned control flow.
- The useful refactor was therefore:
  - keep the local read-only display behavior
  - convert the mutation/update branches into thinner action-to-payload mapping
  - let the shared memory/context handlers reject incomplete selectors and invalid mutations
- This is especially valuable for `/memory`, because its action surface is broad enough that every extra local branch increases drift risk.
- Reducing that branch fan-out lowers the chance that QQ quietly diverges from TUI/CLI behavior over time.

## 2026-04-13 P30.4 QQ Skill Command Thinning

- After the model-selection cut, `/skill` was the next obvious remote-adapter hotspot.
- The QQ handler still owned a long sequence of action-specific branches for something the shared runtime already understands quite well.
- That is exactly the kind of structure that slowly turns an adapter into a second command system.
- The useful observation here is that QQ does not need to fully parse skill semantics to be user-friendly.
- It only needs to do a little:
  - recognize the action shape
  - package the relevant text field
  - return a clean error detail when the shared layer rejects the request
- Everything else is better owned by the shared session skill handler.
- This also exposed a correctness gap:
  - the command catalog already advertised `skill uninstall` and `skill rollback` for QQ
  - but the live QQ handler did not support them yet
- Fixing both together was the right move:
  - thinner adapter
  - closer alignment between catalog and live behavior
  - less duplicated skill-command branching in the remote entrance

## 2026-04-13 P30.4 Shared Model-Selection Source Inference

- After the request-helper and command-scope cuts, the next real boundary offender in QQ was `/model use`.
- The adapter was still acting like a partial model router:
  - fetch the catalog
  - find matching provider ids
  - detect ambiguity
  - detect missing models
- That is the wrong long-term direction because the exact same provider/model pair should mean the same thing no matter which entrance requested it.
- The correct home for that decision is shared model-selection logic.
- The useful compromise here was:
  - do not redesign the whole model API
  - do not force TUI/CLI to change
  - just let shared-session model selection infer `provider_source` when the pair is uniquely resolvable
- That small shift matters a lot architecturally:
  - QQ now knows less about provider-catalog internals
  - ambiguity is decided once in shared logic
  - and future remote entrances can reuse the same omission-friendly behavior instead of copying the same catalog scan
- This is exactly the kind of `P30.4` cut we want:
  - remove adapter-owned routing knowledge
  - keep the shared core more authoritative
  - avoid inventing a bigger abstraction than the problem needs

## 2026-04-13 P30.4 QQ Command Scope Dispatch Thinning

- After the QQ request-helper cleanup, the next remaining adapter smell was more structural than repetitive.
- The adapter still knew one entrance-routing rule:
  - some commands are local
  - some commands only make sense when a shared session is bound
- But that rule was expressed indirectly through repeated `ensureSharedSessionBound(...)` checks inside many handlers.
- That arrangement is easy to live with for a while, but it makes the adapter boundary harder to read:
  - you need to inspect each handler body to learn whether the command is local or shared-session-scoped
  - the dispatch seam itself does not say
- The right move here was still not a new subsystem.
- The right move was to let the command registry say what the command scope is.
- That gives the adapter a cleaner shape:
  - the dispatch layer owns entrance-routing preconditions
  - the handler body focuses more on command behavior
  - and the safety net can still remain deeper in helper functions where needed
- This is a good `P30.4` cut because it improves the boundary without pretending QQ no longer has any command adaptation responsibility.
- It still does.
- But now that responsibility is more explicit and less smeared across handler bodies.

## 2026-04-13 P30.4 QQ Adapter Request Helper Thinning

- After the binding-state and naming cleanups, the next honest `P30.4` smell was not ownership anymore.
- It was repetition inside the active QQ adapter:
  - the same shared-session mutation payload shape
  - the same gateway POST shape
  - the same response-envelope validation
  kept appearing across multiple commands
- That kind of repetition matters here because it makes the adapter look more like a mini remote business layer over time.
- The right response was not to build a new shared remote utility module.
- The right response was to keep the helper extraction inside the QQ adapter itself:
  - one sender-id helper
  - one mutation-payload helper
  - one envelope-post helper
- This keeps the boundary honest:
  - the adapter is thinner
  - the application/gateway contract is unchanged
  - and no new pseudo-shared layer was introduced just to deduplicate a few POST calls
- WeChat was reviewed at the same time and intentionally not refactored:
  - its current request assembly is still small enough
  - forcing symmetry there right now would add abstraction pressure without architectural value

## 2026-04-13 P30.4 Remote Binding State Thinning

- Once the remote adapter names were corrected, a smaller but worthwhile follow-up became obvious:
  - some adapter-local fields were still present simply because they had accumulated over time
  - not because the adapter truly needed to own them per conversation
- The clearest example was QQ `botName`:
  - it is process/global configuration
  - storing it inside every conversation binding object only makes the local state shape look richer than it really is
- The WeChat-side `metadata` field had the opposite problem:
  - the type allowed it
  - the active binding flow did not actually need it
  - so the contract was wider than the live implementation
- This kind of thinning work is easy to underestimate, but it matters for architecture stability:
  - a thinner cache shape is harder to misuse
  - a thinner cache shape is easier to classify as binding/preference only
  - and future adapter additions are less likely to cargo-cult extra local state
- This is the right style of `P30.4` progress:
  - reduce ambiguity
  - reduce local ownership surface
  - do not invent new adapter-side abstractions just to look organized

## 2026-04-13 P30.3 Operator-Flow State Split

- After the supplemental split, the next honest TUI boundary issue was smaller but still important:
  - `pending_model_*`
  - `pending_skill_reload*`
  were still sitting on projection state
- Those fields are tricky because they can mirror real runtime/session detail, especially for gateway-backed sessions.
- But inside the TUI they still behave as operator-flow state:
  - queue a model switch
  - remember a skill reload is pending
  - affect what the operator sees next
- Leaving them on projection makes them look more authoritative than they are in the TUI composition.
- The right move was therefore not to redesign shared DTOs.
- The right move was:
  - keep shared contracts untouched
  - add one `TuiSessionOperatorState`
  - let TUI map that state back into summary projection when it needs to render or mirror remote detail
- This keeps the architecture correction honest without inventing another abstraction layer in the shared runtime.

## 2026-04-13 P30.3 Supplemental Cache Split + P30.4 Naming Tightening

- The live code had already taken the right first step for `P30.3`:
  - remote sync/recovery summaries were moved into `TuiSessionSupplementalState`
- The main risk after that move was no longer runtime behavior.
- It was documentation and naming drift:
  - the boundary map still described those fields as if they belonged to projection proper
  - the remote adapter type name `SessionState` still sounded like canonical session truth
- That kind of mismatch is dangerous because it invites future regressions without any failing test:
  - a developer reads the name
  - assumes stronger ownership than the code should have
  - and reintroduces session-owner behavior by accident
- Tightening the names to `conversation binding` language is a small change, but it is exactly the kind of small change that keeps architecture corrections alive over time.
- This is also a good example of the right refactor pacing for the current phase:
  - do not invent a new subsystem
  - do not expand the feature surface
  - make the already-correct boundary harder to misread
- After this cut, the next honest remote-adapter work is more concrete:
  - shrink active adapter caches further toward binding + preference + display metadata
  - not "add more channel-local session behavior"

## 2026-04-13 P30.2 Session Truth Boundary Lock

- The audit baseline was directionally right, but the current codebase is already better than that older snapshot:
  - `TuiSession` has already been split into projection/runtime/view state
- That matters because without re-reading the live code, it would have been easy to repeat stale conclusions and start refactoring the wrong problem.
- The real job for `P30.2` was therefore not "invent the split."
- The real job was to freeze what already exists and clarify what still remains risky.
- Two useful conclusions fell out of the code-level read:
  - TUI is no longer the biggest ownership offender it once was
  - remote adapters are still more structurally misleading than they should be
- The WeChat-side `SessionState` name is especially important here:
  - it sounds authoritative
  - but under the corrected architecture it is only an adapter-side cache
- That kind of naming mismatch is exactly how architectural drift comes back later.
- Another valuable clarification is that not every field in `TuiSessionProjectionState` has the same semantic weight:
  - some are legitimate shared-session projection
  - some are summary-oriented presentation caches
- They can stay in projection state for now, but they should not be mentally upgraded into truth.
- This is a good stopping point for the phase because it gives the next two cuts a clean handoff:
  - `P30.3` can focus on stricter TUI state composition
  - `P30.4` can focus on shrinking remote adapters instead of rediscovering ownership from scratch

## 2026-04-13 Framework Skeleton Lock

- The recent drift was not just a feature-priority mistake.
- It exposed a framework-shape problem:
  - the project had architecture corrections
  - but it still did not have one short active document that froze where code belongs
- That gap makes it easy to keep doing the right local fix in the wrong structural place.
- The practical answer is not another vague architecture note.
- The practical answer is one explicit skeleton contract that freezes:
  - entrances
  - layers
  - repository mapping
  - allowed dependency direction
  - forbidden drift patterns
- This is especially important for Mini-Agent because the tree now contains:
  - shared runtime/application code
  - active entrance apps
  - compatibility adapters
  - transitional channel paths
- Without a skeleton lock, those categories can keep bleeding into each other during normal implementation.
- Freezing the framework skeleton now gives future work a stronger default:
  - new code should first be placed correctly
  - only then should the specific feature behavior be discussed

## 2026-04-13 P30.4a Remote Conversation Binding Centralization

- Re-reading the corrected architecture made the real next move much clearer:
  - the project does not need "more QQ"
  - it needs a thinner and more canonical `Remote Interaction` path
- The strongest small cut is the remote binding seam.
- Right now the tree already contains the ingredients of the right design:
  - channel ingress DTOs
  - shared application chat flow
  - an existing Python `ConversationBindingStore`
- But the active path still behaves as if channel adapters must carry the reusable session binding themselves.
- That is exactly the kind of partial ownership that makes remote adapters sticky over time:
  - they start with a session id cache
  - then they grow command behavior around it
  - then they become "almost another session system"
- Centralizing `conversation -> session_id` reuse in the shared application ingress path is therefore a good architectural move because it improves the boundary without demanding a full remote rewrite in one jump.
- It also sets up the next normalization steps more honestly:
  - QQ / WeChat / Feishu can become thinner adapters over time
  - the gateway/application stack becomes the canonical place to resume a remote conversation
  - future remote adapters do not need to reinvent local binding stores just to keep continuity

## 2026-04-13 P23.29 Explicit Task Fork Commands

- Once delegation started producing real child sessions, the next architectural gap became very clear:
  - runtime had a real derived-session seam
  - operators still had no explicit way to use it
- That kind of gap is where codebases often drift into duplication:
  - one path for delegated children
  - another path for manual task forks
  - and eventually two almost-the-same session hierarchies
- The right fix here was not to teach TUI how to fake child tasks locally.
- The right fix was to expose the already-correct runtime path through one explicit API and let TUI call that.
- A second useful design decision was to keep session creation and first-task execution separate:
  - create the child session through the explicit fork API
  - then reuse the normal chat execution path for the first child turn
- That kept the design simpler:
  - one API creates derived sessions
  - one existing path runs turns
  - TUI composes them instead of asking the backend for another special-case "fork-and-run" primitive
- The result is a cleaner foundation for later parity work:
  - QQ/CLI can reuse the same explicit fork API
  - lineage-aware child sessions stay a runtime truth, not a TUI-only convenience

## 2026-04-13 P23.28 Delegation-Derived Session Lineage

- After wiring lineage into import/export/restore, one obvious gap remained:
  - explicit delegation still did not create a child session
  - so one of the most natural lineage-producing behaviors in the runtime still had no ancestry-bearing session artifact
- This is an important architectural distinction:
  - a delegated worker execution is not the same thing as a delegated task session
  - the first gives you output
  - the second gives you durable runtime truth
- For this codebase, the second is the one future features actually need.
- If delegation only returns a string to the parent session, then later work such as:
  - task fork
  - partial resume
  - child-task review
  - memory/task summarization by branch
  - branch-local model selection
  becomes much harder because there is no persisted child boundary to attach them to
- The right fix was therefore not to expose lineage in UI first.
- The right fix was to make one real runtime behavior actually produce a lineage-bearing child session.
- Another key design choice here was configuration inheritance.
- A derived task session that loses the parent's:
  - selected model
  - runtime policy
  - KB enabled state
  - context policy
  is technically a child session, but operationally the wrong one.
- Reusing the snapshot-hydration path for derived sessions was therefore a good move:
  - it preserved the existing model/policy restore semantics
  - without inventing another partially overlapping session-construction path
- One subtle but important restraint was also added:
  - delegated child sessions do not inherit remote reply binding by default
  - they are internal task sessions, not accidental second remote chat heads
- That keeps the architecture cleaner:
  - lineage-bearing child sessions exist
  - but remote-channel ownership still belongs to the parent conversation unless explicitly reassigned later
- The result is a better foundation for future task-fork work:
  - there is now one real derived-session path in runtime/application layers
  - `/delegate` already exercises it in production code
  - future explicit fork commands can reuse that path instead of creating another special case

## 2026-04-13 P23.27 Session Lineage Runtime Integration

- The codebase already had a real lineage primitive:
  - `SessionLineageStore`
- But before this slice it was structurally misleading:
  - the primitive existed
  - unit tests proved it worked in isolation
  - and yet the runtime never used it for real managed sessions
- That is exactly the kind of gap that causes future design drift:
  - later work starts assuming lineage exists
  - but actual session import/export/restore semantics still behave as if lineage does not exist
- The right fix was not a brand-new lineage subsystem.
- The right fix was to connect the existing one to runtime truth.
- The important design decision here was to keep lineage runtime-private first:
  - attach lineage metadata to managed session state
  - persist it through internal metadata/snapshot contracts
  - rebuild the in-memory lineage graph on restore
  - avoid prematurely expanding public DTOs before the operator surfaces need them
- This slice also clarified a subtle runtime requirement:
  - persisted restore cannot rely on parent sessions already being present in memory
  - so the lineage store must support placeholder parents and later upgrades
  - otherwise child sessions restored before parents would lose graph correctness
- Adding `restore_node(...)` was therefore not incidental cleanup.
- It was the minimal capability required to make lineage survive restart order.
- The result is valuable beyond lineage itself:
  - snapshot import/export now has a place to carry ancestry semantics
  - future session fork / delegation / compression flows no longer need to invent their own ancestry representation
  - runtime session truth is a little closer to a stable kernel rather than a collection of ad hoc metadata fields

## 2026-04-13 P23.26 Agent Kernel Bootstrap Diagnostics

- After the runtime-boundary cleanup, a clearer agent-core gap surfaced:
  - the unified kernel could already build a working agent
  - but it still could not explain itself in one stable payload
- This mattered more than it first seemed because the kernel is now the shared bootstrap path for:
  - CLI
  - TUI
  - gateway
  - future web/remote surfaces
- Without a kernel-level diagnostics seam, each surface would eventually be tempted to rediscover or re-derive pieces of bootstrap state on its own.
- A second, more operational gap was hiding in the tooling bootstrap:
  - optional capabilities like skills and MCP could fail during initialization
  - the runtime would often continue, which is good for resilience
  - but the failure was largely silent, which is bad for real use and debugging
- The right fix here was not to make bootstrap stricter.
- The right fix was:
  - keep optional capability bootstrap non-fatal
  - but make the result observable in one canonical payload
- The new `kernel_diagnostics` seam is valuable because it centralizes bootstrap truth:
  - selected route
  - runtime policy
  - workspace/shared tool catalogs
  - skills readiness/counts/errors
  - MCP readiness/counts/errors
  - turn-context provider inventory
- This is a good example of agent-core strengthening that improves future extensibility too:
  - RAG / memory / skills / MCP integration can now build on the same kernel self-description
  - instead of adding surface-specific bootstrap probes later

## 2026-04-13 P30.7ai Managed Session Require-Helper Cleanup

- After auditing the remaining operator-facing facade methods, the conclusion was:
  - most of them no longer hide meaningful business logic
  - their size is mostly coming from parameter lists and a repeated restore-or-404 session lookup pattern
- That means a large new extraction here would likely be churn rather than improvement.
- A smaller cleanup was still worthwhile:
  - centralize the repeated `_load_managed_session_unlocked(...)` + `404` pattern
  - leave the genuinely different branches alone
- The resulting helper is intentionally narrow:
  - it does not replace `_load_managed_session_unlocked(...)`
  - it only expresses the stronger contract for the identical facade paths that require a managed session
- This slice is useful because it clarifies the current architectural state:
  - the runtime-manager operator surface is now mostly a real facade
  - the remaining code duplication is minor and local rather than a sign of hidden mixed responsibilities
- It also helps identify a natural stopping point:
  - further refactoring on this surface should now be driven by behavior or policy confusion
  - not by line counts or small amounts of repeated boundary code

## 2026-04-13 P30.7ah Runtime Manager Composition Root Cleanup

- After the registry/operator/transcript/snapshot cleanup wave, the most obvious runtime-manager hotspot was no longer a hidden behavior branch.
- It was simply the constructor:
  - `__init__`
  - one long composition block wiring almost every runtime collaborator in sequence
- This is a different kind of design problem from the earlier ones:
  - not misplaced business logic
  - not duplicated orchestration
  - but poor readability at the composition root
- The right move here was deliberately conservative:
  - do not invent an external builder
  - do not add another layer just to move lines around
  - keep the runtime manager as the composition root
  - but split the wiring into a few internal stages with clearer intent
- The resulting shape is better for maintenance even though total file length does not drop much:
  - `__init__` is now short and readable
  - the wiring stages make dependency order explicit
  - future refactors can target one stage at a time instead of re-reading a 300-line constructor
- This slice reinforces another useful refactor rule for this codebase:
  - not every problem wants a new module
  - sometimes the honest cleanup is to keep the ownership where it is and make the structure legible
- What remains now is narrower and more interpretable:
  - the largest methods are mostly explicit helper/wiring stages
  - several operator-facing methods are mid-sized but increasingly shallow
  - further work should focus on genuinely confusing behavior or duplicated policy, not constructor line counts alone

## 2026-04-13 P30.7ag Snapshot Import Command Surface Cleanup

- After the turn-recording cleanup, `import_session_snapshot(...)` was still one of the obvious big shapes in the runtime manager.
- On closer inspection, the problem was no longer hidden orchestration logic:
  - the real logic already lived in the registry/snapshot handlers
  - the manager was mostly keeping a very wide kwargs-style transport signature
  - and rebuilding `RuntimeSessionSnapshotImportCommand(...)` inline
- That made this a good boundary-cleanup slice rather than a new abstraction slice:
  - the lower layer already had the right command object
  - the manager simply had not adopted it yet
- Moving the manager to the command object cleaned up more than just one method body:
  - tests now use the same import contract as the runtime
  - the shared-session walkthrough helper now uses the same contract too
  - the snapshot-import seam is more explicit about what is being passed across the boundary
- One useful follow-up fell out of the broader regression run:
  - the readiness walkthrough script still encoded the old signature
  - catching that in the runtime bundle was helpful because it proved the new surface is now exercised outside of unit tests too
- This slice is a good example of a better cleanup heuristic for the remaining work:
  - when a method looks large, first ask whether the bulk is actual business logic or just an over-wide interface
  - here the right fix was interface consolidation, not another handler
- The remaining runtime-manager hotspots are therefore increasingly “real”:
  - `__init__` is still the main composition blob
  - several operator-facing methods still look mid-sized, but many of them now mostly contain response shaping and session lookup rather than hidden orchestration

## 2026-04-13 P30.7af Turn Recording Surface Consolidation

- After the registry/operator/cancel-approval extractions, the runtime manager transcript surface was mostly thin already.
- One small but honest boundary leak still remained:
  - `record_turn(...)` was still composing two transcript writes inline in the manager
  - even though `RuntimeSessionTurnScopeHandler` was already the real owner of message/activity/pending-approval recording
- This was a good follow-up because it keeps the refactor honest without overreacting:
  - we did not add another handler
  - we simply let the existing turn-scope owner also own the two-message convenience mutation
- The payoff is modest in file length but useful in boundary clarity:
  - `record_turn(...)` now lives beside `record_message(...)`
  - transcript mutation sequencing is less split across manager + handler
  - the runtime manager reads more consistently as an outer facade
- This slice also confirmed an important heuristic for the ongoing cleanup:
  - not every remaining thick-ish method deserves a brand-new abstraction
  - some of the best progress now comes from finishing ownership handoffs inside the seams we already extracted
- The remaining hotspots are therefore more meaningful:
  - `__init__` is still the dominant composition blob
  - `import_session_snapshot(...)` is still the clearest remaining orchestration body
  - several command-facing methods still look large in raw line counts, but many are already thin enough that further extraction could become churn rather than improvement

## 2026-04-13 P30.7ae Cancel / Approval Operator-Surface Follow-Up

- After the larger operator-surface extraction, two operator-facing branches still stood out as leftover exceptions:
  - `cancel_session_turn(...)`
  - `resolve_pending_approval(...)`
- They were already relying on the extracted interrupt domain handler for the business rules.
- What remained inline in the manager was mostly orchestration:
  - distinguish live session vs persisted-only record
  - append transcript entries
  - preserve approval waiter finalization ordering
- That made this a good follow-up because it completes the operator boundary instead of leaving two special cases behind.
- One subtle behavior had to stay intact:
  - approval waiters must only be finalized after the transcript entry is recorded
  - otherwise the resumed turn can race ahead of the operator-facing approval record
- Another subtle behavior also stayed explicit:
  - persisted-but-not-live sessions still return the earlier `409` responses for cancel/approval instead of silently restoring a session and mutating it
- This slice did not materially reduce total file length the way the earlier registry/operator cuts did.
- It still matters because it reduces exception paths:
  - cancel/approval now belong to the same operator-command surface as control/context/memory/skill/model/policy
  - the runtime manager has fewer “but this one is special” orchestration branches left inline

## 2026-04-13 P30.7ad Session Operator Handler Extraction

- After the session-registry extraction, the remaining runtime-manager thickness was no longer hidden:
  - it was the operator-command surface
  - the manager still owned the orchestration body for control/context/memory/skill/model/policy commands
- By this point those methods were mostly composing already-extracted business handlers:
  - control handler
  - context-policy handler
  - memory command handler
  - skill command handler
  - model-selection handler
  - runtime-policy handler
- That made this a good extraction target because the manager was still thick mostly due to orchestration, not domain ownership.
- The new operator handler now owns:
  - command normalization
  - lock/coordinator composition
  - response shaping
  - busy/queue handling around skills and runtime-memory mutations
  - the remaining transport-facing command transcript shaping for this surface
- Two behavior details were worth preserving explicitly:
  - command metadata spelling:
    - `kb_off` must stay `kb_off`
    - `mcp_reload` is still rendered as `mcp reload`
  - MCP cleanup monkeypatchability:
    - tests patch `mini_agent.runtime.main_agent_runtime_manager.cleanup_mcp_connections`
    - injecting `lambda: cleanup_mcp_connections()` from the manager preserves that seam
    - passing the raw function object would have been cleaner-looking but behaviorally worse for the existing contract
- This slice materially changes the feel of the runtime boundary:
  - registry orchestration now lives in one handler
  - operator-command orchestration now lives in another
  - the manager is much closer to a genuine outer facade rather than a mixed bag of orchestration blocks

## 2026-04-13 P30.7ac Session Registry Handler Extraction

- After the direct-wiring cleanup, the next remaining runtime-manager thickness was not hidden anymore:
  - it was the session registry orchestration itself
  - the manager still owned the full body for acquire/create/import/export/list/detail/recent flows
- Those methods were no longer one-off special cases:
  - they all coordinated the same registry truth
  - active in-memory sessions
  - persisted session records
  - restore/hydrate entry
  - catalog-backed read views
- The clean next move was therefore not another micro-helper:
  - it was one registry-level handler that composes the existing lower-level handlers
  - `access`
  - `creation`
  - `snapshot`
  - `catalog`
- This keeps the architecture honest:
  - runtime manager still owns the `_store_lock` and `_sessions`
  - registry orchestration no longer lives inline beside command execution and live-session mutation logic
- One useful design constraint stayed in place:
  - the registry handler does not introduce a new source of truth
  - it receives the live session map and delegates restore/import back through the existing hydration path
  - so we reduced ownership sprawl rather than moving it sideways
- This cut also clarifies the next runtime seam:
  - session registry plumbing is now much less mixed into the manager
  - the remaining hot spots are more clearly command/mutation orchestration rather than session inventory control

## 2026-04-13 P30.7ab Runtime Manager Direct-Wiring Cleanup

- After the extraction wave, `MainAgentRuntimeManager` still had one quieter form of thickness:
  - it was no longer owning much of the read-model/diagnostics/runtime-memory behavior
  - but it was still pretending to own it through a layer of pass-through helpers
- That is a real boundary smell even when behavior is correct:
  - collaborators look extracted on paper
  - but the composition still routes back through the manager for no semantic reason
- The right next move was not another handler:
  - most of the remaining code was not domain logic
  - it was forwarding logic
  - so the honest fix was direct wiring, not more abstraction
- This cleanup now wires extracted collaborators together directly where possible:
  - `RuntimeSessionDiagnosticsService`
  - `RuntimeSessionReadModelBuilder`
  - `RuntimeTaskMemoryBackendAdapter`
  - `RuntimeSessionCatalogHandler`
  - `RuntimeSessionRestoreHandler`
  - `RuntimeSessionSnapshotHandler`
- One important nuance had to stay intact:
  - agent rebuilds still capture prepared-context state through `RuntimeSessionTurnScopeHandler`
  - that preserves the existing persistence side effect during rebuild/reconfigure flows
  - switching that seam directly to the hydrator would have made the code shorter but weakened the behavior contract
- A second nuance surfaced during verification:
  - some builder methods intentionally use keyword-only arguments such as `recent_limit=` and `transcript=`
  - those cannot always be handed around as raw callables
  - the correct boundary is therefore:
    - direct wiring where signatures already match
    - tiny lambda shims only where signature shaping is structurally required
- This slice is valuable because it removes “fake thinness”:
  - the runtime manager now delegates to real owners more directly
  - fewer manager-local helper names need to be mentally traversed before reaching the real implementation
  - the extracted seams are now more honest to the architecture we have been moving toward

## 2026-04-13 P30.7aa TUI Gateway Client Payload Shaping Consolidation

- After consolidating interaction binding in application services, the same payload-shaping duplication still existed one layer out in the TUI client:
  - `TuiGatewayClient` repeatedly rebuilt:
    - session interaction context payloads
    - create-session payloads
    - chat payload/query shapes
- This was the same pattern as before, but the right fix here was local, not cross-layer:
  - the TUI client should stay self-contained
  - it should not depend on application-layer request/binding types
- The client now has lightweight internal helpers instead:
  - `_GatewaySessionBinding`
  - `_create_session_payload(...)`
  - `_chat_payload(...)`
- That keeps the layer boundaries clean while still removing the duplication:
  - session context payload normalization is centralized within the TUI client
  - async/sync create-session paths share one normalization seam
  - `run_chat(...)` and `stream_chat_events(...)` now share the same chat payload shape
- This is also close to the natural stopping point for this family of cleanup:
  - what remains in the client payloads is mostly operation-specific data
  - further abstraction would likely compress unlike operations together for little gain

## 2026-04-13 P30.7z Session Surface Binding Reuse Across Services

- After request adaptation was unified for chat entrypoints, one smaller duplication cluster still remained in the session-facing services:
  - `SessionApplicationService`
  - `RemoteSessionService`
- Both were repeatedly unpacking the same interaction-context fields:
  - `surface`
  - `channel_type`
  - `conversation_id`
  - `sender_id`
- That duplication was not large enough to justify another heavy handler extraction, but it was still a real boundary leak:
  - both services were manually rebuilding the same interaction kwargs
  - that made it too easy for one path to quietly forget a field in the future
- The existing `SessionSurfaceBinding` was already the right abstraction; it just had not been promoted into a reusable adapter.
- It now owns:
  - `from_values(...)`
  - `from_request(...)`
  - `as_kwargs()`
- Both service layers now reuse that one binding:
  - `SessionApplicationService` for runtime-manager calls and managed-turn construction
  - `RemoteSessionService` for gateway-client calls and default create-session payload shaping
- This is the right stopping point for this slice:
  - the repeated interaction-context unpacking is now centralized
  - the remaining fields being forwarded are mostly operation-specific business fields, not generic surface context
  - further abstraction here would likely start drifting into abstraction-for-its-own-sake

## 2026-04-13 P30.7y Interaction Request Adapter Extraction + Channel Smoke Repair

- After the gateway use case became thin, the next duplication was smaller but still real:
  - gateway chat entrypoints normalized interaction labels and built internal chat-execution requests
  - channel-ingress did another version of the same work when forwarding remote messages into main-agent chat
- That duplication was not worth another heavy handler split, but it was worth one shared application seam.
- A dedicated interaction request adapter now owns that conversion layer:
  - `src/mini_agent/application/interaction_request_adapter.py`
  - it handles:
    - normalized interaction binding creation
    - `ChannelMessageRequest -> MainAgentChatRequest`
    - `MainAgentChatRequest/stream args -> GatewayChatExecutionRequest`
- This keeps the architecture cleaner without over-fragmenting it:
  - gateway and channel-ingress now share one request adaptation boundary
  - remote adapter expansion can reuse the same interaction binding instead of re-copying surface/channel fields
- The follow-up smoke run also exposed two real repo-readiness issues outside the Python application core:
  - `scripts/qq_wechat_smoke.py` assumed WeChat `dist/index.js` already existed
  - the local Node package `src/channels/types` used a brittle `tsc` prepare script that failed during dependency install
- Those were corrected at the repo boundary instead of hand-waving around them:
  - `qq_wechat_smoke.py` now bootstraps missing Node workspaces before launch
  - `src/channels/types/package.json` now uses an explicit `npx -p typescript tsc` build command
  - the smoke now validates oversized-body rejection as a hard failure response, not only a literal `413`
- Result:
  - application-layer request adaptation is more consistent
  - the QQ/WeChat smoke script is again usable on a fresh-ish checkout instead of depending on prebuilt artifacts

## 2026-04-13 P30.7x Gateway Route Execution Handler Extraction

- After moving chat-flow orchestration and main-route execution hooks out, `MainAgentGatewayUseCases` still owned the routed execution shell:
  - parse `/delegate`
  - resolve message route
  - record routing diagnostics
  - execute delegation
  - fall back to the main agent on delegation failure
- That meant the use case was still both:
  - a top-level entrance coordinator
  - and the concrete route/delegation execution engine
- A dedicated route-execution handler now owns that cluster:
  - `src/mini_agent/application/gateway_route_execution_handler.py`
  - it handles:
    - delegation command parsing
    - route resolution + route-stat bookkeeping
    - delegation execution
    - delegation failure fallback to main-agent execution
    - shaping delegation payloads and supplemental stream events
- This leaves `MainAgentGatewayUseCases` in a much clearer role:
  - normalize gateway entry requests
  - forward session operations to the session service
  - hand chat turns to dedicated chat-flow / route-execution handlers
- At this point the use case is close to the intended thin boundary:
  - most remaining methods are straightforward pass-through entrypoints
  - the next refactor no longer has to start from a large mixed orchestration object

## 2026-04-13 P30.7w Gateway Agent Execution Handler Extraction

- After the chat-flow shell moved out, `MainAgentGatewayUseCases` still carried the lower-level main-route execution cluster:
  - single-turn agent execution
  - runtime approval hook construction
  - runtime activity hook construction
  - tool-call preview / output formatting helpers
- That meant the use case still knew too much about how a turn is executed instead of just deciding which route should handle the turn.
- A dedicated execution handler now owns that cluster:
  - `src/mini_agent/application/gateway_agent_execution_handler.py`
  - it handles:
    - one-shot agent execution against a managed turn
    - approval hook injection / restoration
    - activity hook emission
    - tool activity preview / output shaping
- `MainAgentGatewayUseCases` is thinner again:
  - it still resolves routes
  - it still decides delegation vs main-route execution
  - but it no longer builds runtime execution hooks inline
- The next obvious target is now the remaining routed execution shell:
  - `_run_routed_message(...)`
  - `_run_delegation_with_fallback(...)`
  - route-resolution bookkeeping helpers

## 2026-04-13 P30.7v Gateway Chat Flow Handler Extraction

- After the turn-scope lifecycle moved out, the next duplication was higher up in the application layer:
  - `run_chat(...)`
  - `stream_chat_events(...)`
- Those methods were no longer mostly about routing decisions; they were carrying repeated top-level chat orchestration:
  - dry-run behavior
  - turn preparation and bootstrap error shaping
  - response finalization
  - stream heartbeat / delta / done framing
- A dedicated gateway chat-flow handler now owns that shell:
  - `src/mini_agent/application/gateway_chat_flow_handler.py`
  - it handles:
    - dry-run response/stream paths
    - turn preparation
    - non-streaming finalization
    - streaming heartbeat / delta / done coordination
- This keeps the layering cleaner:
  - application chat-flow orchestration has one home
  - `MainAgentGatewayUseCases` now mainly supplies routed execution logic
  - runtime/session concerns remain below in the session service / runtime layers
- The next decomposition target is now more obvious:
  - routed execution internals still live together in the use case:
    - `_run_agent_once(...)`
    - approval hook construction
    - activity hook construction
    - delegation fallback execution

## 2026-04-13 P30.7u Turn Scope Orchestration Extraction

- After the command-entry work, the next orchestration-heavy cluster was not another command path; it was the managed turn scope itself.
- `ManagedSessionTurn` had become a hidden runtime coordinator:
  - acquire/release session lock
  - bind active surface
  - apply queued model / skill changes
  - pull recovery context
  - mark the turn running / finished
  - record the first user message
- That was too much lifecycle knowledge for an application-layer context manager to carry directly.
- A dedicated runtime turn-scope handler now owns that layer:
  - `src/mini_agent/runtime/session_turn_scope_handler.py`
  - it handles:
    - turn enter / exit orchestration
    - turn-scoped message/activity/approval persistence helpers
    - recovery-context clearing
    - prepared-context capture / restore
- This improves the architecture in two useful ways:
  - the application layer now consumes a runtime turn seam instead of rebuilding runtime lifecycle steps inline
  - manager helper methods for turn-scoped mutations now delegate to the same seam instead of each persisting separately
- This is a better setup for the next chat-execution cut:
  - turn enter / exit mechanics are now isolated
  - later refactors can focus on routing, run/stream execution, and event emission without dragging basic session-turn state transitions along with them

## 2026-04-13 P30.7t Skill + Model Command Shell Follow-Up

- The initial command coordinator extraction solved the largest duplication, but not all of it:
  - `manage_session_skills(...)` still had a bespoke success-path lock block
  - `update_session_model_selection(...)` still owned its own full lock/mutate/persist flow
- That mattered because these methods were no longer carrying unique domain logic; they were mostly carrying leftover orchestration shells.
- The useful refinement was not another business handler; it was making the command coordinator slightly more expressive:
  - result-dependent `touch`
  - result-dependent `persist`
- That small capability is what lets one shared command shell cover both:
  - skill mutation success vs busy recheck outcomes
  - model-selection queued vs applied outcomes
- This keeps the boundary cleaner:
  - business decisions still come from the extracted handlers
  - manager still shapes transport responses
  - the common lock/touch/persist shell now lives in one place even when the result decides whether persistence should happen
- An important constraint stayed preserved:
  - model selection still does not gain a new transcript side effect
  - the refactor only unified orchestration, not operator-visible behavior

## 2026-04-12 P30.7s Session Command Coordinator Extraction

- After the earlier handler cuts, the manager still repeated the same command-entry shell in several methods:
  - load session
  - acquire runtime lock
  - execute the command mutation
  - append a command transcript entry
  - touch and persist
- By that point the business logic had already been extracted, but the orchestration shell itself was still duplicated.
- That duplication matters because it keeps the manager thick in a subtler way:
  - not by owning domain logic
  - but by re-implementing the same command lifecycle envelope around several extracted handlers
- A dedicated coordinator now owns that shell:
  - `src/mini_agent/runtime/session_command_coordinator.py`
  - it handles:
    - locked command execution
    - optional transcript construction/append
    - touch/persist ordering
- This extraction became especially important for `update_session_runtime_policy(...)`:
  - it was the last obvious command-shaped method still doing mutation work while inside `_store_lock`
  - moving it onto the shared command seam restores the intended lock layering:
    - `_store_lock` for session lookup/registry access
    - `session.runtime.lock` for live-session command mutation
- The architecture is cleaner now:
  - command business semantics live in dedicated handlers
  - command shell orchestration lives in one coordinator
  - manager invokes both instead of re-implementing either layer inline

## 2026-04-12 P30.7r Session Agent-Runtime Handler Extraction

- After session catalog extraction, the next manager-owned cluster was agent runtime rebuild / reconfiguration:
  - desired/effective runtime policy inspection
  - live-agent runtime policy reconfigure
  - rebuild with selected model identity
  - pending model-selection application
  - pending skill-reload application
  - workspace skill-reload queue mutation
- Those behaviors all belonged to the same concern:
  - mutating the live agent host and the session state that depends on that host
- Keeping them inline in `MainAgentRuntimeManager` meant the manager was still partly acting as an agent-host controller instead of only orchestrating around one.
- A dedicated agent-runtime handler now owns that layer:
  - `src/mini_agent/runtime/session_agent_runtime_handler.py`
  - it handles:
    - runtime policy inspection
    - live-agent runtime policy reconfiguration
    - rebuild with selected identity
    - pending model-selection application
    - pending skill-reload application
    - workspace skill-reload queue mutation
- `MainAgentRuntimeManager` now keeps the right outer responsibilities:
  - decide when these flows should happen
  - hold lock/persist/transcript boundaries
  - delegate the actual live-agent host mutation work
- This extraction also improved the runtime graph consistency:
  - runtime-policy planning now consumes the same desired/effective policy seam that rebuild paths use
  - model-selection and skill-reload paths now share one rebuild boundary instead of reaching into separate inline helpers
  - workspace skill-reload queueing no longer carries its own mutation logic in the manager
- The broader architecture is now more coherent:
  - session access decides reuse / restore / create
  - session creation builds brand-new state
  - session restore hydrates persisted/imported state
  - session live-state handler mutates active in-memory session state
  - session catalog handler owns directory/catalog semantics
  - session agent-runtime handler owns live agent-host mutation
  - manager orchestrates across those seams rather than implementing them inline

## 2026-04-12 P30.7q Session Catalog Handler Extraction

- After live-state extraction, the next manager-owned cluster was session catalog / metadata routing:
  - latest active-session lookup by workspace
  - latest persisted-session lookup by workspace
  - workspace-local title allocation
  - list/detail/recent-message routing
  - remote-channel summary dedupe
  - rename/share metadata mutations
- Those behaviors were related, but they were still spread across several manager helpers and entrypoints.
- That kept `MainAgentRuntimeManager` doing too much directory/catalog work instead of only orchestrating around it.
- A dedicated catalog handler now owns that layer:
  - `src/mini_agent/runtime/session_catalog_handler.py`
  - it handles:
    - latest active/persisted workspace lookup
    - human-readable title allocation
    - list/detail/message read routing
    - session summary dedupe for remote-channel duplicates and hidden stubs
    - rename/share metadata mutation semantics
- `MainAgentRuntimeManager` now keeps the right outer responsibilities:
  - orchestrate lock boundaries
  - invoke the catalog handler
  - persist mutations
  - update live session registry where needed
- This extraction improves the runtime shape in two useful ways:
  - session access and session creation now consume the same catalog boundary for title allocation and workspace lookup
  - list/detail/message/read paths no longer have their own mini directory logic embedded in the manager
- The broader architecture is now more coherent:
  - session access decides reuse / restore / create
  - session creation builds brand-new runtime state
  - session restore hydrates persisted/imported runtime state
  - session live-state handler mutates active in-memory runtime state
  - session catalog handler owns directory/catalog semantics
  - manager orchestrates across those seams rather than implementing them inline

## 2026-04-12 P30.7p Session Live-State Handler Extraction

- After session creation moved out, the next manager hotspot was the live session mutation cluster:
  - surface binding
  - turn start / finish flags
  - transcript append helpers
  - activity aggregation
  - pending approval normalization / cleanup
  - recovery-context cleanup/build
  - runtime reset state cleanup
- These behaviors were tightly related, but they were still implemented as manager-owned low-level helpers.
- That kept `MainAgentRuntimeManager` in the wrong role:
  - it was coordinating flows
  - but it was also directly acting as the live session state machine
- A dedicated live-state handler now owns that mutation layer:
  - `src/mini_agent/runtime/session_live_state_handler.py`
  - it handles:
    - surface/channel binding semantics
    - transcript append and activity-entry reuse
    - busy/running/pending-approval turn state mutations
    - recovery-context build and clearing
    - runtime reset cleanup for live sessions
    - normalized pending-approval parsing reused by other runtime seams
- `MainAgentRuntimeManager` now keeps the right outer responsibilities:
  - acquire locks
  - invoke the live-state handler
  - persist session state
  - coordinate higher-level flows around commands, turns, and restarts
- This extraction also improves consistency across the runtime graph:
  - read-model and interrupt seams now reuse the same pending-approval normalization boundary
  - transcript and surface semantics no longer exist as an inline helper cluster inside the manager
  - recovery/reset semantics stay attached to the same live-session mutation layer instead of being spread across manager helpers
- The architecture is getting cleaner in the intended direction:
  - session access decides whether to reuse / restore / create
  - session creation builds brand-new state
  - session restore hydrates persisted/imported state
  - session live-state handler mutates active in-memory state
  - manager orchestrates across those seams instead of implementing them inline

## 2026-04-12 P30.7o Session Creation Handler Extraction

- After session-access extraction, the next manager-owned duplication was brand-new session construction:
  - `get_or_create_session(...)` create-new branch
  - `create_session(...)`
  were both rebuilding the same runtime state inline.
- The duplicated construction was not just a few assignments:
  - build agent
  - bootstrap lifecycle
  - normalize title and surface shape
  - derive knowledge-base and sandbox diagnostics
  - seed selected-model projection fields
- That made session creation another hidden implementation detail inside the manager instead of a reusable runtime boundary.
- A dedicated creation handler now owns that work:
  - `src/mini_agent/runtime/session_creation_handler.py`
  - it handles:
    - title normalization and workspace-local allocation
    - surface/channel normalization with the existing semantics preserved
    - fresh agent bootstrap
    - lifecycle bootstrap
    - projection assembly for brand-new sessions
    - selected-model projection seeding from the routed runtime identity
- `MainAgentRuntimeManager` now keeps the right outer responsibilities:
  - run workspace/capacity guardrails
  - request a new session from the creation handler
  - register it in `_sessions`
  - persist it
- This is a meaningful cleanup rather than cosmetic extraction:
  - session creation is now one runtime seam shared by both explicit creation and access-driven creation
  - the manager no longer has two slightly diverging inline constructors that could drift over time
  - title-hint and default-surface behavior stay explicit without keeping duplicated state assembly in the manager
- The broader direction is getting more consistent:
  - session access decides reuse vs restore vs create
  - session creation builds brand-new runtime state
  - session restore hydrates persisted/imported runtime state
  - the manager coordinates across those seams instead of implementing each one inline

## 2026-04-12 P30.7n Session Model Selection Handler Extraction

- After `/memory` and `/skill` were extracted, the next manager-owned decision branch was model selection:
  - request normalization
  - busy vs idle selection semantics
  - queued vs immediate-apply response shaping
  - pending-selection eligibility on the next turn
- That logic was smaller than `/memory` or `/skill`, but it still mixed runtime orchestration with domain decisions.
- A dedicated handler now owns that selection logic:
  - `src/mini_agent/runtime/session_model_selection_handler.py`
  - it handles:
    - request normalization
    - plan generation for immediate apply vs queued apply
    - no-op selected behavior when the requested model is already active
    - pending-selection eligibility for deferred application
- `MainAgentRuntimeManager` now keeps only the outer model-selection responsibilities:
  - load session
  - lock the runtime host
  - apply pending-state mutations
  - optionally rebuild the agent
  - persist
  - wrap the transport response
- This is a useful refinement even though the old branch was not huge:
  - it keeps the decomposition pattern consistent across memory / skill / model
  - it makes future runtime-policy extraction less likely to collapse back into another mixed branch
  - it centralizes the queued/immediate model semantics in one testable seam
- The broader regression run also surfaced a separate but valuable cleanup:
  - `scripts/shared_session_gateway_walkthrough.py` still used stale flat-session fields (`busy`, `running_state`, `agent`)
  - the runtime has already been grouped into `projection` / `runtime`
  - syncing the walkthrough script to that shape removed another source of misleading breakage during future refactor validation

## 2026-04-12 P30.7m Session Skill Command Handler Extraction

- After `/memory` was extracted, the next manager hotspot was `/skill`:
  - catalog availability handling
  - read action routing
  - workspace policy/install mutation routing
  - reload queue metadata formatting
  - transcript command-name construction
- That branch was doing the same thing the old `/memory` branch had been doing:
  - mixing runtime orchestration with operator-command formatting and validation
- A dedicated handler now owns the skill-command business branch:
  - `src/mini_agent/runtime/session_skill_command_handler.py`
  - it handles:
    - supported-action validation
    - skill catalog availability / disabled-state handling
    - read action payload assembly
    - mutation preparation for policy/install/uninstall/rollback/refresh
    - busy-queue metadata formatting
    - final command transcript naming
- `MainAgentRuntimeManager` now keeps the right outer responsibilities for `/skill`:
  - load session
  - coordinate busy/lock boundaries
  - queue workspace skill reloads
  - rebuild the active session agent
  - append transcript entries
  - persist session state
  - wrap transport response payloads
- This slice also surfaced a real latent bug:
  - `uninstall` and `rollback` were already implemented in the old inline branch
  - but the accepted action whitelist did not include them
  - so command catalog / TUI command handling advertised actions the runtime entrypoint could reject
- The handler extraction was a good moment to fix that cleanly:
  - no compatibility shim
  - no duplicate path
  - just one corrected runtime action surface with direct regression coverage
- The runtime decomposition pattern is now clearer and more reusable:
  - diagnostics / hydration / runtime-memory / policy coordination are extracted
  - `/memory` command routing is extracted
  - `/skill` command routing is extracted
  - the manager is increasingly a thin orchestration shell instead of a behavior god-object

## 2026-04-12 P30.7l Session Memory Command Handler Extraction

- After the lifecycle/policy extraction, the next manager hotspot was not infrastructure anymore but behavior routing:
  - `/memory` still bundled action validation, selector resolution, durable-memory reads, runtime-memory reads, and mutation formatting inside one method
  - at the same time the manager also owned the outer lock/transcript/persist envelope around that branch
- That was a strong signal the next shrink step should be command-handler decomposition, starting with the memory surface.
- A dedicated handler now owns the memory-command business branch:
  - `src/mini_agent/runtime/session_memory_command_handler.py`
  - it handles:
    - supported-action validation
    - read vs mutation routing
    - durable-memory and runtime-memory payload assembly
    - session/shared selector resolution
    - mutation result shaping for `refresh`, `shared_clear`, `promote_*`, and `save_*`
- `MainAgentRuntimeManager` now keeps the right outer responsibilities for `/memory`:
  - load session
  - enforce busy/lock boundaries
  - append command transcript entries
  - persist session state
  - wrap transport response payloads
- This is a healthier boundary than the previous inline branch:
  - memory behavior has a runtime-local home without dragging transcript/persistence with it
  - manager stays on orchestration duty instead of acting as both coordinator and command formatter
  - later `/skill` and `/model` cuts can follow the same pattern
- The architecture direction is now clearer:
  - hydration structure -> `session_hydration_builder.py`
  - runtime-state sync -> `session_runtime_state_hydrator.py`
  - diagnostics -> `session_diagnostics_service.py`
  - runtime-memory backend -> `session_runtime_memory_backend_adapter.py`
  - persistence internals -> registry/store helpers
  - policy/lifecycle rules -> `session_runtime_policy_coordinator.py`
  - memory command routing -> `session_memory_command_handler.py`
  - manager -> orchestration shell

## 2026-04-12 P30.7k Lifecycle / Policy Coordination Extraction

- After the persistence-wrapper cleanup, the next large non-orchestration cluster inside the manager was lifecycle/policy coordination:
  - workspace guardrails
  - single-main admission checks
  - team saturation/workspace-conflict counters
  - session lifecycle refresh/reset counting
  - runtime diagnostics payload assembly for those counters
- That was a good extraction target because it was:
  - shared across several entrypoints (`get_or_create`, `create`, `import`, diagnostics)
  - rule-heavy rather than hydration/persistence-heavy
  - already conceptually separate from session structure and runtime backends
- A dedicated coordinator now owns those rules and counters:
  - `src/mini_agent/runtime/session_runtime_policy_coordinator.py`
- The coordinator now handles:
  - main-workspace enforcement
  - single-main active-workspace admission checks
  - team capacity enforcement
  - team conflict/saturation counters
  - expired-session id selection
  - lifecycle refresh/reset counting
  - runtime diagnostics payload construction
- `MainAgentRuntimeManager` now keeps lifecycle/policy coordination as wrapper/delegation behavior rather than owning the counter and rule implementations directly.
- This further sharpens the architecture:
  - hydration structure -> `session_hydration_builder.py`
  - runtime-state sync -> `session_runtime_state_hydrator.py`
  - diagnostics -> `session_diagnostics_service.py`
  - runtime-memory backend -> `session_runtime_memory_backend_adapter.py`
  - persistence internals -> metadata registry + shared transcript store
  - policy/lifecycle rules -> `session_runtime_policy_coordinator.py`
- The manager is now much closer to what we wanted:
  - orchestration and flow control
  - not storage internals
  - not backend wiring details
  - not diagnostics implementation
  - not policy counter ownership
- The remaining large seams are now mostly higher-level decomposition questions:
  - command-handler decomposition
  - some memory/skill command branches
  - possibly splitting model/runtime reconfiguration flows further

## 2026-04-12 P30.7j Persistence Wrapper Internals Extraction

- After the runtime-memory backend adapter cut, `_MainAgentRuntimePersistence` was already clearly a wrapper, but it still owned low-level file mechanics:
  - metadata JSON read/write
  - shared transcript path resolution
  - shared transcript file read/write/delete
- That meant the wrapper was conceptually thin, but still operationally doing too much.
- Two dedicated persistence-internal helpers now own those concerns:
  - `src/mini_agent/runtime/session_persistence_metadata_registry.py`
  - `src/mini_agent/runtime/session_shared_transcript_store.py`
- `_MainAgentRuntimePersistence` now composes them instead of carrying the details inline:
  - `SessionPersistence` still handles session transcript/message persistence
  - metadata registry handles runtime metadata upsert/list payload access
  - shared transcript store handles the runtime shared transcript sidecar file lifecycle
- This improves the boundary without changing the outer behavior:
  - save/load/list/delete behavior remains stable
  - loader/builder seams remain unchanged
  - the wrapper is now closer to a composition root than a low-level file handler
- The remaining larger seams are now mostly orchestration-level:
  - lifecycle/policy coordination
  - command-handler decomposition
  - possibly splitting broader memory/skill command branches out of the manager later

## 2026-04-12 P30.7i Runtime-Memory Backend Adapter Extraction

- After diagnostics extraction, the next concrete dependency still leaking through the manager was direct `WorkspaceMemoriaRuntime` access.
- The problem was not only duplication, but inconsistency of access style:
  - hydration and snapshot flows used manager-owned helper methods
  - cleanup/reset paths used manager-owned helper methods
  - runtime-memory command flows instantiated `WorkspaceMemoriaRuntime` inline
- That meant the same backend was being reached through multiple shapes from one coordinator class.
- A dedicated runtime-memory backend adapter now owns those backend calls:
  - `src/mini_agent/runtime/session_runtime_memory_backend_adapter.py`
  - it wraps:
    - session/workspace-shared snapshot payload export
    - session/workspace-shared payload restore
    - session/workspace-shared namespace clearing
    - runtime-memory entry lookup
    - runtime-memory promotion operations
- `MainAgentRuntimeManager` no longer directly instantiates `WorkspaceMemoriaRuntime`.
- The shared adapter is now used by:
  - `session_read_model_builder.py` snapshot export wiring
  - `session_runtime_state_hydrator.py` restore wiring (through manager injection)
  - runtime-memory command flows in the manager
  - reset/delete cleanup wrappers in the manager
- This is a better infrastructure boundary:
  - the manager no longer knows how to construct the backend
  - runtime-memory backend access is consistent across hydration, snapshot, cleanup, and command paths
  - future backend changes or testing seams now have a single runtime-layer entry point
- The next remaining seams are now even more clearly orchestration-side:
  - persistence wrapper internals
  - lifecycle/policy coordination
  - possibly command-handler decomposition inside the manager if we continue shrinking it

## 2026-04-12 P30.7h Session Diagnostics Service Extraction

- After the runtime-state hydrator cut, diagnostics remained the next shared concern still rooted in the manager:
  - memory diagnostics served hydration, runtime capture, and read-model construction
  - sandbox diagnostics served hydration, persistence refresh, and read-model construction
- That was a strong sign diagnostics wanted their own service boundary:
  - they are shared computations
  - they are not orchestration
  - and they are not part of session-structure assembly
- A dedicated diagnostics service now owns those computations:
  - `src/mini_agent/runtime/session_diagnostics_service.py`
  - it handles:
    - memory diagnostics from live sessions
    - memory diagnostics from persisted records
    - sandbox diagnostics from live sessions
    - sandbox diagnostics from persisted records
- The new service is now consumed by three different runtime seams:
  - `session_hydration_builder.py` for persisted-record normalization
  - `session_runtime_state_hydrator.py` for runtime refresh flows
  - `session_read_model_builder.py` for summary/detail/snapshot construction
- `MainAgentRuntimeManager` now mainly provides wrapper methods for diagnostics rather than owning their implementations.
- This is a healthier direction for the runtime boundary:
  - structure assembly lives in the hydration builder
  - live runtime synchronization lives in the runtime-state hydrator
  - diagnostics computation lives in the diagnostics service
  - manager continues shrinking toward pure orchestration
- The remaining candidates are now more infrastructural than structural:
  - runtime-memory backend accessors (`WorkspaceMemoriaRuntime` adapters)
  - persistence wrapper internals
  - possibly a session-lifecycle/session-policy coordination service if we want the manager thinner still

## 2026-04-12 P30.7g Session Runtime State Hydrator Extraction

- After hydration unification, the next mixed responsibility became the shared hydration helper itself:
  - `_hydrate_session_unlocked(...)` no longer duplicated session assembly
  - but it still directly restored runtime-memory payloads, restored prepared-context state onto the live agent, and refreshed diagnostics
- That was the wrong boundary:
  - session hydration decides what state should exist
  - runtime-state hydration decides how that state is synchronized into the live runtime host and workspace memory backends
- A dedicated runtime-state hydrator now owns those runtime synchronization substeps:
  - `src/mini_agent/runtime/session_runtime_state_hydrator.py`
  - it handles:
    - runtime task-memory restore
    - workspace-shared runtime-memory merge
    - prepared-context restore onto the live agent
    - prepared-context capture from the live agent
    - memory/sandbox diagnostics refresh
- `MainAgentRuntimeManager` now delegates:
  - post-build hydration substeps from `_hydrate_session_unlocked(...)`
  - prepared-context restore wrapper
  - prepared-context capture wrapper
- This is a cleaner ownership split:
  - `session_hydration_builder.py` owns normalized hydration payloads and session-structure assembly
  - `session_runtime_state_hydrator.py` owns live runtime-state synchronization
  - `MainAgentRuntimeManager` now sits more squarely as the coordinator between them
- The remaining larger seams are now clearer:
  - runtime-memory storage functions still live on the manager as static helpers
  - diagnostics builders still live on the manager because read-model construction depends on them too
  - if we keep shrinking, the next cuts are likely a `runtime memory adapter` or a `session diagnostics service`

## 2026-04-12 P30.7f Session Hydration Unification

- After the restore/load extraction, the next duplication moved into session hydration itself:
  - `import_session_snapshot(...)` still assembled runtime sessions inline
  - `_restore_persisted_session_unlocked(...)` had become smaller, but still ran a similar runtime assembly sequence
- That was the wrong shape for the next phase:
  - import and restore are different sources of session state
  - but once normalized, they should flow through the same runtime hydration pipeline
  - otherwise every future change to agent bootstrap, KB state, token restore, runtime memory restore, or prepared context restore has to be made twice
- The restore-specific builder was replaced with a hydration builder:
  - `src/mini_agent/runtime/session_hydration_builder.py`
  - it now covers both:
    - persisted-record hydration payload normalization
    - imported-snapshot hydration payload normalization
    - transcript import
    - session-state assembly
    - stored recovery projection application
- `MainAgentRuntimeManager` now has a shared hydration path:
  - `_hydrate_session_unlocked(...)`
  - both persisted restore and snapshot import delegate to that same helper
  - the helper now owns the common runtime assembly flow:
    - build agent
    - apply runtime policy overrides
    - restore messages/tokens
    - apply KB state
    - build lifecycle/session state
    - restore runtime-task/workspace-shared memory payloads when present
    - restore prepared-context state
    - refresh diagnostics
    - register session
- This is a better boundary for the next cut:
  - source normalization lives in the hydration builder
  - runtime assembly lives in a single helper
  - the manager no longer has one import-specific session constructor and one restore-specific constructor
- The hydration layer is still not the final endpoint:
  - runtime-memory restore and prepared-context restore are still hydrated inline in the manager helper
  - which makes them the next natural extraction target if we want to continue shrinking runtime orchestration further

## 2026-04-12 P30.7e Runtime Restore/Load Boundary Extraction

- After the persistence save builder cut, the next boundary problem was concentrated in restore/load:
  - `MainAgentRuntimeManager._restore_persisted_session_unlocked(...)` still knew too much about persisted-record shape
  - `_MainAgentRuntimePersistence.load_session_record(...)` still performed runtime-record normalization and transcript attachment inline
- That was the wrong ownership split:
  - transcript import and restore-payload normalization are reconstruction concerns
  - persistence should only read/write persisted artifacts
  - the runtime manager should orchestrate agent rebuild and runtime-only refresh, not hand-assemble recovered state buckets
- A dedicated runtime restore builder now owns the pure reconstruction side:
  - `src/mini_agent/runtime/session_restore_builder.py`
  - it handles:
    - transcript import from persisted records
    - restore-payload normalization
    - reconstructed `MainAgentSessionState` assembly
    - stored recovery snapshot application onto projection state
- A dedicated persistence loader now owns persisted runtime-record normalization:
  - `src/mini_agent/runtime/session_persistence_loader.py`
  - it filters runtime records by session kind
  - it attaches shared transcript payloads to loaded records
- The extracted seams improved boundary direction:
  - `RuntimeSessionReadModelBuilder` now depends on the restore builder's transcript importer instead of the runtime manager carrying that logic inline
  - `MainAgentRuntimeManager` now mainly coordinates:
    - build agent
    - apply runtime-policy override
    - restore agent messages/tokens
    - apply KB flag and prepared-context state
    - register recovered session
- The restore path is still not fully minimal yet:
  - runtime-memory restore and imported-snapshot creation still have overlap with persisted restore
  - but the large persisted-record reconstruction block is now extracted, which makes a later import/restore unification cut much more straightforward

## 2026-04-12 P30.7d Runtime Persistence Record Builder Extraction

- After the read-model builder extraction, the next persistence seam was easier to see:
  - `_MainAgentRuntimePersistence.save_session(...)` still did two different jobs
  - it performed file/metadata I/O
  - and it assembled the full runtime metadata record while also refreshing sandbox diagnostics
- That was the wrong ownership split:
  - record assembly is a serialization concern
  - sandbox refresh is runtime state maintenance
  - only the actual writes belong to persistence
- A dedicated runtime persistence builder now owns the serialization side:
  - `src/mini_agent/runtime/session_persistence_record_builder.py`
  - it builds:
    - transcript-entry payloads
    - persisted runtime metadata records
    - pending-approval payload serialization for stored metadata
- The runtime manager now owns the sandbox refresh explicitly inside `_persist_session_unlocked(...)` before calling persistence.
- This is a better boundary for the next runtime cut:
  - persistence save is no longer secretly reaching back into live runtime diagnostics collection
  - serialization concerns now have their own module instead of living inline in the persistence writer
  - `MainAgentRuntimeManager` remains the place where runtime state is refreshed before persistence
- The persistence layer is not fully minimal yet:
  - record loading and transcript attachment still live in `_MainAgentRuntimePersistence`
  - but the biggest save-path mixing has been removed, which makes a later restore-path extraction much more straightforward

## 2026-04-12 P30.7c Runtime Session Read-Model Builder Extraction

- Once runtime session state was grouped, the next real decomposition seam became much easier to isolate:
  - `MainAgentRuntimeManager` still contained the full summary/detail/snapshot assembly logic
  - recovery/message/pending-approval read-model helpers were still living beside runtime coordination
- The right next step was not persistence extraction yet:
  - persistence save/load still depends on the same read-model and snapshot shapes
  - extracting the read-model builder first means the later persistence cut can depend on a narrower builder seam instead of the whole runtime manager
- A dedicated runtime builder module now owns that read-model assembly:
  - `src/mini_agent/runtime/session_read_model_builder.py`
  - it receives normalization/diagnostic/snapshot callbacks from the runtime manager rather than reaching into runtime internals directly
- That design is important:
  - the builder is extracted, but not turned into a new god-service
  - it is still bounded to “assemble read models from already-owned data”
  - runtime manager remains the owner of execution state and runtime-side helper orchestration
- The manager still contains some thin wrapper methods after this cut:
  - that is acceptable for now because call sites remain stable while the large builder bodies are gone
  - the architectural win is that read-model construction now has a dedicated home and can evolve/test independently
- This cut did not yet solve persistence mixing:
  - `_MainAgentRuntimePersistence.save_session(...)` still shapes stored records inline
  - runtime manager still participates directly in record/snapshot save paths
  - that is now the most natural next runtime decomposition target

## 2026-04-12 P30.7b Runtime Session State Composition Cut

- After the TUI grouped-state cut and the projection-boundary cleanup, the runtime side still had the same structural smell in a different place:
  - `MainAgentSessionState` was still one flat object carrying session truth, runtime host state, and transcript state together
- The cleanest next cut was to split the data model before extracting more services:
  - if we extracted builders/persistence first, they would still depend on the same mixed field bag
  - once the grouped state exists, later extractions can be narrower and more honest
- The runtime session is now grouped into:
  - `projection`: session-facing truth, recovery caches, diagnostics, model selection
  - `runtime`: live agent host, cancel/approval state, lock
  - `transcript_state`: transcript entries plus turn/transcript indexing
- This is materially better even though `MainAgentRuntimeManager` is still large:
  - field ownership is now explicit in the core data model
  - session-service and runtime-manager code must choose which bucket they are touching
  - accidental mixing is harder because there is no longer a flat field bag to lean on
- The cut also revealed a useful constraint:
  - tests that reach into runtime session internals are currently part of the architecture contract for this refactor track
  - updating those tests was not noise; it confirmed the grouped-state model is visible and consistent at the runtime seam
- What this cut did not solve yet:
  - `MainAgentRuntimeManager` still owns too many responsibilities
  - persistence save/load logic is still inside the same manager path
  - `SessionService` still depends on `MainAgentSessionState` rather than a narrower lease/session interface
- That means the next clean runtime step is now clearer:
  - extract session projection/snapshot builders and/or persistence helpers out of the runtime manager
  - then narrow application-layer dependence on the grouped runtime session state

## 2026-04-12 P30.7a Session Projection Boundary Cleanup

- The runtime/session scan showed one cheap but important clean-up before the larger runtime-state split:
  - shared session read models still lived beside terminal-only presentation state
  - summary -> detail construction still depended on `summary.__dict__`
- That combination was structurally awkward:
  - `session/projection.py` could not honestly claim to be a shared read-model module while owning `TerminalSessionProjection`
  - `summary.__dict__` worked today, but it coupled runtime/session builders to dataclass internals and made future `slots=True` tightening harder
- The clean repair was to separate those two concerns now instead of carrying them into the next runtime refactor:
  - `TerminalSessionProjection` now lives in `src/mini_agent/tui/session_projection.py`
  - `SessionDetailProjection` now has an explicit `from_summary(...)` constructor
- This is a better boundary for the next runtime cuts:
  - shared session projections are now transport/application-facing only
  - terminal presentation is now clearly terminal-owned
  - detail-projection construction is explicit rather than relying on object internals
- The slice intentionally did not try to solve the larger runtime-manager problem yet:
  - `MainAgentSessionState` is still wide
  - `MainAgentRuntimeManager` is still oversized
  - but one source of projection/presentation mixing has been removed, which reduces noise for the next decomposition pass
- Focused regression stayed green across session projection, TUI, interaction-surface, and gateway use-case coverage.

## 2026-04-12 P30.2/P30.3 TUI Session State Composition Cut

- `TuiSession` was still the biggest local boundary leak after the entrance-contract fix:
  - projection data from remote/gateway sync
  - local runtime handles and resume state
  - chat-scroll / expand-collapse / cache state
  - all lived on one flat struct
- The safest next cut was not a one-shot rewrite of `app.py`, but a composition cut with bounded callsite migration.
- `TuiSession` now groups state explicitly into:
  - `projection`
  - `runtime`
  - `view`
- The first migration wave deliberately focused on the places most likely to reintroduce ownership bugs:
  - UI persistence/load
  - remote session summary/detail application
  - submission-loop attach/shutdown
  - runtime reset and chat-scroll state
- The second migration wave confirmed the same pattern holds deeper in the TUI:
  - chat transcript storage and activity/detail expand-collapse are pure `view` concerns
  - task ownership, resume payloads, active run handles, and local agent attachment are `runtime` concerns
  - selected/pending model identity, KB enablement, recovery summaries, and operator diagnostics are `projection` concerns
- Pulling the main `_run_chat_turn(...)` path onto grouped state is especially important:
  - before this cut, the core local execution path still mutated the flat session object directly
  - after this cut, the most important local run/resume path is structurally aligned with the intended boundary model
- The third migration wave showed the same split is also correct for execution-control behavior:
  - approvals, cancel, workflow, and remote-turn control are mostly `projection + runtime`
  - channel metadata used by remote control (`channel_type / conversation_id / sender_id`) belongs to projection, not view/runtime
  - local runtime rebuild actions like MCP reload belong to runtime lifecycle, while their operator-visible summaries belong to projection/view
- This matters because the old flat structure made control flow deceptively simple while hiding responsibility drift:
  - operator command handlers were mutating run-state, approval-state, and remote-control metadata through one undifferentiated object
  - after this cut, the control layer is much closer to the intended “surface drives session projection and runtime host” model
- This keeps the direction aligned with the target architecture:
  - TUI is moving toward a session projection + runtime host + operator view
  - instead of continuing as an accidental session owner
- Internal flat-field delegation is still present for unchanged callsites:
  - that is a temporary migration seam inside the TUI module
  - not a public compatibility contract
  - it lets us keep behavior stable while shrinking the ambiguous surface incrementally
- The largest remaining flat-field clusters are now easier to isolate:
  - sandbox/memory/context-policy diagnostics helpers
  - some session/thread summary helpers
  - a smaller set of command handlers that still mix diagnostics reads with control writes
- The fourth migration wave confirmed that the remaining diagnostics/control cluster belongs to grouped state too:
  - prepared context, prepared-context diagnostics, memory diagnostics, sandbox diagnostics, and context policy are all operator-visible session projection state
  - the local agent only contributes runtime data used to refresh those diagnostics; it should not own the cached diagnostic snapshots themselves
  - task listings, command-detail expand state, and token-estimate caches are pure `view` state rather than mixed session metadata
- That matters because diagnostics were one of the last places where the old flat session shape still made ownership ambiguous:
  - command handlers were validating, mutating, and re-rendering context/memory state through the same flat object path
  - after this cut, the command layer reads/writes through `projection/runtime/view` in the same way as the main turn path
- `src/mini_agent/tui/app.py` no longer contains direct flat access for the migrated grouped session fields.
- The internal `TuiSession.__getattr__/__setattr__` delegation seam is therefore much more isolated now:
  - still useful for stabilizing unchanged callsites
  - but no longer carrying the core diagnostics/control flow
- The final seam-removal cut is now complete:
  - `TuiSession` and its grouped sub-state dataclasses are now `slots=True`
  - the alias delegation layer has been removed instead of being left behind as a permanent escape hatch
  - remaining helper paths that still used flat `target.*` access were migrated to explicit `projection/runtime/view`
- This is a materially better boundary than the earlier migration stage:
  - before, the code path was mostly explicit but the data model still tolerated old flat access
  - now the data model itself rejects that drift, so the architectural rule is enforced by code shape rather than convention
- The remaining intentional flat-access reference is only in test coverage:
  - one regression test now confirms that old alias access raises `AttributeError`
  - that protects the boundary from silently regressing in later TUI edits
- A follow-up scan shows the next analogous boundary problem has shifted to the runtime layer rather than remaining inside TUI:
  - `MainAgentRuntimeManager` is still a very large mixed unit (`4668` lines, `133` defs/classes)
  - `MainAgentSessionState` is still a single flat object carrying runtime host state, session truth, recovery state, diagnostics, transcript state, and persistence-facing fields together
- The runtime-side issue is therefore different from the old TUI alias seam:
  - there is no hidden `__getattr__/__setattr__` shim like TUI had
  - but there is still a “god state object” and a “god manager” that concentrate too many responsibilities in one place
- The most obvious duplication seam is projection building:
  - runtime manager builds summary/detail/snapshot from live session state
  - runtime manager builds summary/detail/snapshot again from persisted records
  - both paths repeat the same field mapping with only small differences
- `session/projection.py` also shows a second boundary blur:
  - transport read models (`SessionSummaryProjection`, `SessionDetailProjection`, etc.) live beside `TerminalSessionProjection`
  - that means terminal presentation concerns are still bundled into the generic session projection module
- The current projection code also still relies on dataclass internals in a brittle way:
  - `SessionDetailProjection.from_transport_payload(...)` uses `**summary.__dict__`
  - runtime manager does the same in `_build_session_detail(...)` and `_build_session_detail_from_record(...)`
  - if these projections ever get the same `slots=True` tightening that TUI just received, those internal spreads will break
- The clean next refactor cut is therefore:
  - split runtime session state into narrower state groups
  - extract projection builders out of `MainAgentRuntimeManager`
  - move terminal-facing projection/presentation logic out of the generic `session/projection.py`
- Focused regression confirms the first composition cut did not break:
  - TUI UI-state restore behavior
  - chat history/follow scrolling behavior
  - P30.1 shared-session interaction-surface bundles
- Follow-up regression now also locks grouped ownership more explicitly in:
  - context command routing
  - local-runtime remote-sync skip behavior
  - memory command busy gating
  - runtime policy updates
  - completed-task listing and local clear behavior

## 2026-04-12 P30.1 Code Guardrails - Interaction Surface Contract

- Active runtime/application paths were still using loosely normalized free-form strings for `surface` and `channel_type`.
- That made it easy to keep behavior working short-term, but hard to enforce the corrected architecture in code.
- The right low-risk cut was not changing session semantics immediately, but adding one shared classifier seam and routing existing flows through it.
- A dedicated resolver now explicitly classifies:
  - normalized surface label
  - normalized remote channel adapter
  - user entrance (`cli/tui/webui/remote`)
- We intentionally preserved the current external session behavior:
  - `origin_surface/active_surface` for QQ flows still stay `qq`
  - TUI takeover flows are still represented as `origin=qq active=tui`
  - no API contract expansion was required for this slice
- Runtime binding logic now reuses the same resolver and supports both:
  - current direct channel surface (`surface=qq`)
  - future explicit remote entrance mode (`surface=remote` + `channel_type=qq`)
- The gateway turn-context metadata now carries explicit entrance/channel classification fields (`entrance`, `remote_channel`) for follow-up refactor phases.
- Focused regression confirms no behavior drift in core shared-session paths.

## 2026-04-12 P30 Four-Entrance Architecture Correction Sync

- The previous active wording was still slightly off even after the session-boundary correction:
  - it treated `QQ` as if it were a peer to `CLI / TUI / WebUI`
  - that is an implementation shortcut, not the intended product model
- The correct product-side entrance model is now:
  - `CLI`
  - `TUI`
  - `WebUI`
  - `Remote Interaction`
- `Remote Interaction` should be treated as a first-class entrance category, not as a single bot.
- `QQ / WeChat / Feishu` belong under a remote-channel adapter sub-layer:
  - they are concrete implementations of the remote entrance
  - they are not additional peer entrances
- This correction matters structurally, not only semantically:
  - if the project keeps flattening product entrances and concrete adapters together, later refactor work will keep smuggling channel-specific logic into architecture decisions
- `headless` also needed to be clarified:
  - it is a runtime mode, not a user-side entrance
- The project still does need an API layer, but its place is the interface / transport layer:
  - it serves WebUI and remote-channel adapters
  - it must not become a duplicate business layer below the shared services
- The active P30 execution order needed one correction after this design update:
  - the first next cut should be a four-entrance boundary lock
  - then the session-truth and TUI/channel normalization cuts should continue on top of that clarified taxonomy

## 2026-04-12 P30.1 QQ Channel Hard Consolidation

- The repo currently has one real QQ runtime path and two stale parallel implementations:
  - live runtime path: `src/apps/qqbot_channel`
  - stale Node/TypeScript package: `src/channels/qqbot`
  - stale Python OneBot adapter: `src/mini_agent/channels/qqbot.py`
- `RuntimeStackManager` already treats `src/apps/qqbot_channel` as the only runtime entry, so deleting the other QQ implementations aligns with the current production path instead of changing it.
- The current problem is not the official SDK dependency itself:
  - `qq-official-bot` is only the protocol/runtime bridge
  - Mini-Agent-specific logic lives in the app-side adapter layer and the Python gateway/session services
- `scripts/qq_wechat_smoke.py` still depends on the deleted-path assumption:
  - it runs QQ smoke through `src/channels/qqbot/src/smoke_runner.ts`
  - that smoke path must move before the old package can be removed cleanly
- `tests/test_channels.py` still imports `mini_agent.channels.qqbot`, so the legacy Python adapter cannot be removed until those tests are updated or trimmed.
- Several active docs still mention `src/channels/qqbot` as if it were the current QQ implementation:
  - `docs/RUNTIME_FLOW.md`
  - `docs/REFACTOR_TASKS.md`
  - `docs/DEVELOPMENT_INDEX.md`
- The P29/P30 architecture documents already support this cleanup direction:
  - `P29` explicitly calls out the parallel QQ implementations as boundary debt
  - `P30` explicitly locks QQ as an adapter only, not a second session system
- The live QQ app path had drifted behind the retired package on several guardrails:
  - gateway auth header passthrough
  - `/workspace` allowed-root enforcement
  - inbound message truncation
  - configurable outbound reply chunking
- Those capabilities had to be restored into `src/apps/qqbot_channel` before deleting the old package, otherwise the hard consolidation would have reduced real runtime behavior.
- The old combined `scripts/qq_wechat_smoke.py` was stale on both channel paths:
  - QQ still pointed at `channels/qqbot`
  - WeChat still pointed at `channels/wechat`
  - both had to be moved to `src/...` paths to remain executable against the current tree
- Focused QQ verification is now clean:
  - `npm run check --prefix src/apps/qqbot_channel`
  - a mock-gateway run of `npm run smoke --prefix src/apps/qqbot_channel`
  - `uv run pytest tests/test_channels.py tests/test_markdown_links.py -q`
- The remaining combined smoke failure is outside the QQ path:
  - `uv run python scripts/qq_wechat_smoke.py` now reaches both current channel roots
  - but still fails on the pre-existing WeChat oversized-body `413` expectation
  - that is a separate WeChat hardening issue, not a regression introduced by the QQ consolidation

## 2026-04-12 Repo Hygiene And Documentation Audit

- The current root `README.md` is still an older upstream/demo-style document and no longer matches the real project surface:
  - it still documents `config.yaml`-centric setup
  - it still claims `git submodule update --init --recursive` is part of normal setup
  - it still brands builtin skills as `Claude Skills`
  - it links to `./README_CN.md`, but the repo currently has no root `README_CN.md`
- The current runtime reality is different:
  - terminal-first unified entry is `mini-agent` / `mini`
  - runtime modes include `tui`, `cli`, `headless`, `serve`, `stack`, and `qq`
  - preset providers are keyed by official env vars:
    - `OPENAI_API_KEY`
    - `ANTHROPIC_API_KEY`
    - `GEMINI_API_KEY`
    - `MINIMAX_API_KEY`
  - local fallback is `.env.local`
  - custom providers are persisted to `~/.mini-agent/providers.json`
- The skills path is now bundled in-repo under `src/mini_agent/skills/`; it is not an actively used git submodule dependency.
- `.gitmodules` still points to `https://github.com/anthropics/skills.git`, but `git submodule status` returns empty and the declared submodule path does not represent the current runtime layout.
- `docs/DEVELOPMENT_GUIDE.md` and `docs/DEVELOPMENT_GUIDE_CN.md` still describe the old skill/submodule/config path model and should be treated as stale active docs until corrected.
- `docs/README_CN.md` is also a stale duplicate of the old README track and no longer matches the current repo contract.
- The repo root contains multiple ignored one-off probe files that are clearly not product assets:
  - delete/recycle experiments (`delete*.vbs`, `delete*.ps1`, `recycle_bin.cs`, `rename_delete.vbs`, `runas_delete.ps1`)
  - ad hoc DOCX probes (`read_docx*.py`)
  - temporary TUI/model state dumps (`tmp_*.json`)
  - `test.txt`
- Those probe files are personal/local experiments, not reusable scripts:
  - they contain hard-coded local machine paths
  - they are already ignored in `.gitignore`
  - they should be cleaned, not promoted into tracked `scripts/` or `tests/`
- The repo also contains ignored cache and walkthrough residue that should be physically cleaned for hygiene:
  - `tests/__pycache__/`
  - `scripts/__pycache__/`
  - `.ruff_cache/`
  - `.tmp-*`
  - temp acceptance/readiness outputs under `workspace/`
- `src/` root also contained a second category of hygiene drift:
  - 24 ad hoc `test_*` files mixed directly into the source tree
  - contents were standalone streaming/file-I/O probe scripts plus sample input/output files
  - they were not referenced by runtime code, docs, or repo tests
  - they did not belong in `src/`, `tests/`, or `scripts/` in their current form and were safe to remove
- `src/**/__pycache__/` directories were present across many runtime packages:
  - these were interpreter cache artifacts, not source assets
  - they should be physically cleaned during repo-hygiene passes
- `scripts/setup-config.ps1` and `scripts/setup-config.sh` were not just slightly stale:
  - they still downloaded templates from an old GitHub raw path
  - they still documented the old `config.yaml`-centric onboarding flow as the primary path
  - they did not reflect the current env-first preset-provider behavior
- Several live/integration tests still encoded legacy path assumptions:
  - direct reads from `mini_agent/config/config.yaml`
  - direct reads from `mini_agent/config/system_prompt.md`
  - direct MCP loads from `mini_agent/config/mcp.json`
  - these tests worked only because `scripts/test_stable.py` changed the working directory to `src/`
- Some active docs had a different class of hygiene problem:
  - `docs/CONTRIBUTING.md` still used generic-but-misleading old fork/clone guidance and dead links
  - `docs/CONTRIBUTING_CN.md` had become unreadable due to encoding corruption
  - `docs/DIRECTORY_STRUCTURE.md` was also encoding-corrupted and no longer belonged in the active doc surface
- After the second cleanup pass, the remaining hits for `git submodule` / `Claude Skills` in active docs are intentional historical clarifications, not setup instructions.
- A deeper verification pass surfaced one structural import issue:
  - importing `mini_agent.commands.mcp_support` first executed `mini_agent.commands.__init__`
  - the package then eagerly imported `.execution`, which imported `skill_support`, which imported `runtime.tooling`
  - `runtime.tooling` already imported `.mcp_support`, creating a circular import during stable-suite collection
  - converting `mini_agent.commands` exports to lazy resolution removed that cycle cleanly
- Stable-suite verification also exposed test isolation drift:
  - security-policy tests were being affected by ambient `MINI_AGENT_APPROVAL_PROFILE`, `MINI_AGENT_AGENT_MODE`, and `MINI_AGENT_ACCESS_LEVEL`
  - those tests validate explicit config objects, so they now clear runtime-policy env vars locally to stay deterministic
- Some documents now look historical rather than active-operational:
  - `docs/devlog_2026-04-05.md`
  - `docs/devlog_2026-04-07.md`
  - `docs/CROSS_DEVICE_HANDOFF_2026-04-07.md`
  - `docs/GITHUB_UPLOAD_SCOPE_2026-04-07.md`
  - likely `docs/DOCUMENTATION_REORG_REPORT.md`
- A follow-up implementation detail surfaced during verification:
  - rewriting `pyproject.toml` with PowerShell's default UTF-8 mode introduced a BOM
  - `uv` / `tomllib` then failed to parse the file with `TOMLDecodeError: Invalid statement (at line 1, column 1)`
  - writing the file back as UTF-8 without BOM fixed the build immediately

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

## 2026-04-12 Repo Hygiene Pass 3: Scripts / Docs / Generated Artifacts

- After the `src/test_*` cleanup, the next hygiene risk was not code logic but stale entrypoints:
  - `scripts/run_agent_studio.ps1` still pointed at pre-`src/` Studio paths
  - `scripts/run_qqbot_channel.ps1` and `scripts/run_wechat_channel.ps1` still contained hard-coded personal filesystem paths
  - `scripts/run_release_gate_openwebui.ps1` was no longer the maintained path and kept WebUI-era operator assumptions alive
- The repo also still had local generated residue that could mislead future scans:
  - `src/apps/agent_studio/node_modules`
  - `src/apps/qqbot_channel/node_modules`
  - `src/apps/qqbot_channel/runtime.log`
  - repo-owned `__pycache__` directories
- The clean fix was boundary clarification, not more wrappers:
  - move obsolete launchers to `scripts/archive/`
  - add `scripts/README.md` and `scripts/archive/README.md`
  - archive the stale `docs/agent_studio_quickstart_zh-CN.md`
  - update active docs to point at `uv run mini-agent stack up`, `scripts/start_runtime_stack.ps1`, and direct `python scripts/release_gate.py ...` usage
- Documentation accuracy needed a second pass too:
  - several active docs still used pre-`src/` path forms such as `apps/agent_studio_gateway/...` or `channels/qqbot/...`
  - these were corrected where they are part of the active surface or active planning set, so current readers land on real files instead of historical tree layouts
- Verification worth keeping in mind:
  - `uv run pytest tests/test_markdown_links.py -q` -> `1 passed`
  - `uv run python scripts/test_stable.py` -> `819 passed, 32 deselected`

## 2026-04-12 Repo Hygiene Pass 4: Archive P18/P19 + Split CI Scripts

- Root docs were still carrying a full completed-phase bundle from `P18/P19`:
  - hard-refactor execution plan and route backlog
  - closeout baseline evidence
  - rollout contract, runbook, alerting, canary, FAQ, weekly template
- Those files were still technically linked from active indexes, which made the root `docs/` surface look broader and more current than it really is.
- The cleaner boundary was:
  - keep `docs/` root centered on current terminal-first and `P29/P30` execution docs
  - move completed `P18/P19` phase docs into `docs/archive/`
  - update indexes so archived material remains discoverable but no longer impersonates active guidance
- `scripts/` had a second discoverability problem:
  - root mixed daily developer helpers with release-handoff / promotion / matrix scripts
  - the directory looked “active” even when several files were only meaningful in CI or release workflows
- The clean split for scripts is now:
  - active operator/developer helpers stay in `scripts/`
  - release/CI/reporting scripts move to `scripts/ci/`
  - obsolete launchers stay in `scripts/archive/`
- This keeps the repo surface honest:
  - current execution anchor is `P30_SURFACE_SESSION_REFACTOR_TASK_PLAN.md`
  - archived phase docs are still traceable
  - CI-only scripts are still present, but they no longer crowd the day-to-day script surface
- Verification:
  - `uv run pytest tests/test_markdown_links.py -q` -> `1 passed`
  - `uv run python scripts/ci/release_gate.py --help`
  - `uv run python scripts/ci/release_promotion_checklist.py --help`
  - `uv run python scripts/ci/open_webui_verify.py --help`
  - `uv run python scripts/test_stable.py` -> `819 passed, 32 deselected`

## 2026-04-12 Repo Hygiene Pass 5: Final Root-Docs Slimming

- After the larger archive pass, a few obviously non-mainline docs were still sitting in `docs/` root:
  - `ANTI_DUPLICATION_REPORT_2026-04-07.md`
  - `EXTERNAL_OSS_INDEX.md`
  - `MODEL_DISCOVERY_INTEGRATION.md`
- These were either one-off analysis outputs or environment-specific reference aids, not current execution docs.
- The right final cleanup was to archive them and keep only archive links from the remaining active indexes.
- Verification:
  - `uv run pytest tests/test_markdown_links.py -q` -> `1 passed`

## 2026-04-12 Runtime-Policy and Session-Control Extraction

- The runtime-policy extraction exposed an important read-model boundary:
  - `update_session_runtime_policy(...)` can write `session.projection.sandbox_diagnostics`
  - but `get_session_detail(...)` does not blindly trust that projection when a live agent exists
  - it rebuilds sandbox diagnostics from the agent via `RuntimeSessionDiagnosticsService.collect_sandbox_diagnostics(...)`
- That means a test that only monkeypatches the manager reconfigure method is incomplete:
  - the write path can look correct
  - the read path can still report old or empty policy values if the live agent test double has no runtime-policy state
- The right fix was to harden the test seam, not to weaken the production read model:
  - `_SelectableAgent` now exposes a minimal `runtime_policy_engine.policy`
  - the fake reconfigure logic updates that live policy object
  - the assertion now verifies the same user-visible diagnostics flow the product actually uses
- Session-control logic was a good next extraction because it had become a mini-subsystem inside the manager:
  - action normalization and validation
  - busy-state gating
  - compaction/drop-memory dispatch
  - KB enable/disable toggles
  - MCP status/list/reload flow and transcript formatting
- Pulling that into `session_control_handler.py` improves the boundary without changing surface behavior:
  - manager now orchestrates session lookup, locking, transcript recording, and persistence
  - the handler owns the command semantics and response/detail rendering
- One subtle constraint during the extraction was monkeypatch stability:
  - existing tests patch MCP helpers on `mini_agent.runtime.main_agent_runtime_manager`
  - injecting handler dependencies through manager-owned lambdas preserved that patch seam without adding a compatibility wrapper layer

## 2026-04-12 Context-Policy Extraction

- `update_session_context_policy(...)` was a strong next extraction target because it already had a clean semantic boundary:
  - one command family
  - one projection field (`session.projection.context_policy`)
  - existing normalization and formatting helpers already lived in `turn_context.py`
- The main logic inside the manager was no longer orchestration; it was command semantics:
  - normalize action names
  - validate allowed actions
  - reject busy shared sessions
  - normalize include/exclude source lists
  - coerce budget minima
  - render transcript command/summary/details
  - build the response DTO
- Pulling that into `session_context_policy_handler.py` keeps the boundary honest:
  - the handler owns policy mutation rules
  - the manager owns session lookup, locking, transcript append, and persistence
- This extraction also highlights a useful rule for later cuts:
  - when a branch mutates exactly one projection field and already depends on a dedicated domain helper module, it is usually ready to leave the manager
- The additional `budget/reset` and busy-session tests matter:
  - before this cut, the include path had coverage but the other action branches were mostly relying on incidental surface behavior
  - now the handler seam has explicit behavior locks for non-default budgets and `409` rejection while busy

## 2026-04-12 Interrupt / Approval Extraction

- `cancel_session_turn(...)` and `resolve_pending_approval(...)` form one real subdomain:
  - both operate on the currently running shared-session turn
  - both coordinate pending approval waiters
  - both must preserve transcript ordering relative to the live turn state machine
- The useful boundary split here is:
  - manager keeps session lookup and persisted-session conflict semantics
  - interrupt handler owns live-session cancel/approval rules
- This cut is slightly trickier than the previous ones because approval resolution has an ordering constraint:
  - if the waiter is resumed too early, the live turn may race ahead of the command transcript entry
  - the extracted handler therefore returns a small execution object with a `finalize()` step
  - manager appends the transcript first, then finalizes the waiter, preserving the existing visible ordering
- Cancel handling also has an important shared-session nuance:
  - `/cancel` should release any approval waiters with `None` while also setting the cancel event
  - that behavior now lives with the interrupt logic instead of remaining inline in the manager
- Restart-recovery approval conflicts are now more clearly localized:
  - the “interrupted after restart, send a new message” rule is part of the interrupt domain, not general manager plumbing

## 2026-04-12 Snapshot Import / Export Extraction

- The snapshot layer had reached the right extraction point because the deeper pieces were already separated:
  - hydration payload construction already lived in `session_hydration_builder.py`
  - snapshot DTO construction already lived in `session_read_model_builder.py`
  - manager still owned the remaining gatekeeping/orchestration glue around them
- That made snapshot import/export a good “thin coordinator” cut rather than a deep redesign:
  - import path still needs store locking and final hydration
  - but collision checks, auto-id allocation handoff, and payload preparation no longer need to stay inline in the manager
  - export path only needs to resolve “live session vs persisted record vs missing”
- One useful reminder from this cut:
  - constructor wiring order matters once extracted handlers depend on other extracted builders
  - `_session_snapshots` had to be initialized after `_session_hydration_builder` and read-model wiring existed
  - this was a clean initialization-order bug, not a design bug
- The new dedicated tests close a real seam that was only indirectly covered before:
  - duplicate imported snapshot ids
  - export from persisted record without reloading the session into memory first

## 2026-04-12 Restore / Hydrate Extraction

- The next clean cut after snapshot import/export was not more persistence metadata work; it was the restore/hydrate orchestration itself.
- By this point the restore chain already had strong lower-level structure:
  - `session_hydration_builder.py` knew how to normalize records and build session state
  - `session_runtime_state_hydrator.py` knew how to restore runtime memory and prepared-context state
  - manager still owned the glue that turned those pieces into a live restored session
- That glue was substantial enough to deserve its own handler:
  - payload preparation from persisted record
  - agent rebuild for the selected identity
  - restore-time runtime-policy reconfiguration
  - agent message/token restoration
  - knowledge-base enabled-state restoration
  - lifecycle bootstrap and session-state instantiation
  - post-state runtime hydration
- The right boundary is:
  - restore handler owns “how to hydrate”
  - manager owns “where the hydrated session lives” (`_sessions`) and “when to persist”
- One practical lesson from this cut:
  - the best focused validation was not new micro-tests for every helper branch
  - it was reusing the real restart/recovery tests that already exercise persisted restore semantics end-to-end
  - this gives much stronger confidence than a purely synthetic handler-only test would

## 2026-04-12 Session-Access Extraction

- After restore/hydrate left the manager, the next heavy mixed branch was `get_or_create_session(...)`.
- That method still combined two different responsibilities:
  - deciding which path to take
  - executing the chosen path
- The path-decision part had enough structure to stand on its own:
  - normalize request fields
  - reuse existing active session by explicit id
  - reuse same-workspace active session under team mode without id
  - restore persisted session by explicit id
  - restore latest persisted same-workspace session without id
  - fall through to create-new while enforcing team capacity
- Pulling that into `session_access_handler.py` improves the boundary cleanly:
  - handler decides which branch applies
  - manager performs the side effects for the chosen branch
- This cut also reinforces a useful refactor pattern for the rest of the manager:
  - “selection logic” and “mutation/orchestration logic” should not live in the same method when the selection tree is large
- One small but worth-keeping cleanup happened during this slice:
  - widening lint coverage surfaced an unused `asyncio` import in `tests/test_p19_runtime_matrix.py`
  - removing it keeps the widened verification path clean without changing behavior
