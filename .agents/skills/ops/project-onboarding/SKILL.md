---
name: project-onboarding
description: Prepare a new or empty single-project agentic operations vault from business context, tools, routines, goals, and constraints. Use when the user asks to onboard a business, initialize or prepare an empty project, learn what a project should know, map tools/connectors, propose starter automations, create first context/wiki/domain files, initialize local state/checks, or turn setup answers into review-only skills, schedules, recurring work, and automation candidates.
---

# Project Onboarding

Use this skill to prepare one project. Do not introduce a separate workspace concept. In this skill, "project" means the current repo or vault the assistant will operate from.

## Core Rule

The owner should only need to ask for onboarding. The agent runs the local bootstrap/check scripts, interviews the owner, and creates the review pack. Do not tell the owner to run setup scripts as the primary path.

Create a review pack before promoting project-specific files unless the owner explicitly asks to write final project files directly. Onboarding output usually starts under `inbox/project-onboarding/<date>-<slug>/`; after review, promote approved pieces into `AGENTS.md`, `context/`, `wiki/`, `domains/`, `.agents/`, `projects/`, `rules/`, or `state/`.

The template `AGENTS.md` is only a pre-onboarding bootstrap. The onboarding pack must include `proposed/AGENTS.md` with the learned project mission, direct file references, known tools, known routines, and approval boundaries. Recommend promoting that file first after review so future agent turns load the project-specific contract.

Never ask for passwords, API keys, tokens, bank details, tax IDs, private keys, or account credentials during onboarding. Tool setup should be recorded as review-only until the owner explicitly approves a connection path.

Background jobs are approval-gated. You may prepare scheduler and inbox-auto-ingest install instructions, but do not install launchd jobs or enable external schedules without explicit approval.

## Workflow

1. Read `00-start-here.md` if it exists. If the project is not empty, inspect the relevant existing `context/`, `domains/`, `.agents/skills/`, `.agents/schedules.yaml`, `.agents/recurring.yaml`, and `wiki/` indexes before proposing changes.
2. Run local bootstrap and baseline checks yourself:
   ```bash
   python3 system/tools/bootstrap_project.py
   ```
   If this fails, fix obvious local template issues when safe, or report the blocker. Continue the interview only if the failure does not make the project unsafe to initialize.
3. Identify the onboarding mode:
   - `new-project`: little or no project context exists.
   - `refresh-project`: project exists, but business/tool context needs improvement.
   - `template-dry-run`: prepare generic starter output for a reusable template.
4. Gather baseline answers:
   - project/business name
   - country or operating region
   - business type and product/service
   - customer/user groups
   - primary objective the assistant should protect
   - current operating routines
   - tools already used
   - approval boundaries and risky actions
   - first useful outcome expected from the assistant
5. Ask adaptive follow-up questions one at a time when needed. Prefer choices or short prompts. Stop once you have enough information to create starter context, priorities, tool review tasks, automation candidates, and open questions.
6. Build a tool map. For each tool, capture category, purpose, owner, source access path, likely connector/API/export/manual path, setup risk, and the first useful workflow.
7. Propose automations as review-only candidates. Rank by business impact, frequency, setup difficulty, and risk. Classify each as `safe-local`, `review-only`, `needs-permission`, or `needs-credentials`.
8. Generate the onboarding pack with `scripts/create_onboarding_pack.py` when baseline answers are available. Add any richer interview synthesis by editing the generated markdown files.
9. Run verification after pack creation:
   ```bash
   python3 system/tests/agentic_os_local_checks.py
   ```
10. Prepare the post-onboarding handoff:
   - review pack path
   - bootstrap/check status
   - highest-value files to promote first, usually `proposed/AGENTS.md` plus `proposed/context/work.md` and `proposed/context/current-priorities.md`
   - hook activation reminder: Codex may require hooks to be enabled or approved in the app/runtime UI; Claude Code hook execution should be verified in the installed runtime
   - help path: run `get-help` or visit https://whatifitworks.co
11. Present the review pack summary, verification result, hook reminder, help path, and recommended promotions. Ask before promoting anything into live project files.

## Interview Guidance

Use [references/interview-guide.md](references/interview-guide.md) for question banks and business-type prompts. Use [references/setup-suggestion-rubric.md](references/setup-suggestion-rubric.md) to classify tools, skills, routines, scripts, templates, memory work, and recurring jobs.

Keep the first interview practical. The goal is not to fully model the business; it is to create enough reliable context for useful first routines and safe future learning.

## Review Pack

When enough baseline context is known, the agent runs:

```bash
python3 .agents/skills/ops/project-onboarding/scripts/create_onboarding_pack.py \
  --project-name "<name>" \
  --business-type "<business type>" \
  --country "<country or region>" \
  --product "<product or service>" \
  --customer "<main customer/user group>" \
  --primary-goal "<primary objective>" \
  --tool "<tool name>:<category>:<access path>:<purpose>:<owner>:<first workflow>:<risk>" \
  --routine "<routine title>:<cadence>:<short summary>"
```

The script writes:

- `README.md` - operator summary
- `onboarding-summary.md` - business and project context
- `tool-map.md` - tool/source review table
- `automation-candidates.md` - starter automation ideas
- `starter-file-plan.md` - proposed file placements
- `setup-suggestions.json` - machine-readable suggestions
- `proposed/` - draft starter files to review before promotion
- `proposed/AGENTS.md` - project-specific agent contract with direct file references

## Promotion Rules

After the owner approves the review pack:

- Promote `proposed/AGENTS.md` first so the next agent turn starts from the project-specific mission, source map, tools, routines, and approval rules.
- Promote business operating truth into `context/`.
- Promote durable synthesis into `wiki/`.
- Promote source/tool contracts into `sources/` or `domains/`.
- Promote repeated procedures into `.agents/skills/<namespace>/<skill>/`.
- Promote schedules into `.agents/schedules.yaml` only when the cadence and tool access are clear.
- Promote recurring obligations into `.agents/recurring.yaml` only when they represent real work, not setup guesses.
- Log meaningful policy or direction changes in `decisions/log.md`.

Do not overwrite existing project files without showing the proposed diff or a clear file-by-file summary.

## Optional Background Jobs

After the review pack is approved, ask explicitly before installing any background jobs.

- Scheduler: `bash .agents/install-launchd.sh`
- Inbox auto-ingest watcher: `bash .agents/hooks/install-inbox-auto-ingest-launchd.sh`

Only install these when the owner approves and the relevant config has been reviewed.

## Done Criteria

- The project has a reviewable onboarding pack.
- Local runtime state has been initialized or the blocker is clearly reported.
- Baseline checks have run or their blocker is clearly reported.
- Hook activation guidance has been shown to the owner.
- A project-specific `proposed/AGENTS.md` exists, or the blocker is clearly reported.
- Tool setup items are review-only and do not contain secrets.
- Starter context, wiki, routines, and automations are separated from live files until approved.
- Open questions are explicit.
- The final response names the pack path, the highest-value next promotion step, the hook activation reminder, and the `get-help` path.
