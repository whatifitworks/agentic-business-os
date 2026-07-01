# State

This folder is part of Agentic Business OS.

- `skill-namespace-plan.json` records whether a skill namespace migration is pending or already applied.
- `ledger.jsonl` is the append-only, hash-chained business ledger: decisions, external actions, outcomes, evidence links, and approval-boundary evaluations. Write through `system/tools/ledger.py append`; check with `ledger.py verify`.
- `approval-boundaries.compiled.json` is the generated JSON mirror of `rules/approval-boundaries.yaml` so the runtime gate works without PyYAML. Regenerate with `system/tools/approval_boundaries_audit.py --compile`; never edit by hand.
- `golden-questions.json` defines the known-answer questions behind the memory benchmark (see the `memory-benchmark` skill).
- `golden-question-runs.jsonl` is the append-only history of benchmark runs; the trend across runs is the proof that vault memory is compounding rather than rotting.
