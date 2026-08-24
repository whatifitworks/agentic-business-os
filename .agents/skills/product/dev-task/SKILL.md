---
name: dev-task
description: "Orchestrate a dev task: risk-classify, autonomous apply + PR, cross-model review loop, automated verification, hand off. /dev-task, bugs, features."
---

# Dev Task

Bridge this ops/assistant repo and a **separate code workspace** so dev tasks run end-to-end from the ops
chat - no manual copy-paste. The pipeline runs **autonomously** from investigation -> apply + open PR ->
review<->fix loop -> automated verification -> hand-off. There is **no pre-apply "approve the plan" gate**;
the project owner's only touchpoints are the **manual testing and the manual merge** at the very end.

The coding agent runs as **one persistent coder session per sub-repo** (driven via a runner) so context
lives in the session instead of being re-fed every turn. Reviews run on a **different model tier** from the
coder for an independent perspective. Review depth and hand-off detail **scale with task risk** - but the
risk tier adds **no mid-pipeline human gate**.

## The flow

The pipeline is autonomous end-to-end until the hand-off. The dev agent writes code, opens the PR, and the
review<->fix loop runs on that PR with no human approval pause. The owner first engages at manual testing.

1. The owner describes a task. Phase 0 **classifies risk** (low/medium/high - this sets review-lens count +
   hand-off detail only) and, for multi-repo work, plans a **dependency-first sequence**.
2. The skill starts a coder session in the target repo via the runner and drives it with `resume` across the
   whole loop.
3. **Investigate -> apply, no gate between.** The coder emits one **structured block** per turn
   (`DEV_TASK_DATA_REQUEST` | `DEV_TASK_QUESTION` | `DEV_TASK_REPORT` | `DEV_TASK_RESULT`). Ops fulfills data
   via its integrations and answers genuine blocking `QUESTION`s, but a `REPORT` (the proposed plan) is
   **logged and auto-advanced to apply** - it is not surfaced for approval. (The plan is visible later as the
   PR diff + the review comments.)
4. Apply runs **full-cycle by default**: edit + build + branch + commit + push + open a PR. Code lands on a
   branch/PR (never the main branch).
5. A **cross-model review panel** (N lenses by risk) reviews **the PR** and **posts findings as PR comments**.
   Blocking findings loop back into the coder session -> fix -> push -> re-review, **until reviewers pass**
   (cap 3 rounds).
6. **Automated verification** runs - **mandatory for any change that renders a UI surface** (Phase 2.6:
   build/serve, drive the changed surface, AI-judge integrity + aesthetics, post the verdict + screenshots to
   the PR). Integrity failures or clear visual defects loop back like a review block.
7. **Prepare release + hand-off.** For a user-shipping app change, the skill proposes a **version bump +
   release-notes entry** (Phase 2.7) which the **owner verifies** and which ride on the PR branch. Then it
   hands off the PR + review outcome + verification verdict + a what-changed summary + a manual-test
   checklist. The owner does the **residual manual testing** and the **manual merge**.
8. **Ship to a testing track.** After the owner merges, the skill (where automated) builds and uploads to an
   internal/testing distribution track so the owner installs and tests the real build. Nothing merges to the
   main branch automatically.

## Constants

```
WORKSPACE_ROOT  = <path to the separate code workspace>
SUB_REPOS       = <the app's sub-repos, e.g. backend | ios | android | web>
LOG_DIR         = logs/dev-tasks                  # relative to this ops repo
CONFIG_FILE     = .agents/skills/product/dev-task/config.yaml
RUNNER          = <persistent coder-session runner you provide>   # see "Driving the coder session"
```

Each sub-repo has its own main branch and remote; all open PRs via the host's PR command (`gh pr create`
or equivalent). Record the per-repo build commands, schemes, and gotchas in a `sub-repo-reference.md`
sidecar and inject the matching section into the coder prompt.

## Runtime config

**Read [config.yaml](config.yaml) at the start of every run (Phase 0).** It controls the coder
(`runner`/`model`/effort), `scope` (how far apply goes), the `review` panel (runner/model/lenses),
`risk_tiers` (review-lens count + hand-off detail per tier - **no gates**), `risk_high_signals` (the
classifier rubric), `verify` (Phase 2.6), `release` (Phase 2.7/4), and `post_ship_watch` (Phase 5).

