---
name: weekly-review
description: "Interactive weekly review: summarize daily plans, check priorities and metrics, surface drift, propose next week's focus areas."
---

# Weekly Review

Use this skill when the project owner wants to wrap up the week, inspect drift, or choose next week's focus.

## Source Of Truth

- Daily plans: `logs/daily-plans/` plus current `context/today.md`
- Weekly reviews: `logs/weekly-reviews/`
- Priorities: `context/current-priorities.md` when present
- Goals: `context/goals.md` when present
- Metrics/state: project-specific files under `state/metrics/` when present

## Workflow

1. Get the current date and ISO week number:
   ```bash
   date "+%Y-%m-%d %H:%M %A %V"
   ```
2. Gather this week's daily plans from `logs/daily-plans/` and `context/today.md`.
3. Count completed and open checklist items.
4. Ask the owner what unplanned work happened and what consumed more time than expected.
5. Read priorities and goals when present. Compare actual work against them.
6. Review any available metrics or project-specific scorecards, but do not invent data when files are absent. When `state/golden-questions.json` has questions, run `python3 system/tools/golden_questions.py --record` then `--trend`, and report whether vault memory improved, held, or regressed this week.
7. Surface:
   - wins
   - fell-through items
   - unplanned work
   - recurring drift
   - blocked decisions
8. Propose two or three focus themes for next week, each with a concrete outcome.
9. After review, save `logs/weekly-reviews/YYYY-WXX.md`.

## Rules

- This is a conversation, not a report dump.
- Be direct about drift between priorities and actual work.
- Do not inflate routine maintenance into strategic progress.
- Do not plan weekend work as required capacity.
- If the owner points to concrete task cards, tickets, screenshots, or a current queue order, preserve those literal tasks as the first next-week focus lane. Do not translate them into broad phase labels unless the owner asks for that abstraction.
- If the owner corrects the review, update the saved review before finishing.
