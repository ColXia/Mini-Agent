---
name: android-native-dev
description: Build or refactor Android native features in Kotlin or Java, including screens, ViewModel flows, Compose UI, Gradle wiring, and Android app debugging. Use whenever the user asks for Android-native app work, Android UI changes, Android integration, Gradle or manifest fixes, or device-specific mobile behavior.
metadata:
  trigger_keywords:
    - Android
    - 安卓
    - Kotlin
    - Compose
    - Gradle
---

# Android Native Dev

Work within the existing Android project structure instead of inventing a parallel mobile stack.

## Use This Skill For

- Android app screens and flows
- Jetpack Compose or XML-based UI work
- ViewModel / repository / navigation wiring
- Manifest, permission, and Gradle configuration
- Android-specific bugs, lifecycle issues, and integration fixes

## Workflow

1. Identify the active Android structure:
   - app modules
   - Gradle setup
   - package layout
   - UI approach: Compose or Views
2. Find the smallest vertical slice that proves the change works.
3. Preserve platform conventions already present in the repo.
4. Keep business logic out of Activities and Fragments when the project already uses a cleaner seam.
5. Prefer focused build or test commands over broad full-project rebuilds when possible.

## Implementation Expectations

- Match the current architectural style before introducing new patterns.
- Keep navigation, state, and side effects explicit.
- Handle loading, empty, and error UI states for user-facing flows.
- Be careful with Android permissions, lifecycle transitions, and background work.

## Validation

If Android tooling is available in the workspace, verify using the lightest useful command first, such as module build, lint, or targeted tests.

If full device/emulator validation is unavailable, still leave the code in a state that is structurally consistent with the existing Android app and call out the exact validation gap.
