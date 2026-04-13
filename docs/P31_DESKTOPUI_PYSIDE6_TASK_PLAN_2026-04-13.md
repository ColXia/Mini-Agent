# P31 DesktopUI(PySide6) Decision And Task Plan

> Status: active
> Date: 2026-04-13
> Decision owner: Mini-Agent core refactor
> Decision result: adopt `PySide6 DesktopUI` as the third maintained user-facing entrance

## 1. Decision Summary

Mini-Agent now freezes the third maintained product entrance as:

- `CLI`
- `TUI`
- `DesktopUI`
- `Remote Interaction`

Clarifications:

- `DesktopUI` replaces `browser-first WebUI` as the primary end-user graphical entrance
- the old browser Studio path is no longer the canonical product direction
- existing browser assets may remain as paused compatibility/prototype material, but they are not the active mainline
- `Remote Interaction` still remains an entrance category; current active adapter scope is still `QQ` only

## 2. Why Option 1 Won

Chosen option:

- build a separate `PySide6` desktop frontend
- reuse the shared Mini-Agent service/runtime/session contracts
- do not try to map the current `prompt_toolkit` TUI directly into a desktop shell

Why this is the right fit:

- the project core is Python-first already
- `PySide6` gives a real desktop window instead of another browser workbench
- desktop-native windowing, panels, tray, notifications, drag/drop, file pickers, and future local integrations are all easier to own cleanly
- it avoids turning TUI rendering rules into a long-term UI constraint
- it keeps TUI free to remain the developer/operator surface instead of forcing it to become the end-user desktop shell

## 3. Architecture Decision

### Product-entrance model

The active four entrances are now:

1. `CLI`
2. `TUI`
3. `DesktopUI`
4. `Remote Interaction`

Browser-based `WebUI` is downgraded to:

- paused compatibility/prototype path
- not the canonical maintained third entrance
- not the current implementation priority

### Boundary rule

`Session` remains the single truth model.

That means:

- DesktopUI does not own sessions
- DesktopUI does not own chat execution rules
- DesktopUI does not create a second state system
- DesktopUI only operates sessions through shared application/runtime services

### Transport rule

For the first DesktopUI delivery slices, DesktopUI will connect to the existing local gateway host.

Recommended first transport shape:

- DesktopUI launches or attaches to the local gateway
- DesktopUI uses HTTP for commands/query operations
- DesktopUI uses SSE/stream transport for live turn output

This keeps the first version simple and testable.

## 4. Key Assessment: Can We Start Directly On The Current Gateway?

Short answer:

- not as-is
- but we also do not need a large gateway rewrite first

The correct move is:

- first land one thin `application service seam` hardening slice
- then build DesktopUI on top of the existing gateway transport

### Why not start directly with the current shape

The code audit shows that the lower layers are already reusable:

- `SessionApplicationService` is already surface-neutral enough
- runtime/session truth is now significantly cleaner after the `P30.5` convergence work
- interface contracts already exist for session, model, memory, approval, and stream flows

But one important leak still exists:

- the top shared orchestration is still named and shaped as `MainAgentGatewayUseCases`
- chat flow/execution handler naming is still gateway-oriented
- that makes a desktop app too likely to depend on HTTP-shaped orchestration instead of true surface-neutral services

### Decision

Do **not** start by bypassing the gateway.

Do **not** start by letting DesktopUI import gateway-specific orchestration classes directly as its long-term service boundary.

Instead:

- extract one surface-neutral interaction/service facade first
- keep gateway as a thin transport host over that facade
- then let DesktopUI reuse the same facade through the gateway transport

## 5. Seam-First Implementation Rule

The first required hardening slice is not a rewrite.

It is a thin service-boundary correction:

1. Introduce a surface-neutral application facade for:
   - chat turn execution
   - chat streaming
   - session lifecycle operations
   - model selection/listing
   - command dispatch
   - approval actions
2. Reduce `MainAgentGatewayUseCases` into a gateway transport adapter/composition wrapper instead of the canonical top-level orchestration name.
3. Freeze one surface-neutral stream event contract that DesktopUI and remote adapters can both consume.
4. Keep `FastAPI` route handlers as translation only.

