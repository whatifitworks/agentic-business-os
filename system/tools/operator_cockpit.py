#!/usr/bin/env python3
"""Generate a compact Agentic Business OS operator cockpit."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from ops_state import (
    connect,
    health_summary,
    pending_briefs,
    recent_runs,
    recent_validations,
    sync_briefs,
    sync_recurring,
)
from ops_v2_hooks import run as run_hooks
from recurring_review import review_recurring
from repo_audit import run as run_repo_audit, summarize as summarize_repo_audit


def parse_json(value: str | None, fallback: Any) -> Any:
    if not value:
        return fallback
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return fallback


def latest_validation_details(conn) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    row = conn.execute(
        """
        SELECT name, ran_at, status, errors, warnings, info, pending_count,
               blocked_count, failed_count, report_path, brief_path,
               details_json
        FROM validation_results
        ORDER BY id DESC
        LIMIT 1
        """
    ).fetchone()
    if row is None:
        return None, []
    data = dict(row)
    details = parse_json(data.pop("details_json", None), [])
    return data, details


def scheduler_state(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT task, last_ran_at, last_exit_code, last_outcome, last_status,
               last_runner, last_model, last_brief_path
        FROM scheduler_task_state
        ORDER BY task
        """
    ).fetchall()
    return [dict(row) for row in rows]


