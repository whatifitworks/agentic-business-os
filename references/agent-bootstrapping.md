# Agent Bootstrapping Reference

Use this reference when changing agent behavior, adding a new source-of-truth area, debugging context drift, or deciding where a new instruction belongs.

Root instructions should be routers. Detailed procedures belong in skills, rules, context files, manifests, references, or docs.

## Bootstrap Policy

- Keep `AGENTS.md` as the canonical thin router for shared instructions.
- Keep `CLAUDE.md` as a short Claude-specific wrapper that imports `AGENTS.md`.
- Put a rule in a root file only when the agent needs it before choosing which files to read.
- Put procedures in skills, not root instructions.
- Put human business context in `context/`, not root instructions.
- Put reusable behavioral rules in `rules/`, not duplicated across skills.
- Put machine-readable startup metadata in skill `manifest.yaml` files when workflows need explicit contracts.
- Keep context narrow. If a task needs a broad audit, say that explicitly and summarize findings instead of keeping every file in active context.

## Context Loading Pattern

The default task bootstrap is:

1. Read `00-start-here.md`.
2. Use `domains/`, `indexes/`, and `wiki/start-here.md` if present to narrow the source of truth.
3. If a skill applies, read its canonical namespaced `SKILL.md` and only the sidecars needed for that run.
4. Load the narrowest source-of-truth file from the project map.
5. Consult the local wiki only when the task crosses the durable knowledge boundary.

## Source-Of-Truth Map

| Area | Source of truth | Use for |
| --- | --- | --- |
| Daily plan | `context/today.md` when used | Current task queue and same-day notes |
| Priorities | `context/current-priorities.md` when used | Active priority order |
| Goals | `context/goals.md` when used | Commitments and milestones |
| Durable learnings | `context/key-learnings.md` or `wiki/` | Lessons that should shape future decisions |
| Business context | `context/work.md` when used | Product, business model, scale, tools |
| Tech and tooling | `context/tech-stack.md` when used | Product, infra, and ops tooling context |
| Memory boundary | `00-start-here.md` | Root-vault entrypoint and memory spine router |
| Communication | `rules/communication-style.md` | Tone, formatting, and drafting style |
| Data analysis | `rules/data-analysis.md` | How to present numbers and uncertainty |
| Project conventions | `rules/project-conventions.md` | Tool and workflow quirks |
| Memory workflow | `rules/memory-workflow.md` | How and when to read/write memory |
| Workflows | `.agents/skills/` | Repeatable procedures |
| Schedule table | `.agents/schedules.yaml` | Headless scheduled task definitions |
| Recurring obligations | `.agents/recurring.yaml` | Human reminders and periodic work |
| Active workstreams | `projects/` | Working artifacts for active priority and operational workstreams |
| Decisions | `decisions/log.md` | Append-only decision log |
| Outputs | `outputs/` | Final reports, dashboards, briefs, drafts, and shareable deliverables |
| Sources | `sources/` | Source cards, source contracts, raw exports, and adapter evidence |
| Runtime state | `system/state/` | Generated local state for scheduler runs, health, and queues |

## Memory Boundary

The repo root owns the local durable knowledge layer.

- `inbox/` is the default landing zone for generated artifacts, source material, and candidate insights before ingest.
- `wiki/` is the canonical place for short durable synthesis after ingest.
- `indexes/` keeps the graph navigable.
- `outputs/` holds final human-facing deliverables after ingest or explicit approval.
- `sources/` holds raw external exports, source cards, and adapter evidence.
- `state/` holds manifests, queues, rolling JSON histories, and append-only machine-readable logs.
- `context/`, `projects/`, `decisions/`, `scripts/`, and `system/` remain canonical for their own operational roles.

Use `00-start-here.md` before broad memory discovery. Do not put raw transcripts, long command output, secrets, or private customer content into durable memory.

## Skills

Skills are the procedure layer. Each skill lives under `.agents/skills/<namespace>/<skill>/SKILL.md` with YAML frontmatter and optional sidecars in the same folder.

Use skills when:

- The owner names a workflow or slash command.
- The task clearly matches an existing skill description.
- A scheduled task references the skill.

When adding skills:

- Use the smallest procedure that makes the workflow repeatable.
- Put heavy templates, examples, lookup tables, and quirks in sidecars.
- Keep descriptions specific enough for automatic selection.
- Add a `manifest.yaml` when the workflow needs explicit tool, context, output, or approval contracts.

## Scheduler And Recurring Work

The scheduler spine lives in:

- `.agents/scheduler.sh`
- `.agents/scheduler_helper.py`
- `.agents/schedules.yaml`
- `.agents/recurring.yaml`
- `system/tools/ops_state.py`
- `system/state/`

`schedules.yaml` owns scheduled task definitions. `recurring.yaml` owns obligations the owner should not have to remember manually. Planning should surface due or overdue recurring work.

When scheduler semantics change, keep statuses explicit: `pending`, `informational`, `blocked`, `failed`, and `reviewed`.

## Agent Docs Maintenance

When adding a new instruction, choose the narrowest durable home:

- Every task needs it before file selection: root file.
- One workflow needs it: skill or skill sidecar.
- One business area needs it: context or project file.
- It is durable knowledge: `inbox/` first, then a focused wiki page after ingest.
- It is a repeatable style or analysis rule: `rules/`.
- It is a one-time investigation: `inbox/` first, then `outputs/` after ingest or explicit approval.
- It is a strategic decision: `decisions/log.md`.

Do not duplicate the same instruction in root docs, skills, and context files. Prefer one canonical home and link to it.
