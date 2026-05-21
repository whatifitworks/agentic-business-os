#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["PyYAML>=6.0"]
# ///
"""Helper for .agents/scheduler.sh.

Bash is fine for invoking the runners and shuffling files around, but
parsing schedules.yaml, doing CET/CEST timezone math, tracking last-run
state, and reading frontmatter from log files all want a real language.
This script is invoked from scheduler.sh via `uv run` so PEP 723 picks
up PyYAML automatically on first run.

Subcommands:
  due           Print a JSON array of tasks that are due to run NOW.
  record-run    Update last-run.json with a new run timestamp for one task.
  pending       Print a JSON array of log files whose frontmatter says
                `status: pending`, sorted newest first.
  list          Print every task from schedules.yaml as a JSON array
                (used by /run-scheduled to find a task by name).
  frontmatter   Print one log file's frontmatter as a JSON object.
  get-task      Print one task from schedules.yaml as a JSON object.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

import yaml


# ---------- File IO -----------------------------------------------------------


def load_schedules(path: str) -> dict[str, Any]:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def load_last_run(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text() or "{}")
    except json.JSONDecodeError:
        return {}


def load_state_last_run(path: str | None) -> dict[str, str]:
    """Return last run timestamps from ops.db, keyed by task.

    Missing or unreadable DBs are treated as absent so the scheduler can safely
    fall back to .agents/last-run.json during the transition.
    """
    if not path:
        return {}
    p = Path(path)
    if not p.exists():
        return {}
    try:
        conn = sqlite3.connect(p)
        rows = conn.execute(
            "SELECT task, last_ran_at FROM scheduler_task_state"
        ).fetchall()
    except sqlite3.Error as exc:
        print(f"WARN: could not read state db {path}: {exc}", file=sys.stderr)
        return {}
    finally:
        try:
            conn.close()
        except UnboundLocalError:
            pass
    return {str(task): str(ran_at) for task, ran_at in rows}


def save_last_run(path: str, data: dict[str, Any]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _stringify_datetimes(obj: Any) -> Any:
    """Recursively convert datetime/date objects to ISO strings.

    PyYAML auto-parses ISO-formatted timestamps into native datetime
    objects, which json.dump cannot serialize. We always want strings
    on the wire so the bash side and `jq` can read them.
    """
    if isinstance(obj, datetime):
        return obj.isoformat()
    if hasattr(obj, "isoformat"):  # date
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _stringify_datetimes(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_stringify_datetimes(v) for v in obj]
    return obj


def read_frontmatter(path: Path) -> dict[str, Any]:
    """Return YAML frontmatter from a markdown file as a dict, or {}."""
    try:
        text = path.read_text()
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    block = text[4:end]
    try:
        loaded = yaml.safe_load(block)
    except yaml.YAMLError:
        return {}
    if not isinstance(loaded, dict):
        return {}
    return _stringify_datetimes(loaded)


# ---------- Schedule parsing & due calculation --------------------------------


WEEKDAYS = {
    "MON": 0, "TUE": 1, "WED": 2, "THU": 3,
    "FRI": 4, "SAT": 5, "SUN": 6,
}


def parse_schedule(spec: str, hours: list[int] | None) -> dict[str, Any]:
    """Normalize a schedule string into a structured descriptor."""
    if spec.startswith("daily_"):
        m = re.fullmatch(r"daily_(\d{1,2}):(\d{2})", spec)
        if not m:
            raise ValueError(f"bad daily schedule: {spec!r}")
        return {"kind": "daily", "hour": int(m.group(1)), "minute": int(m.group(2))}

    if spec.startswith("weekly_"):
        m = re.fullmatch(r"weekly_([A-Za-z]{3})_(\d{1,2}):(\d{2})", spec)
        if not m:
            raise ValueError(f"bad weekly schedule: {spec!r}")
        wd = m.group(1).upper()
        if wd not in WEEKDAYS:
            raise ValueError(f"unknown weekday in {spec!r}")
        return {
            "kind": "weekly",
            "weekday": WEEKDAYS[wd],
            "hour": int(m.group(2)),
            "minute": int(m.group(3)),
        }

    if spec.startswith("every_") and spec.endswith("h"):
        if not hours:
            raise ValueError(
                f"schedule {spec!r} requires an explicit `hours: [...]` list"
            )
        return {"kind": "multi_daily", "hours": [int(h) for h in hours]}

    raise ValueError(f"unknown schedule format: {spec!r}")


def last_target_at_or_before(schedule: dict[str, Any], now: datetime) -> datetime | None:
    """Return the most recent scheduled fire time at or before `now`."""
    if schedule["kind"] == "daily":
        target = now.replace(
            hour=schedule["hour"], minute=schedule["minute"],
            second=0, microsecond=0,
        )
        if target > now:
            target -= timedelta(days=1)
        return target

    if schedule["kind"] == "weekly":
        target = now.replace(
            hour=schedule["hour"], minute=schedule["minute"],
            second=0, microsecond=0,
        )
        delta_days = (now.weekday() - schedule["weekday"]) % 7
        target -= timedelta(days=delta_days)
        if target > now:
            target -= timedelta(days=7)
        return target

    if schedule["kind"] == "multi_daily":
        candidates: list[datetime] = []
        for h in schedule["hours"]:
            t = now.replace(hour=int(h), minute=0, second=0, microsecond=0)
            if t > now:
                t -= timedelta(days=1)
            candidates.append(t)
        return max(candidates) if candidates else None

    return None


def is_due(schedule: dict[str, Any], now: datetime, last_run_iso: str | None) -> bool:
    """Decide whether a task should fire on this scheduler tick.

    A task fires when the most recent scheduled time at or before `now`
    is later than the task's last successful run. We also gate against
    very old missed runs so the scheduler does not spam a backlog after
    the machine has been off for days.
    """
    target = last_target_at_or_before(schedule, now)
    if target is None:
        return False

    last_run: datetime | None = None
    if last_run_iso:
        try:
            last_run = datetime.fromisoformat(last_run_iso)
        except ValueError:
            last_run = None
        else:
            if last_run.tzinfo is None:
                last_run = last_run.replace(tzinfo=now.tzinfo)

    if last_run is not None and last_run >= target:
        return False

    # Catch-up window: don't fire weekly tasks more than 7 days late,
    # daily/multi-daily tasks more than 25 hours late.
    max_lag = timedelta(days=7) if schedule["kind"] == "weekly" else timedelta(hours=25)
    if now - target > max_lag:
        return False

    return True


# ---------- Subcommands --------------------------------------------------------


def cmd_due(args: argparse.Namespace) -> None:
    data = load_schedules(args.schedules)
    tz = ZoneInfo(data.get("timezone", "Europe/Berlin"))

    now = (
        datetime.fromisoformat(args.now).astimezone(tz)
        if args.now
        else datetime.now(tz)
    )
    last_run_data = load_last_run(args.last_run)
    state_last_run = load_state_last_run(args.state_db)

    out: list[dict[str, Any]] = []
    for task in data.get("tasks", []):
        if not task.get("enabled", True):
            continue
        if task.get("mode") != "async":
            continue
        try:
            sched = parse_schedule(task["schedule"], task.get("hours"))
        except ValueError as exc:
            print(f"WARN: {task.get('name','?')} - {exc}", file=sys.stderr)
            continue
        task_name = task["name"]
        last = state_last_run.get(task_name) or last_run_data.get(task_name, {}).get("ran_at")
        if is_due(sched, now, last):
            out.append(task)

    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


def cmd_record(args: argparse.Namespace) -> None:
    data = load_last_run(args.last_run)
    data[args.task] = {
        "ran_at": args.time,
        "exit": args.exit_code,
        "outcome": args.outcome,
    }
    save_last_run(args.last_run, data)


def cmd_pending(args: argparse.Namespace) -> None:
    logs_dir = Path(args.logs_dir)
    reminder_tasks: set[str] | None = None
    if args.schedules:
        schedules = load_schedules(args.schedules)
        reminder_tasks = {
            task.get("name", "")
            for task in schedules.get("tasks", [])
            if task.get("remind_until_reviewed") is True
        }

    out: list[dict[str, Any]] = []
    if logs_dir.exists():
        for sub in sorted(p for p in logs_dir.iterdir() if p.is_dir()):
            if sub.name == "scheduler":
                continue
            for f in sorted(sub.glob("*.md"), reverse=True):
                fm = read_frontmatter(f)
                task_name = fm.get("task", "")
                if reminder_tasks is not None and task_name not in reminder_tasks:
                    continue
                if fm.get("status") == "pending":
                    out.append({
                        "file": str(f),
                        "log_dir": sub.name,
                        "name": f.name,
                        "task": task_name,
                        "generated_at": fm.get("generated_at", ""),
                        "needs_reply_count": fm.get("needs_reply_count"),
                    })
    out.sort(key=lambda e: e.get("generated_at", ""), reverse=True)
    json.dump(out, sys.stdout, indent=2)
    sys.stdout.write("\n")


def cmd_list(args: argparse.Namespace) -> None:
    data = load_schedules(args.schedules)
    json.dump(data.get("tasks", []), sys.stdout, indent=2)
    sys.stdout.write("\n")


def cmd_get_task(args: argparse.Namespace) -> None:
    data = load_schedules(args.schedules)
    for task in data.get("tasks", []):
        if task.get("name") == args.name:
            json.dump(task, sys.stdout, indent=2)
            sys.stdout.write("\n")
            return
    print(f"ERROR: no task named {args.name!r} in {args.schedules}", file=sys.stderr)
    sys.exit(2)


def cmd_frontmatter(args: argparse.Namespace) -> None:
    fm = read_frontmatter(Path(args.file))
    json.dump(fm, sys.stdout, indent=2)
    sys.stdout.write("\n")


# ---------- Entry point --------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="scheduler_helper.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("due", help="print JSON array of tasks due now")
    d.add_argument("--schedules", required=True)
    d.add_argument("--last-run", required=True)
    d.add_argument("--state-db", default=None, help="Optional ops.db path; preferred over --last-run when populated")
    d.add_argument("--now", default=None, help="ISO timestamp override (mostly for tests)")
    d.set_defaults(func=cmd_due)

    r = sub.add_parser("record-run", help="update last-run.json after a run")
    r.add_argument("--last-run", required=True)
    r.add_argument("--task", required=True)
    r.add_argument("--time", required=True)
    r.add_argument("--exit", dest="exit_code", type=int, default=0)
    r.add_argument("--outcome", default="success")
    r.set_defaults(func=cmd_record)

    pn = sub.add_parser("pending", help="list pending review files across logs/")
    pn.add_argument("--logs-dir", required=True)
    pn.add_argument(
        "--schedules",
        default=None,
        help="When set, include only pending briefs for tasks with remind_until_reviewed: true",
    )
    pn.set_defaults(func=cmd_pending)

    ls = sub.add_parser("list", help="list every task from schedules.yaml")
    ls.add_argument("--schedules", required=True)
    ls.set_defaults(func=cmd_list)

    gt = sub.add_parser("get-task", help="print one task from schedules.yaml by name")
    gt.add_argument("--schedules", required=True)
    gt.add_argument("--name", required=True)
    gt.set_defaults(func=cmd_get_task)

    fm = sub.add_parser("frontmatter", help="print frontmatter from one markdown file")
    fm.add_argument("--file", required=True)
    fm.set_defaults(func=cmd_frontmatter)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
