---
name: run-scheduled
description: Manually run any task defined in .agents/schedules.yaml interactively, ignoring its schedule and async/sync mode. Use whenever the project owner asks to "run the support triage now", "run the daily statistics report", "run the SEO scan", "/run-scheduled X", or otherwise wants to fire a scheduled workflow ad-hoc. Looks the task up by name, loads its underlying skill, and runs the SKILL.md procedure with all approval gates intact.
---

# Run-scheduled

Run any task from [.agents/schedules.yaml](../../../../.agents/schedules.yaml) on demand, with the user in the loop.

## Procedure

1. **No task name given?** Run:
   ```bash
   uv run .agents/scheduler_helper.py list --schedules .agents/schedules.yaml
   ```
   Present every task as a short table (`name`, `skill`, `schedule`, `mode`, `runner`, `model`, `enabled`). Ask which one to run, then stop.

2. **Look the task up by name:**
   ```bash
   uv run .agents/scheduler_helper.py get-task \
     --schedules .agents/schedules.yaml \
     --name <name>
   ```
   If exit code is non-zero, fall back to the `list` subcommand to show available task names, then stop.

3. **Load the underlying skill** by resolving `.agents/skills/*/<task.skill>/SKILL.md` first, then falling back to `.agents/skills/<task.skill>/SKILL.md` for legacy direct skills. Read the resolved SKILL.md in full. The `prompt` field on the task is written for the **headless** variant (it tells the runner "do not send replies", "write to {{LOG_FILE}}", etc). For an interactive run, the SKILL.md procedure is the source of truth — the headless prompt is informational only.

4. **Run the skill interactively** with the user in the loop:
   - Use the SKILL.md flow as written, including every approval gate and confirmation prompt the skill defines.
   - Do **not** redirect output to `logs/<log_dir>/`. Do **not** create a brief file with `status: pending` frontmatter. Do **not** touch [.agents/last-run.json](../../../../.agents/last-run.json). Those are async-only behaviors.
   - Substitute or strip any `{{LOG_FILE}}` placeholder you see — it has no meaning for interactive runs.
   - Honor the configured `model`. If it differs from the active session's model, mention the difference once but do not auto-switch.
   - If the user added extra context after the task name (e.g. "run-scheduled support-triage focus on the German tickets"), factor it in.

5. **Respect every gate.** When the SKILL.md says "send the reply", "create the ClickUp task", "delete spam", or "schedule the campaign", present the action and wait for explicit confirmation before acting. Same approval discipline as a normal session — the on-demand wrapper does not loosen anything.

6. **Disabled tasks still run.** If `enabled: false`, run the task anyway (the user explicitly asked) but mention it is currently disabled in the schedule.

## What this skill does NOT do

- Touch [.agents/last-run.json](../../../../.agents/last-run.json). The scheduler manages that, and on-demand runs are intentionally separate from the schedule history so a manual run does not delay the next scheduled one.
- Create or update files under `logs/<log_dir>/`. Those are produced exclusively by [.agents/scheduler.sh](../../../../.agents/scheduler.sh).
- Send macOS notifications. Notifications are an async-mode feature.
