# P30 Session Truth Boundary Map

> Status: active
> Date: 2026-04-13
> Phase: `P30.2 Session Truth Boundary Lock`
> Purpose: explicitly document what TUI and remote adapters are allowed to cache, and what remains canonical session truth
> Update 2026-04-14 (`P32.60`): the old WeChat/channel trees referenced below were removed from the active repo. Their entries remain here as audit evidence only.

## 1. Core Conclusion

The current codebase is in a better state than the earlier audit baseline:

- `TuiSession` is no longer one mixed struct
- it is already split into:
  - projection state
  - supplemental state
  - operator state
  - runtime state
  - view state

That means `P30.2` is not a greenfield cleanup.
It is a boundary-lock step:

- document the current ownership clearly
- identify what is already correct
- identify what still looks like accidental ownership drift
- freeze the rules before `P30.3` and `P30.4`

Follow-up note:

- the first `P30.3` tightening slice has now landed
- TUI-local sync / recovery summary fields were moved under `TuiSessionSupplementalState`
- this reduces the chance that summary-oriented remote caches are mistaken for shared session projection

## 2. Canonical Rule

The canonical rule remains:

- `Session` is the single source of truth
- TUI is not a session owner
- remote adapters are not session owners
- gateway/application/runtime layers remain the place where session truth is created, mutated, and persisted

Allowed local caches must therefore be interpreted as one of:

1. `session projection/cache`
2. `runtime handle`
3. `view-only state`
4. `remote binding/delivery convenience`

They must not silently become domain truth.

## 3. TUI Ownership Map

Primary file:

- `src/mini_agent/tui/app.py`

### 3.1 `TuiSession`

`TuiSession` is now a container only:

- `session_id`
- `title`
- `projection`
- `operator`
- `runtime`
- `view`

Interpretation:

- `session_id` and `title` are terminal-local references to a shared session identity
- they are not a second TUI-owned session model
- canonical details still come from shared session projections and runtime state

### 3.2 `TuiSessionProjectionState`

Classification: `session projection/cache`

These fields are allowed because they mirror shared session/runtime truth for presentation and local operator flow.
They must be refreshable from shared read models and must not be treated as the authoritative source.

This state now also carries one explicitly non-canonical child cache:

- `supplemental`

That child exists so summary/sync/recovery cache does not blur back into projection semantics.

#### Identity / route projection

- `origin_surface`
- `active_surface`
- `reply_enabled`
- `busy`
- `running_state`
- `channel_type`
- `conversation_id`
- `sender_id`
- `shared`

#### Usage / model projection

- `token_usage`
- `token_limit`
- `knowledge_base_enabled`
- `selected_model_source`
- `selected_provider_id`
- `selected_model_id`

#### Approval / queue projection

- `pending_approvals`

#### Context / diagnostics projection

- `last_prepared_context`
- `prepared_context_diagnostics`
- `memory_diagnostics`
- `sandbox_diagnostics`
- `context_policy`

#### TUI-local supplemental handle

- `supplemental`

### 3.3 `TuiSessionSupplementalState`

Classification: `supplemental surface cache`

These fields are explicitly TUI-local summary/sync caches.
They may be derived from shared session detail, remote activity history, or local recovery/resume flow.
They must never be interpreted as canonical transcript, approval, or recovery truth.

#### Remote activity summary cache

- `remote_message_count`
- `remote_updated_at`
- `remote_last_activity_summary`
- `remote_last_command_summary`

#### Recovery summary cache

- `remote_recovery_state`
- `remote_recovery_summary`
- `recovery_running_state`
- `recovery_pending_approvals`

Important note:

These fields are especially easy to misuse.
They are not canonical transcript or session state.
They are operator-facing summaries derived from shared session detail, recovery state, or activity history.

### 3.4 `TuiSessionOperatorState`

Classification: `operator-flow cache`

These fields support TUI-local command flow and operator interaction.
They may mirror shared session detail when the session is gateway-backed, but inside the TUI they are still a local cache layer rather than canonical session truth.

#### Pending model selection cache

- `pending_model_source`
- `pending_provider_id`
- `pending_model_id`

#### Pending skill-runtime cache

- `pending_skill_reload`
- `pending_skill_reload_reason`

Important note:

This is the second `P30.3` tightening cut.
These fields previously lived on `TuiSessionProjectionState`, which made them look more like shared session projection than they really are in TUI state composition.

### 3.5 `TuiSessionRuntimeState`

Classification: `runtime handle`

These fields are entrance-local runtime coordination state.
They exist because the TUI can host local execution.
They are not part of persisted or shared session truth.

#### Resume / local task coordination

- `restored_agent_messages`
- `pending_resume_task_id`
- `pending_resume_agent_messages`
- `next_task_index`
- `active_task_id`
- `pending_resume_started`

#### Live runtime handles

- `agent`
- `submission_loop`
- `loop_bus`
- `cancel_event`

Interpretation:

- these fields may exist only while the TUI is coordinating a local runtime
- they must never be used as evidence that the TUI owns the session itself
- gateway-shared sessions and local runtime-hosted sessions are both still the same session truth underneath

### 3.6 `TuiSessionViewState`

Classification: `view-only state`

These fields are strictly presentation or local UX state.
They must not be consumed as session truth by runtime/application logic.

#### Chat and task presentation

