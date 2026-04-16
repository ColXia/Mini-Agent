# P32 Remote Interaction Architecture Lock

> Status: Active
> Date: 2026-04-14
> Goal: permanently stop architecture drift where `QQ` gets treated like a fifth entrance or dormant remote adapters stay alive in the active tree

## 1. Locked Product Model

The user-side entrances are only:

1. `CLI`
2. `TUI`
3. `DesktopUI`
4. `Remote Interaction`

`QQ` is not a peer entrance.
`QQ` is the current concrete adapter under `Remote Interaction`.

## 2. Active Remote Scope

The active codebase carries exactly one remote adapter path:

- `src/apps/qqbot_channel/`

Everything else is out of the active implementation scope unless a new architecture decision explicitly reintroduces it.

That means:

- no active `WeChat` adapter tree
- no active `Feishu` adapter tree
- no legacy parallel Python/TypeScript channel stacks
- no browser `WebUI / OpenWebUI` path

## 3. Physical Repo Rules

To prevent drift, future remote work must follow these rules:

1. Do not list `QQ` alongside `CLI / TUI / DesktopUI` as a peer entrance.
2. Do not revive `src/channels/*`, `src/mini_agent/channels/*`, or `src/gateway/channels/*`.
3. Do not keep dormant "future adapter" code in the active tree.
4. New remote adapters, if approved later, must start as new app-path implementations under `src/apps/`.
5. Remote adapters may own protocol glue, channel credentials, delivery formatting, and local binding hints only.
6. Remote adapters must not own session truth, runtime policy, command semantics, or model/memory business logic.

## 4. Hard-Refactor Actions In P32.60

This lock slice performs the following cleanup:

- keep `src/apps/qqbot_channel/` as the only maintained remote adapter app
- remove legacy channel trees:
  - `src/channels/types/`
  - `src/channels/wechat/`
  - `src/mini_agent/channels/`
  - `src/gateway/channels/`
- remove obsolete smoke/test surfaces tied to deleted channel trees
- lock interaction normalization so only `QQ` resolves as an active remote adapter
- sync active docs so they describe `Remote Interaction` correctly

## 5. Acceptance

The slice is considered complete when all of the following are true:

1. Active docs describe entrances as `CLI / TUI / DesktopUI / Remote Interaction`.
2. `QQ` is described only as the active remote adapter.
3. The active repo no longer contains old `WeChat` or legacy channel trees.
4. Tests no longer teach the old multi-channel active model.
5. Future work has one obvious path: extend shared application/runtime layers first, and touch the QQ adapter only as a thin transport shell.
