# P27 Skill Workspace Task Plan

> Status: Active
> Date: 2026-04-11
> Scope: make skills globally discoverable but workspace-governed, so agent-core can stay lightweight while still being controllable from TUI/CLI/gateway

## 1. Goal

Refine Mini-Agent skills into one clean model:

- skills are discovered from builtin/workspace/plugin/remote sources
- workspace decides which discovered skills are active for that workspace
- agent prompt injection, `get_skill`, turn-context skill hints, and operator commands all read the same workspace policy

The target is not a second skill system. The target is one runtime path with one workspace policy seam.

## 2. Guardrails

- keep the existing `AgentSkillLoader` as the discovery source of truth
- do not add a parallel skill registry outside the current loader/runtime chain
- keep workspace policy persisted under the workspace, not mixed into global user state
- make TUI/CLI/gateway reuse the same `/skill` action seam
- prefer direct refactor over compatibility wrappers

## 3. Target Design

### Plane S1: Global skill discovery

Owns:

- builtin skills
- workspace skill files
- plugin skills
- remote registered skills

Implementation:

- `AgentSkillLoader`
- source-priority override rules stay unchanged

### Plane S2: Workspace skill policy

Owns:

- active mode: `all` or `allowlist`
- allowlist entries
- denylist entries

Storage:

- `<workspace>/.mini-agent/skill_policy.json`

### Plane S3: Runtime filtered skill view

Owns:

- what the agent sees in `SKILLS_METADATA`
- what `get_skill(...)` can load
- what `SkillCatalogTurnContextProvider` can suggest

Implementation:

- `WorkspaceSkillRuntimeBridge`
- policy-aware filtering on top of the raw loader

## 4. Implementation Phases

### Phase 1: Workspace skill policy foundation

Status:

- completed in current slice

Tasks:

- add persisted `WorkspaceSkillPolicyStore`
- support `all` + `allowlist` mode
- support explicit allowlist / denylist mutation helpers
- add a policy-aware runtime bridge for prompt injection and `get_skill`

Acceptance:

- workspace can persist skill activation state
- agent metadata prompt only lists active skills
- inactive skills are not loadable through `get_skill`

### Phase 2: Runtime and turn-context integration

Status:

- completed in current slice

Tasks:

- feed workspace policy into shared tool initialization
- make `SkillCatalogTurnContextProvider` respect workspace-active skills
- include skill-policy file in TUI skill-catalog change signature

Acceptance:

- skill hints only suggest workspace-active skills
- manual skill-policy edits can be detected by TUI refresh checks

### Phase 3: Operator command integration

Status:

- completed in current slice

Tasks:

- extend `/skill` across TUI/CLI/QQ/gateway:
  - `list`
  - `active`
  - `show`
  - `search`
  - `mode`
  - `enable`
  - `disable`
  - `reset`
  - `refresh`
- keep all mutations on the same runtime/gateway seam
- rebuild the current session agent after local or remote policy change when idle

Acceptance:

- operator can inspect workspace skill state without leaving TUI/CLI
- remote shared sessions can update workspace skill policy through gateway
- busy sessions return a clear “policy updated, refresh after turn” response

## 5. Current Slice Landed

- persisted workspace skill policy under `.mini-agent/skill_policy.json`
- `WorkspaceSkillRuntimeBridge`
- policy-aware skill metadata injection in kernel bootstrap
- policy-aware skill turn-context filtering
- TUI/CLI/gateway `/skill active|mode|enable|disable|reset`
- remote command summary support for new skill actions
- regression coverage for policy-filtered runtime bridge and updated command catalog
- remote shared-session coverage for `/skill active|mode|enable|disable|reset`
- gateway use-case coverage for idle rebuild and busy-without-rebuild policy updates
- remote error-path coverage for `not_found`, `disabled`, `unavailable`, and invalid `mode`
- TUI operator-message consistency coverage for local/remote `unknown action`, invalid local `mode`, and remote `disabled/unavailable` policy mutations
- lazy cross-session local skill-runtime reload signaling:
  - non-current local sessions with warmed agents are marked pending and invalidated after workspace skill changes
  - busy local sessions auto-apply pending skill reload after the current turn finishes
  - switching back to a pending local session auto-warms the refreshed skill runtime
- TUI surfaces pending local skill-runtime reload state in threads/status views

## 6. Next Recommended Slice

Status update:

- item 1 is now landed in TUI status as a compact local skill runtime / policy overview
- item 2 is now partially landed through shared-session `pending_skill_reload` projection and richer remote command feedback
- item 3 is now landed for the current `/skill` control seam across TUI / CLI / QQ / gateway

The next meaningful gap is not more policy surface polish. The next meaningful gap is installation semantics.

### Phase 4: Skill Installation And Registration Pipeline (mostly landed)

Goal:

- let an operator, and later an approved agent action, add a new workspace skill without manually editing the skill directory blind

Minimum desired shape:

- one explicit install path into `<workspace>/.mini-agent/skills/`
- validate `SKILL.md` structure before activation
- persist any install source metadata separately from runtime policy
- require explicit approval before agent-authored skill files are written
- refresh the active loader and expose the new skill through the existing `/skill` seam

Now landed:

- shared `WorkspaceSkillInstaller`
- `/skill install <path>` across TUI / CLI / QQ / gateway
- agent-facing `install_skill(...)` tool for inline workspace skill creation
- agent-facing `install_skill_from_path(...)` tool for importing:
  - an existing local skill directory
  - a local `SKILL.md`
  - a single-skill archive
  - an `http/https` URL to one of those sources
- persisted workspace install-source ledger at `<workspace>/.mini-agent/skill_sources.json`
- validation + auto-activation through the existing workspace skill policy seam
- operator install output now surfaces the ledger location
- metadata/runtime guidance now explicitly allows multi-skill composition for cross-domain tasks
- agent-facing `uninstall_skill(...)` and `rollback_skill(...)`
- `/skill uninstall <skill_name>` and `/skill rollback <skill_name>` across TUI / CLI / gateway shared sessions
- workspace backup storage under `<workspace>/.mini-agent/skill-backups/`
- source-ledger-driven uninstall / rollback lifecycle instead of install-only bookkeeping
- archive extraction guardrails so packaged skills cannot write outside the extract destination

Not yet implemented:

- persisted remote skill registration catalog
- marketplace-oriented remote source catalog / trust policy
- richer repair flows beyond latest-backup rollback

Recommended order:

1. add persisted remote skill registration catalog
2. add marketplace-oriented trust / source policy
3. add richer repair actions beyond latest-backup rollback