- `messages`
- `tasks`
- `active_activity_message_index`
- `activity_details_expanded`
- `command_details_expanded`

#### Scroll / render cache

- `chat_render_revision`
- `chat_scroll_line`
- `chat_follow_output`
- `usage_cache_signature`
- `usage_cache_estimate`
- `usage_cache_at`

## 4. TUI Boundary Assessment

### Already aligned

- the projection/runtime/view split exists
- the summary/sync/recovery cache now has its own `supplemental` bucket
- the operator-flow pending state now has its own `operator` bucket
- terminal display shaping has a dedicated read model:
  - `src/mini_agent/tui/session_projection.py`
- shared transport/session projections already exist:
  - `src/mini_agent/session/projection.py`

### Remaining caution areas

- `TuiSessionSupplementalState` is now correctly separated, but it still requires discipline:
  - no new session-truth fields should drift into it
  - read paths must keep treating it as summary cache only
- `TuiSessionOperatorState` is now correctly separated, but it still requires discipline:
  - no durable/session-owner business rules should drift into it
  - it should remain a TUI-local operator-flow layer rather than a second session model
- local resume/task fields still live beside session references, which can encourage accidental coupling in `tui/app.py`

This means `P30.3` is still needed even though the first split already landed.

## 5. Remote Adapter Ownership Map

Remote adapters should only keep:

- conversation binding
- delivery preferences
- channel display metadata
- channel SDK/runtime state

They should not keep:

- real session truth
- session business rules
- independent command semantics

### 5.1 Active QQ Adapter State

Primary file:

- `src/apps/qqbot_channel/bot.mjs`

Current per-conversation state object:

- `conversationId`
- `sessionId`
- `followLatest`
- `workspaceDir`
- `dryRun`

Classification:

#### Binding / addressing convenience

- `conversationId`
- `sessionId`

Interpretation:

- `conversationId` is the remote conversation identity
- `sessionId` is now only a convenience cache / fallback hint
- after remote binding centralization, it must not be treated as the canonical source of remote continuity

#### Delivery / selection preference

- `followLatest`

Interpretation:

- this is a remote-operator preference for which shared session the adapter should follow
- it is not session truth

#### Remote operator preference

- `workspaceDir`
- `dryRun`

Interpretation:

- these are input-routing preferences
- they are not owned by the session domain itself

#### Display metadata

- none currently persisted per conversation

### 5.2 WeChat Adapter State

Primary files:

- `src/channels/wechat/src/channel.ts`
- `src/channels/wechat/src/conversation_binding_store.ts`
- `src/channels/types/src/index.ts`

Current stored `RemoteConversationBindingState` fields:

- `conversation_id`
- `session_id`
- `workspace_dir`
- `dry_run`

Classification:

#### Binding / addressing convenience

- `conversation_id`
- `session_id`

Interpretation:

- `conversation_id` is the adapter-side conversation key
- `session_id` is currently a legacy convenience cache and should not remain the only continuity source

#### Remote operator preference

- `workspace_dir`
- `dry_run`

#### Channel-local metadata

- `metadata`

Important note:

The older interface name `SessionState` was structurally misleading.
It read like a true session model, but in the corrected architecture it is only an adapter-side cache.
Renaming it to `RemoteConversationBindingState` is the right `P30.4` direction because it makes the weaker ownership visible in the type itself.

## 6. Canonical Cache Contract

### 6.1 Entrances may cache

- session read-model projections
- entrance-local runtime handles
- view-only presentation state

### 6.2 Entrances may not cache as truth

- authoritative session lifecycle
- authoritative transcript history
- authoritative approval state
- authoritative model/runtime policy state

### 6.3 Remote adapters may cache

- conversation key
- resolved session id hint
- workspace/default routing preference
- delivery preference
- display metadata

### 6.4 Remote adapters may not cache as truth

- the only valid `session_id` binding source
- command business behavior
- model/memory/RAG/skill/MCP business state
- approval lifecycle truth
- a second persistent session model

## 7. Current Canonical Path

After the latest remote binding centralization, the intended path is:

`remote adapter -> /api/v1/channel/message -> application binding/service layer -> shared runtime/session truth`

This means:

- Python-side `RemoteConversationBindingService` + `ConversationBindingStore` is now the canonical binding path
- adapter-local `sessionId/session_id` caches are now transitional convenience only

## 8. What P30.3 and P30.4 Should Use From This Map

### P30.3 TUI Session Model Split

Use this map to:

- keep `projection/runtime/view` separation strict
- keep summary/sync/recovery cache in `supplemental` instead of expanding projection again
- keep TUI-local pending model / skill-reload flow in `operator` instead of expanding projection again
- move any future summary-only data away from implicit session ownership semantics
- prevent local runtime handles from leaking back into routing truth

### P30.4 Remote Channel Adapter Normalization

Use this map to:

- reduce QQ and WeChat local state to binding + preference + display metadata
- stop naming adapter-local caches as if they were true session state
- converge remote adapters onto the same thin contract

## 9. Status

`P30.2 Session Truth Boundary Lock` is now satisfied at the documentation/ownership level:

- TUI fields are classified
- remote adapter caches are classified
- the allowed cache contract is explicit

The next implementation cuts should therefore proceed as:

1. `P30.3 TUI Session Model Split`
2. `P30.4 Remote Channel Adapter Normalization`
