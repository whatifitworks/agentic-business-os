---
name: adapter-recording-review
description: Review Browser/Computer adapter run records for evidence quality, confidence, stale UI assumptions, and memory routing. Use after adapter-runner records a result, when adapter evidence needs approval, or when deciding whether an adapter output should become an inbox item, output, source, process-only record, or blocked follow-up.
---

# Adapter Recording Review

Review one adapter run record and decide whether it is trustworthy enough to use.

## Inputs

- adapter run JSON under `sources/adapters/runs/`
- linked Markdown evidence note
- optional screenshot/export evidence path
- adapter contract under `.agents/adapters/<adapter>/`

## Review Workflow

1. Read the run JSON.
2. Read the linked Markdown evidence note.
3. Read the adapter contract and steps only if the result is ambiguous.
4. Check:
   - status is `success`, `blocked`, or `failed`
   - evidence path exists
   - evidence artifacts exist when claimed
   - target and inputs match the adapter contract
   - confidence matches evidence quality
   - caveats are explicit
   - stale UI/freshness limits are not violated
5. Decide:
   - `accepted` - evidence supports the structured values
   - `blocked` - missing evidence, login/manual verification, UI drift, or ambiguous result
   - `needs-inbox` - durable finding should enter memory through an inbox envelope
   - `drop/process-only` - fixture or low-value run needs no durable promotion

## Validation

Run:

```bash
python3 system/tools/browser_computer_adapter.py validate
python3 system/tools/ops_v2_hooks.py --hook adapter-evidence-check
```

## Output

Return:

- reviewed record path
- decision
- evidence gaps
- confidence correction, if any
- memory action: none, create inbox envelope, or process-only
- recommended adapter contract update, if the run exposed a fragile step

Do not edit wiki directly from an adapter review. Durable findings go through `inbox/`.
