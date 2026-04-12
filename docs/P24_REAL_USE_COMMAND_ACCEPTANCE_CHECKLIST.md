# P24 Real-Use Command Acceptance Checklist

> Status: Active
> Last updated: 2026-04-11
> Scope: command-level manual acceptance before daily real use for `TUI / CLI / QQ / gateway`

## 1. Goal

This checklist is the manual command-level companion to the existing automated readiness scripts.

Use it when we want to answer one practical question:

`Can Mini-Agent be used right now as a real daily terminal agent without command-surface surprises?`

This document does not replace automated tests.
It complements them with operator-visible checks across the actual command surfaces.

## 2. Source of Truth

When this checklist conflicts with runtime behavior, use these in order:

1. [`src/mini_agent/commands/catalog.json`](../src/mini_agent/commands/catalog.json)
2. [`tests/test_command_catalog.py`](../tests/test_command_catalog.py)
3. [`src/mini_agent/cli.py`](../src/mini_agent/cli.py)

Useful companion scripts:

- [`scripts/terminal_readiness_gate.py`](../scripts/terminal_readiness_gate.py)
- [`scripts/tui_manual_checklist.py`](../scripts/tui_manual_checklist.py)
- [`scripts/tui_interaction_walkthrough.py`](../scripts/tui_interaction_walkthrough.py)
- [`scripts/shared_session_gateway_walkthrough.py`](../scripts/shared_session_gateway_walkthrough.py)

## 3. Recommended Order

Run the checks in this order to keep failure localization simple:

1. Validate command catalog and entrypoints.
2. Validate headless and CLI local operation.
3. Validate TUI local operation.
4. Validate gateway and QQ shared-session command paths.
5. Validate restart and recovery behavior.

## 4. Preflight

Before doing the manual command checks, confirm:

- `uv sync` completed successfully.
- At least one usable model key exists in system environment variables or repo-root `.env.local`.
- If QQ is in scope, `src/apps/qqbot_channel/.env` is configured.
- WebUI is out of scope for this checklist.

Recommended quick preflight:

```powershell
Set-Location D:\file\Mini-Agent
uv run pytest tests/test_command_catalog.py -q
uv run mini --help
uv run mini qq status
```

## 5. Runtime Entry Checks

| Command | What to verify | Pass when |
| --- | --- | --- |
| `uv run mini --help` | Unified entry exists and shows `serve/cli/tui/stack/qq` | Help prints without traceback and includes `qq` shortcut |
| `uv run mini --mode headless --prompt "Reply with exactly: READY" --output-format json --workspace D:\file\Mini-Agent` | Headless path is usable | Output is valid JSON and contains a successful final reply |
| `uv run mini --mode cli --workspace D:\file\Mini-Agent` | CLI starts normally | CLI prompt appears without startup crash |
| `uv run mini --mode tui --workspace D:\file\Mini-Agent` | TUI starts normally | Main layout renders and accepts input |
| `uv run mini qq status` | Runtime stack management exists | Status prints `gateway/qqbot/workspace` summary even if stack is stopped |
| `uv run mini qq --workspace D:\file\Mini-Agent` | One-command shared runtime entry works | Gateway starts, QQ bot starts if configured, and TUI attaches |

## 6. CLI Command Checklist

Run these inside CLI interactive mode.

