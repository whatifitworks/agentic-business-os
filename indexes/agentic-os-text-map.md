# Agentic OS Text Map

This is the text-first operating map for Agentic Business OS. Use it when a diagram is not enough, or when an agent needs to decide where to read from, where to write to, and how the system is meant to be used.

The repo root is the project vault and the agentic operating system.

## Mental Model

Agentic Business OS has six layers:

1. Bootstrap and navigation tell an agent how to start without loading the whole repo.
2. Domains define ownership, goals, active workflows, and routing.
3. Skills execute repeatable workflows.
4. The memory spine captures generated artifacts, promotes useful knowledge, and keeps the graph connected.
5. Automation runs schedules, hooks, adapters, and agents.
6. Verification checks structure, routing, graph health, hooks, and eval fixtures.

The core loop is:

```text
task request
  -> runtime loads AGENTS.md or CLAUDE.md
  -> read 00-start-here.md for project navigation
  -> identify domain
  -> load only the matching skill and linked context
  -> execute work
  -> place generated artifacts in the correct folder
  -> ingest durable knowledge through inbox/
  -> update indexes, decisions, state, or project files when needed
  -> run the relevant checks
```

## Text Tree

```text
agentic-business-os/
  AGENTS.md               shared operating contract
  CLAUDE.md               Claude Code bootstrap shim to AGENTS.md
  00-start-here.md        project navigation entrypoint after bootstrap
  README.md               human repo overview

  .agents/                agentic runtime definitions
    skills/               reusable workflow procedures, namespaced by domain
    agents/               role definitions and agent registry
    hooks/                lifecycle checks and hook contracts
    adapters/             Browser/Computer pseudo-MCP workflows and evidence contracts
    templates/            agent-facing templates
    schedules.yaml        scheduled workflow definitions
    recurring.yaml        recurring obligations surfaced by planning

  .codex/                 Codex project config
  .claude/                Claude Code config

  domains/                domain ownership cards
  context/                current operating truth
  rules/                  reusable policy and style rules
  references/             stable SOPs, examples, guidebooks
  decisions/              append-only meaningful decision log

  inbox/                  memory intake queue
  wiki/                   short durable synthesis promoted from inbox
  indexes/                graph spine and navigation maps
  outputs/                final human-facing deliverables
  sources/                raw external data, source cards, adapter evidence
  state/                  manifests, queues, rolling metrics, machine-readable history
  dropped/                material rejected with reasons

  projects/               active/background workstream folders
  archives/               inactive completed or parked work
  logs/                   runtime logs, scheduler traces, operational evidence
  scripts/                deterministic project-owned scripts
  system/                 audits, schemas, tests, health reports, context loader
  evals/                  test fixtures for routing, hooks, skills, memory behavior
  templates/              reusable content/document/envelope templates
  tmp/                    scratch only
```

## How To Use It

Start every task from the smallest useful context:

```text
AGENTS.md or CLAUDE.md, loaded by the runtime
  -> 00-start-here.md
  -> domains/<owner>.md
  -> .agents/skills/<namespace>/<skill>/SKILL.md, if a repeatable workflow applies
  -> only the linked context/wiki/project/source/output files needed for the task
```

If ownership is unclear, use:

```bash
python3 system/tools/context_loader.py load --domain <domain>
python3 system/tools/context_loader.py load --skill <skill>
```

Generated work should not be scattered into arbitrary folders. A task should update a source-of-truth file directly, produce a final output, or create an inbox item for ingest.

## Folder Roles

### Entrypoints

`00-start-here.md` is the first read. It points to the minimum context and the memory spine.

`AGENTS.md` is the operating contract. Keep it thin. It should define always-needed rules, not detailed procedures.

`README.md` is the human overview. It should stay short and point to indexes.

### Domains

`domains/` answers "who owns this work?" A domain file should define mission, goals, relevant skills, expected outputs, key sources, and active projects.

### Skills

`.agents/skills/` answers "how do we repeatedly do this workflow?" Skills should contain trigger conditions, workflow steps, required sources/tools, output locations, verification requirements, and failure handling.

### Hooks

`.agents/hooks/` and `system/tools/agentic_os_hooks.py` guard the operating system. Hooks should catch broken graph links, stale inbox work, missing manifests, adapter evidence gaps, schedule drift, source-of-truth corruption, likely secret leaks, and eligible inbox files that should be queued for memory ingest.

### Adapters

`.agents/adapters/` defines Browser/Computer workflows that behave like MCP alternatives when no API or MCP server exists. Adapter evidence belongs in `sources/adapters/`, usually with run records under `sources/adapters/runs/`.

### Memory Spine

`inbox/` is the staging area for memory ingest. `wiki/` is short durable synthesis. `outputs/` is for accepted human-facing deliverables. `sources/` is for provenance and raw evidence. `state/` is for machine-readable continuity. `dropped/` preserves rejected material with enough reason to avoid reprocessing.

### Verification

`system/tools/` contains deterministic checks. `evals/` contains fixtures. Run the smallest relevant check after changes, and run the full repo audit before publishing template changes.
