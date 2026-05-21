# Work Session Journal

Capture structured learning events from meaningful Agentic Business OS work.

This is not a raw transcript logger. It records compact, redacted events that can later be reviewed by `learning-review`.

## Trigger

- the project owner corrects the assistant or a skill.
- A task requires repeated manual steps.
- A skill is confusing, verbose, inefficient, or too brittle.
- A tool, MCP server, adapter, scheduler, or hook blocks work.
- A successful workflow should become reusable.
- A new automation, adapter, skill, recurring task, or memory rule becomes obvious.

## Action

Run:

```bash
python3 system/tools/work_session_journal.py record \
  --event-type correction \
  --summary "<short summary>" \
  --skill "<skill-name>" \
  --friction "<what was inefficient/confusing>" \
  --automation-candidate "<optional idea>"
```

The tool writes:

- `state/learning-events.jsonl`

## Rules

- Do not read or mine Codex/Claude raw chat stores for this loop.
- Do not log secrets, private customer content, raw screenshots, raw Computer Use state, full transcripts, or long command output.
- Prefer compact summaries that explain the learning signal.
- If a learning event has durable strategic value, route a concise candidate through `inbox/` and `memory-ingest`.
- Scheduled `learning-review` consumes these events and proposes improvements; it does not auto-patch.
