---
name: learning-review
description: Review learning events, raw-chat signals, and failures; propose agentic-OS improvements without auto-patching. Use for the learning loop.
---

# Learning Review

Use this skill to turn recent interaction and workflow evidence into explicit Agentic Business OS self-improvement suggestions. It is the project-local "dreaming" loop, but it stays operational: it reads compact learning events, identifies concrete system/workflow candidates, and asks the project owner before any patch.

This skill is about improving the agentic OS itself, not remembering or acting on the project business topics. Product, analytics, support, accounting, growth, or strategy learnings belong in their domain skills and memory-ingest flow.

## Sources

- `state/learning-events.jsonl` - compact structured events recorded by `work_session_journal.py` or extracted from ephemeral raw chat captures
- `logs/raw-chats/` - gitignored raw chat captures retained for seven days only; captures use one file per runtime thread/session and store parsed visible user and assistant messages, not internal tool records
- `state/learning-raw-chat-manifest.json` - processed raw-chat capture manifest
- `logs/*/*-brief.md` - scheduled and workflow briefs when they show tool, schedule, or workflow failure
- `system/tools/learning_review.py` - deterministic review helper

## Workflow

1. Generate a review:

   ```bash
   python3 system/tools/learning_review.py review --days 7
   ```

   The review command first extracts learning events from gitignored `logs/raw-chats/` and purges expired raw captures.

2. For scheduled/headless mode, write the brief to the provided path:

   ```bash
   python3 system/tools/learning_review.py review --days 7 --brief-output <LOG_FILE>
   ```

3. Review candidates with the project owner. For each candidate choose one:
   - `accept-patch`: run `skill-improvement-loop` or make a focused patch with validation.
   - `accept-inbox`: write a concise memory candidate to `inbox/`.
   - `project-task`: create or update an agentic-OS/project-system workstream artifact.
   - `dismiss`: mark as not useful with a short reason.
   - `defer`: keep pending and name when to revisit.

4. Do not auto-patch unless the project owner explicitly asks. Scheduled learning review is suggest-only.

## Recording New Events

When a useful learning event happens during a session, record it:

```bash
python3 system/tools/work_session_journal.py record \
  --event-type correction \
  --summary "<what happened>" \
  --skill "<skill-name>" \
  --friction "<what was confusing or inefficient>" \
  --automation-candidate "<optional automation idea>"
```

Use this for:

- the project owner correcting how a skill should behave
- repeated manual steps
- confusing answers or unclear prompts
- blocked tools or missing automation
- successful workflows that should become reusable skills
- the project owner expressing satisfaction, frustration, distrust, confusion, or changed expectations about the system
- the project owner using a skill, hook, adapter, schedule, or memory workflow differently than intended

## Rules

- Read only project-local ephemeral captures under `logs/raw-chats/`; do not mine global Codex/Claude history stores.
- Raw captures must be purged after seven days and must never enter `inbox/`, `wiki/`, `outputs/`, or git.
- Do not store secrets, private customer content, raw Computer Use screen state, full transcripts, or long command output outside the gitignored ephemeral raw-chat capture path.
- Do not produce candidates for ordinary the project business topics, overdue obligations, product facts, analytics findings, or strategy decisions. Those belong to domain skills, `recurring-review`, daily planning, and memory-ingest.
- Learning-review candidates must improve the OS: skills, hooks, agents, adapters, prompts, schedules, evals, docs, context loading, or user workflow ergonomics.
- Fixed/resolved implementation issues should remain historical events, not active candidates.
- Prefer concise summaries over raw dumps.
- Learning review suggestions must name an owner, a reason, and a proposed action.
- Nothing from a scheduled learning review is applied automatically.

## Output

Return:

- review period
- candidate count
- top candidates grouped by type
- recommended next action for each candidate
- whether the candidate should become a patch, eval, skill/hook/adapter update, project-system task, or dismissal
