---
name: repo-health
description: "Run the deterministic repo hygiene audit: navigation, stale briefs, scheduler drift, MCP config drift, manifest coverage. Use for repo health checks."
---

# Repo Health

Use this skill to audit `agentic-business-os` itself. The source of truth for checks is [repo_audit.py](../../../../system/tools/repo_audit.py); do not reimplement the audit manually in chat. The audit also validates the context ownership index used by [context_loader.py](../../../../system/tools/context_loader.py).

## Procedure

1. Run the audit and refresh the human-readable health artifact:
   ```bash
   python3 system/tools/repo_audit.py --output system/health/repo-audit.md
   ```

2. Read the summary in [repo-audit.md](../../../../system/health/repo-audit.md) and separate:
   - `error` items: fix before continuing system work when they affect active docs, scheduler behavior, MCP config, or skill contracts.
   - actionable `warn` items: stale `pending`, `blocked`, or `failed` briefs that need review or an explicit decision.
   - historical warnings: append-only decision-log links or archived references that are useful to know but usually should not be rewritten.

3. For scheduled runs, the scheduler uses the command runner from [.agents/schedules.yaml](../../../../.agents/schedules.yaml):
   ```bash
   python3 system/tools/repo_audit.py \
     --output system/health/repo-audit.md \
     --brief-output {{LOG_FILE}} \
     --task-name repo-health \
     --state-db system/state/ops.db \
     --exit-zero
   ```
   The brief status is `blocked` when the audit finds errors or stale pending/blocked/failed briefs. Otherwise it is `informational`.

4. Do not mark stale pending briefs reviewed unless the underlying work was actually reviewed or the project owner explicitly decides to archive/skip them. Report the stale queue and ask for the next handling step if review is outside the current task.

5. After fixes, rerun:
   ```bash
   python3 system/tools/repo_audit.py --output system/health/repo-audit.md
   ```

## Expected Outputs

- [system/health/repo-audit.md](../../../../system/health/repo-audit.md) is refreshed.
- `system/state/ops.db` gets a `validation_results` row when `--state-db` is provided.
- Scheduled runs write `logs/repo-health/YYYY-MM-DD-HH:MM-brief.md`.
- The final response names remaining errors and actionable warnings, if any.
