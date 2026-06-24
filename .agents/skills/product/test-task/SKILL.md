---
name: test-task
description: "Verify a code change: build/serve, drive the change, AI-judge integrity + aesthetics, post screenshots to the PR. /test-task, 'test this PR'."
---

# Test Task

Standalone verification that runs **after** the dev agent ([dev-task](../dev-task/SKILL.md)). Given a branch
or PR for a UI surface (mobile, web, or an API), it builds/serves the app, drives the **actual changed
behavior**, captures the screens, and has **this session look at them** - an **integrity** check ("anything
broken?") on every screen, plus an **aesthetic** review ("would users like it?") when the change touches UI -
then reports as a PR comment. Final taste stays with the project owner on the real build.

**Run the visual judgment on your strongest vision-capable model.** This is the quality-critical last line of
defense - it exists to catch the broken/leftover/empty section that code review cannot. If your harness lets a
skill pin a model tier, pin the verification agent to a strong one; it runs once per UI PR, not in a loop.

**Do the vision judgment inline, in this session** - look at each screenshot and reason about it. Don't spawn
a separate headless agent for it: you're judging a rendered screen, not reviewing code you authored, so
there's no self-grading bias to avoid.

**Platform sidecars - load the one for the target surface.** Build commands, drivers, login chains, and
gotchas live there, not here:
- mobile (iOS/Android) -> [platforms/mobile.md](platforms/mobile.md)
- web -> [platforms/web.md](platforms/web.md)
- API (no UI) -> [platforms/api.md](platforms/api.md)

## Inputs
- A **pull request** (preferred), or a branch/ref + acceptance criteria.
- **When invoked by dev-task, the acceptance criteria / test cases are passed in** (the dev agent's REPORT
  carries them). Use that list as the spine of step 1.5 instead of re-deriving intent from the diff alone -
  dev-task knows what the change promised; don't reverse-engineer it.

## Test accounts
To reach a state (logged-in, premium, etc.), log in as a **named test account** - never a real user. Keep
labels in a tracked file and credentials in a **gitignored** sibling, read at runtime, **never** pasted into
logs / screenshots / PRs. Writes are OK *scoped to the test account's own data*; **never** mutate
subscription / entitlement / payment / real-account state, complete a real purchase, or spam prod rate limits
- stop and ask first. **Destructive actions are OK to actually perform on a test account** whose data you may
mutate (if the backend soft-deletes / the account regenerates) - that is how you verify they *work*.

## Testing discipline (applies to every surface)
These rules make a run real verification, not a rubber stamp. The sidecar has the *how*; this is the *what*.

**A login-gated screen is NOT "unreachable" - log in, do not fall through.** If the change is on a screen
needing a logged-in / owned-data state, you **must** drive a credentialed login to reach it. Having the test
accounts means the state IS reachable. Posting a screenshot of a screen that does **not** contain the change
does not count as verification. Only fall through when the state genuinely cannot be reached even *with* a
test account (e.g. store-billing UI on a non-store build - see the sidecar), and say exactly why.

**Verify the REQUIREMENT, not just the static render.** A screenshot of a control existing is not proof the
feature works. Exercise the behavior end to end and capture each step. e.g. a delete: tap it -> confirm the
dialog appears (capture it) -> confirm -> verify it returns to the right screen -> verify the state refreshed
(the item is actually gone; check the datastore/API if there's a data effect).

**Gated controls (visible only in some states) - verify BOTH directions.** A control shown conditionally
(owned vs not, free vs paid, empty vs populated) is only verified when you confirm it **appears in the
allowed state AND is absent in the disallowed state**. Confirm absence via the platform's element-tree dump,
not by eyeballing the screenshot.

## Flow

**1 - Target.** Identify the branch/PR; fetch its diff. Preserve the working branch. **Load the platform
sidecar** for the changed surface.

**1.5 - Enumerate the cases to test BEFORE capturing.** Start from the **acceptance criteria passed by
dev-task** (or, standalone, derive them from the diff + requirement). Don't test one happy path and stop.
Walk: happy path; behavior + state change (drive it end to end); negative/gated (both directions); edge/
boundary (empty, error, cancel/dismiss, loading, first-run vs returning); other entry points. Mark any case
you genuinely can't reach (and why) - "I only ran the happy path" is not acceptable.

**2 - Build / serve.** Use the sidecar's command. Verify the real result (build succeeded / page serves) -
`| tail` masks failures. Must pass before continuing.

**3 - Install / open.** Per the sidecar.

**4 - Capture key screens.** Drive the changed surface per the sidecar. Captures must be settled - wait for a
real element, never a fixed timer.

**5 - Integrity check (ALWAYS).** Look at each capture and judge for objective breakage: overlap, clipping,
truncation, blank/error/loading state, broken/missing images, misalignment, unreadable contrast, content cut
off. Emit per screen `{ screen, ok, confidence, issues: [{severity, what, where}] }`. A loading spinner or
half-rendered content = `ok:false` (the capture wasn't settled). For web, console errors are an integrity
signal too.

**6 - Aesthetic review (ONLY when UI changed).** If the diff touches UI: does it look good and on-brand,
would users like it, any clarity/conversion concerns. Emit `{ screen, verdict, strengths, concerns,
conversion_notes }`. Tie concerns to retention/conversion where relevant. Be a sharp designer, not a rubber
stamp.

**7 - Report on the PR.** Write the comment (overall verdict, integrity result, aesthetic review if run) with
the screenshot embedded, and post it to the PR. Host private-repo screenshots somewhere the PR can render
them (e.g. an object store + the host's image proxy). **Get the owner's approval before posting** (external
write).

**8 - Record.** Write the run + verdicts to a runs archive. Route a real bug to the inbox as a candidate.

## Notes
- **No pixel-diff gate.** Dynamic screens (rotating content, async feeds) make pixel diffing too brittle - two
  captures of the same screen can differ a lot. **The AI look is the check.** (Pixel diff is fine only for
  genuinely static screens.)
- **Beauty stays human.** This catches broken / off / unclear; the final taste call is the owner's on the
  real build.
- **Captures are deterministic** because you pin the status bar / chrome and wait for a real element (never a
  fixed timer) - the app loads async.
