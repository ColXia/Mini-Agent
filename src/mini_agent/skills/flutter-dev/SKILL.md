---
name: flutter-dev
description: Build or refactor Flutter application features across widgets, state management, routing, and platform integration. Use whenever the user asks for Flutter screens, widget fixes, cross-platform mobile UI work, Dart app flow changes, or Flutter plugin/configuration issues.
metadata:
  trigger_keywords:
    - Flutter
    - Dart
    - 跨平台移动端
    - widget
    - 路由
---

# Flutter Dev

Use Flutter as a structured widget and state system, not as a loose pile of screens.

## Use This Skill For

- new Flutter screens and flows
- widget tree cleanup and composition
- routing and navigation
- state management integration
- platform channel or plugin wiring

## Workflow

1. Inspect the current Flutter app shape:
   - routing
   - state management style
   - feature/module layout
   - theme and design primitives
2. Implement the smallest working user flow first.
3. Reuse the existing state approach already chosen by the project.
4. Keep widgets focused and composable.

## Expectations

- Preserve theme consistency.
- Avoid over-nesting build methods when extraction would improve clarity.
- Treat loading, empty, and error states as first-class.
- Keep platform-specific integration explicit when Android or iOS behavior differs.

## Validation

When Flutter tooling is available, prefer targeted commands such as analyze, targeted tests, or narrow app validation before broader rebuilds.

If local platform runtimes are unavailable, leave a clear note about what still needs device/emulator confirmation.