Precedence: per-call override from the owner > config.yaml > fallback. **Surface the effective config once
at the top** so the owner can override at any prompt.

### Scope - how far the apply phase goes

| Scope | Apply ends after | Branch | Commit | Push | PR |
|---|---|---|---|---|---|
| `edit-only` | verify build, leave tree dirty | no | no | no | no |
| `commit-only` | commit on feature branch | yes | yes | no | no |
| `push-only` | push feature branch | yes | yes | yes | no |
| `full-cycle` | PR opened | yes | yes | yes | yes |

## Phase 0 - Setup, risk, sequencing

1. Gather (ask or infer): **task description + why**, target sub-repo if obvious, **related artifacts**
   (ticket, crash signature, analytics event, issue - these seed the data menu), **constraints** (feature
   flag? backward compat? deadline?).
2. **Classify risk** against `risk_high_signals`: **high** if the task touches payments/billing, auth/
   security, DB migrations, data deletion, money math, webhooks, or prod infra; **medium** for app/business
   logic and API endpoints; **low** for copy/styling/config/docs/tests-only. State the tier and why; the
   owner can override. The tier sets **only** the review-lens count + hand-off detail - never a pre-apply gate.
3. **Multi-repo decomposition:** if the task spans repos, split into per-repo sub-tasks and **sequence by
   dependency** (e.g. the API change is investigated, applied, reviewed, and merged/deployed *before* the
   client sub-tasks that consume it). Pass the upstream contract into the downstream threads as context.
4. Generate a slug `<repo-hint>-<brief-desc>`. Create the trace log `LOG_DIR/YYYY-MM-DD-<slug>.md` with task
   + constraints + risk tier + seed artifacts. Append every iteration.

## Driving the coder session (the engine)

Use a runner that keeps **one persistent coding-agent session alive across iterations** (captures the
session handle, resumes it each turn) rather than a fresh process per message. The runner is
**backend-agnostic** - any coding-agent CLI that can start + resume a session and return its last message,
usage, and a timeout/exit signal. Keep credentials and any MCP/tool config out of the coder (the ops side
fulfills production data via `DEV_TASK_DATA_REQUEST`).

The runner contract the skill depends on:
- **start** a session in a repo dir (investigate = read-only; apply = write).
- **resume** the same session every subsequent turn (no context re-feed).
- Return `{session_id, last_message, usage, exit_code, timed_out}`.
- **`--schema <file>`** to force structured JSON output where the output is single-shape (see schemas).
- **`--stream`** to tee a live transcript to a trace file so a long phase is observable (without it, the
  last message returns only at turn end - rely on the live process + the timeout to tell alive from hung).

Write the prompt to a file (never inline huge prompts). Parse `last_message` for the structured block; log
`usage` and `timed_out`. On timeout or non-zero exit, surface the last trace to the owner.

## Phase 1 - Investigate loop

The coder is told: **investigate, propose, do not write code yet.** Loop (cap = `max_iterations_per_phase`):

```
thread = runner.start(repo=WORKSPACE_ROOT, prompt=investigate_prompt, mode=read-only)
loop:
  block = parse(thread.last_message)
  DATA_REQUEST  -> fulfill via your integrations; resume(thread, DATA_RESPONSE)
  QUESTION      -> ask the owner; resume(thread, answer)   # only genuine blocking judgment calls
  REPORT        -> the proposed plan. LOG it and AUTO-ADVANCE to Phase 2 for EVERY tier - no approval pause.
                   First sanity-check the plan against the real code yourself; if it's clearly wrong, resume
                   with the correction instead of bouncing to the owner.
  none          -> resume("Emit exactly one structured block.")
```

**No report gate.** The skill never pauses to have the owner "approve the plan" before apply. Phase 1 only
stops for a real `DEV_TASK_QUESTION` or a data request.

**The REPORT carries acceptance criteria.** `DEV_TASK_REPORT` includes an `acceptance_criteria` field - the
concrete, checkable list of what proves the change works (per case: action -> expected result), including the
negative/gated cases. Log it; Phase 2.6 hands it to the verification agent as the case list, so it tests what
the change *promised* instead of reverse-engineering intent from the diff.

## Phase 2 - Apply loop (scope-driven)