Acceptance for this seam slice:

- DesktopUI can be designed against a surface-neutral contract
- gateway remains only the local host/transport layer
- no new business behavior is added into route handlers

## 6. Repository Direction

Recommended target layout:

```text
src/mini_agent/
  application/              shared surface-neutral services
  desktop/                  DesktopUI view models, controller helpers, client facade
  tui/                      developer terminal surface
  runtime/                  runtime/session orchestration
  interfaces/               shared DTOs and event contracts

src/apps/
  agent_studio_gateway/     local host / transport composition root
  desktop_ui/               PySide6 app bootstrap / packaging entry
  qqbot_channel/            remote adapter app
  agent_studio/             paused browser compatibility/prototype path
```

Repository rule:

- DesktopUI rendering/view state belongs under `src/mini_agent/desktop/`
- Desktop app process bootstrap belongs under `src/apps/desktop_ui/`

## 7. Detailed Execution Plan

### P31.1 Decision Freeze And Naming Correction

Scope:

- sync architecture docs from `WebUI` mainline wording to `DesktopUI` mainline wording
- record browser Studio as paused compatibility path
- freeze the rule that DesktopUI is a separate frontend, not a TUI wrapper

Deliverables:

- architecture docs updated
- task plan updated
- progress/findings synced

### P31.2 Thin Application Seam Hardening

Scope:

- introduce a new surface-neutral top application facade
- demote gateway naming from canonical behavior owner to transport wrapper
- define surface-neutral stream event DTOs for desktop/tui/remote reuse

Likely code targets:

- `src/mini_agent/application/`
- `src/mini_agent/interfaces/`
- `src/apps/agent_studio_gateway/main.py`

Acceptance:

- a future desktop client can depend on `surface service` semantics instead of `gateway use cases`
- gateway route files do not become business owners

### P31.3 Desktop Runtime Host Integration

Scope:

- create DesktopUI bootstrap app using `PySide6`
- add local gateway supervisor logic:
  - connect to existing host if running
  - or spawn/monitor local gateway if absent
- add health/reconnect/basic diagnostics

Acceptance:

- one desktop launcher can bring up or attach to the local Mini-Agent backend
- backend lifecycle is visible to the operator

### P31.4 Desktop Core Shell

Scope:

- main desktop window
- session list/thread panel
- main conversation/work area
- right-side contextual panels for model/status/task info
- streaming message rendering

Non-goal:

- no browser-shell embedding
- no TUI widget mirroring layer

### P31.5 Desktop Interaction Parity (First Usable Cut)

Scope:

- send prompt
- stream reply
- session switch/create/fork/share
- model list and switch
- approvals
- basic slash-command entry
- task/activity timeline visibility

Acceptance:

- DesktopUI reaches first daily-usable parity for the core operator path

### P31.6 Desktop Capability Follow-up

Scope:

- workspace picker
- upload/file drop
- memory/RAG/skills entry points
- richer diagnostics panes
- packaging and launch shortcuts

## 8. Non-Goals For The First DesktopUI Cut

- no attempt to preserve browser-first Studio as the main UX direction
- no attempt to wrap TUI rendering into Qt widgets
- no direct runtime embedding shortcut that bypasses the shared service boundary
- no WeChat/Feishu work
- no large gateway rewrite

## 9. Recommended Immediate Next Step

The next coding step should be:

- `P31.2 Thin Application Seam Hardening`

Reason:

- it is the smallest change that prevents future architecture drift
- after that, DesktopUI can safely start on top of the current gateway transport
- starting UI work before that seam lands would likely reintroduce gateway-owned behavior under a different name

## 10. Final Implementation Conclusion

Conclusion for execution order:

1. first harden the thin `application service seam`
2. then reuse the current gateway as DesktopUI's first transport/backend
3. then build the `PySide6 DesktopUI` shell and interaction slices

This is the best balance between:

- speed
- architectural cleanliness
- avoiding another later hard-refactor
