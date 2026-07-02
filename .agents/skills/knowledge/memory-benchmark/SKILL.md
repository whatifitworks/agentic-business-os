---
name: memory-benchmark
description: "Curate golden questions about the business and score the vault against them over time — the measurable proof memory is compounding. /memory-benchmark"
argument-hint: "[run | trend | add questions | fix failures]"
---

# Memory Benchmark

## What this does

Turns "the agent learns your business" into a number. A golden question is something the owner actually needs answered correctly and currently — "what's our refund policy?", "which channel acquires the cheapest customers?", "who is our fulfillment partner?". The benchmark (`system/tools/golden_questions.py`) checks that vault retrieval still surfaces the canonical answer for each one and that withdrawn claims haven't crept back in. Recorded runs build the trend: score going up means memory is compounding; going down means it's rotting.

Definitions: `state/golden-questions.json`. History: `state/golden-question-runs.jsonl`.

## Curating questions

1. Harvest candidates from what the owner really asks: `context/` priorities and goals, recent `decisions/log.md` entries, wiki areas, recurring questions in sessions. Ask the owner which answers going stale would actually hurt.
2. For each question (aim for 5, grow to ~20):
   - `id` — short kebab-case.
   - `question` — phrased the way the owner would ask it.
   - `canonical_paths` — the vault file(s) where the current answer lives. Verify each exists and actually contains the answer before adding.
   - `must_include` — 1-3 phrases the correct answer must contain. Specific enough to fail when the fact changes.
   - `stale_claims` — only when there's a real withdrawn claim to guard against; don't invent them.
3. Set `updated_at`, keep the owner's approval for the final set, and never put secrets or credentials in questions or phrases.

## Running and recording

```bash
python3 system/tools/golden_questions.py --record
python3 system/tools/golden_questions.py --trend
```

Record on a rhythm — after each weekly review, or whenever significant knowledge lands. One-off unrecorded runs are fine for debugging but don't build the trend.

## Fixing failures

A failing question is a memory bug with a name. For each:

- **Canonical not found in top results** — the answer file may be buried, duplicated, or the knowledge never made it out of `inbox/`. Fix the vault (promote, merge, or move content), not the question — unless the question was genuinely mis-specified.
- **Missing phrases** — the canonical file no longer states the fact plainly, or the fact changed. Update the file through the normal memory-ingest path, then update `must_include` only if the *truth* changed.
- **Contradiction (stale claim reappeared)** — find the line, correct it with an explicit negation/correction marker, and check where it leaked from.

After fixes, re-run with `--record` so the recovery shows in the trend. Chronic failures belong in `memory-graph-health` territory — say so rather than papering over them.

## Reporting

When asked for status (and during weekly-review): report latest score, delta since last run, failing ids with one-line causes, and whether the overall trend is improving, holding, or regressing. A regression is a headline, not a footnote.

## Rules

- Questions must be things the owner cares about, not trivia the vault happens to contain. A benchmark nobody would miss is theater.
- Never tune a question to make a failure pass. Fix the vault, or fix a genuinely wrong question and say which you did.
- Don't record runs against an empty question set.
- Keep the set stable enough to compare across months; note additions/removals in the ledger (`kind: note`) so trend jumps are explainable.
