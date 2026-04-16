# P33 LLM Runtime Upgrade Plan

Date: 2026-04-14
Status: completed
Scope: model runtime / provider registry / routing / streaming / Ollama local integration

Execution note (2026-04-16): treat `P33` as completed historical planning. The landed slice-by-slice execution record continues in `task_plan.md`, `progress.md`, and `findings.md`.

## Goal

Stabilize the LLM runtime so it remains:

- light enough for Mini-Agent
- strong enough for long-running agent work
- protocol-clean enough to keep growing
- explicit enough to support future `RAG / memory / skills / MCP / remote / desktop`

This slice does not treat "four native SDK integrations" as a goal.
The real goal is a stable multi-supplier runtime that can keep the agent working across:

- official providers
- relay stations / compatible gateways
- local models

## Locked Decisions

### 1. Runtime stays protocol-centric, not brand-centric

The project does not need one native SDK per brand.
The runtime should continue to center on protocol execution classes, not vendor-name classes.

Current practical protocol families:

- `anthropic`
- `openai`

This is acceptable because real use will often go through relay stations and compatibility layers.

### 2. Gemini is removed from active runtime scope

`Gemini` is not an active target for the maintained runtime path.
It should be removed from:

- preset providers
- discovery defaults
- runtime tests/docs that present it as a maintained path

Historical references may remain in archived docs only.

### 3. MiniMax remains in the Anthropic-compatible runtime family

MiniMax is an active provider target, but it does not need its own execution client.
It should stay in the `anthropic` compatibility family, with provider-specific binding/config layered above protocol execution.

### 4. Canonical truth moves to provider registry + session identity

The correct long-term truth sources are:

- provider/model inventory truth: provider registry
- active runtime truth for one session: `(source, provider_id, model_id)`
- runtime policy truth: `config.runtime` + runtime policy config

`config.llm` should no longer act as a peer truth source in the hot runtime path.

Correct future role for `config.llm`:

- bootstrap fallback only
- developer-safe recovery path only
- legacy import source only

It should not remain a first-class routing owner once registry routing is available.

### 5. Capability routing only adds the capabilities that matter now

Do not over-design route scoring.
Add only:

- `tools`
- `thinking`
- `context_window`

Do not add pricing / user preference / subjective quality scoring into the routing core right now.

### 6. Native streaming is a real deficiency and must be fixed

Current interaction streaming is application-layer chunk replay over a completed reply.
The runtime must gain true provider-native streaming.

### 7. Ollama should be added as a local-provider path

Ollama is a meaningful addition for private/local tasks.
It should be integrated as a first-class local runtime option, not left as an accidental custom-provider hack.

Official references used for planning:

- Ollama OpenAI compatibility: https://docs.ollama.com/openai
- Ollama Anthropic compatibility: https://docs.ollama.com/api/anthropic-compatibility
- Ollama local/cloud authentication behavior: https://docs.ollama.com/api/authentication

## Current State Diagnosis

### Strengths

- Kernel construction is centralized in `agent_core/kernel.py`
- route selection, failover, and protocol execution are already separated
- session-scoped model identity already exists
- provider registry already exists for preset/custom providers

### Current structural weaknesses

- runtime hot path still treats `config.llm` as a peer route source
- protocol clients still contain provider-specific compatibility decisions
- no provider-native LLM streaming abstraction exists
- latest-model discovery is still partly heuristic / fallback-based
- route selection still scores mostly by model-name matching instead of capability constraints
- response abstraction is too small for future streaming / richer normalized metadata
- protocol request defaults are still too hard-coded in execution clients

## Target Architecture

### A. Truth model

There should be exactly three truths:

1. Provider registry truth
   - custom providers from `providers.json`
   - preset/local providers from generated runtime registry entries
   - discovered model metadata persisted in provider state

2. Session selection truth
   - selected identity
   - pending identity

3. Runtime policy truth
   - `config.runtime.retry`
   - `config.runtime.request_policy`
   - `config.runtime.rectifier`
   - approval/runtime mode
   - other global runtime policy defaults

### B. Runtime layers

