# P23 QQ/TUI Shared Session Runbook

> Status: Active
> Last updated: 2026-04-09
> Scope: Real manual verification for `QQ -> gateway -> runtime -> TUI` shared-session handoff, local-session sharing, and gateway restart recovery

## Goal

Use the shortest runnable path to verify these behaviors:

1. QQ messages enter the main runtime and create or reuse a shared session.
2. TUI can see the QQ-origin session in Threads within a short sync interval.
3. TUI can take over the same `session_id` and continue the task.
4. TUI local sessions stay private until explicitly shared with `/session share`.
5. Shared sessions survive gateway restart and remain discoverable from TUI and QQ.
6. QQ `/continue` can pull the latest 10 messages from the shared transcript.
7. QQ `/status` and `/continue` can show a restart-aware recovery snapshot, including the last known running state and recent activity.
8. Remote/shared sessions shown in TUI can display intermediate activity such as `thinking`, `shell`, and tool progress, not only the final reply.
9. QQ and remote TUI can trigger shared-session context controls (`/compact`, `/drop_memories`) without breaking session routing ownership.
10. QQ and remote TUI can switch one shared session's active provider/model without mutating unrelated session defaults.
11. QQ and remote TUI can inspect runtime task memory and explicitly confirm durable memory writes on the bound shared session.

## Scripted Drill

For a repeatable non-QQ-login readiness pass, you can now run:

```powershell
Set-Location D:\file\Mini-Agent
python scripts/shared_session_gateway_walkthrough.py
```

This scripted drill does not require a live QQ bot session, but it does validate the same gateway-managed shared-session mainline:

1. qq-origin metadata and transcript shaping
2. remote activity transcript visibility
3. TUI takeover and continued work on the same `session_id`
4. shared-session `/compact` and `/drop_memories`
5. remote `/cancel`
6. TUI import/export roundtrip
7. gateway restart persistence
8. interrupted-after-restart recovery snapshot
9. remote session-scoped model switching
10. remote shared-session memory diagnostics and explicit memory confirmation

## Prerequisites

- Run from repo root: `D:\file\Mini-Agent`
- Python env available through `uv`
- Node.js available for the QQ bot
- QQ official bot credentials:
  - `QQBOT_APPID`
  - `QQBOT_SECRET`
- At least one usable model configuration for the agent

## Recommended Shortest Setup

For this manual run, the safest path is:

1. Use a preset provider key in repo-root `.env.local`
2. Use QQ bot `.env` only for QQ channel configuration

This avoids first-run interactive setup noise and keeps the verification path simple.

## One-Command Startup

Once `.env.local` and `src/apps/qqbot_channel/.env` are ready, you can use the
new runtime stack entry instead of opening three terminals manually:

```powershell
Set-Location D:\file\Mini-Agent
uv run mini qq --workspace D:\file\Mini-Agent
```

Behavior:

1. Starts the gateway in the background.
2. Starts QQ bot automatically when `src/apps/qqbot_channel/.env` exists.
3. Sets `MINI_AGENT_GATEWAY_BASE` and attaches the TUI in the current terminal.

Shortcut notes:

- `uv run mini` is now the short alias for `uv run mini-agent`
- `uv run mini qq` is the short alias for `uv run mini-agent stack up --qqbot --tui`
- `uv run mini qq status|down|logs` are short aliases for the corresponding runtime-stack actions

Useful companion commands:

```powershell
uv run mini qq status
uv run mini qq logs --target gateway
uv run mini qq logs --target qqbot
uv run mini qq down
```