Immediately after the report (auto-advanced), resume the thread (or start a `write` thread in the sub-repo)
told: **apply the proposed change; go as far as `scope` allows.** Inject the sub-repo reference. Emits
`DEV_TASK_RESULT` when done or `QUESTION` on trouble.

### Hard branch/git rules (every scope >= commit-only)
- Feature branch from the main branch. **Never touch the main branch.** No force-push.
- **Never** bypass hooks/signing (`--no-verify`, `--no-gpg-sign`, etc.). One commit per logical change,
  conventional style (read recent `git log` first).
- **Build must pass before commit** - on failure emit `DEV_TASK_QUESTION`, never commit unverified code.
- Push without `--force`. Open the PR via the host's PR command.

## Phase 2.5 - Cross-model review panel (reviews the PR)

After apply opens the PR, run the review panel **on the PR**, **on a different model than the coder**. Number
of lenses = `risk_tiers[tier].review_lenses`. Reviewers get the **full changed file(s)** alongside the diff
(a bare diff hides unchanged-but-relevant context and causes false positives) and may read related code.
**The review verdict + findings MUST be posted as a PR comment** - a review only the orchestrator saw is
indistinguishable from no review. Blocking findings loop back to the coder; re-review; repeat (cap 3 rounds).

- **Verify every `block` before looping.** A block is a claim, not a fact - check it against the full file;
  dismiss context-blind false positives with evidence rather than sending the coder to "fix" a non-issue.
- **Apply reviewer-warning scope before looping.** Only a confirmed `warn` in production functional code -
  code that ships or executes as part of the product or its production migrations - is eligible for an
  automatic fix, and only when that fix stays inside the approved scope. A `warn` or `nit` attributable
  solely to tests, fixtures, snapshots, documentation, examples, developer/support tooling, or workflow
  code is report-only: surface it in the hand-off, but do not auto-fix it, re-review it, or block readiness.
  A confirmed `block` in those files still loops when it invalidates correctness, security, migration, or
  verification evidence. This policy governs AI review findings; configured format, compile, lint, test,
  security, and CI gates must still pass at their required warning threshold.
- Spawn each lens as its own independent reviewer, **schema-forced** with `schemas/review.schema.json` (its
  output is exactly one REVIEW block - single-shape, safe to force). Lens prompts: [prompt-templates.md](prompt-templates.md).
- Low risk runs 1 lens (correctness); high runs all (correctness, security, performance, regression).

## Phase 2.6 - Automated verification

Invoke the **[test-task](../test-task/SKILL.md)** skill on the PR. **Mandatory after the review passes (and
after the review comment is on the PR), before hand-off**, for any change that renders a UI surface. Only a
pure-backend change with no rendered surface skips it. The verdict + screenshots **MUST be posted to the
PR**; integrity failures or clear visual defects loop the task back to the coder like a review block.

- **Hand test-task the acceptance criteria** from the Phase 1 REPORT so it verifies what the change
  *promised*, not just what the diff touched (covering the negative/gated/empty cases a diff-only reading
  misses).
- A clear visual defect (broken/leftover/empty section, overflow, readability break) loops back; only minor
  aesthetic nits are surfaced to the owner, not auto-fixed.

## Phase 2.7 - Prepare release: version bump + notes

**Required for any user-shipping app change** (skip for backend/docs/infra/tests-only per `release.skip_for`).
A user-shipping change must not hand off without a **version bump + a release-notes entry on the PR branch**.

- Bump the app version with a **scriptable helper** rather than hand-editing the project's version files -
  hand edits miss occurrences across build configurations / targets and drift sub-targets out of sync. The
  helper should scope the bump to the app target and bump every relevant configuration uniformly.
- Add a user-facing release-notes entry (in-app "what's new" and/or store notes), matching the app's voice.
- **Verify with the owner** (always on - release notes are outward-facing): show the version numbers + the
  notes; on approval, commit them to the PR branch so they merge with the change.

## Phase 3 - Hand-off & manual testing

**Hard gate - do NOT hand off until the PR carries the required artifacts:** the **review verdict** (Phase
2.5) and - for a UI change - the **verification verdict + >=1 embedded screenshot** (Phase 2.6). A review or
verdict reported only in chat does not count; post it to the PR and re-check. (A handoff-check script that
inspects the PR for these artifacts is the reliable enforcement.)

