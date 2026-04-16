# P33b Runtime Truth And Provider Governance Plan

Date: 2026-04-15
Status: completed
Scope: model configuration truth / provider governance / routing determinism / capability evidence / discovery integrity

Execution note (2026-04-16): original `P33.1` through `P33.8` are treated as the completed runtime-upgrade baseline, and `P33b` should now also be treated as completed historical planning rather than an active line.

## Goal

Upgrade the runtime again so the next generation of model/provider work is:

- deterministic when the operator asks for an exact model
- explicit about which layer owns model truth
- honest about provider/model capabilities
- safe to evolve across preset, custom, and local provider paths
- observable enough to explain why one route was chosen

This slice is not another provider-SDK expansion.
It is a truth-and-governance correction for the runtime that `P33` already upgraded.

## Why This Slice Exists

The original `P33` line already landed the most important runtime upgrades:

- registry-first routing
- protocol-bound execution profiles
- richer response/event model
- native streaming
- discovery metadata persistence
- capability-aware routing seam
- request-policy binding
- Ollama local-provider integration

But the current code still exposes a second class of problems:

- capability truth is still partly inferred too optimistically
- automatic routing can still silently fall back when an exact model name misses
- discovery cache scope is too coarse for multiple compatible endpoints
- custom-provider discovery can overwrite configured inventory too aggressively
- bootstrap preset choice is still order-driven rather than policy-driven
- provider configuration still presents some "configurable but not truly runnable" shapes

Those are no longer `P33` protocol-foundation problems.
They are runtime-governance problems.

## Locked Decisions

### 1. `P33` stays closed as the protocol/runtime-foundation baseline

`P33b` does not reopen:

- protocol-native streaming
- response normalization
- Ollama first-class local integration
- protocol-binding ownership

Those are now foundation, not open design questions.

### 2. Runtime remains protocol-centric

`P33b` still does not introduce new brand-native runtime families.

Maintained runtime execution families remain:

- `openai`
- `anthropic`

Provider governance must layer above those protocol families, not beside them.

### 3. Exact requests and automatic routing are different intents

The runtime must distinguish between:

- exact request:
  - operator or session explicitly asked for one provider/model identity
- automatic route:
  - runtime is free to choose the best compatible route

Exact requests must fail loudly when they cannot be honored.
Automatic routes may fall back, but only explicitly and observably.

### 4. Unknown capability is not the same as supported capability

Capability truth must stop collapsing into a binary guessed-true model.

At minimum, runtime-governance decisions must distinguish:

- supported
- unsupported
- unknown

Unknown may remain usable, but it must not be presented as confirmed support.

### 5. Discovery must enrich registry truth, not destroy it

Discovery is allowed to:

- add inventory evidence
- refresh recommendation metadata
- add capability/context metadata

Discovery is not allowed to silently erase valid configured inventory just because one fetch returned a smaller list.

### 6. Bootstrap behavior must become policy-driven

When multiple preset providers are available, runtime bootstrap should not depend on whichever provider happens to be checked first in code order.

Bootstrap selection must become:

- explicit
- explainable
- reproducible

### 7. Config contract and runnable-runtime contract must match

If a provider shape is accepted by configuration and operations surfaces, the runtime story for that shape must be explicit.

The project should not keep "looks configurable" provider modes that cannot actually execute on the maintained runtime path.

## Current State Diagnosis

### Strengths from `P33`

- provider registry is already the active runtime source of route truth
- protocol binding already owns compatibility policy
- native streaming already exists end-to-end
- request policy and rectifier ownership are already much cleaner
- session-scoped selected/pending model identity already exists
- Ollama is already integrated into the same provider/model registry path

### Remaining structural weaknesses

- capability inference still treats many models as tool-capable or thinking-capable without real evidence
- route intent is still too fuzzy between "exact request" and "best available route"
- automatic fallback can still hide model-name misses
- discovery cache is keyed too broadly for multi-endpoint compatible providers
- custom-provider discovery can rewrite configured inventory too aggressively
- bootstrap preset choice is still implicit-order driven
- provider protocol configuration still exposes some ambiguous or misleading contracts
- route diagnostics still explain too little about why one route beat another

## Target Architecture

### A. Truth model

There should now be four explicit truths:

1. Provider definition truth
   - provider identity
   - protocol family
   - auth/base URL
   - operator-configured inventory

2. Discovery evidence truth
   - discovered models
   - freshness
   - evidence source
   - capability confidence

3. Session/runtime selection truth
   - selected identity
   - pending identity
   - exact-vs-automatic route intent

4. Runtime policy truth
   - retry
   - request policy
   - rectifier
   - bootstrap selection policy

### B. Route-intent model

The runtime should support two route modes:

1. Exact
   - explicit provider/model request
   - no silent model fallback
   - mismatch is an error

2. Automatic
   - route planner may rank candidates
   - compatibility filtering allowed
   - fallback allowed
   - final decision must remain inspectable

### C. Capability model

Minimal capability state should become:

- `supports_tools`: `true | false | unknown`
- `supports_thinking`: `true | false | unknown`
- `context_window`: explicit value or unknown
- evidence metadata:
  - source
  - freshness
  - confidence

### D. Registry / discovery relation

Registry should separate:

- configured inventory
- discovered inventory
- effective recommended default

