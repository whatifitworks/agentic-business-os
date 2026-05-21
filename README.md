# Agentic Business OS

Agentic Business OS is a local-first template for running one business or serious project with Codex, Claude Code, and review-first automation.

It gives an agent a stable operating structure: where to read context, where to write outputs, how to preserve durable memory, how to run recurring workflows, how to capture UI-only evidence, and how to keep the system auditable as it learns the business.

## What You Get

- A thin agent bootstrap contract: `AGENTS.md`, `CLAUDE.md`, and `00-start-here.md`
- A memory spine: `inbox/`, `wiki/`, `sources/`, `outputs/`, `state/`, and `dropped/`
- Starter context files in `context/` that onboarding can replace
- Core skills for onboarding, memory ingest, repo health, recurring review, learning review, adapters, and design work
- Claude and Codex runtime hook templates
- Scheduler scaffolding and macOS launchd installers
- SQLite runtime state through `system/state/ops.db`
- Browser/Computer adapter contracts for UI workflows that lack APIs
- A `get-help` skill for troubleshooting and contacting the maintainers
- Local audits and eval fixtures
- Privacy guardrails for downstream private projects

## Who This Is For

Use this when you want an AI assistant to learn a business or project over time without turning the repository into a pile of chat logs.

The template works best when the owner wants:

- a persistent local knowledge base
- repeatable operating routines
- review gates before external actions
- auditable reports and decisions
- optional automation after boundaries are clear

## Quick Start

1. Create a new repo from this template.
2. Open it in Codex or Claude Code.
3. Ask the agent to run the `project-onboarding` skill.
4. Answer the onboarding questions. The agent should run local bootstrap and checks itself.
5. Review the onboarding pack under `inbox/project-onboarding/...`.
6. Promote approved proposed files into live `context/`, `domains/`, `wiki/`, `.agents/`, `rules/`, or `state/` paths.
7. Only then connect tools, enable schedules, or install background jobs.

Full setup guide: [docs/setup.md](docs/setup.md)

## First Run With An Agent

Tell the agent:

```text
Run project-onboarding for this project. Learn the business, tools, routines, approval boundaries, and first useful automation candidates. Create a review pack before changing live files.
```

The onboarding skill runs the local bootstrap/check scripts, asks the setup questions, and creates reviewable starter files first. It does not ask for credentials or connect external tools.

## Runtime Support

Codex:

- Project config: `.codex/config.toml`
- Stop hooks: ephemeral learning capture and inbox auto-ingest check
- Post-onboarding action: Codex may require hooks to be enabled or approved in the app/runtime UI
- Add project-specific MCP servers only after onboarding

Claude Code:

- Project config: `.claude/settings.json`
- Skill symlink: `.claude/skills -> ../.agents/skills`
- Commands: `.claude/commands/`
- Local secret example: `.claude/settings.local.example.json`
- Post-onboarding action: verify hook execution in the installed Claude Code runtime

Secrets belong in gitignored local files, not in committed configs or chat.

## Core Concepts

`context/` holds current operating truth, such as mission, goals, tools, and priorities.

`inbox/` is the intake queue for generated artifacts, source drops, and memory candidates.

`wiki/` is concise durable synthesis after review or ingest.

`sources/` preserves evidence: source cards, raw exports, adapter run records, and provenance.

`outputs/` holds final human-facing reports, briefs, dashboards, and deliverables.

`state/` holds manifests, queues, and machine-readable histories.

`system/state/ops.db` is generated runtime state. It is initialized during onboarding by `bootstrap_project.py` and ignored by git.

## Skills

Public core skills are intentionally generic:

- `project-onboarding`
- `get-help`
- `daily-planning`
- `weekly-review`
- `memory-ingest`
- `memory-graph-health`
- `repo-health`
- `recurring-review`
- `run-scheduled`
- `learning-review`
- `skill-improvement-loop`
- `adapter-builder`
- `adapter-runner`
- `adapter-recording-review`
- `design-studio`

Domain-specific skills, such as support desks, analytics providers, app-store review workflows, accounting, or email platforms, should be added later as project-local skills or optional plugins.

## Background Jobs

Optional macOS scheduler:

```bash
bash .agents/install-launchd.sh
```

Optional macOS inbox watcher:

```bash
bash .agents/hooks/install-inbox-auto-ingest-launchd.sh
```

Review `.agents/schedules.yaml`, `.agents/recurring.yaml`, and the memory workflow before installing background jobs. Onboarding may prepare these commands, but should ask before running them.

## Checks

Run the full local check suite:

```bash
python3 system/tests/agentic_os_local_checks.py
```

Run a lighter repo audit:

```bash
python3 system/tools/repo_audit.py --exit-zero
```

## Updating From Upstream

This repository is designed to be the public upstream template. Real businesses will usually keep private overlays for context, tools, schedules, and domain skills.

Recommended downstream flow:

1. Pull upstream template changes into the private project.
2. Keep private context and provider-specific skills local.
3. Extract only generic improvements back to this repo through normal branches and pull requests.
4. Run privacy scans and local checks before publishing.

More detail: [docs/sync.md](docs/sync.md)

## Maintainer And Help

Agentic Business OS is maintained by [What If It Works](https://whatifitworks.co).

For setup, onboarding, hooks, sync, publishing, or customization help, ask the agent to run `get-help`. It will prepare a redacted support note and point you to the official contact path.

## Privacy Model

The template should never require public business data, customer content, credentials, revenue numbers, or raw transcripts.

Use `docs/privacy.md` before adding integrations, source exports, or public examples.