def successful_runs(conn) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT task, MAX(ran_at) AS last_success_at
        FROM scheduler_runs
        WHERE exit_code = 0
          AND outcome NOT IN ('blocked', 'failed')
          AND COALESCE(status, '') NOT IN ('blocked', 'failed')
        GROUP BY task
        ORDER BY task
        """
    ).fetchall()
    return [dict(row) for row in rows]


def inbox_items(root: Path) -> list[Path]:
    inbox = root / "inbox"
    if not inbox.exists():
        return []
    ignored = {"README.md", ".gitkeep", ".DS_Store"}
    return sorted(path for path in inbox.rglob("*") if path.is_file() and path.name not in ignored and not path.name.startswith("."))


def parse_simple_yaml_value(text: str, field: str) -> str:
    match = re.search(rf"(?m)^{re.escape(field)}:\s*(.+?)\s*$", text)
    if not match:
        return ""
    return match.group(1).strip().strip("'\"")


def learning_review_briefs(root: Path) -> list[dict[str, Any]]:
    logs = root / "logs" / "learning"
    if not logs.exists():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(logs.glob("*-brief.md"), key=lambda item: item.stat().st_mtime, reverse=True):
        text = path.read_text(errors="replace")
        out.append({
            "file": path.relative_to(root).as_posix(),
            "status": parse_simple_yaml_value(text, "status") or "unknown",
            "candidate_count": parse_simple_yaml_value(text, "candidate_count") or "unknown",
            "event_count": parse_simple_yaml_value(text, "event_count") or "unknown",
            "generated_at": parse_simple_yaml_value(text, "generated_at") or "unknown",
        })
    return out


def adapter_inventory(root: Path) -> list[dict[str, str]]:
    adapters = root / ".agents" / "adapters"
    out: list[dict[str, str]] = []
    for path in sorted(adapters.glob("*/adapter.yaml")):
        text = path.read_text(errors="replace")
        out.append(
            {
                "name": parse_simple_yaml_value(text, "name") or path.parent.name,
                "tool_type": parse_simple_yaml_value(text, "tool_type") or "unknown",
                "status": parse_simple_yaml_value(text, "status") or "unknown",
                "last_verified_at": parse_simple_yaml_value(text, "last_verified_at") or "unknown",
                "path": path.as_posix(),
            }
        )
    return out


def active_priorities(root: Path, limit: int = 4) -> list[str]:
    path = root / "context" / "current-priorities.md"
    if not path.exists():
        return []
    priorities: list[str] = []
    for line in path.read_text(errors="replace").splitlines():
        match = re.match(r"^##\s+\d+\.\s+(.+?)\s*$", line)
        if match:
            priorities.append(match.group(1))
        if len(priorities) >= limit:
            break
    return priorities


def failure_candidates(root: Path) -> list[Path]:
    return sorted((root / "inbox").glob("*failure-candidate.md")) if (root / "inbox").exists() else []


def bullet_row(items: list[dict[str, Any]], empty: str, formatter, limit: int = 10) -> list[str]:
    if not items:
        return [f"- {empty}"]
    lines = [f"- {formatter(item)}" for item in items[:limit]]
    remaining = len(items) - limit
    if remaining > 0:
        lines.append(f"- ...and {remaining} more")
    return lines


def issue_formatter(issue: dict[str, Any]) -> str:
    return f"`{issue.get('code')}` [{issue.get('path')}] {issue.get('message')}"


def render(args: argparse.Namespace) -> str:
    root = Path.cwd()
    db = Path(args.db)
    recurring_path = Path(args.recurring)
    logs_dir = Path(args.logs_dir)
    schedules = Path(args.schedules)
    today = date.fromisoformat(args.today) if args.today else date.today()

    with connect(db) as conn:
        if recurring_path.exists():
            sync_recurring(conn, recurring_path, today)
        if logs_dir.exists():
            sync_briefs(conn, logs_dir, schedules if schedules.exists() else None)

        health = health_summary(conn, include_ok=False)
        due = review_recurring(recurring_path, today) if recurring_path.exists() else []
        pending = pending_briefs(conn, reminders_only=False)
        validations = recent_validations(conn, 1)
        validation, details = latest_validation_details(conn)
        scheduler = scheduler_state(conn)
        successes = successful_runs(conn)
        latest_runs = recent_runs(conn, 5)

    repo_issues, _repo_pending_counts = run_repo_audit(root)
    repo_counts = summarize_repo_audit(repo_issues)
    errors = repo_counts.get("error", 0)
    warnings = repo_counts.get("warn", 0)
    repo_issue_dicts = [
        {
            "level": issue.level,
            "code": issue.code,
            "path": issue.path,
            "message": issue.message,
        }
        for issue in repo_issues
    ]
    learning = learning_review_briefs(root)
    learning_files = {str(item.get("file")) for item in learning}
    operational_pending = [
        item for item in pending
        if str(item.get("file")) not in learning_files
        and not str(item.get("file")).startswith("logs/learning/")
    ]
    pending_count = len(operational_pending)
    overdue_count = sum(1 for item in due if item.get("state") == "overdue")
    due_count = sum(1 for item in due if item.get("state") == "due")
    inbox_pending = inbox_items(root)
    hook_issues = run_hooks(root, hook="all")
    hook_errors = sum(1 for issue in hook_issues if issue.level == "error")
    hook_warnings = sum(1 for issue in hook_issues if issue.level == "warn")
    adapters = adapter_inventory(root)
    failures = failure_candidates(root)
    pending_learning = [item for item in learning if item.get("status") == "pending"]
    priorities = active_priorities(root)
    failed_health = [item for item in health if item.get("status") == "failed"]
    blocked_health = [item for item in health if item.get("status") == "blocked"]

    if errors or hook_errors or failed_health:
        overall = "failed"
    elif pending_count or overdue_count or blocked_health or inbox_pending or failures:
        overall = "blocked"
    elif warnings or hook_warnings or due_count or pending_learning:
        overall = "warning"
    else:
        overall = "ok"

    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "# Agentic Business OS Cockpit",
        "",
        f"Generated: `{generated}`",
        f"Overall: `{overall}`",
        "",
        "## At A Glance",
        "",
        f"- Repo audit: {errors} errors, {warnings} warnings",
        f"- Hooks: {hook_errors} errors, {hook_warnings} warnings",
        f"- Inbox: {len(inbox_pending)} pending files",
        f"- Pending operational briefs: {pending_count}",
        f"- Recurring work: {overdue_count} overdue, {due_count} due",
        f"- Adapter contracts: {len(adapters)}",
        f"- Failure candidates: {len(failures)}",
        f"- Learning review: {len(pending_learning)} pending briefs",
        f"- Problem health components: {len(health)}",
        "",
        "## Active Priority Stack",
        "",
    ]
    lines.extend([f"- {item}" for item in priorities] or ["- No priorities found in context/current-priorities.md."])

    lines.extend([
        "",
        "## Inbox",
        "",
    ])
    lines.extend([f"- `{path.as_posix()}`" for path in inbox_pending[:10]] or ["- Inbox is clear."])
    if len(inbox_pending) > 10:
        lines.append(f"- ...and {len(inbox_pending) - 10} more")

    lines.extend([
        "",
        "## Hook Health",
        "",
        f"- Errors: {hook_errors}",
        f"- Warnings: {hook_warnings}",
    ])
    if hook_issues:
        lines.extend(
            f"- `{issue.hook}:{issue.code}` [{issue.path}] {issue.message}"
            for issue in hook_issues[:8]
        )
    else:
        lines.append("- No hook issues found.")

    lines.extend([
        "",
        "## Adapter Inventory",
        "",
    ])
    lines.extend(bullet_row(
        adapters,
        "No adapter contracts registered.",
        lambda item: (
            f"{item['name']}: {item['tool_type']} / {item['status']} "
            f"(verified {item['last_verified_at']}, `{item['path']}`)"
        ),
        limit=10,
    ))

    lines.extend([
        "",
        "## Skill Improvement Queue",
        "",
    ])
    lines.extend([f"- `{path.as_posix()}`" for path in failures[:10]] or ["- No failure candidates waiting in inbox."])

    lines.extend([
        "",
        "## Learning Review Queue",
        "",
    ])
    lines.extend(bullet_row(
        pending_learning or learning[:1],
        "No learning review briefs found.",
        lambda item: (
            f"{item['status']}: {item['candidate_count']} candidates, "
            f"{item['event_count']} events (`{item['file']}`, generated {item['generated_at']})"
        ),
        limit=5,
    ))

    lines.extend([
        "",
        "## Blocked Or Degraded",
        "",
    ])
    lines.extend(bullet_row(
        health,
        "No blocked or failed health components recorded.",
        lambda item: (
            f"{item['component_type']}/{item['component_name']}: "
            f"{item['status']} ({item['summary']})"
        ),
        limit=8,
    ))

    lines.extend(["", "## Due Recurring Work", ""])
    lines.extend(bullet_row(
        due,
        "No due or overdue recurring tasks.",
        lambda item: (
            f"{item['state']}: {item['name']} "
            f"(due {item.get('due_on') or 'unknown'}, action {item.get('recommended_action') or 'unknown'})"
        ),
        limit=12,
    ))

    lines.extend(["", "## Pending Review Queue", ""])
    lines.extend(bullet_row(
        pending,
        "No pending briefs in the SQLite queue.",
        lambda item: f"{item['file']} ({item.get('task') or item.get('log_dir')}, generated {item.get('generated_at') or 'unknown'})",
        limit=10,
    ))

    actionable = [
        issue for issue in repo_issue_dicts
        if issue.get("level") == "error"
        or issue.get("code") in {"stale_pending_brief", "blocked_brief", "failed_brief"}
    ]
    other = [issue for issue in repo_issue_dicts if issue not in actionable]

    lines.extend(["", "## Repo Audit", ""])
    lines.append(f"- Live: {errors} errors, {warnings} warnings")
    if validation:
        lines.extend([
            f"- Latest recorded DB run: `{validation['ran_at']}` status `{validation['status']}`",
            f"- Recorded report: `{validation.get('report_path') or 'not recorded'}`",
        ])
    else:
        lines.append("- No validation result recorded in SQLite yet.")
    if actionable:
        lines.extend(["", "Actionable:"])
        lines.extend(bullet_row(actionable, "No actionable repo-health issues.", issue_formatter, limit=10))
    if other:
        lines.extend(["", "Other warnings:"])
        lines.extend(bullet_row(other, "No other warnings.", issue_formatter, limit=5))

    lines.extend(["", "## Scheduler", ""])
    lines.extend(bullet_row(
        scheduler,
        "No scheduler task state recorded yet.",
        lambda item: (
            f"{item['task']}: exit={item['last_exit_code']} "
            f"outcome={item['last_outcome']} status={item.get('last_status') or ''} "
            f"at {item['last_ran_at']}"
        ),
        limit=10,
    ))
    if successes:
        lines.extend(["", "Last successful scheduled runs:"])
        lines.extend(bullet_row(
            successes,
            "No successful scheduled runs recorded yet.",
            lambda item: f"{item['task']}: {item['last_success_at']}",
            limit=10,
        ))
    if latest_runs:
        lines.extend(["", "Recent runs:"])
        lines.extend(bullet_row(
            latest_runs,
            "No recent run history recorded.",
            lambda item: f"{item['task']}: {item['outcome']}/{item.get('status') or ''} at {item['ran_at']}",
            limit=5,
        ))

    return "\n".join(lines) + "\n"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="system/state/ops.db")
    parser.add_argument("--recurring", default=".agents/recurring.yaml")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--schedules", default=".agents/schedules.yaml")
    parser.add_argument("--today", help="YYYY-MM-DD override for recurring calculations")
    parser.add_argument("--output", default="system/health/operator-cockpit.md")
    parser.add_argument("--brief-output", help="Optional scheduler brief path to overwrite")
    return parser


def overall_from_rendered(rendered: str) -> str:
    match = re.search(r"(?m)^Overall: `([^`]+)`", rendered)
    return match.group(1) if match else "unknown"


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    rendered = render(args)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(rendered)
    if args.brief_output:
        brief = Path(args.brief_output)
        brief.parent.mkdir(parents=True, exist_ok=True)
        overall = overall_from_rendered(rendered)
        status = "informational" if overall in {"ok", "warning"} else "blocked"
        generated = datetime.now().astimezone().isoformat(timespec="seconds")
        brief.write_text(
            "\n".join([
                "---",
                f"status: {status}",
                "task: ops-cockpit",
                f"generated_at: {generated}",
                f"cockpit_report: {output}",
                "---",
                "",
                "# Ops Cockpit",
                "",
                f"- Overall: `{overall}`",
                f"- Full report: `{output}`",
                "",
            ])
        )
    print(f"WROTE: {output}")


if __name__ == "__main__":
    main()