The runtime may merge those views for routing, but discovery should not become the sole owner of configured provider inventory.

## Detailed Upgrade Plan

## P33b.1 Route Intent Hardening

### Objective

Stop silent model fallback when the operator actually asked for an exact model.

### Changes

- introduce an explicit route-intent distinction for:
  - exact request
  - automatic route
- make exact requests fail when the requested model/provider cannot be matched
- keep automatic routing free to fall back only on the automatic path
- update bootstrap and agent-kernel route entrypoints so the intent is explicit in diagnostics

### Acceptance

- exact provider/model requests no longer silently route to a provider default model
- automatic routing still works for non-exact startup and best-route flows
- route diagnostics expose whether the route was exact or automatic

## P33b.2 Capability Truth Grading

### Objective

Replace guessed-true capability truth with graded capability evidence.

### Changes

- introduce tri-state or equivalent graded capability semantics:
  - `supported`
  - `unsupported`
  - `unknown`
- preserve raw evidence source and confidence in model metadata
- stop defaulting most compatible-provider models to implicit support without evidence
- update route filtering/scoring to:
  - hard-filter `unsupported`
  - prefer `supported`
  - allow but down-rank `unknown`

### Acceptance

- runtime no longer treats missing capability evidence as confirmed support
- routing can explain whether a chosen route was supported or merely unknown
- capability metadata remains usable across preset/custom/local providers

## P33b.3 Discovery Integrity And Cache Scope

### Objective

Make discovery refresh safe and endpoint-specific.

### Changes

- scope discovery cache by:
  - provider type
  - normalized base URL
  - effective protocol flavor when relevant
- separate configured inventory from discovered inventory, or merge without destructive overwrite
- stop custom-provider discovery from shrinking configured model lists by accident
- preserve recommendation metadata without letting one fetch destroy operator-defined truth

### Acceptance

- switching between different compatible endpoints no longer reuses the wrong discovery cache
- custom-provider discovery does not silently erase valid configured inventory
- discovered metadata remains fresh and traceable

## P33b.4 Bootstrap Provider Governance

### Objective

Make startup provider selection explicit and policy-driven.

### Changes

- define one bootstrap selection policy seam
- remove code-order dependency from "first available preset" behavior
- support explicit bootstrap preference and deterministic priority ordering
- keep Ollama opt-in and prevent hidden local-daemon takeover of cloud defaults
- make bootstrap diagnostics report:
  - selected provider
  - why it won
  - what alternatives were present

### Acceptance

- multi-key startup produces deterministic and explainable provider selection
- bootstrap no longer depends on provider enumeration order
- local-provider enablement remains explicit and non-surprising

## P33b.5 Provider Contract Tightening

### Objective

Align configurable provider shapes with actually runnable runtime shapes.

### Changes

- clarify the difference between:
  - provider source (`preset` / `custom`)
  - provider protocol family (`openai` / `anthropic`)
- audit and remove or constrain misleading provider API types that are not really runnable
- align ops DTOs, registry validation, and runtime execution expectations
- keep discovery compatibility fallback explicit rather than pretending it is a native runtime family

### Acceptance

- provider configuration surface no longer advertises fake runtime modes
- ops/config/runtime layers tell the same protocol story
- custom providers remain supported through explicit maintained protocol families only

## P33b.6 Route Observability And Diagnostics

### Objective

Make routing decisions explainable enough for operators and future surfaces.

### Changes

- add route-decision diagnostics covering:
  - route intent
  - provider candidates considered
  - capability evidence state
  - exact-match or fallback reason
  - bootstrap-selection reason
- expose these diagnostics through the existing runtime/logging/service seams
- keep the event/log contract surface-neutral for future DesktopUI and ops usage

### Acceptance

- one route decision can be explained without reading internal code
- runtime logs and diagnostics distinguish exact-match failure from automatic fallback
- future surfaces can display route reasoning without inventing their own analysis layer

## Recommended Execution Order

1. `P33b.1 Route Intent Hardening`
2. `P33b.2 Capability Truth Grading`
3. `P33b.3 Discovery Integrity And Cache Scope`
4. `P33b.4 Bootstrap Provider Governance`
5. `P33b.5 Provider Contract Tightening`
6. `P33b.6 Route Observability And Diagnostics`

## Why `P33b.1` Is First

The current highest-risk remaining behavior is silent mismatch handling:

- operator asks for one model
- runtime quietly gives another

As long as that remains possible, later capability and governance improvements still sit on an unsafe contract.

So the first implementation slice should make route intent explicit before any broader capability or cache redesign.

## Immediate Deliverables For The Next Implementation Turn

### Next recommended slice

- `P33b.1 Route Intent Hardening`

### Immediate code goals

- audit route entrypoints in:
  - `agent_core/kernel.py`
  - `model_manager/runtime.py`
  - `model_manager/model_mapper.py`
  - session model-selection helpers
- split exact request semantics from automatic route semantics
- add focused regression coverage for:
  - explicit missing model
  - explicit wrong provider/model pair
  - automatic route still allowed to choose provider default

## Non-Goals

- no new vendor-native runtime SDK line
- no reintroduction of Gemini into active runtime scope
- no DesktopUI feature work
- no browser-surface revival
- no pricing/preference scoring engine
- no full multi-profile UX redesign in this first `P33b` cut
