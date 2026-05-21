#!/usr/bin/env python3
"""Review recurring obligations for stale or decision-needed tasks."""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import Any

from ops_state import due_date_for, parse_iso_date, parse_recurring_yaml, recurring_state


def recommendation_for(task: dict[str, Any], state: str, overdue_days: int) -> tuple[str, str]:
    cadence = str(task.get("cadence") or "")
    skill = task.get("skill")
    status = str(task.get("status") or "active")
    if status == "paused" and state == "due":
        return (
            "review-pause",
            "Paused task has reached deferred_until; decide whether to reactivate, defer again, cancel, or convert to a project.",
        )
    if state == "overdue" and cadence.startswith("once_"):
        return (
            "do-cancel-or-convert",
            "One-time task is overdue; either do the concrete work, cancel it as obsolete, or convert it into a project. Do not mark complete unless work happened.",
        )
    if state == "overdue":
        if skill:
            return (
                "do-defer-or-pause",
                "Recurring task is overdue; run the linked skill, defer with a blocker, or pause/cancel if the obligation is no longer valid.",
            )
        return (
            "clarify-owner",
            "Recurring task is overdue and has no skill; assign an owner skill/project, do it manually, defer, pause, or cancel.",
        )
    if state == "due":
        return (
            "do-or-defer",
            "Task is due; plan the concrete output today or defer/pause with a reason if it should not surface now.",
        )
    return ("no-action", "Task does not need operator action today.")


def review_recurring(recurring_path: Path, today: date, include_not_due: bool = False) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for task in parse_recurring_yaml(recurring_path):
        last_done = parse_iso_date(task.get("last_done"))
        status = str(task.get("status") or "active")
        deferred_until = parse_iso_date(task.get("deferred_until"))
        grace_days = int(task.get("grace_days") or 3)
        cadence = str(task["cadence"])
        due_on = due_date_for(cadence, last_done, today)
        state, overdue_days = recurring_state(due_on, last_done, today, grace_days, cadence, status, deferred_until)
        action, recommendation = recommendation_for(task, state, overdue_days)
        if not include_not_due and state not in {"due", "overdue"} and action == "no-action":
            continue
        rows.append(
            {
                "name": task["name"],
                "cadence": cadence,
                "skill": task.get("skill"),
                "status": status,
                "last_done": task.get("last_done"),
                "due_on": due_on.isoformat() if due_on else None,
                "state": state,
                "overdue_days": overdue_days,
                "recommended_action": action,
                "recommendation": recommendation,
                "update_commands": update_commands(str(task["name"])),
            }
        )
    return rows


def update_commands(name: str) -> dict[str, str]:
    quoted = name.replace('"', '\\"')
    return {
        "complete_after_work": f'python3 system/tools/ops_state.py --db system/state/ops.db complete-recurring --recurring .agents/recurring.yaml --name "{quoted}" --date YYYY-MM-DD',
        "pause_or_defer": f'python3 system/tools/ops_state.py --db system/state/ops.db set-recurring-status --recurring .agents/recurring.yaml --name "{quoted}" --status paused --reason "<why>" --deferred-until YYYY-MM-DD',
        "cancel": f'python3 system/tools/ops_state.py --db system/state/ops.db set-recurring-status --recurring .agents/recurring.yaml --name "{quoted}" --status cancelled --reason "<why obsolete>"',
    }


def render_markdown(rows: list[dict[str, Any]]) -> str:
    lines = ["# Recurring Review", ""]
    if not rows:
        lines.append("No due, overdue, or decision-needed recurring tasks.")
        return "\n".join(lines)
    for row in rows:
        lines.extend(
            [
                f"## {row['name']}",
                "",
                f"- State: `{row['state']}`",
                f"- Due on: `{row['due_on']}`",
                f"- Overdue days: `{row['overdue_days']}`",
                f"- Recommended action: `{row['recommended_action']}`",
                f"- Recommendation: {row['recommendation']}",
                "",
            ]
        )
    return "\n".join(lines)


def command_review(args: argparse.Namespace) -> int:
    today = parse_iso_date(args.today) if args.today else date.today()
    if today is None:
        raise SystemExit(f"invalid --today: {args.today}")
    rows = review_recurring(Path(args.recurring), today, include_not_due=args.include_not_due)
    if args.json:
        print(json.dumps({"today": today.isoformat(), "tasks": rows}, indent=2))
    else:
        print(render_markdown(rows))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review", help="Review recurring tasks that need action")
    review.add_argument("--recurring", default=".agents/recurring.yaml")
    review.add_argument("--today", help="YYYY-MM-DD override")
    review.add_argument("--include-not-due", action="store_true")
    review.add_argument("--json", action="store_true")
    review.set_defaults(func=command_review)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
