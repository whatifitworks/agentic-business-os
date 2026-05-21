# Agentic Business OS

A local-first template for building an agentic operating system around one business or project.

The template provides a review-first memory spine, reusable Codex/Claude skills, adapter contracts for UI-only workflows, hooks, scheduler scaffolding, health checks, and eval fixtures. A new project should first learn the business, tools, routines, and approval boundaries before enabling automations.

## First Run

1. Read `AGENTS.md`.
2. Read `00-start-here.md`.
3. Run the `project-onboarding` skill to create a review pack.
4. Promote approved files into `context/`, `domains/`, `.agents/`, `state/`, and `wiki/`.
5. Enable hooks, schedules, and external tools only after reviewing approval boundaries.

## Included Core

- onboarding and starter-file generation
- memory ingest and memory graph health
- repo health, recurring review, learning review, and skill improvement loop
- Browser/Computer adapter contracts and evidence capture
- scheduler helper, hook docs, state schemas, and eval scaffolding
- design-studio workspace pattern for AI-assisted design projects

## Sync And Publishing

This public template does not ship the private project bridge used by any one downstream business. Downstream projects should keep their own sync/export bridge locally, then send generic improvements back here through ordinary Git branches and pull requests.