This is the **first** point where the owner engages - a hand-off, not a gate the pipeline waited on. Present,
per `risk_tiers[tier].handoff`: **step-by-step** (high risk, one logical hunk at a time) or **summary**
(low/medium). Then hand off for manual testing: the PR link, the review outcome, the verification verdict,
and a checklist of the **residual** (real-device feel, payment/edge cases, anything no automated flow
reached, the final taste call). The PR stays open and unmerged.

## Phase 4 - Merge & ship to a testing track

1. Close the trace log: final status, branch, commit, PR URL, risk tier, review outcome, summary.
2. **Merge is manual.** dev-task never merges. Once the owner confirms manual testing passed, the owner merges.
3. **Ship to a testing track** (where automated): build from the main branch and upload to an internal/
   testing distribution track, then surface the link so the owner installs and tests the real build.
4. **Multi-repo:** if this was the upstream sub-task of a sequenced job, wait for the owner's merge/deploy
   before starting the downstream sub-tasks; pass the upstream contract as context.
5. If a support ticket was referenced, draft the "fix shipped" reply (don't auto-send).
6. **High-risk change -> register a post-ship watch (Phase 5).**

## Phase 5 - Post-ship watch (high risk only)

For a high-risk change, the pre-merge gates can't catch a regression that only shows under real traffic.
After it ships, **register a watch and run it when it fires** (per `post_ship_watch`; default on for `high`,
~24h window): add a once-task to the recurring obligations, due the next business day, then check the live
signals for the changed surface via your integrations - error rate / new exception signatures (backend),
new crash signatures (mobile), and a conversion sanity check if the change touches a paid/conversion
surface. **Suggest-only - never auto-rollback.** Record `clean` or `anomaly <evidence>` in the trace log; on
an anomaly, surface to the owner and open a follow-up dev-task if the cause is clear.

## Data-request handlers

The coder requests production data; the skill fulfills via this project's integrations and resumes with a
`DEV_TASK_DATA_RESPONSE`. Map each request category to one of your integrations, with auto-approve limits
and a review gate for writes:

| Request category | Auto-approve | Review gate |
|---|---|---|
| datastore query | read-only, bounded limit | any write/DDL |
| logs / log query | read-only | very large scans |
| support ticket / thread | read-only | — |
| billing/subscription record | read-only | — |
| analytics events | read-only | very expensive |
| auth / user record | read-only | any write |
| issue / PR | read-only | — |
| object-store read | scoped buckets | other buckets |

Anything off-list: surface to the owner ("not in auto-fulfill handlers, asking").

## Hard rules

- **Never push to the main branch**; always a feature branch. **Never** bypass hooks/signing. **Never**
  force-push without explicit approval. **Never** delete branches/files/migrations unless the task requires it
  and the owner approves.
- **No mid-pipeline human gates.** Autonomous from investigate -> apply + PR -> review<->fix -> verification.
  The human touchpoints are manual testing + the manual merge. Pause earlier only if the owner asked per-call
  or for a genuine `DEV_TASK_QUESTION`.
- **Mandatory PR artifacts.** Before hand-off the PR MUST carry the review verdict and - for any UI change -
  the verification verdict + >=1 embedded screenshot, posted to the PR itself.
- **Review panel runs on a different model than the coder.** No self-review by the coding agent.
- **Do not spend fix-loop time on non-production reviewer warnings.** AI-review `warn`/`nit` findings in
  tests, fixtures, snapshots, documentation, examples, developer/support tooling, or workflow code are
  report-only and never block hand-off. Only production-functional-code warnings are fix-eligible. This
  does not relax deterministic lint/compiler/test/security/CI gates or confirmed blockers that undermine
  the validity of migration, verification, correctness, or security evidence.
- **Caps:** `max_iterations_per_phase`, 3 review->fix rounds, a per-call timeout. On any cap, surface state -
  never loop forever. **Trace-log every iteration.**

## Prompt templates & schemas

Investigate / apply / review-lens / walkthrough prompts: [prompt-templates.md](prompt-templates.md). JSON
Schemas for `--schema` structured output: [`schemas/`](schemas/) - `report.schema.json` (carries
`acceptance_criteria`), `result.schema.json`, `data_request.schema.json`, `question.schema.json`,
`review.schema.json`. Force a schema only where output is single-shape (the review lenses); investigate/apply
turns legitimately choose among block types, so parse the fenced block and validate its fields.
