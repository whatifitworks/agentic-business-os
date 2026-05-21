---
name: memory-ingest
description: Review Agentic Business OS memory inbox items, decide whether each item should be promoted, appended as evidence, preserved source-only, recorded process-only, dropped, or escalated, then keep the Obsidian memory graph indexed and concise.
---

# Memory Ingest

Use this skill when the project owner asks to process memory inbox items, ingest generated work, update the local knowledge wiki, or decide whether a source belongs in memory.

## Source Of Truth

- Memory vault root: repo root
- Inbox: `inbox/`
- Durable wiki: `wiki/`
- Indexes: `indexes/`
- Dropped inputs: `dropped/`
- Manifest: `state/ingest-manifest.json`

## Workflow

1. Read `00-start-here.md`, then `inbox/README.md` and `indexes/README.md`.
2. Inspect the inbox item just enough to classify it.
3. Search `wiki/` and `indexes/` before creating a page.
4. Pick exactly one outcome:
   - promote into a short durable wiki update
   - append concise evidence to an existing evidence/source page
   - create a source card only for unusually important or distinct sources
   - process-only when the artifact adds no synthesis and should be recorded in the manifest without retaining a second copy
   - drop when it is irrelevant, duplicated, or too low signal
   - ask the project owner when relevance is strategically ambiguous
5. Keep Markdown short. Link to sources instead of copying bulky material.
6. Add or refresh index links in the same pass as any wiki change.
7. Record processed or dropped outcomes in `state/ingest-manifest.json` or a clear drop note.
8. Run `python3 system/tools/memory_graph_audit.py` before finishing.

## One Item Worker Mode

Use this mode when triggered by `system/tools/inbox_auto_ingest.py` or a background `memory-inbox-processor` agent.

1. Process exactly one inbox path named by the trigger. Do not opportunistically process neighboring files.
2. Process only the inbox path named by the trigger. The v2 inbox should not contain compatibility shelves.
3. If the item is an envelope, follow its `artifact_paths` to the full artifact before deciding.
4. Prefer linking and concise synthesis over copying content into `wiki/`.
5. After the outcome, update:
   - `state/ingest-manifest.json`
   - `state/memory-ingest-queue.json` when this run came from the auto-ingest trigger
   - any touched `indexes/`, `sources/`, `outputs/`, `dropped/`, or `wiki/` files
6. Run:

   ```bash
   python3 system/tools/memory_graph_audit.py --scope root
   python3 system/tools/ops_v2_hooks.py --hook all
   ```

7. If the classification is ambiguous, mark the queue item `blocked` or `needs-daniels` instead of guessing.

## Promotion Rule

Promote only knowledge that helps future decisions about retention, conversion, onboarding, churn, the flagship feature, paywall, acquisition, support quality, analytics confidence, or operational reliability.

Do not promote routine task chatter, raw dashboards, temporary status updates, or long reports that should stay as linked artifacts.

## Retention Rule

Do not create a root `processed/` shelf. It is retired.

For process-only items:

- record the decision in `state/ingest-manifest.json`
- remove the inbox copy when it has no independent retention value
- route retained evidence to `sources/`, final deliverables to `outputs/`, rejected material to `dropped/`, and historical material to `archives/` only when there is a clear traceability reason

## Graph Rule

No durable wiki page may be orphaned. Every new `wiki/` page must be reachable from `00-start-here.md`, `indexes/`, `domains/`, or another wiki page.
