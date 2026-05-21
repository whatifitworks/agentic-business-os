# Onboarding

`project-onboarding` is the first real workflow for a new Agentic Business OS project.

It should learn enough about the business, tools, routines, goals, and approval boundaries to make the project useful without connecting tools or writing live operating files prematurely.

The normal UX is agent-operated: the owner asks for onboarding, answers questions, and reviews the pack. The onboarding agent runs local bootstrap and verification scripts itself.

## What Onboarding Produces

The skill creates a review pack under:

```text
inbox/project-onboarding/<date>-<project-name>/
```

The pack includes:

- business/project summary
- tool map
- approval boundaries
- automation candidates
- starter file plan
- proposed starter files
- project-specific `proposed/AGENTS.md`
- machine-readable setup suggestions
- post-onboarding hook activation and help guidance

## What Onboarding Does Automatically

Onboarding should:

- initialize local runtime state with `system/tools/bootstrap_project.py`
- run deterministic local checks after pack creation
- interview the owner about the business, tools, routines, goals, and approval boundaries
- create review-only proposed files before changing live operating context
- create a project-specific `proposed/AGENTS.md` with the learned mission, direct source-map references, known tools, known routines, and approval boundaries

## What Onboarding Does Not Do Automatically

Onboarding does not:

- ask for credentials
- connect external tools
- enable schedules
- install launchd jobs
- write to customer, billing, publishing, or production systems
- overwrite live project files without review

## Post-Onboarding Handoff

After the review pack is created, onboarding should tell the owner:

- local bootstrap and checks passed, or which blocker remains
- where the review pack is
- which files are recommended for promotion first; normally `proposed/AGENTS.md`, then `proposed/context/work.md` and `proposed/context/current-priorities.md`
- Codex may require hooks to be enabled or approved in the app/runtime UI
- Claude Code hook activation should be verified in the installed runtime
- `get-help` can prepare a safe support note for What If It Works: https://whatifitworks.co

## Promotion

After review, promote approved files into:

- `AGENTS.md` for the project-specific agent contract and exact source map
- `context/` for current operating truth
- `domains/` for ownership boundaries
- `wiki/` for concise durable synthesis
- `sources/` for source contracts
- `.agents/skills/` for repeated procedures
- `.agents/recurring.yaml` for real recurring obligations
- `.agents/schedules.yaml` for approved scheduled workflows
- `rules/` for project-specific operating rules

Do not promote everything blindly. The review pack is a proposal.

## Starter Context

The template ships starter placeholders in `context/` and a generic bootstrap `AGENTS.md`. Onboarding can propose replacements for those files, but the project is still navigable before onboarding runs.

After onboarding, `AGENTS.md` should usually stop being generic. Promote the reviewed `proposed/AGENTS.md` so future agent turns start with the real project mission, source map, tools, routines, and approval boundaries.
