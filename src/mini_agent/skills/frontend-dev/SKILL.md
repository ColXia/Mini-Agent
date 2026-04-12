---
name: frontend-dev
description: Handle frontend UI work for web pages, components, dashboards, and interaction polish.
license: Complete terms in LICENSE.txt
metadata:
  trigger_keywords:
    - 前端
    - 页面
    - 组件
    - 界面
    - Web UI
    - React
    - dashboard
---

# Frontend Dev

Ship frontend work that feels intentional and usable, not placeholder UI.

## Use This Skill For

- Building a new web UI or component set
- Refactoring an existing frontend without breaking the design language
- Improving responsiveness, layout, accessibility, or interaction flow
- Producing a polished demo UI quickly

If the task is mostly backend, orchestration, or API work, prefer `fullstack-dev` and use this skill only for the UI slice.

## Working Rules

1. Inspect the existing stack before adding new dependencies.
2. Preserve the current design system when the repo already has one.
3. If no design system exists, choose a clear visual direction and keep it consistent.
4. Avoid generic AI-looking UI: no default purple gradients, no flat boilerplate dashboards, no lazy spacing.
5. Make desktop and mobile behavior both usable before calling the task done.

## Bundled Frontend Bootstrap

This skill includes a lightweight frontend bootstrap path for new projects:

- `scripts/init-artifact.sh <project-name>`
- `scripts/bundle-artifact.sh`

Use these scripts when the task needs a fresh React + TypeScript + Tailwind + shadcn/ui starting point or a self-contained HTML deliverable.

Do not force the bootstrap onto an existing application that already has its own frontend structure.

## Recommended Workflow

1. Identify the target surface:
   - existing app page/component
   - new frontend app shell
   - one-file demo/prototype
2. Inspect current routes, component structure, and styling primitives.
3. Define the smallest visible improvement or vertical slice first.
4. Implement structure before polish:
   - layout
   - state flow
   - user actions
   - empty/loading/error states
5. Polish the result:
   - typography
   - spacing rhythm
   - visual hierarchy
   - keyboard/focus behavior
   - responsive behavior
6. Validate in a browser when the app can run locally.

## Design Bar

- Make primary actions obvious.
- Separate user input, system status, and content areas clearly.
- Use contrast and spacing to create hierarchy before adding decoration.
- Prefer a few deliberate motion cues over constant animation.
- Keep long content readable with wrapping, spacing, and clear section breaks.

## Validation

When the app can run locally, pair this skill with `webapp-testing` and verify:

- core interaction flow
- responsive layout at narrow and wide widths
- obvious rendering glitches
- console/runtime errors if relevant

If the task is UI-heavy and also requires backend wiring, load `fullstack-dev` as well.