Target layers:

1. Provider registry layer
   - provider definitions
   - model inventory
   - capability metadata
   - discovery metadata

2. Route planner layer
   - selection based on requested identity + capability requirements
   - failover ordering

3. Protocol binding layer
   - convert provider route into execution profile
   - base URL normalization
   - auth mode
   - rectifier options
   - request defaults

4. Protocol execution layer
   - OpenAI protocol client
   - Anthropic protocol client

5. Response normalization layer
   - buffered result
   - streaming events

6. Agent/application consumption layer
   - planner loop
   - TUI
   - DesktopUI
   - Remote Interaction

## Detailed Upgrade Plan

## P33.1 Registry Truth Consolidation

### Objective

Make provider registry the only maintained runtime route source.

### Changes

- remove `Gemini` from active preset/runtime support
- keep `MiniMax` as active `anthropic`-family provider
- downgrade `config.llm` from route owner to bootstrap input
- when `config.llm` exists and registry is empty:
  - synthesize a `bootstrap-config` provider entry
  - route through the same registry path as every other provider
- stop letting kernel/runtime branch between:
  - registry route path
  - direct `config.llm` route path

### Acceptance

- kernel runtime selection always resolves through one provider catalog path
- `config.llm` never bypasses registry routing in the hot path
- Gemini disappears from active preset/runtime UX

## P33.2 Protocol Boundary Hardening

### Objective

Separate protocol execution from provider compatibility policy.

### Changes

- turn `LLMClient` into a thin protocol-dispatch facade only
- extract provider compatibility decisions into explicit protocol binding/profile objects
- remove provider/domain-specific branching from protocol wrapper code
- move items such as:
  - MiniMax base URL suffix handling
  - provider-specific request tweaks
  - auth quirks
  into binding/config profiles rather than protocol clients

### Acceptance

- OpenAI protocol client only knows OpenAI protocol mechanics
- Anthropic protocol client only knows Anthropic protocol mechanics
- provider-specific compatibility rules live outside those clients

## P33.3 Rich Response Model Upgrade

### Objective

Prepare the runtime for real streaming and richer normalized provider output.

### Changes

- replace the too-thin buffered-only response idea with:
  - `LLMCompletionResult`
  - `LLMStreamEvent`
- normalized event families should include at least:
  - `message_start`
  - `thinking_delta`
  - `text_delta`
  - `tool_call`
  - `usage`
  - `message_stop`
  - `error`
- buffered completion should be an aggregation of the same normalized event stream

### Acceptance

- runtime can consume both buffered and streamed output through one normalized model
- future provider metadata additions no longer require reworking the entire agent loop contract

## P33.4 Native Streaming Upgrade

### Objective

Replace fake application-layer streaming with provider-native streaming.

### Changes

- add native stream method to LLM client base contract
- implement provider-native streaming in:
  - OpenAI protocol client
  - Anthropic protocol client
- update agent execution loop to consume stream events directly
- propagate native events through:
  - gateway SSE
  - TUI
  - DesktopUI
  - Remote Interaction
- keep buffered path as fallback/aggregation mode

### Acceptance

- first visible assistant text can appear before the full reply completes
- thinking/tool events can surface during execution instead of after completion
- current fake chunk replay path is removed from the main runtime flow

## P33.5 Model Discovery / Latest Selection Upgrade

### Objective

Make model discovery and latest-selection more explicit and less heuristic.

### Changes

- split discovery strategies by provider class:
  - API discovery
  - curated manifest
  - hybrid availability check
- add persisted metadata for discovered models:
  - `discovered_at`
  - `discovery_source`
  - `discovery_confidence`
  - `context_window`
  - `supports_tools`
  - `supports_thinking`
- stop treating "latest by created timestamp" as the universal answer
- add provider-specific recommendation policy:
  - `official_default`
  - `curated_latest`
  - `discovered_latest`

### Recommended provider strategies

- OpenAI:
  - API discovery + curated flagship filtering
- Anthropic:
  - curated manifest first, because there is no stable live models API path in current runtime assumptions
