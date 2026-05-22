---
name: daily-planning
description: Interactive daily planning session for a single project. Reviews the previous plan, checks inbox/recurring/scheduler signals, proposes a small focused plan, and writes context/today.md plus an archive copy under logs/daily-plans/.
---

# Daily Planning

Use this skill when the project owner wants to plan the day, start a work session, review yesterday's open items, or decide what to work on next.

This is the generic daily planning workflow. Rename or wrap it locally only when a project wants a branded routine.

## Source Of Truth

- Active plan: `context/today.md`
- Plan archive: `logs/daily-plans/`
- Priorities: `context/current-priorities.md`
- Goals: `context/goals.md`
- Recurring work: `.agents/recurring.yaml`
- Schedules: `.agents/schedules.yaml`
- Inbox queue: `inbox/` and `state/memory-ingest-queue.json`

## Workflow

1. Get the current local date and time with `date`.
2. Read `context/today.md` if it exists. If it is from an earlier date, archive it to `logs/daily-plans/YYYY-MM-DD.md` before creating today's plan.
3. Review unfinished items from the previous plan. Ask whether each is done, still open, blocked, deferred, or dropped.
4. Run a memory inbox preflight:
   ```bash
   python3 system/tools/inbox_auto_ingest.py scan
   python3 system/tools/inbox_auto_ingest.py status
   ```
   If pending inbox items exist, surface them before planning. Process them only when the owner agrees.
5. Check recurring obligations:
   ```bash
   python3 system/tools/recurring_review.py review --recurring .agents/recurring.yaml
   ```
6. Check scheduler/repo health only enough to catch blockers:
   ```bash
   python3 system/tools/repo_audit.py --exit-zero
   ```
7. Read current priorities and goals when those files exist.
8. Apply freshness reconciliation before carrying forward or proposing priority items.
9. Propose a plan with no more than six work items, grouped as ops, focus, admin, or optional.
10. Ask for confirmation or edits.
11. Write the confirmed plan to `context/today.md`.

## Freshness Reconciliation

Weekly reviews, priority docs, recurring lists, and older daily plans are planning inputs, not final authority. Before suggesting an item that came from an older plan, weekly review, recurring list, or project note:

- Check the latest `context/today.md`, recent `logs/daily-plans/`, relevant project notes, and any named task/card IDs.
- Suppress the original item when newer evidence says it is done, completed, closed, accepted, parked, paused, cancelled, or superseded.
- If status is unclear, propose `Verify status of <item>` or ask the project owner instead of re-adding the stale item as work.
- Never re-plan completed planning items just because they still appear in a weekly review, priority stack, or recurring source.

## Plan Format

```markdown
---
date: YYYY-MM-DD
status: active
---

# Today

## Signal Scan
- Inbox: ...
- Recurring: ...
- Health: ...

## Plan
- [ ] Ops - ...
- [ ] Focus - ...

## Notes
```

## Rules

- Keep exactly one active plan file: `context/today.md`.
- Do not mark work complete unless the owner explicitly says it is done or the work is actually completed during the session.
- Preserve concrete deliverables from recurring tasks. Do not downgrade them into vague research placeholders.
- Planning is not execution unless the owner explicitly switches into execution.
