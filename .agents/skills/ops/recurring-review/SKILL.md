---
name: recurring-review
description: Review Agentic Business OS recurring obligations for due, overdue, paused, stale once-task, or no-owner states, then recommend do, defer, pause, cancel, or convert actions without falsely marking work complete.
---

# Recurring Review

Use this skill when recurring obligations are noisy, stale, overdue, or need cleanup before or during daily planning.

## Source Of Truth

- Editable source: `.agents/recurring.yaml`
- Machine mirror: `system/state/ops.db`
- State helper: `system/tools/ops_state.py`
- Review helper: `system/tools/recurring_review.py`

`ops_state.py` is the only approved way to mark recurring work complete, paused, or cancelled.

## Workflow

1. Sync the recurring source into SQLite:

   ```bash
   python3 system/tools/ops_state.py --db system/state/ops.db sync-recurring --recurring .agents/recurring.yaml
   ```

2. Review due, overdue, and stale decision-needed items:

   ```bash
   python3 system/tools/recurring_review.py review --recurring .agents/recurring.yaml
   ```

3. For each surfaced task, choose exactly one action:
   - `do`: plan or execute the concrete task output.
   - `defer`: pause with a blocker and a `deferred_until` date.
   - `pause`: pause because the obligation is valid but not currently active.
   - `cancel`: cancel because the obligation is obsolete.
   - `convert`: create or update a project when a one-time task is too large for a recurring reminder.

4. Only after actual work has happened, mark complete:

   ```bash
   python3 system/tools/ops_state.py --db system/state/ops.db complete-recurring \
     --recurring .agents/recurring.yaml \
     --name "<exact recurring task name>" \
     --date YYYY-MM-DD
   ```

5. For pause/cancel/defer decisions, update status instead of editing `last_done`:

   ```bash
   python3 system/tools/ops_state.py --db system/state/ops.db set-recurring-status \
     --recurring .agents/recurring.yaml \
     --name "<exact recurring task name>" \
     --status paused \
     --reason "<why it should not surface right now>" \
     --deferred-until YYYY-MM-DD
   ```

## Rules

- Do not mark stale work complete unless the work actually happened.
- Do not let overdue one-time tasks surface forever. Do, cancel, or convert them.
- Tasks with no skill must name a concrete manual output or be assigned to a skill/project.
- Paused tasks whose `deferred_until` has arrived are due for operator review, not automatically active or complete.
- Daily planning should surface the recommended action, not just repeat the task name.

## Output

Report:

- task name
- due date and overdue days
- recommended action
- exact `ops_state.py` command to complete, pause/defer, or cancel
- any unclear ownership that the project owner must decide
