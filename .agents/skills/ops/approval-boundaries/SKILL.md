---
name: approval-boundaries
description: "Author, review, and enforce the machine-readable contract of what the agent may do without a human — observe first, then enforce. /approval-boundaries"
argument-hint: "[review | edit | enforce | status]"
---

# Approval Boundaries

## What this does

Maintains `rules/approval-boundaries.yaml` — the contract that says which agent actions are fine (`allow`), which need a human first (`ask`), and which never happen (`deny`). The runtime gate (`system/tools/approval_gate.py`, wired as a Claude Code PreToolUse hook) evaluates every tool call against it and logs matches to the ledger. In `observe` mode nothing is blocked — the log shows what *would* have been gated. In `enforce` mode, ask/deny decisions actually gate the call.

This is the safety spine of the whole OS: automation is only trustworthy when its limits are written down, versioned, and checkable.

## Status check

For "status" or a general question, report:

1. Current `mode`, rule count, and `updated_at` from `rules/approval-boundaries.yaml`.
2. Recent evaluations: `python3 system/tools/ledger.py query --kind boundary_evaluation --limit 20`
3. Whether the compiled mirror is in sync: `python3 system/tools/approval_boundaries_audit.py`

## Authoring or editing rules

1. Interview the owner about the actions that worry them, in their language: sending anything external (email, posts, campaigns, replies), moving money, changing customer records, deleting things, publishing. One batch of questions, not a quiz.
2. Translate each worry into a rule: unique kebab-case `id`, one-line `intent` in plain words, `decision` (`allow`/`ask`/`deny`), and `match` — tool-name globs plus optional `input_any` patterns. Follow `system/schemas/approval-boundaries.schema.yaml` for matching semantics.
3. Keep `deny` for never-events (credentials, payments). Use `ask` for anything the owner wants eyes on. Do not gate safe local work — a contract that fires constantly gets ignored.
4. Show the owner the full diff of the contract before writing it.
5. After writing: validate and compile, then record the change:
   ```bash
   python3 system/tools/approval_boundaries_audit.py --compile
   python3 system/tools/ledger.py append --kind decision --actor human:owner \
     --summary "Updated approval boundaries: <what changed>" --ref rules/approval-boundaries.yaml
   ```

## Reviewing the observe log

Weekly (or when asked), summarize `boundary_evaluation` entries since the last review:

- Which rules fired, how often, and on what tools.
- False positives — matches on work the owner considers safe. Propose narrowing the pattern.
- Near misses — risky calls that matched nothing. Propose a new rule.
- If the log is clean and complete for a week or two of normal work, propose flipping to `enforce`.

## Turning enforcement on

1. Only with explicit owner approval, never on your own initiative.
2. Set `mode: enforce`, update `updated_at`, recompile the mirror, and append a ledger `decision` entry recording who approved it and why.
3. Remind the owner: the gate fails open on internal errors, Codex sessions treat the contract as instructions rather than a hard gate, and `mode: observe` is one edit away if enforcement gets in the way.

## Rules

- Never weaken or bypass a boundary to get your own current task unblocked. If a rule blocks you, say so and stop.
- Every contract edit is owner-approved, recompiled, and ledger-logged in the same session.
- Keep the public template's rules generic; business-specific rules (named tools, amounts, recipients) belong downstream.
- Do not log raw sensitive input into the ledger; the gate already truncates input heads.
- If `approval_boundaries_audit.py` fails, fix the contract before doing anything else — a broken contract means the gate is silently inactive.
