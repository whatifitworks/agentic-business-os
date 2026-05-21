# Inbox Auto-Ingest Trigger

Purpose: when a new eligible file appears under `inbox/`, queue it for memory ingest and optionally launch a background worker that processes exactly one item.

## Eligibility

Queue files under `inbox/` except:

- `inbox/README.md`
- `.gitkeep`, `.DS_Store`, and other hidden control files

## Commands

```bash
python3 system/tools/inbox_auto_ingest.py scan
python3 system/tools/inbox_auto_ingest.py launch --runner codex
python3 system/tools/inbox_auto_ingest.py launch --runner codex --hook-json
```

Use `scan` for deterministic detection only. Use `launch` from a real runtime hook, file watcher, scheduler, or manual command when background ingest is desired.
Use `--hook-json` for Codex `Stop` hooks because that event requires JSON on stdout.

Preferred runtime wiring is project-local after-response hooks:

- Codex `Stop` hook in `../../.codex/config.toml`
- Claude Code `Stop` hook in `../../.claude/settings.json`

They run only when the corresponding runtime reaches the end of a response.

On macOS, [install-inbox-auto-ingest-launchd.sh](install-inbox-auto-ingest-launchd.sh) installs an optional `WatchPaths` trigger for `inbox/` when files may arrive outside any active LLM session.

## Worker Contract

The background worker must:

1. Load `.agents/skills/knowledge/memory-ingest/SKILL.md`.
2. Process exactly one queued inbox path.
3. Preserve full source artifacts.
4. Promote only concise, linked synthesis into `wiki/`.
5. Update `state/ingest-manifest.json`.
6. Update `state/memory-ingest-queue.json`.
7. Run graph and hook checks before finishing.

If the item is ambiguous, the worker must mark it `blocked` or `needs-daniels` rather than guessing.