Windows shortcut script:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_runtime_stack.ps1
```

## Step 1: Prepare the Agent Model Key

Copy the local template:

```powershell
Set-Location D:\file\Mini-Agent
Copy-Item .env.local.example .env.local -Force
```

Then edit `.env.local` and keep only the key you really want to use, for example:

```env
MINIMAX_API_KEY=your_real_key_here
```

Notes:

- `.env.local.example` is only a template and is not loaded by the program.
- Actual load order is: system environment variables first, then repo-root `.env.local`.
- If no key is available, the first interactive launch may ask once whether to create one.

## Step 2: Prepare the QQ Bot Config

Create the QQ bot env file:

```powershell
Set-Location D:\file\Mini-Agent
Copy-Item src\apps\qqbot_channel\.env.example src\apps\qqbot_channel\.env -Force
```

Edit `src\apps\qqbot_channel\.env` and fill at least:

```env
QQBOT_APPID=your_appid
QQBOT_SECRET=your_secret
QQBOT_SANDBOX=true
QQBOT_MODE=websocket
MINI_AGENT_GATEWAY_BASE=http://127.0.0.1:8008
QQBOT_DEFAULT_WORKSPACE=D:/file/Mini-Agent
QQBOT_DEFAULT_DRY_RUN=false
```

Recommended for local manual verification:

- `QQBOT_MODE=websocket`
- `QQBOT_SANDBOX=true` if your bot is in sandbox mode

## Step 3: Install Local Dependencies

Repo Python deps:

```powershell
Set-Location D:\file\Mini-Agent
uv sync
```

QQ bot deps:

```powershell
Set-Location D:\file\Mini-Agent\src\apps\qqbot_channel
npm install
```

## Step 4: Start the Gateway

Open terminal A:

```powershell
Set-Location D:\file\Mini-Agent
uv run mini-agent serve --host 127.0.0.1 --port 8008 --workspace D:\file\Mini-Agent
```

Expected signals:

- startup self-check prints
- `Starting Studio API host...`
- gateway keeps running without exiting

Optional health check in another terminal:

```powershell
Invoke-RestMethod http://127.0.0.1:8008/api/v1/system/health
```

## Step 5: Start the QQ Bot

Open terminal B:

```powershell
Set-Location D:\file\Mini-Agent\src\apps\qqbot_channel
npm run start
```

Expected signals:

- no `Missing QQBOT_APPID or QQBOT_SECRET`
- log includes `qqbot-channel started`

If needed, watch this log file:

```text
src/apps/qqbot_channel/runtime.log
```

## Step 6: Start the TUI

Open terminal C:

```powershell
Set-Location D:\file\Mini-Agent
$env:MINI_AGENT_GATEWAY_BASE = "http://127.0.0.1:8008"
uv run mini-agent --mode tui --workspace D:\file\Mini-Agent
```

Notes:

- TUI polls remote shared sessions in the background.
- Current sync interval is about 2 seconds.
- Local TUI sessions are private by default.
- Use `/session share` when you want a local TUI thread to become gateway-visible.
- Use `/session unshare` to pull a TUI-origin shared thread back to local-only mode.
- Shared sessions now keep session-scoped model selection in gateway state.
- TUI remote `/model apply|use ...` and QQ `/model show|list|use ...` operate on the bound shared session itself.
- QQ now also supports `/memory status|show|list|refresh|promote|save` on the bound shared session.
- If the remote session does not appear quickly, run `/session sync` in the TUI input box.

## Step 7: Manual Verification Flow

### A. Verify QQ channel is alive

From QQ, send:

```text
/ping
```

Expected:

- QQ bot replies `pong`

### B. Create a QQ-origin shared session

From QQ, send a real task, for example:

```text
帮我读取 README，总结当前项目状态
```

Expected:

- QQ receives an answer
- a shared session is created or reused for that QQ conversation

### C. Observe the session in TUI

Go back to TUI and wait 2 to 3 seconds.

Expected:

- a new remote session appears in Threads
- the thread shows remote/source metadata from QQ

If not visible:

```text
/session sync
```

### D. Take over from TUI

Select the remote session in Threads, then run:

```text
/session takeover
```

If you want to target by id:

```text
/session takeover <session_id>
```

Expected:

- TUI shows takeover success
- the session remains the same shared `session_id`
- follow-up prompts from TUI continue the same conversation
- during execution, the main chat panel can show streamed activity blocks such as `thinking` and `shell`

### E. Continue the same task from TUI

In the TUI input box, send a follow-up prompt, for example:

```text
继续，把关键模块按 TUI、CLI、Gateway 三类整理
```

Expected:

- work continues in the same session
- this TUI follow-up is not auto-pushed back to QQ as a normal reply

### F. Share a local-only TUI session

Switch to a local thread in TUI, then run:

```text
/session share
```

Expected:

- the current local thread is promoted into a gateway-managed shared session
- the thread keeps its TUI title after sharing
- future work on that thread goes through gateway
- the shared thread is now eligible for QQ `/session` discovery

### G. Unshare a TUI-origin shared session back to local-only

In TUI, switch to a shared thread that originally came from TUI, then run:

```text
/session unshare
```

Expected:

- the shared thread is exported back into TUI local state with context preserved
- gateway deletes that shared session
- after unshare, the thread persists in local `tui_sessions.json`
- the thread is no longer visible from QQ `/session`

Notes:

- this is only supported for `origin_surface=tui` shared threads
- if the shared thread is currently owned by another surface, take it back first with `/session takeover`

### H. Pull context from QQ

Back in QQ, send:

```text
/continue
```

Expected:

- QQ receives a compact recovery snapshot first
- that snapshot includes route ownership, current/interrupted state, and the latest activity summary when available
- QQ then receives the latest 10 shared-session messages
- returned messages can include the TUI follow-up context and assistant replies

### H1. Inspect recovery status from QQ

Back in QQ, send:

```text
/status
```

Expected:

- when a shared session is bound, QQ returns a recovery-oriented status block instead of only local cache info
- if the gateway restarted during a turn, the reply includes `interrupted after restart: ...`
- if TUI has already taken over, the route shows the current ownership such as `qq->tui / own`

### H2. Trigger shared-session context control from QQ

Back in QQ, send one of:

```text
/compact keep latest context
/drop_memories clear older context
```

Expected:

- QQ receives a message/token delta summary
- TUI shows a new command block in the shared transcript after the next sync
- the session keeps its current ownership/routing until an explicit `/session takeover`

### H3. Verify shared-session model switching from QQ and TUI

Back in QQ, first inspect the bound shared session model:

```text
/model show
```

Expected:

- QQ returns the current `selected` model for the bound shared session
- if a queued switch exists, QQ also shows `pending`

Then list available provider/models from gateway:

```text
/model list
```

Expected:

- QQ returns provider-grouped models from the gateway registry
- the currently selected model is marked as selected
- if a switch is queued while the session is busy, the target model is marked as queued

Then switch the bound shared session model from QQ, for example:

```text
/model use openai gpt-5.3
```

Expected:

- QQ returns `Selected model: openai/gpt-5.3` when the session is idle
- TUI `Threads` / `Status` / header model hint update after the next sync
- the change only affects the current shared session, not unrelated sessions

Now, in TUI on the same shared session, inspect or switch again:

```text
/model show
/model use openai gpt-5.4
```

Expected:

- TUI shows the same selected model that QQ just set
- after TUI `/model use ...`, QQ `/model show` reflects the same new selected model
- the shared session keeps the same `session_id`

Finally, verify queued semantics while the shared session is busy:

1. Start one longer-running task from QQ or TUI on the shared session
2. While the task is still running, switch model from the other surface

Example from QQ while TUI is busy:

```text
/model use openai gpt-5.3
```

Expected:

- the switch response says the model is queued instead of immediately selected
- TUI shows `current -> target queued`
- after the running turn finishes, the next real turn on that same shared session uses the queued model

### H4. Verify shared-session memory diagnostics and explicit memory confirmation from QQ

Back in QQ, first inspect the runtime memory selector list for the bound shared session:

```text
/memory list
```

Expected:

- QQ returns the current session runtime-memory preview with numbered selectors
- the first item can also be referenced as `latest`
- the list is scoped to the currently bound shared session only

Then promote one runtime memory item into durable workspace memory:

```text
/memory promote note latest
```

Expected:

- QQ returns the promoted target and content summary
- the bound shared session transcript records the memory command
- the workspace `MEMORY.md` gains the distilled promoted note

Then explicitly save one manual conclusion, for example after a KB-grounded turn:

```text
/memory save note 已确认：这个工作区的 KB 结论需要人工确认后再进入 durable memory
/memory save profile 用户偏好中文回复
```

Expected:

- QQ returns the saved target and content
- when the latest prepared context included `knowledge_base`, the workspace note is categorized as `kb_confirmed`
- profile saves go into global durable profile memory, not the workspace-local `USER.md`

### I. Bind QQ to another shared session

From QQ, send:

```text
/session
```

Expected:

- QQ returns the current shared-session list
- each session has a `#n` selector

