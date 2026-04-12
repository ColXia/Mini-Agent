# P28 Builtin Skill Realignment Plan

## Goal

Realign Mini-Agent builtin skills around a MiniMax-first bundled set instead of continuing to treat the current Anthropic-style example bundle as the long-term default.

This is a bundled-skill curation and migration slice, not a new skill runtime.

The runtime contract stays the same:

- builtin + workspace skill discovery
- workspace policy filtering
- `get_skill(...)` loading
- TUI / CLI / gateway `/skill ...` control

The change in this slice is the builtin catalog itself.

## Final Target Builtin Set

### Core Development

- `frontend-dev`
- `fullstack-dev`
- `android-native-dev`
- `ios-application-dev`
- `flutter-dev`
- `react-native-dev`
- `shader-dev`
- `mcp-builder`
- `webapp-testing`
- `skill-creator`

### Documents And Office

- `minimax-docx`
- `minimax-pdf`
- `pptx-generator`
- `minimax-xlsx`

### Multimodal And Creative

- `minimax-multimodal-toolkit`
- `gif-sticker-maker`
- `vision-analysis`
- `minimax-music-gen`

### Optional Entertainment / Demo

- `buddy-sings`
- `minimax-music-playlist`
- `minimax-novel-demo`

## Current State

The current builtin bundle under `src/mini_agent/skills/` is still mostly an Anthropic-style reference/example set:

- `algorithmic-art`
- `artifacts-builder`
- `brand-guidelines`
- `canvas-design`
- `docx`
- `pdf`
- `pptx`
- `xlsx`
- `internal-comms`
- `mcp-builder`
- `minimax-multimodal-toolkit`
- `minimax-novel-demo`
- `skill-creator`
- `slack-gif-creator`
- `template-skill`
- `theme-factory`
- `webapp-testing`

Only a small subset already matches the intended MiniMax-first direction.

## Migration Policy

### Keep

Keep these because they already fit Mini-Agent's platform direction and do not conflict with the target bundle:

- `mcp-builder`
- `webapp-testing`
- `skill-creator`
- `minimax-multimodal-toolkit`
- `minimax-novel-demo` (but treat it as optional/demo tier, not core)

### Replace

Replace the current generic document skills with MiniMax-aligned counterparts:

- `docx` -> `minimax-docx`
- `pdf` -> `minimax-pdf`
- `pptx` -> `pptx-generator`
- `xlsx` -> `minimax-xlsx`

Replace older example/demo skills when there is a cleaner MiniMax-first equivalent:

- `slack-gif-creator` -> `gif-sticker-maker`

### Add

Add these because they are part of the chosen final builtin set and are currently missing:

- `frontend-dev`
- `fullstack-dev`
- `android-native-dev`
- `ios-application-dev`
- `flutter-dev`
- `react-native-dev`
- `shader-dev`
- `vision-analysis`
- `minimax-music-gen`
- `buddy-sings`
- `minimax-music-playlist`

### Archive

Move these out of the default builtin bundle because they are example-library artifacts or product-misaligned for Mini-Agent:

- `algorithmic-art`
- `artifacts-builder`
- `brand-guidelines`
- `canvas-design`
- `internal-comms`
- `template-skill`
- `theme-factory`

Archived skills can remain in `docs/archive/` or a dedicated non-runtime bundle for reference, but should no longer appear in the default builtin runtime catalog.

## Execution Phases

### Phase 1: Catalog Decision And Documentation Lock

- record the target builtin set and migration policy
- stop treating the Anthropic example bundle as the product target
- identify stale docs that still describe "Claude Skills" as the builtin baseline

### Phase 2: Document Skill Replacement

- replace builtin document skill names/content with:
  - `minimax-docx`
  - `minimax-pdf`
  - `pptx-generator`
  - `minimax-xlsx`
- keep runtime loading mechanics unchanged
- update tests that assert builtin skill names

Current status:

- first slice landed
- builtin runtime registration names now resolve to the new document skill names
- system prompt Python-skill hints and bundled skills README now use the new names
- deeper document-skill doc cleanup and any future resource-structure realignment remain follow-up work

### Phase 3: Core Development Skill Introduction

- add:
  - `frontend-dev`
  - `fullstack-dev`
  - `android-native-dev`
  - `ios-application-dev`
  - `flutter-dev`
  - `react-native-dev`
  - `shader-dev`
- confirm they are discoverable, policy-controlled, and shown in Tier 1 metadata

Current status:

- first core-dev slice landed
- builtin `artifacts-builder` has been replaced by `frontend-dev`
- builtin `fullstack-dev` now exists as a real Mini-Agent skill instead of remaining only a target name in planning
- repo-level loader coverage now asserts the new names are discoverable through the actual bundled skills directory

### Phase 4: Multimodal / Creative Alignment

- keep `minimax-multimodal-toolkit`
- add:
  - `gif-sticker-maker`
  - `vision-analysis`
  - `minimax-music-gen`
- verify these do not conflict with MCP image/web tools and remain optional by task relevance

Current status:

- first multimodal alignment slice landed
- builtin `slack-gif-creator` has been replaced by `gif-sticker-maker`
- builtin `vision-analysis` now exists as a real Mini-Agent skill and is positioned to use the vision-capable MCP path when available
- `minimax-multimodal-toolkit` remains the generation-oriented multimodal entry, while `vision-analysis` covers inspection/reading
- builtin `minimax-music-gen` now exists as a focused music-generation layer above the broader multimodal toolkit

### Phase 5: Optional Demo Tier

- keep `minimax-novel-demo`
- add:
  - `buddy-sings`
  - `minimax-music-playlist`
- classify these as optional/demo-facing rather than core coding-agent skills

Current status:

- optional/demo tier is now materially landed
- `minimax-novel-demo` remains in place
- builtin `buddy-sings` now exists as a short sung/jingle demo skill
- builtin `minimax-music-playlist` now exists as a small playlist planning/generation skill
- these two stay explicitly positioned as optional/demo-facing, not core coding-agent guidance

### Phase 6: Archive And Doc Cleanup

- archive old example-only builtin skills
- update root/docs references that still say:
  - "Claude Skills"
  - Anthropic example repository is the recommended builtin baseline
- keep workspace skill install and custom skill creation docs, but rewrite builtin references to the new MiniMax-first catalog

Current status:

- archive step is now materially landed for the default builtin runtime path
- `algorithmic-art`, `brand-guidelines`, `canvas-design`, `internal-comms`, `template-skill`, and `theme-factory` have been moved to `docs/archive/builtin-skills/`
- the runtime-default bundled skills directory under `src/mini_agent/skills/` no longer exposes those archived names
- bundled skill docs now point operators to the archive explicitly instead of treating those legacy entries as still active builtin defaults

## Acceptance Criteria

- builtin discovery exposes the new MiniMax-first bundled set
- workspace skill policy continues to work without schema changes
- Tier 1 metadata prompt no longer injects old Anthropic-branded builtin skills by default
- `/skill list` reflects the new bundled catalog clearly
- stale docs no longer describe the old builtin bundle as the product-default direction

## Non-Goals

- no new skill runtime
- no new workspace policy format
- no marketplace/package installer redesign
- no remote skill source catalog redesign

## Risks

- many docs still reference "Claude Skills" or the Anthropic example repository, so partial migration will create documentation drift if catalog changes land before doc cleanup
- tests may encode old builtin names and fail until updated
- replacing bundled skills without preserving quality thresholds could reduce practical agent usefulness; quality matters more than matching a list mechanically

## Recommended First Implementation Slice

Land the migration in this order:

1. replace the four document skills
2. add `frontend-dev`, `fullstack-dev`, `vision-analysis`, and `gif-sticker-maker`
3. archive the most obviously product-misaligned example skills
4. then expand to mobile / shader / music optional tiers