| Command | What to verify | Pass when |
| --- | --- | --- |
| `/help` | Help text uses catalog-backed commands | Command families include `model`, `memory`, `context`, `kb`, `workflow` |
| `/stats` | Session stats path is alive | Returns current session stats without crash |
| `/history` | Local message history is tracked | Returns current message count or equivalent history summary |
| `/model show` | Current model is visible | Provider/model info is shown clearly |
| `/model list` | Model listing works | At least current provider/model candidates are listed |
| `/model use <provider_id> <model_id>` | Hot switch path works in CLI | Switch succeeds and next `/model show` reflects the same selection |
| `/sandbox status` | Current sandbox boundary is inspectable | Backend / mode / approval / guardrails render without crash |
| `/kb status` | KB explicit toggle state is visible | Current KB state is returned |
| `/kb on` then `/kb off` | KB can be toggled locally | Status changes and is reflected by `/kb status` |
| `/context show brief` | Prepared-context summary is visible | Returns bounded context summary without dumping raw internals |
| `/context include knowledge_base` | Context policy can be adjusted | Include list updates cleanly |
| `/context reset` | Context policy reset works | Policy returns to default state |
| `/memory overview` | Cross-layer memory summary works | Runtime/durable/consolidated overview renders |
| `/memory list` | Session runtime memory list works | Session entries are listed with selectors |
| `/memory show latest` | Session runtime entry detail works | One concrete runtime entry opens cleanly |
| `/memory consolidated` | Consolidated layer is inspectable | Consolidated snapshot or empty-state message renders |
| `/memory profile` | Global profile browsing works | Global durable profile is readable |
| `/memory notes` | Workspace durable notes are browsable | Workspace notes or empty-state message renders |
| `/memory export markdown` | Explicit export path works | Export succeeds or returns a clear bounded failure |
| `/workflow run Summarize the current repo state` | Minimal workflow entry works | Workflow stages complete and final summary returns |
| `/compact keep latest context` | Explicit compaction works | Context shrinks and response explains the effect |
| `/drop_memories keep latest turn` | Aggressive context drop works | Older context is pruned without breaking the session |
| `/clear` | Local session reset is real | Transcript/runtime residue is cleared consistently |
| `/exit` | CLI exits cleanly | Process exits without traceback |

## 7. TUI Local Checklist

Run these inside TUI input.

| Command | What to verify | Pass when |
| --- | --- | --- |
| `/help` | TUI help matches live command surface | Help shows `session`, `model`, `memory`, `context`, `tasks`, `cancel` |
| `/session new` | New local thread can be created | New thread appears in Threads |
| `/session list` | Thread listing works | Current threads are listed in command output |
| `/session rename <new_title>` | Title editing works | Threads and status reflect the new title |
| `/session <n>` | Numeric session jump works | Focus changes to the selected session |
| `/session share` | Runtime session can be exposed to remote surfaces | Share state updates in TUI and gateway sees it |
| `/session unshare` | Runtime session can be hidden from remote surfaces | Share state clears without changing session identity |
| `/model list` | Provider/model panel and command output align | Current provider/model is visible in both UI and command output |
| `/model use <provider_id> <model_id>` | TUI command hot-switch works | Selected marker and effective model stay consistent |
| `/model filter <keyword>` and `/model filter clear` | Model filtering works | Candidate list filters and restores correctly |
| `/model limit list` | Limit metadata is readable | Model limit info or empty-state message renders |
| `/sandbox status` | TUI sandbox surface is wired | Command output renders current backend / policy / caps without crash |
| `/kb status` | KB state is visible in TUI | Status renders without affecting chat layout |
| `/context show brief` | Context diagnostics are visible | Output appears as command/system feedback, not chat pollution |
| `/memory overview` | Cross-layer memory summary renders cleanly | Output is readable inside TUI command surface |
| `/memory shared list` | Shared runtime memory surface is inspectable | Workspace-shared entries list cleanly |
| `/tasks list` | Minimal task lifecycle is visible | Current TUI session tasks are listed |
| `/activity collapse` then `/activity expand` | Activity block control works | Activity blocks collapse and expand predictably |
| `/command collapse` then `/command expand` | Command block control works | Command feedback blocks collapse and expand predictably |
| `/cancel` during a running turn | Running turn can be interrupted | Current turn stops and TUI remains usable |
| `/approve` or `/deny <token>` with a waiting approval | Approval path is usable from TUI | Waiting tool call resolves cleanly |
| `/clear` | TUI local session reset is real | Chat, prepared context, and runtime residue do not unexpectedly reappear |

## 8. QQ and Shared-Session Checklist

Run these after gateway and QQ bot are up.

