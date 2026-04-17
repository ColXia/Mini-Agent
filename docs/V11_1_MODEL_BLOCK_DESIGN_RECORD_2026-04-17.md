# Mini-Agent v11.1 Model Block Design Record

> Status: discussion record
> Date: 2026-04-17
> Scope: main agent-model architecture only
> Related:
> - [V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md](./V11_1_AGENT_WORKSPACE_EXECUTION_ARCHITECTURE_2026-04-17.md)
> - [ARCHITECTURE.md](./ARCHITECTURE.md)
> - [P33B_RUNTIME_TRUTH_AND_PROVIDER_GOVERNANCE_PLAN_2026-04-15.md](./P33B_RUNTIME_TRUTH_AND_PROVIDER_GOVERNANCE_PLAN_2026-04-15.md)

## 1. Purpose

This document records the `v11.1` model-block decision after the latest architecture correction.

Its purpose is to freeze one thing clearly:

- the main agent model system must not be mixed back into `workspace` or `session`

This record only covers the main agent-facing model path.
Feature models such as `embedding / ocr / rerank` are intentionally excluded from the main model chain in this version.

## 2. Final Statement

The `v11.1` model block is defined as:

`ModelPool + AgentModelService`

Meaning:

- `ModelPool` is the global model supply substrate
- `AgentModelService` is the agent-side model binding and switching service
- `Agent Core` consumes only the bound model adapter and the bound capability profile

Neither `Workspace` nor `Session` is part of the main agent model chain.

## 3. Hard Boundary

The following boundaries are locked:

- model supply serves `Agent`, not `Workspace`
- model choice is an `Agent` concern, not a `Session` concern
- workspace does not own or filter the main chat model binding
- session does not own or override the main chat model binding
- capability truth such as `supports_tools / supports_thinking / context_window` belongs to the model side and the agent side
- if the model supports a capability, agent may use it
- if the model does not support a capability, agent must not fake it through unrelated session/workspace logic

## 4. Main Split

## 4.1 ModelPool

The global supply substrate.

Owns:

- provider registry
- model catalog
- provider secrets / endpoint metadata
- protocol-family facts
- model capability facts
- health / circuit-breaker / failover state
- adapter construction prerequisites

Does not own:

- current agent binding
- current session preference
- workspace-local policy filtering for the main agent chain

## 4.2 AgentModelService

The agent-side model owner.

Owns:

- agent default model policy
- current agent model binding
- model switching
- binding maintenance
- capability-aware adapter exposure to the agent core

Does not own:

- provider storage details
- session model state
- workspace model policy
- feature-model orchestration

## 5. Main Objects

The following objects are the recommended `v11.1` model-block primitives.

### 5.1 ProviderEntry

Global provider definition.

Suggested fields:

- `provider_id`
- `protocol_family`
- `api_base`
- `secret_ref`
- `headers`
- `timeout`
- `enabled`
- `priority`

### 5.2 ModelDescriptor

Global model entry.

Suggested fields:

- `provider_id`
- `model_id`
- `display_name`
- `model_kind`
- `context_window`
- `learned_token_limit`
- `supports_tools`
- `supports_thinking`
- `capability_confidence`
- `metadata`

For the main agent chain, recommended `model_kind` values are:

- `chat`
- `reasoning`

Feature-model categories should not be mixed into this main object path in `v11.1`.

### 5.3 ModelCapabilityProfile

The capability truth that matters to the agent.

Suggested fields:

- `supports_tools`
- `supports_thinking`
- `context_window`
- `token_limit`
- `structured_output_support`
- `streaming_support`
- `capability_source`
- `capability_confidence`

This object is what the core should actually inspect to decide whether a capability can be used.

### 5.4 ModelPoolSnapshot

Point-in-time supply view.

Suggested fields:

- available providers
- available models
- health state
- breaker state
- failover metadata

This is an internal supply-side snapshot, not a session or workspace object.

### 5.5 AgentModelPolicy

The static model policy owned by the agent profile.

Suggested fields:

- default route intent
- preferred model binding hint
- prefer-local vs prefer-remote tendency
- fallback preference
- tool-heavy tendency
- reasoning-heavy tendency

This is owned by the agent, not the session.

### 5.6 AgentModelBinding

The current main model binding for the agent instance.

Suggested fields:

- `agent_id`
- `provider_id`
- `model_id`
- `binding_kind`
- `capability_profile`
- `fallback_chain`
- `bound_at`
- `switch_generation`

This is the main runtime fact for the agent model chain.

### 5.7 ModelAdapterFactory

Factory that turns an `AgentModelBinding` into a real runtime adapter.

Responsibilities:

- resolve provider configuration
- resolve secret reference
- build protocol-specific client
- normalize configuration
- return unified `ModelAdapter`

The agent core must not instantiate concrete provider clients directly.

## 6. Main Runtime Topology

