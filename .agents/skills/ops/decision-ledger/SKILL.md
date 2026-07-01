---
name: decision-ledger
description: "Record decisions, actions, and outcomes in the hash-chained ledger with evidence links, and answer \"why did we do X?\" from it. /decision-ledger"
argument-hint: "[record <what happened> | why <question> | verify]"
---

# Decision Ledger

## What this does

Keeps the tamper-evident history of what this business decided and did: `state/ledger.jsonl` (machine-readable, hash-chained, written via `system/tools/ledger.py`) plus the human-readable `decisions/log.md`. Six months from now, "why did we drop that supplier?" gets answered with the original reasoning and the evidence that was on the table — not a shrug.

Entry kinds: `decision` (a direction was chosen), `action` (something external was done), `outcome` (what resulted), `evidence` (a source that shaped a decision), `note`.

## Recording a decision

1. Get the decision, the reasoning, and the context in the owner's words. Ask only for what's missing.
2. Append one line to `decisions/log.md` in the established format:
   ```
   [YYYY-MM-DD] DECISION: <what was decided> | REASONING: <why> | CONTEXT: <what was true at the time>
   ```
   If `decisions/log.md` does not exist yet, create it with a `# Decision Log` heading, a one-line intro, then a `---` separator before the first entry (the index tool inserts itself after that separator).
3. Refresh the scannable index: `python3 system/tools/decisions_index.py --apply`
4. Chain it, linking every evidence file that shaped the call:
   ```bash
   python3 system/tools/ledger.py append --kind decision --actor human:owner \
     --summary "<what was decided>" --ref decisions/log.md --ref <evidence path> ...
   ```
   Evidence lives where it lives — `sources/`, `outputs/`, `wiki/` — the ledger just points at it.

## Recording actions and outcomes

- After an approved external action (a sent campaign, a published post, a changed record): `append --kind action` with refs to the artifact and, when relevant, the approval context. The approval gate already logs its own `boundary_evaluation` entries; this entry is the *what happened*, not the permission.
- When results land (metrics, replies, consequences): `append --kind outcome --ref <the action's entry id>` so the loop closes. Use `--data-json` for numbers worth keeping structured.

## Answering "why did we do X?"

1. `python3 system/tools/ledger.py query --contains "<topic>"` — find the decision/action/outcome trail.
2. Open the refs it points to (decision log line, evidence files) rather than reconstructing from memory.
3. `python3 system/tools/vault_search.py "<topic>"` for durable synthesis the trail may have missed.
4. Answer with the timeline: what was decided, on what evidence, what was done, what came of it. Quote the ledger ids so the owner can audit the claim.

## Verifying integrity

`python3 system/tools/ledger.py verify` — also part of repo-health local checks. A broken chain means a past entry was edited or deleted; report exactly which line and stop treating the ledger as authoritative until the owner resolves it (corrections are new entries referencing the corrected id, never edits).

## Rules

- Never edit or delete existing ledger lines or past `decisions/log.md` entries. Corrections are new entries that reference what they correct.
- Always write through `ledger.py append` — hand-written lines break the hash chain.
- One decision, one entry. Don't batch unrelated decisions into a single line.
- Record decisions when they are made, in the same session — a reconstructed ledger is a diary, not a record.
- Keep summaries plain and self-contained; the reader six months out has no session context.
