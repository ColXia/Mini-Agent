---
name: ios-application-dev
description: Build or refactor iOS application features in Swift, SwiftUI, or UIKit, including navigation, view state, app lifecycle, capability wiring, and native platform debugging. Use whenever the user asks for iPhone or iPad app work, SwiftUI screens, UIKit changes, Xcode project fixes, or iOS-specific behavior.
metadata:
  trigger_keywords:
    - iOS
    - 苹果
    - Swift
    - SwiftUI
    - UIKit
    - Xcode
---

# iOS Application Dev

Treat iOS work as platform-specific engineering, not generic frontend work.

## Use This Skill For

- SwiftUI screens and state flow
- UIKit view/controller work
- navigation and presentation fixes
- Info.plist or capability wiring
- iOS-specific bugs and app behavior

## Workflow

1. Inspect the existing iOS structure:
   - SwiftUI or UIKit
   - project layout
   - navigation style
   - model/state conventions
2. Implement the smallest shippable feature slice first.
3. Preserve the repo's current Apple-platform patterns before introducing a new architecture.
4. Keep side effects and view state separated where the codebase already expects that.

## Guardrails

- Respect platform conventions for lifecycle and permissions.
- Avoid burying app logic in view code when an existing coordinator/store/view-model seam exists.
- Handle empty, loading, and failure states for user-visible flows.

## Validation

If Xcode-driven validation is not available on the current machine, still complete the code changes carefully and state the exact runtime verification gap.

If project-local tests or static checks exist, run the narrowest relevant ones first.