```text
ModelPool
  ├─ ProviderEntry
  ├─ ModelDescriptor
  ├─ capability facts
  ├─ health / breaker / failover
  └─ ModelAdapterFactory

AgentProfile
  └─ AgentModelPolicy

AgentInstance
  └─ AgentModelBinding

AgentModelService
  ├─ reads ModelPool
  ├─ applies AgentModelPolicy
  ├─ maintains AgentModelBinding
  ├─ exposes switch interface
  └─ returns ModelAdapter + ModelCapabilityProfile

AgentCore
  └─ consumes ModelAdapter + ModelCapabilityProfile
```

## 7. Selection / Binding / Switching

## 7.1 Selection

Selection is owned by `AgentModelService`.

Inputs:

- `AgentModelPolicy`
- `ModelPoolSnapshot`
- explicit switch request

Output:

- `AgentModelBinding`

## 7.2 Binding

Binding lives on:

- `AgentInstance`

Binding does not live on:

- `Session`
- `Workspace`

## 7.3 Switching

Switching should be exposed through a dedicated agent-model interface.

Suggested APIs:

- `switch_agent_model(agent_id, target)`
- `clear_agent_model_override(agent_id)`
- `get_agent_model_binding(agent_id)`
- `list_agent_model_candidates(agent_id)`

These are agent-model core APIs, not session APIs.

## 8. Capability Gating

Model capability truth belongs to the model side and the agent side.

Rules:

- if the current model supports tools, the agent may enable tool usage
- if the current model does not support tools, the agent must not route into tool-calling mode
- if the current model supports thinking, the agent may enable reasoning/thinking mode
- if the current model does not support thinking, the agent must not emulate it through unrelated session/workspace policy
- context and token behavior should be shrunk to the model capability profile rather than session/workspace overrides

## 9. Session and Workspace Exclusion

This record explicitly excludes the following from the main agent model chain:

- session-owned model selection
- workspace-owned main chat model selection
- workspace filtering of the main chat model binding
- session persistence of the main chat model as shared truth

Session may later display the current agent model as read-only runtime fact.
Workspace may later use the model pool through feature middleware.
Neither becomes the owner of the main agent model chain.

## 10. Feature Models Are Not In This Main Chain

This record intentionally excludes:

- embedding models
- ocr models
- rerank models
- future feature-specialized models

These should later be connected through workspace-side middleware, for example:

- `WorkspaceFeatureRuntime`
- `WorkspaceEmbeddingService`
- `WorkspaceOcrService`

Those future systems may consume `ModelPool`, but they should not share the main `AgentModelBinding`.

## 11. CapabilitySnapshot Integration

`CapabilitySnapshot` should carry the resolved main agent model state, but only as agent-model output.

Recommended fields:

- `agent_model_binding`
- `agent_model_capability_profile`
- `agent_model_route_diagnostics`

It should not mix in:

- workspace model policy
- session model selection
- feature model bindings

## 12. Recovery / Checkpoint Rule

Checkpoint and run state should persist model identity and capability facts, but not live clients or secrets.

Allowed in checkpoint / run state:

- `provider_id`
- `model_id`
- route diagnostics snapshot
- capability profile
- fallback-chain identity

Forbidden in checkpoint / run state:

- API keys
- live provider client instances
- active network sessions

Recovery flow:

1. load bound provider/model identity
2. reload provider configuration from the global pool
3. rebuild adapter through `ModelAdapterFactory`
4. if unavailable, apply failover / reroute policy outside the core

## 13. Repository Mapping Recommendation

The current `model_manager/` directory should gradually align to this split.

Recommended supply-side owners:

- `provider.py`
- `preset_providers.py`
- `model_registry_service.py`
- `capability_probe.py`
- `health_monitor.py`
- `circuit_breaker.py`
- `failover.py`

Recommended new or refactored agent-model owners:

- `agent_model_service.py`
- `agent_model_policy.py`
- `agent_model_binding.py`
- `model_adapter_factory.py`
- `model_route_diagnostics.py`

Current `session_selection_service.py` is no longer aligned with the corrected `v11.1` boundary and should not remain the long-term owner of main model selection semantics.

## 14. Final Baseline

This record is aligned if the project follows these outcomes:

- model supply serves agent only
- model pool and agent model binding are separate systems
- session does not own main model selection
- workspace does not own main model selection
- feature models are postponed to workspace-side middleware
- agent core consumes only unified adapter + capability profile
- capability truth remains between agent and model systems, not session/workspace

## 15. Next Step

The next recommended design slice after this record is:

- `v11.2 model core object design`

That slice should freeze:

- `ProviderEntry`
- `ModelDescriptor`
- `ModelCapabilityProfile`
- `ModelPoolSnapshot`
- `AgentModelPolicy`
- `AgentModelBinding`
- `ModelAdapterFactory`
- `AgentModelService`
