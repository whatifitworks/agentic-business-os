---
name: create-goal
description: "Turn a vague idea into a clear, runnable goal with a verifiable /goal completion condition, saved as its own file to run now or later. /create-goal"
argument-hint: "[the goal or rough idea]"
---

# Create Goal

## What this does

Helps you turn a rough intention into a clear, **runnable** goal — one with success criteria you can actually verify, and a completion condition that Claude Code's built-in `/goal` can evaluate. Each goal is saved as its own file so you can run it now or come back to it later. Use it whenever you catch yourself with a fuzzy "I should..." that you can't tell when you've finished.

The hard part of any goal is the **done test**. `/goal` keeps Claude working across turns until a small, fast evaluator model confirms your condition is met — but that evaluator **only sees what Claude has surfaced in the conversation. It does not run commands or read files on its own.** So a condition only works if Claude's own output can demonstrate it. Getting that condition right is this skill's main job.

## Step 1: Get the rough idea

If `$ARGUMENTS` holds the idea, start there. Otherwise ask: *"What's the goal — what do you want to be true when it's done?"* One or two sentences is enough to begin.

If the owner instead wants to **run or revisit an existing goal**, jump to "Run a saved goal" below.

## Step 2: Sharpen it (one tight round)

Ask only what's missing, in one batch (3-4 questions max). Aim the questions at the part that's usually fuzzy:

1. **Done test** — How will we *know* it's finished? What's the single measurable end state (a number, a passing check, an empty queue, a shipped artifact)?
2. **Proof** — How can Claude *demonstrate* that end state in its own output (run a command and show the result, produce the artifact, show the count)? If nothing Claude could say would prove it, the goal isn't runnable yet — reshape it.
3. **Guardrails** — What must NOT change or break on the way there? What's explicitly out of scope?
4. **Bound & deadline** — How long should it run before stopping to check in (turns or time), and is there a real-world deadline?

Don't over-interrogate. One round, then draft.

## Step 3: Draft the goal and stress-test the completion condition

Write the goal using the schema in Step 4. Then **stress-test the completion condition** — this is the core of the skill. A condition that survives many turns has all four of:

- **One measurable end state** — a test result, a build exit code, a file or issue count, an empty queue, a published output. Not "improve" or "make better".
- **A stated, demonstrable check** — exactly how Claude proves it *in the conversation*, e.g. "`npm test` exits 0 and the output is shown", "`git status` is clean", "the file count under `src/` is N". The evaluator only sees the transcript, so the proof has to land there.
- **Constraints that matter** — what must hold the whole way, e.g. "no other test file is modified", "the public API is unchanged".
- **A turn or time bound** — append a stop clause so it can't run forever, e.g. "...or stop after 20 turns". (The whole condition can be up to 4,000 characters.)

Run this checklist against the draft and rewrite until every box is yes:

- [ ] Could a fresh model, reading only the transcript, confirm this is met?
- [ ] Is the end state a thing you can point at, not a vibe?
- [ ] Does it say how Claude should prove it?
- [ ] Does it name what must not change?
- [ ] Does it have a stop clause?

Show the owner the drafted goal and the final one-line condition. If the owner can't yet name a verifiable end state, save the goal as `proposed` with the open question recorded — do not invent a fake metric to make it look measurable.

## Step 4: Save it

Create one file per goal at `context/goals/<slug>.md` (slug = short kebab-case). Use this schema:

```
---
goal: <slug>
title: <short title>
status: proposed        # proposed | active | achieved | cleared
created: <YYYY-MM-DD>
deadline: <date | none>
bound: <"stop after N turns" | time clause | none>
---

## Outcome
<what is true in the world when this is done>

## Why it matters
<the stakes — why this is worth a goal>

## Completion condition
<the /goal-ready text: measurable end state + how Claude proves it in-conversation
 + constraints + bound. This is what you paste after /goal.>

## Definition of done
- [ ] <demonstrable criterion>
- [ ] <demonstrable criterion>

## Constraints / non-goals
- <what must not change / out of scope>

## First action
<the concrete first step>

## Log
- <YYYY-MM-DD> — created
```

Then add (or update) the one-line entry in the `context/goals.md` index under **Active Goals**, linking to the goal file. Keep the index short — depth lives in the goal file. `daily-planning` and `weekly-review` read `context/goals.md`, so a good index keeps goals in front of you.

## Step 5: Run it now, or save for later

Ask the owner: **run it now, or save for later?**

- **Run now** — set `status: active`, log the date, then present the exact, ready-to-send command:

  ```
  /goal <completion condition>
  ```

  The built-in `/goal` is started by the owner sending that line — a skill cannot press enter on a slash command for them. Sending it kicks off the loop; `◎ /goal active` shows while it runs, `/goal` checks status, and `/goal clear` stops it. For an unattended run, the same works as `claude -p "/goal <condition>"`.
- **Save for later** — leave it `proposed` in the index. It can be run any time by sending its `/goal` line.

This skill stays generic: `/goal` is the default runner, but a goal file is just a clear definition — a downstream project can also drive it with a Stop hook, `/loop`, or a scheduled task. Don't assume one run mechanism.

## Run a saved goal

When the owner wants to act on an existing goal instead of creating one:

1. Read the `context/goals.md` index and list active goals (title, status, one-line condition).
2. Let the owner pick one, or infer it from their message.
3. Open its `context/goals/<slug>.md` and present the completion condition as a ready-to-send `/goal <condition>`.
4. Offer to refine the condition first if it does not pass the Step 3 checklist.

## Rules

- The completion condition must be **demonstrable from Claude's own output** — never write a condition the evaluator cannot see proof of.
- Every condition needs a **stop clause**. No unbounded goals.
- Don't fabricate a metric to make a goal look measurable. If the end state is genuinely fuzzy, save it `proposed` and name the open question.
- **Never start the `/goal` loop on the owner's behalf.** Prepare it and hand it over; the owner sends it.
- One file per goal; keep `context/goals.md` a short index. Move achieved goals to the **Achieved** section, and archive them when the list grows.
- Stay generic. Don't hardcode goal types or assume how a given project runs its goals.
