# Mini-Agent Bundled Skills

This directory contains the builtin skills shipped with Mini-Agent.

Skills are loaded dynamically through progressive disclosure:

- Level 1: name + description
- Level 2: full `SKILL.md`
- Level 3: bundled `scripts/`, `references/`, and `assets/` as needed

## Preferred Bundled Catalog

These are the skills Mini-Agent is actively aligning around as the product-default bundle.

### Core Development

- `frontend-dev` - frontend UI construction, refactor, and polish
- `fullstack-dev` - end-to-end product slice implementation across surface and backend
- `android-native-dev` - Android native app development
- `ios-application-dev` - iOS application development
- `flutter-dev` - Flutter app development
- `react-native-dev` - React Native app development
- `shader-dev` - shader and rendering effect development
- `mcp-builder` - MCP server design and implementation guidance
- `webapp-testing` - Playwright-based local web testing
- `skill-creator` - create and improve skills

### Documents And Office

- `minimax-docx` - Word document workflows
- `minimax-pdf` - PDF workflows
- `pptx-generator` - PowerPoint workflows
- `minimax-xlsx` - spreadsheet workflows

### Multimodal And Creative

- `minimax-multimodal-toolkit` - MiniMax multimodal generation
- `minimax-music-gen` - focused MiniMax music generation guidance
- `vision-analysis` - image and screenshot analysis
- `gif-sticker-maker` - short looping GIF and sticker creation

### Optional / Demo

- `minimax-novel-demo` - optional demo-oriented writing workflow
- `buddy-sings` - short playful sung demo responses
- `minimax-music-playlist` - multi-track playlist planning and generation guidance

## Document Boundary

Mini-Agent uses a single normalized document parsing entrypoint:

- `docling_parse`: parsing and text extraction
- document skills: higher-level authoring, editing, and workflow orchestration

The document skills should not act like a parallel parsing subsystem.

## Archived Legacy Skills

The older example-style skills have been moved out of the default builtin bundle and archived under:

- `docs/archive/builtin-skills/`

They remain available as reference material, but they are no longer part of the runtime-default skill catalog.

## Creating Custom Skills

For custom skill creation:

- read `agent_skills_spec.md`
- inspect `skill-creator/`

Each skill is a directory containing a `SKILL.md` file plus optional bundled resources.