Then bind to one of them:

```text
/session 2
```

Expected:

- QQ binds the current conversation to shared session `#2`
- subsequent QQ messages continue that shared session

Note:

- QQ can only bind to gateway/shared sessions.
- TUI local-only sessions are not visible to QQ until they become shared/gateway sessions.

### J. Verify gateway restart persistence

Restart the stack or the gateway process:

```powershell
uv run mini-agent stack down
uv run mini qq --workspace D:\file\Mini-Agent
```

Expected:

- previously shared sessions are still listed after restart
- QQ `/session` still shows them
- TUI `/session sync` brings them back into Threads
- continuing the same shared `session_id` resumes prior context instead of creating a brand-new session

## Success Criteria

The real-use path is considered passed if all of these are true:

1. QQ can trigger agent work successfully.
2. TUI can see the QQ session without creating a parallel local-only session.
3. TUI takeover keeps the same conversation context.
4. TUI local-only sessions stay private until `/session share` is used.
5. Gateway-shared sessions remain discoverable after restart.
6. QQ `/continue` returns shared transcript content instead of empty history.
7. QQ `/status` and `/continue` expose enough recovery context to understand whether a session is idle, running, handed off, or interrupted after restart.
8. Shared sessions shown in TUI expose interrupted recovery state and intermediate activity flow instead of only the final assistant reply.
9. Shared-session `/compact` and `/drop_memories` work from QQ and remote TUI without silently changing session ownership.
10. Shared-session `/model show|list|use` stays consistent between QQ and TUI, and busy-session switches queue then apply on the next turn.
11. Shared-session `/memory list|promote|save` stays consistent between QQ and TUI and only affects the currently bound shared session.

