---
name: vision-analysis
description: Analyze images, screenshots, photos, diagrams, and visual evidence. Use whenever the task depends on understanding what is visible in an image or screenshot rather than only reading text, including UI bug reports, screenshot review, design critique, before/after comparison, scene understanding, and multimodal inspection tasks.
metadata:
  trigger_keywords:
    - 图片
    - 截图
    - 图像
    - 视觉分析
    - 看图
    - 界面截图
    - screenshot
---

# Vision Analysis

Use actual vision tooling instead of guessing from partial textual hints.

## Primary Approach

1. Obtain the image or screenshot.
2. Use a vision-capable tool if one is available.
3. Return a structured reading of what is visible, what is uncertain, and what action should follow.

## Preferred Tools

- If the MCP tool `mcp_minimax_coding_plan_understand_image` is available, use it for image understanding.
- If the image is a web page or application state, capture a fresh screenshot first with Playwright rather than reasoning from memory.
- If multiple images are involved, compare them explicitly instead of describing each in isolation.

## Common Task Shapes

- UI bug triage:
  - clipping
  - overflow
  - selection mismatch
  - spacing/alignment issues
  - unreadable text or contrast
- Design review:
  - hierarchy
  - rhythm
  - visual balance
  - affordance clarity
- Screenshot comparison:
  - what changed
  - what regressed
  - what still looks wrong
- Diagram or scene reading:
  - key entities
  - relationships
  - labels
  - ambiguity

## Response Shape

Prefer this structure:

1. `Summary`
2. `Observed details`
3. `Uncertainty or missing visibility`
4. `Recommended next step`

## Guardrails

- Do not claim text or details that are not visible.
- Do not rely on stale screenshots if the UI may already have changed.
- If the image is insufficient, say exactly what extra image or crop is needed.

If the issue is a UI implementation problem, combine this skill with `frontend-dev` or `webapp-testing`.
