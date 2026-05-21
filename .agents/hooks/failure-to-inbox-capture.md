# Failure To Inbox Capture

Capture repeatable tool, hook, adapter, or skill failures as redacted `inbox/` candidates when the failure contains durable learning.

## Trigger

- A skill asks the wrong question, guesses, or violates a documented contract.
- A tool command fails in a repeatable way and the expected behavior is known.
- A hook emits a false positive or misses a real problem.
- An adapter fails because UI assumptions, defaults, schema, or evidence rules were wrong.

Do not capture one-off harmless failures or transient network/system issues unless they repeat or the project owner gives a correction that should change a skill, hook, adapter, or tool.

## Input Contract

Use a small JSON case with the minimum reproducible context:

- `id`
- `workflow` or `skill`
- `command` or `tool`
- `cwd`
- `exit_code`
- `expected_behavior`
- `actual_behavior`
- `user_correction`
- `stdout_excerpt` or `stderr_excerpt`
- `deterministic`
- `repeated`
- `owner_hint`

## Action

Run:

```bash
python3 system/tools/failure_capture.py capture --case <case.json>
```

When the analysis says `should_capture: true` and the item has durable value, write the candidate:

```bash
python3 system/tools/failure_capture.py capture --case <case.json> --write-inbox
```

The output goes to `inbox/<timestamp>-<case>-failure-candidate.md` and then the normal `memory-ingest` skill decides whether it becomes process-only, a skill update, a hook update, a memory rule update, a project task, or dropped.

## Redaction Rules

- Redact tokens, passwords, API keys, bearer headers, Slack tokens, OpenAI-like keys, and credential-bearing URLs before writing.
- Keep only short stdout/stderr excerpts.
- Never capture private customer data, raw Computer Use screen state, screenshots, or complete logs by default.
- Prefer a source path reference when a full artifact already exists under `sources/` or `logs/`.

## Failure Behavior

- If owner is unclear, write `needs-owner-triage`.
- If the failure is deterministic, add or update an eval after the owner file is changed.
- If redaction is uncertain, do not write to `inbox/`; report the blocker.
