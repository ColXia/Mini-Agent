---
name: react-native-dev
description: Build or refactor React Native features spanning screens, navigation, state flow, native bridge integration, and cross-platform mobile behavior. Use whenever the user asks for React Native app work, Expo or bare RN screens, mobile UI fixes, bridge/plugin integration, or Android/iOS behavior in a JavaScript-based mobile app.
metadata:
  trigger_keywords:
    - React Native
    - RN
    - Expo
    - 移动端
    - 原生桥接
---

# React Native Dev

Build for the active React Native stack instead of treating the app like a generic web React project.

## Use This Skill For

- React Native screens and flows
- Expo or bare-RN integration work
- navigation and state flow fixes
- mobile UI behavior across Android and iOS
- bridge/plugin setup and platform-specific adjustments

## Workflow

1. Identify the active stack:
   - Expo or bare React Native
   - navigation library
   - state management style
   - platform-specific directories and config
2. Implement one working end-to-end mobile slice first.
3. Keep shared logic shared, and platform-specific behavior explicit.
4. Preserve the existing design primitives and navigation structure.

## Guardrails

- Do not assume web-only CSS or browser behavior will map cleanly to mobile.
- Handle safe areas, keyboard overlap, and smaller viewports deliberately.
- Respect existing native configuration instead of adding duplicate config sources.

## Validation

Run the narrowest useful checks available in the repo.

If device/emulator validation is unavailable, call that out explicitly and keep the code aligned with the current project conventions so the next real-device check is low risk.