| Command | What to verify | Pass when |
| --- | --- | --- |
| `/ping` | QQ bot is alive | Returns `pong` or equivalent alive response |
| `/help` | QQ command surface is visible | Help includes `session`, `model`, `memory`, `context`, `continue` |
| `/status` | Shared-session stats work | Returns bound session status cleanly |
| `/session` | Shared-session list works | Shared sessions are listed with selectable numbers |
| `/session <n>` | Remote session rebinding works | Current QQ conversation binds to the selected shared session |
| `/continue` | Remote transcript recap works | Returns recent transcript items from the bound session |
| `/model show` | Session-scoped model state is visible | Returns selected or pending provider/model for the shared session |
| `/model list` | Remote model list works | Available provider/model list returns without corrupting session binding |
| `/model use <provider_id> <model_id>` | Shared-session model switch works | Next `/model show` reflects the same session-scoped model |
| `/context show brief` | Shared-session context diagnostics work | QQ can read prepared-context status for the bound session |
| `/context reset` | Shared-session context policy reset works | Policy resets without dropping the session |
| `/memory overview` | Shared-session memory overview works | Runtime/durable/consolidated summary returns cleanly |
| `/memory shared list` | Shared runtime memory is visible remotely | QQ can inspect workspace-shared runtime entries |
| `/memory promote shared latest` | Explicit promotion works remotely | Shared promotion succeeds on the bound session |
| `/memory save note <text>` | Manual durable confirmation works remotely | Durable note save succeeds and response is explicit |
| `/approve [token]` or `/deny [token]` | Remote approval flow works | Waiting approval resolves from QQ |
| `/cancel` | Remote cancellation works | Running shared turn stops cleanly |
| `/reset` | Shared-session reset works | Current shared session resets without deleting the binding system |
| `/clear` | QQ local conversation cache can be cleared | Local QQ-side cache resets without crashing the bot |

## 9. Cross-Surface Handoff Checklist

These are the most important real-use checks because they validate the product, not just isolated commands.

| Flow | What to verify | Pass when |
| --- | --- | --- |
| QQ sends a normal task | QQ-origin task creates or reuses a shared session | Session appears in TUI Threads after sync interval or `/session sync` |
| TUI takes over a QQ-origin session | Shared-session handoff works | TUI becomes active surface and continues on the same `session_id` |
| TUI replies on QQ-origin session | Reply routing stays correct | Final answer is sent back to QQ, while TUI also shows the full work trace |
| TUI local session stays private by default | Local/shared boundary is honest | Local-only sessions do not appear in QQ before `/session share` |
| TUI shares a local session | Explicit promotion works | Shared session becomes visible remotely and remains the same thread |
| TUI unshares a TUI-origin shared session | Explicit demotion works | Session returns to local-only mode without transcript loss |
| Model switch from QQ is reflected in TUI | Session-scoped model parity works | TUI status and actual next-turn model match QQ selection |
| Memory and context commands from QQ are reflected in TUI | Shared operator surface is unified | TUI sees the same memory/context effect on the bound session |

## 10. Restart and Recovery Checklist

| Action | What to verify | Pass when |
| --- | --- | --- |
| `uv run mini qq down` then `uv run mini qq --workspace ...` | Runtime stack restart works | Gateway and QQ bot come back cleanly |
| Reopen TUI after restart | Shared-session persistence works | Previously shared sessions are discoverable again |
| QQ `/continue` after restart | Recovery transcript remains usable | Recent messages still return after restart |
| TUI opens a restarted shared session | Recovery state is visible | Session detail still shows enough status to continue |
| Continue the interrupted session with a new prompt | Recovery continuation is usable | Work resumes without creating an unrelated fresh thread |

## 11. Minimum Pass Bar

For a real daily-use green light, at minimum these must all pass:

1. `uv run mini --help`
2. Headless single-prompt JSON run
3. CLI `/model show`, `/kb status`, `/memory overview`, `/clear`
4. TUI `/session new`, `/session share`, `/model use`, `/cancel`
5. QQ `/ping`, `/session`, `/continue`, `/model show`
6. One QQ-origin task appearing in TUI and being continued there
7. One restart followed by successful shared-session recovery

If any one of those fails, the system is not yet ready for dependable real use.

## 12. Notes

- WebUI remains paused and is intentionally out of scope.
- KB remains an explicit tool path; this checklist does not assume passive KB injection.
- This checklist is manual by design. For automated coverage, always pair it with:
  - `uv run pytest tests/test_command_catalog.py -q`
  - `uv run python scripts/terminal_readiness_gate.py`
  - `uv run python scripts/shared_session_gateway_walkthrough.py`
