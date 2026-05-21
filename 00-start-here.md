# Start Here

This is the low-token navigation entrypoint for a project built with Agentic Business OS.

## Load Order

1. Confirm `AGENTS.md` is loaded.
2. Use `domains/` to identify ownership when domains exist.
3. Load the matching skill under `.agents/skills/` when a workflow applies.
4. Read only the linked context, wiki, output, source, or project file needed for the task.
5. Put new generated artifacts with possible durable value in `inbox/`.

## First Setup

Use `.agents/skills/ops/project-onboarding/SKILL.md` to learn the project, run local bootstrap/checks, and create a review-first onboarding pack.

## Memory Spine

- `inbox/` - review queue
- `wiki/` - durable synthesis
- `outputs/` - final deliverables
- `sources/` - source cards and raw exports
- `dropped/` - rejected material
- `state/` - manifests and queues