- MiniMax:
  - official discovery where available + curated fallback
- Ollama:
  - local API discovery + local availability only

### Acceptance

- default model selection is based on explicit provider strategy, not only heuristic timestamps
- model capability metadata becomes available to routing

## P33.6 Capability-Aware Routing Upgrade

### Objective

Keep routing simple, but make it aware of the three capabilities that matter now.

### Changes

- extend model/provider metadata with:
  - `supports_tools`
  - `supports_thinking`
  - `context_window`
- define one minimal runtime route requirement profile, for example:
  - `require_tools`
  - `prefer_thinking`
  - `min_context_window`
- route selector should:
  - filter out incompatible candidates
  - rank compatible candidates by model match + priority

### Acceptance

- tool-required sessions do not route onto models that cannot support tools
- context-sensitive sessions can avoid clearly undersized models
- route selection still stays lightweight and deterministic

## P33.7 Request Policy / Protocol Parameter Upgrade

### Objective

Move hard-coded request parameters into explicit request policy configuration.

### Changes

- define normalized request-policy fields such as:
  - `max_output_tokens`
  - `reasoning_split_enabled`
  - `thinking_budget_tokens`
  - `temperature`
  - `streaming_enabled`
  - `tool_choice_policy`
- remove hard-coded protocol defaults from clients where possible
- let route/binding layer compute effective request settings per model/provider

### Acceptance

- protocol clients are not the long-term owner of provider/model policy
- request defaults become inspectable and testable

## P33.8 Ollama Local Provider Integration

### Objective

Add Ollama as a first-class local provider path for private/local work.

### Design direction

- add `ollama-local` as a maintained local provider class
- treat it as a local-provider family, not a random custom provider
- default runtime protocol mode:
  - `anthropic` compatibility for coding-agent use
- optional mode:
  - `openai` compatibility when needed

### Why this direction

Official Ollama docs currently show:

- OpenAI-compatible local endpoint under `http://localhost:11434/v1/...`
- Anthropic-compatible local endpoint under `http://localhost:11434/...`
- local API access does not require real authentication

That makes Ollama a good fit for the current protocol-centric runtime.

### Changes

- add Ollama provider metadata/profile
- support no-auth local provider mode
- add local health check / daemon reachability check
- discover locally available models from Ollama API
- support local model context-window override policy:
  - manual override
  - learned limit
  - future Modelfile-aware enhancement
- expose Ollama in provider/model management UX

### Acceptance

- user can enable a local Ollama provider without fake external API-key requirements
- Ollama models can be selected per session just like other providers
- local/private tasks can be routed to Ollama intentionally

## Recommended Execution Order

1. P33.1 Registry Truth Consolidation
2. P33.2 Protocol Boundary Hardening
3. P33.3 Rich Response Model Upgrade
4. P33.4 Native Streaming Upgrade
5. P33.5 Discovery / Latest Selection Upgrade
6. P33.6 Capability-Aware Routing Upgrade
7. P33.7 Request Policy Upgrade
8. P33.8 Ollama Local Provider Integration

## Why Ollama Is Last In This Sequence

Ollama should not be bolted onto a drifting runtime.
If added too early, it will inherit:

- old config truth ambiguity
- fake streaming behavior
- weak discovery/default logic
- provider/protocol boundary leakage

So the right approach is:

- stabilize the runtime seam first
- add Ollama on top of the corrected seam

## Immediate Deliverables For The Next Implementation Turn

The next implementation slice should not attempt the whole plan.
It should land the first concrete cut:

### Next recommended slice

- `P33.1 Registry Truth Consolidation`

### Immediate code goals

- remove Gemini from active preset/runtime path
- define and document the new truth rule:
  - provider registry owns runtime provider/model inventory
  - session identity owns active model selection
  - `config.llm` becomes bootstrap-only
- implement a synthetic bootstrap provider path so runtime does not need a separate direct `config.llm` route branch

## Non-Goals

- no cost-based route scoring
- no subjective "best model" chooser
- no broad multimodal response redesign in the first slice
- no per-brand native SDK expansion just for symmetry
