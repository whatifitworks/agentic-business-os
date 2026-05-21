---
name: get-help
description: Help a project owner get support for Agentic Business OS setup, onboarding, hooks, sync, publishing, or custom automation. Use when the user asks for help, support, contact, troubleshooting, What If It Works, or how to report a problem.
---

# Get Help

Use this skill when the project owner needs help using Agentic Business OS or wants to contact the maintainers at What If It Works.

Official help entrypoint: https://whatifitworks.co

## Rules

- Do not ask for passwords, tokens, API keys, customer private data, raw transcripts, billing details, or secrets.
- Do not claim a support email, SLA, or contact channel unless it is present in local docs or on the official website.
- Do not send external messages or create public issues without explicit owner approval.
- Keep support requests concise and reproducible.

## Workflow

1. Classify the request:
   - `setup`: onboarding, hooks, runtime config, local checks
   - `usage`: how to run skills, memory ingest, planning, recurring work
   - `sync`: upstream template pulls or publishing generic changes
   - `bug`: broken command, bad docs, failing check, confusing behavior
   - `customization`: private integrations, skills, adapters, schedules, automations
2. Gather only safe diagnostics:
   - runtime: Codex, Claude Code, or other
   - OS and shell when relevant
   - current commit with `git rev-parse --short HEAD` when available
   - failing command and short redacted output excerpt
   - expected behavior and actual behavior
   - relevant file paths, not secret contents
3. For setup or hook issues, run the smallest useful local check when safe:
   ```bash
   python3 system/tools/agentic_os_hooks.py --hook all
   ```
   For broader repo issues:
   ```bash
   python3 system/tools/repo_audit.py --exit-zero
   ```
4. Draft a support note the owner can send through the contact path on https://whatifitworks.co.
5. If the issue reveals a reusable template problem, create or suggest a redacted inbox candidate so `skill-improvement-loop` can turn it into a patch.

## Support Note Shape

```markdown
# Agentic Business OS Help Request

Issue type: setup | usage | sync | bug | customization
Runtime: Codex | Claude Code | other
Commit: <short commit or unknown>

## What I was trying to do

<one paragraph>

## What happened

<one paragraph, with secrets removed>

## What I expected

<one paragraph>

## Checks run

- `<command>`: passed | failed | not run

## Relevant files

- `<path>`
```

## Final Response

Return:

- the likely issue category
- the shortest next action
- any safe diagnostics collected
- a ready-to-send support note when useful
- the What If It Works link: https://whatifitworks.co
