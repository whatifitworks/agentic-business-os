# Hooks

Lifecycle checks and capture points for Agentic Business OS.

Hooks should usually warn or queue work. Blocking is reserved for destructive actions, broken memory graph writes, or cases where proceeding would corrupt source-of-truth state.

## Hook Contracts

- Session end: write durable insight candidates to `inbox/`.
- Skill completion: require output path, status, and memory-candidate check.
- Wiki write: warn when a `wiki/` page is not indexed.
- Inbox health: warn on stale `inbox/` items.
- Inbox auto-ingest: queue eligible new `inbox/` files and optionally launch a one-item background memory ingest worker.
- Failure-to-inbox capture: redact repeatable tool, hook, adapter, or skill failures into `inbox/` candidates when they have durable learning value.
- Graph health: run `system/tools/memory_graph_audit.py`.
- Scheduler health: surface disabled, stale, or blocked scheduled workflows.
- Source hygiene: ensure dropped items and process-only outcomes have manifest records.
- Adapter evidence: verify Browser/Computer adapter runs produce evidence and source-card metadata.
- Prompt secret scan: warn before generated artifacts with likely secrets enter memory.
- Pre-compaction handoff: preserve working state in `inbox/` when a session risks context loss.
- Agent output contract: verify delegated agent handoffs include changed paths, evidence, blockers, and memory candidates.
- Work-session journal: record compact learning events for corrections, manual steps, blockers, and automation candidates.
- Ephemeral chat capture: save raw runtime chat payloads locally under `logs/raw-chats/`, extract compact learning events, and purge captures after seven days.

## Current Implementation

Hook definitions live in [registry.yaml](registry.yaml). Deterministic checks are implemented by [agentic_os_hooks.py](../../system/tools/agentic_os_hooks.py). Runtime editor/agent hook wiring can call that script by hook name; unsupported hooks should produce a visible warning rather than silently passing.

## Inbox Auto-Ingest

Preferred wiring for normal LLM-generated files is project-local after-response hooks:

- Codex: [../../.codex/config.toml](../../.codex/config.toml) has a `Stop` hook.
- Claude Code: [../../.claude/settings.json](../../.claude/settings.json) has a `Stop` hook.

Both scan `inbox/` and launch the one-item background worker only when an eligible pending item exists.
The Codex hook uses `--hook-json` because Codex `Stop` hooks require JSON on stdout.

## Runtime Activation

Committed config is not always enough to prove hooks are active in the user's runtime.

- Codex may require hooks to be enabled or approved in the app/runtime UI after onboarding.
- Claude Code reads `.claude/settings.json`, but users should verify hook execution in their installed version.
- The static hook check validates files and contracts; it cannot prove a specific runtime UI has enabled hooks.

Use [inbox_auto_ingest.py](../../system/tools/inbox_auto_ingest.py) directly for manual checks:

```bash
python3 system/tools/inbox_auto_ingest.py scan
python3 system/tools/inbox_auto_ingest.py launch --runner codex
python3 system/tools/inbox_auto_ingest.py launch --runner codex --hook-json
```

The trigger ignores only `inbox/README.md` and hidden control files. The launched worker must process exactly one item through the `memory-ingest` skill and update `state/memory-ingest-queue.json`.

## Failure Capture

Use [failure_capture.py](../../system/tools/failure_capture.py) when a repeatable failure should become memory input instead of staying in chat history:

```bash
python3 system/tools/failure_capture.py capture --case evals/failure-capture/cases.json
python3 system/tools/failure_capture.py capture --case evals/failure-capture/cases.json --write-inbox
```

The capture writes only a redacted candidate envelope. `memory-ingest` decides whether the result is process-only, a skill update, a hook update, a memory rule update, a project task, or dropped.

## Work Session Journal

Use [work_session_journal.py](../../system/tools/work_session_journal.py) when a session exposes a learning signal:

```bash
python3 system/tools/work_session_journal.py record \
  --event-type correction \
  --summary "Skill asked the wrong question" \
  --skill adapter-runner \
  --friction "Asked for inputs despite default_inputs"
```

The scheduled `learning-review` task scans these events and proposes improvements. It is suggest-only by default.

## Ephemeral Raw Chat Capture

Raw chat capture is allowed only as short-lived local telemetry. Captures are gitignored under `logs/raw-chats/`, parsed into compact learning events, and purged after seven days.

```bash
python3 system/tools/ephemeral_chat_capture.py capture --runtime codex --stdin-json --extract --purge
python3 system/tools/ephemeral_chat_capture.py extract --purge
python3 system/tools/ephemeral_chat_capture.py purge
```

Never route raw chat captures to `inbox/`, `wiki/`, `outputs/`, or git.

For files that appear while no LLM session is active, the optional macOS folder watcher can be installed with:

```bash
bash .agents/hooks/install-inbox-auto-ingest-launchd.sh
```

Uninstall it with:

```bash
bash .agents/hooks/install-inbox-auto-ingest-launchd.sh --uninstall
```
