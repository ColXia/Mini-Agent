# P39 Kernel / Model-Runtime Mixed Boundary Plan

Date: 2026-04-16
Status: in_progress
Scope: honest post-`P38` landing plan for the deferred mixed `kernel / model-runtime` bundle

## Goal

Land the current dirty-tree `kernel / model-runtime` work as an explicit mixed slice instead of continuing to treat it as an ambiguous deferred backlog.

The target outcome is:

- one honest post-`P38` implementation line for the mixed bundle
- a locked landing order that keeps upstream runtime/protocol work separate from downstream `kernel` adoption
- no fake `P34` commit story for code that now clearly includes `P33b`-class runtime-governance behavior

## Why This Slice Exists

The earlier strict boundary audit already showed that the current `kernel.py` diff is not a pure core-only adoption.

The new follow-up audit sharpens that conclusion:

- `kernel.py` now consumes:
  - injected `config / config_loader`
  - `RouteIntent`
  - `RouteRequirementProfile`
  - bootstrap-only route input
  - request-policy defaults
  - rectifier options
  - richer route/capability/bootstrap diagnostics
- `FailoverLLMClient` now depends on:
  - `ProtocolRequestPolicy`
  - `RequestRectifierOptions`
  - protocol execution profiles
  - streaming failover behavior
- `runtime.py` now owns:
  - bootstrap-provider fallback truth
  - capability-truth metadata
  - richer routed candidate diagnostics
  - explicit route snapshots / error recording
- `tests/test_agent_core_kernel.py` now validates:
  - route intent
  - route requirements
  - capability truth
  - bootstrap selection story
  - runtime retry / request-policy / rectifier propagation
  - injected config/config_loader behavior

That is not a core-only story anymore.

## Boundary Judgment

### What `P39` really is

`P39` is the mixed landing line for:

- runtime/provider bootstrap truth
- routed model selection semantics
- protocol execution profile binding
- failover and streaming hot-path alignment
- `kernel` adoption of those upstream contracts

### What `P39` is not

`P39` is not:

- a pure `P34` `kernel.py` cleanup
- a docs-only closure line
- a repo-wide hygiene pass

## Locked Slice Structure

### P39.1 Upstream Runtime / Protocol Substrate

This is the upstream contract bundle that the new `kernel` depends on.

Primary files:

- `src/mini_agent/config.py`
- `src/mini_agent/config/config-example.yaml`
- `src/mini_agent/model_manager/bootstrap.py`
- `src/mini_agent/model_manager/model_registry_service.py`
- `src/mini_agent/model_manager/runtime.py`
- `src/mini_agent/model_manager/failover.py`
- `src/mini_agent/llm/protocol_binding.py`
- `src/mini_agent/llm/base.py`
- `src/mini_agent/llm/llm_wrapper.py`
- `src/mini_agent/llm/openai_client.py`
- `src/mini_agent/llm/anthropic_client.py`

Primary behaviors:

- `runtime.retry` / `runtime.request_policy` / `runtime.rectifier` config shape
- bootstrap-only provider fallback via synthetic `bootstrap-config`
- explicit routed selection requirements and route-intent support
- capability-truth metadata on routed candidates
- protocol execution profile binding outside the concrete clients
- normalized buffered + streaming completion path in failover/client hot paths

Expected focused tests:

- `tests/test_model_routing_runtime.py`
- `tests/test_model_failover.py`
- `tests/test_llm_protocol_binding.py`
- `tests/test_llm_streaming.py`
- `tests/test_llm_completion_result.py`
- adjacent provider/runtime config tests as needed

Acceptance:

- upstream runtime/protocol behavior is internally coherent without relying on `kernel.py`
- request-policy / rectifier / streaming behavior is covered by focused tests
- bootstrap fallback and candidate diagnostics are validated at the runtime layer

### P39.2 Kernel Adoption And Diagnostics Closure

This is the downstream consumer cut once the upstream substrate is stable.

Primary files:

- `src/mini_agent/agent_core/kernel.py`
- `src/mini_agent/runtime/turn_context_provider_builder.py`
- `tests/test_agent_core_kernel.py`

Primary behaviors:

- injected `config / config_loader` ownership
- routed selection through explicit `RouteIntent` and `RouteRequirementProfile`
- failover construction through request-policy and rectifier-aware runtime contracts
- kernel diagnostics exposing route/capability/bootstrap truth
- typed runtime bindings instead of ad-hoc `setattr(...)`

Acceptance:

- `kernel.py` reads as a consumer of the upstream runtime/protocol substrate rather than as the owner of those semantics
- kernel tests validate the final integrated story without re-owning upstream behavior
- the `P39` commit story remains phase-honest

### P39.3 Verification And Commit Slicing

Before any final commit choice:

- run focused upstream tests for `P39.1`
- run focused kernel tests for `P39.2`
- rerun the maintained active-path perimeter if the slice touches shared active runtime paths
- confirm commit boundaries do not silently absorb unrelated `P36 / P37 / Desktop / remote` work

## Recommended Landing Order

The safest order is:

1. stabilize and verify the upstream runtime/protocol substrate
2. then land the downstream `kernel` adoption on top of that substrate
3. only then decide whether the two parts travel as:
   - one honest combined `P39` commit sequence
   - or two adjacent commits inside the same `P39` line

Current recommendation:

- keep `P39.1` and `P39.2` conceptually separate even if they remain in one working branch
- do not start from `kernel.py` first

## Current Validation Status

Focused validation on the current dirty tree is already strong enough to proceed with this order.

- upstream runtime/protocol substrate:
  - `uv run pytest tests/test_model_routing_runtime.py tests/test_model_failover.py tests/test_provider_config.py tests/test_request_rectifier.py tests/test_model_mapper.py tests/test_preset_providers.py tests/test_llm_protocol_binding.py tests/test_llm_streaming.py tests/test_llm_completion_result.py tests/test_model_registry_service.py tests/test_model_discovery.py tests/test_session_model_selection_service.py tests/test_cli_models_command.py -q`
  - result: `91 passed`
- downstream kernel-consumer slice:
  - `uv run pytest tests/test_agent_core_kernel.py tests/test_cli_submission_loop.py tests/test_main_agent_surface_service.py -q`
  - result: `118 passed`

This does not mean `P39` is committed or fully closed yet.
It means the planned landing order is already backed by code and focused tests rather than by architecture preference alone.

## Current Slice Status

- `P39.1` upstream runtime/protocol substrate:
  - materially complete and ready to cut as the first implementation slice
- `P39.2` kernel adoption and diagnostics closure:
  - still pending and should reopen only after the upstream slice is preserved cleanly

## Non-Goals

`P39` is not intended to:

- reopen wider repo-wide lint cleanup
- continue general `P38` closure work by drift
- bundle `DesktopUI` or remote product polish
- relabel mixed model/runtime/provider work as pure `agent_core`

## Exit Criteria

`P39` is successful when:

- the mixed bundle has one honest, documented landing story
- upstream runtime/protocol behavior is validated on its own terms
- downstream `kernel` adoption is reduced to a real consumer integration cut
- no fake pure-`P34` commit message is needed to land the work