## Fast Troubleshooting

### Gateway exits immediately

Most likely causes:

- no available model key
- invalid `config.yaml`
- startup self-check blocked

Check:

- repo-root `.env.local`
- gateway terminal output

### QQ bot starts but does not answer

Check:

- `QQBOT_APPID` and `QQBOT_SECRET`
- `QQBOT_SANDBOX` matches your bot environment
- `QQBOT_INTENTS` include message intents
- `src/apps/qqbot_channel/runtime.log`

### QQ answers, but TUI does not show the remote session

Check:

- TUI terminal has `MINI_AGENT_GATEWAY_BASE=http://127.0.0.1:8008`
- gateway is the same host and port used by QQ bot
- wait at least one sync interval
- run `/session sync`

### QQ or TUI `/model list` fails

Check:

- gateway is reachable from both QQ bot and TUI
- the provider registry is initialized and at least one provider/model is available
- preset keys or custom providers are actually configured

Quick checks:

```powershell
uv run mini qq status
Invoke-RestMethod http://127.0.0.1:8008/api/v1/agent/models
```

### `/model use` succeeds on one surface but the other surface still shows the old model

Check:

- you are looking at the same shared `session_id`
- wait one TUI remote-sync interval or run `/session sync`
- if the session was busy, confirm whether the switch is queued and send one more real turn to consume it

### QQ `/memory list` or `/memory promote` fails

Check:

- the QQ conversation is already bound to a real shared session
- the shared session has runtime task memory entries to promote
- the gateway is reachable and `POST /api/v1/agent/sessions/{session_id}/memory` is healthy

Quick recovery:

1. Send one normal task message to create or advance the shared session
2. Retry `/memory list`
3. Use `latest` or the displayed numeric selector from that list

### `/continue` says there is no current session

That usually means the QQ conversation has not yet created a session in this bot process.

Do this first:

1. Send one normal task message from QQ
2. Wait for the agent reply
3. Retry `/continue`

## Stop Commands

Use `Ctrl+C` in:

- terminal A for the gateway
- terminal B for the QQ bot
- terminal C for the TUI

## Current Known Gaps

This runbook verifies the shared-session mainline, but it does not yet cover:

- gateway-managed remote approval/resume semantics comparable to local TUI restart recovery
- full production-grade QQ persistence beyond current bot-process session mapping behavior
- richer QQ-side structured control beyond the current `/status`, `/continue`, `/cancel`, `/context`, `/model`, `/memory`, `/compact`, and `/drop_memories`
