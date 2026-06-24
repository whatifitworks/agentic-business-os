# test-task - mobile sidecar (iOS / Android)

Platform mechanics for verifying a **mobile** change. The shared spine (flow, testing discipline, report/
record) is in [../SKILL.md](../SKILL.md); this is the *how* for mobile.

## Build + install + capture
- **Build** the debug app for a simulator/emulator with the platform's CLI (e.g. `xcodebuild` for iOS,
  `gradlew assembleDebug` for Android). Verify the real success line - `| tail` masks failures.
- **Install** onto a booted simulator/emulator and **drive** the UI with a flow runner (an open-source
  UI-automation tool). Keep one flow per screen under a tracked `flows/<platform>/` dir.
- **Pin the status bar / system chrome** to fixed values so captures are deterministic, and **wait for a real
  element** (never a fixed timer) - the app loads async.

## Credentialed login + onboarding
- Pass test-account credentials to the flow at runtime (never echo them). Selectors are often the visible
  **text**, not internal accessibility ids.
- **One-time onboarding** (welcome carousel, permission prompts, profile questionnaire) persists once
  completed. Routine runs should **not** wipe local state (that re-triggers the whole gauntlet); complete
  onboarding once on a stable device to establish a persisted session, then launch straight to the target.
- When onboarding *does* appear on a fresh state, **walk it through to the target screen** - never screenshot
  the onboarding as if it were the target.

## Driving controls
- **Icon-only / un-text-matchable controls:** read the element tree (the runner's hierarchy dump) for the
  element's accessibility text + exact bounds, then tap by the bounds center - don't guess coordinates.
- **Element-tree dump** is also how you satisfy the shared "verify gated controls BOTH directions" rule:
  confirm a control is present in the allowed state and **absent** in the disallowed state.

## Environment limits to know (legitimate fall-throughs)
- **Store-driven UI may not render on an emulator / non-store build.** In-app-purchase / subscription
  paywalls driven by the platform's billing service often show a store-error state on a locally-built debug
  app instead of real products/prices. The non-product parts of the screen still render and are captureable,
  but **product/price UI is not verifiable here** - it's an environment limit, not a bug; don't loop it back
  to the coder. Verify it on a real internal/testing-track build with a license-tester account, or fall
  through to manual testing (and say exactly why).
