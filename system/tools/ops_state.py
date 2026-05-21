#!/usr/bin/env python3
"""SQLite state helpers for Agentic Business OS runtime state.

This is the first machine-owned state spine for the ops repo. Markdown briefs
remain the human-facing artifacts, but scheduler run history and review-queue
metadata are mirrored into SQLite so later phases can stop depending on
markdown scans as the source of truth.
"""

from __future__ import annotations

import argparse
import calendar
import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "5"


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def connect(db_path: Path) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS schema_meta (
          key TEXT PRIMARY KEY,
          value TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scheduler_runs (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          task TEXT NOT NULL,
          ran_at TEXT NOT NULL,
          exit_code INTEGER NOT NULL,
          outcome TEXT NOT NULL,
          status TEXT,
          runner TEXT,
          model TEXT,
          brief_path TEXT,
          runner_log_path TEXT,
          created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_scheduler_runs_task_ran
          ON scheduler_runs(task, ran_at DESC);

        CREATE TABLE IF NOT EXISTS scheduler_task_state (
          task TEXT PRIMARY KEY,
          last_ran_at TEXT NOT NULL,
          last_exit_code INTEGER NOT NULL,
          last_outcome TEXT NOT NULL,
          last_status TEXT,
          last_runner TEXT,
          last_model TEXT,
          last_brief_path TEXT,
          last_runner_log_path TEXT,
          updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS brief_queue (
          path TEXT PRIMARY KEY,
          task TEXT,
          log_dir TEXT,
          status TEXT,
          generated_at TEXT,
          needs_reply_count INTEGER,
          remind_until_reviewed INTEGER NOT NULL DEFAULT 0,
          reviewed_at TEXT,
          source TEXT NOT NULL DEFAULT 'markdown',
          updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_brief_queue_status_generated
          ON brief_queue(status, generated_at DESC);

        CREATE TABLE IF NOT EXISTS validation_results (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          ran_at TEXT NOT NULL,
          status TEXT NOT NULL,
          errors INTEGER NOT NULL,
          warnings INTEGER NOT NULL,
          info INTEGER NOT NULL,
          pending_count INTEGER NOT NULL DEFAULT 0,
          blocked_count INTEGER NOT NULL DEFAULT 0,
          failed_count INTEGER NOT NULL DEFAULT 0,
          report_path TEXT,
          brief_path TEXT,
          details_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_validation_results_name_ran
          ON validation_results(name, ran_at DESC);

        CREATE TABLE IF NOT EXISTS health_events (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          component_type TEXT NOT NULL,
          component_name TEXT NOT NULL,
          checked_at TEXT NOT NULL,
          status TEXT NOT NULL,
          severity INTEGER NOT NULL,
          summary TEXT NOT NULL,
          details_json TEXT NOT NULL,
          created_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_health_events_component_checked
          ON health_events(component_type, component_name, checked_at DESC);

        CREATE TABLE IF NOT EXISTS component_health (
          component_type TEXT NOT NULL,
          component_name TEXT NOT NULL,
          last_checked_at TEXT NOT NULL,
          status TEXT NOT NULL,
          severity INTEGER NOT NULL,
          summary TEXT NOT NULL,
          consecutive_ok INTEGER NOT NULL DEFAULT 0,
          consecutive_problem INTEGER NOT NULL DEFAULT 0,
          last_ok_at TEXT,
          last_problem_at TEXT,
          updated_at TEXT NOT NULL,
          PRIMARY KEY(component_type, component_name)
        );

        CREATE TABLE IF NOT EXISTS recurring_tasks (
          name TEXT PRIMARY KEY,
          cadence TEXT NOT NULL,
          skill TEXT,
          status TEXT NOT NULL DEFAULT 'active',
          status_reason TEXT,
          deferred_until TEXT,
          last_done TEXT,
          grace_days INTEGER NOT NULL DEFAULT 3,
          due_on TEXT,
          state TEXT NOT NULL,
          overdue_days INTEGER NOT NULL DEFAULT 0,
          source_path TEXT NOT NULL,
          updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_recurring_tasks_state_due
          ON recurring_tasks(state, due_on);
        """
    )
    ensure_columns(conn, "recurring_tasks", {
        "status": "TEXT NOT NULL DEFAULT 'active'",
        "status_reason": "TEXT",
        "deferred_until": "TEXT",
    })
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('schema_version', ?)",
        (SCHEMA_VERSION,),
    )
    conn.commit()


def ensure_columns(conn: sqlite3.Connection, table: str, columns: dict[str, str]) -> None:
    existing = {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}
    for name, definition in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def read_frontmatter(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    block = text[4:end]
    out: dict[str, Any] = {}
    for line in block.splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out


def normalize_repo_path(path: Path) -> str:
    try:
        resolved = path.resolve()
        root = Path.cwd().resolve()
        return resolved.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()
    except OSError:
        return path.as_posix()


def int_or_none(value: Any) -> int | None:
    if value in (None, "", "null"):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def reminder_tasks_from_schedules(path: Path | None) -> set[str]:
    if path is None or not path.exists():
        return set()
    reminders: set[str] = set()
    current_name: str | None = None
    for raw in path.read_text(errors="replace").splitlines():
        line = raw.strip()
        name_match = re.match(r"- name:\s*([^#\s]+)", line)
        if name_match:
            current_name = name_match.group(1).strip("'\"")
            continue
        if current_name and re.match(r"remind_until_reviewed:\s*true\b", line):
            reminders.add(current_name)
    return reminders


def parse_scalar(value: str) -> str | None:
    value = value.strip()
    if value in {"null", "NULL", "~", ""}:
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    return value


def parse_recurring_yaml(path: Path) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for raw in path.read_text(errors="replace").splitlines():
        task_match = re.match(r"^\s{2}- name:\s*(.+?)\s*$", raw)
        if task_match:
            if current:
                tasks.append(current)
            current = {"name": parse_scalar(task_match.group(1))}
            continue
        if current is None:
            continue
        field_match = re.match(r"^\s{4}([a-z_]+):\s*(.*?)\s*$", raw)
        if not field_match:
            continue
        key, value = field_match.groups()
        if key in {"cadence", "skill", "status", "status_reason", "deferred_until", "last_done", "grace_days"}:
            current[key] = parse_scalar(value)
    if current:
        tasks.append(current)
    return [task for task in tasks if task.get("name") and task.get("cadence")]


def parse_iso_date(value: Any) -> date | None:
    if value in (None, "", "null"):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


def month_day(year: int, month: int, day: int) -> date:
    last_day = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last_day))


def add_months(d: date, months: int) -> date:
    month_index = d.month - 1 + months
    year = d.year + month_index // 12
    month = month_index % 12 + 1
    return month_day(year, month, d.day)


def first_weekday_after(start: date, weekday: int) -> date:
    return start + timedelta(days=(weekday - start.weekday()) % 7)


def due_date_for(cadence: str, last_done: date | None, today: date) -> date | None:
    if cadence.startswith("monthly_"):
        day = int(cadence.split("_", 1)[1])
        candidate = month_day(today.year, today.month, day)
        if last_done and last_done >= candidate:
            return add_months(candidate, 1)
        return candidate

    if cadence.startswith("every_") and cadence.endswith("d"):
        days = int(cadence.removeprefix("every_").removesuffix("d"))
        return (last_done + timedelta(days=days)) if last_done else today

    if cadence.startswith("every_") and cadence.endswith("w"):
        weeks = int(cadence.removeprefix("every_").removesuffix("w"))
        return (last_done + timedelta(weeks=weeks)) if last_done else today

    if cadence.startswith("weekly_"):
        weekdays = {"MON": 0, "TUE": 1, "WED": 2, "THU": 3, "FRI": 4, "SAT": 5, "SUN": 6}
        weekday = weekdays[cadence.split("_", 1)[1]]
        if last_done:
            return first_weekday_after(last_done + timedelta(days=1), weekday)
        start_of_week = today - timedelta(days=today.weekday())
        return first_weekday_after(start_of_week, weekday)

    if cadence.startswith("once_"):
        return None if last_done else parse_iso_date(cadence.removeprefix("once_"))

    if cadence.startswith("quarterly_"):
        _, month_text, day_text = cadence.split("_", 2)
        start_month = int(month_text)
        day = int(day_text)
        months = [((start_month - 1 + offset) % 12) + 1 for offset in (0, 3, 6, 9)]
        years = range((last_done.year if last_done else today.year), today.year + 2)
        candidates = sorted(month_day(year, month, day) for year in years for month in months)
        if last_done:
            for candidate in candidates:
                if candidate > last_done:
                    return candidate
        for candidate in candidates:
            if candidate >= today.replace(month=1, day=1):
                return candidate
    return None


def recurring_state(
    due_on: date | None,
    last_done: date | None,
    today: date,
    grace_days: int,
    cadence: str,
    status: str,
    deferred_until: date | None,
) -> tuple[str, int]:
    if status == "cancelled":
        return "cancelled", 0
    if status == "paused" and (deferred_until is None or today < deferred_until):
        return "paused", 0
    if cadence.startswith("once_") and last_done:
        return "done", 0
    if due_on is None:
        return "unknown", 0
    if today < due_on:
        return "not_due", 0
    overdue_days = (today - due_on).days
    if overdue_days > grace_days:
        return "overdue", overdue_days
    return "due", overdue_days


def sync_recurring(conn: sqlite3.Connection, recurring_path: Path, today: date) -> int:
    now = utc_now()
    tasks = parse_recurring_yaml(recurring_path)
    conn.execute("DELETE FROM recurring_tasks")
    for task in tasks:
        last_done = parse_iso_date(task.get("last_done"))
        status = str(task.get("status") or "active")
        deferred_until = parse_iso_date(task.get("deferred_until"))
        grace_days = int(task.get("grace_days") or 3)
        due_on = due_date_for(str(task["cadence"]), last_done, today)
        state, overdue_days = recurring_state(
            due_on,
            last_done,
            today,
            grace_days,
            str(task["cadence"]),
            status,
            deferred_until,
        )
        conn.execute(
            """
            INSERT INTO recurring_tasks(
              name, cadence, skill, status, status_reason, deferred_until,
              last_done, grace_days, due_on, state, overdue_days, source_path,
              updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(name) DO UPDATE SET
              cadence=excluded.cadence,
              skill=excluded.skill,
              status=excluded.status,
              status_reason=excluded.status_reason,
              deferred_until=excluded.deferred_until,
              last_done=excluded.last_done,
              grace_days=excluded.grace_days,
              due_on=excluded.due_on,
              state=excluded.state,
              overdue_days=excluded.overdue_days,
              source_path=excluded.source_path,
              updated_at=excluded.updated_at
            """,
            (
                task["name"],
                task["cadence"],
                task.get("skill"),
                status,
                task.get("status_reason"),
                task.get("deferred_until"),
                task.get("last_done"),
                grace_days,
                due_on.isoformat() if due_on else None,
                state,
                overdue_days,
                str(recurring_path),
                now,
            ),
        )
    conn.commit()
    return len(tasks)


def replace_recurring_task_fields(recurring_path: Path, name: str, fields: dict[str, str | None]) -> None:
    lines = recurring_path.read_text(errors="replace").splitlines()
    start, end = recurring_task_bounds_from_lines(lines, name)
    field_lines: dict[str, int] = {}
    insert_before = end
    for i in range(start + 1, end):
        match = re.match(r"^\s{4}([a-z_]+):", lines[i])
        if match:
            field_lines[match.group(1)] = i
            if match.group(1) in {"last_done", "grace_days"}:
                insert_before = min(insert_before, i)

    inserted = 0
    for key, value in fields.items():
        if value is None:
            continue
        replacement = f"    {key}: {value}"
        line_index = field_lines.get(key)
        if line_index is not None:
            lines[line_index] = replacement
        else:
            lines.insert(insert_before + inserted, replacement)
            inserted += 1

    recurring_path.write_text("\n".join(lines) + "\n")


def recurring_task_bounds_from_lines(lines: list[str], name: str) -> tuple[int, int]:
    starts: list[tuple[int, str]] = []
    for i, raw in enumerate(lines):
        task_match = re.match(r"^\s{2}- name:\s*(.+?)\s*$", raw)
        if task_match:
            starts.append((i, parse_scalar(task_match.group(1)) or ""))

    matches = [idx for idx, task_name in starts if task_name == name]
    if not matches:
        known = ", ".join(task_name for _, task_name in starts[:10])
        raise ValueError(f"no recurring task named {name!r}; first known tasks: {known}")
    if len(matches) > 1:
        raise ValueError(f"multiple recurring tasks named {name!r}; refusing ambiguous update")

    start = matches[0]
    following = [idx for idx, _ in starts if idx > start]
    end = following[0] if following else len(lines)
    return start, end


def complete_recurring_task(recurring_path: Path, name: str, completed_on: date) -> None:
    lines = recurring_path.read_text(errors="replace").splitlines()
    start, end = recurring_task_bounds_from_lines(lines, name)
    last_done_line = None
    grace_line = None
    for i in range(start + 1, end):
        if re.match(r"^\s{4}last_done:", lines[i]):
            last_done_line = i
            break
        if re.match(r"^\s{4}grace_days:", lines[i]):
            grace_line = i

    replacement = f"    last_done: {completed_on.isoformat()}"
    if last_done_line is not None:
        lines[last_done_line] = replacement
    elif grace_line is not None:
        lines.insert(grace_line, replacement)
    else:
        lines.insert(end, replacement)

    recurring_path.write_text("\n".join(lines) + "\n")


def yaml_scalar(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def set_recurring_task_status(
    recurring_path: Path,
    name: str,
    status: str,
    reason: str | None,
    deferred_until: date | None,
) -> None:
    if status not in {"active", "paused", "cancelled"}:
        raise ValueError("status must be one of: active, paused, cancelled")
    if status != "active" and not reason:
        raise ValueError("non-active recurring task status requires --reason")
    fields: dict[str, str | None] = {"status": status}
    if reason:
        fields["status_reason"] = yaml_scalar(reason)
    if deferred_until:
        fields["deferred_until"] = deferred_until.isoformat()
    replace_recurring_task_fields(recurring_path, name, fields)


def record_run(
    conn: sqlite3.Connection,
    *,
    task: str,
    ran_at: str,
    exit_code: int,
    outcome: str,
    status: str | None,
    runner: str | None,
    model: str | None,
    brief_path: str | None,
    runner_log_path: str | None,
) -> None:
    now = utc_now()
    conn.execute(
        """
        INSERT INTO scheduler_runs(
          task, ran_at, exit_code, outcome, status, runner, model,
          brief_path, runner_log_path, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (task, ran_at, exit_code, outcome, status, runner, model, brief_path, runner_log_path, now),
    )
    conn.execute(
        """
        INSERT INTO scheduler_task_state(
          task, last_ran_at, last_exit_code, last_outcome, last_status,
          last_runner, last_model, last_brief_path, last_runner_log_path, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(task) DO UPDATE SET
          last_ran_at=excluded.last_ran_at,
          last_exit_code=excluded.last_exit_code,
          last_outcome=excluded.last_outcome,
          last_status=excluded.last_status,
          last_runner=excluded.last_runner,
          last_model=excluded.last_model,
          last_brief_path=excluded.last_brief_path,
          last_runner_log_path=excluded.last_runner_log_path,
          updated_at=excluded.updated_at
        """,
        (task, ran_at, exit_code, outcome, status, runner, model, brief_path, runner_log_path, now),
    )
    if brief_path:
        upsert_brief(conn, Path(brief_path), remind_until_reviewed=False)
    record_health(
        conn,
        component_type="scheduled_task",
        component_name=task,
        checked_at=ran_at,
        status=health_status_from_run(exit_code, outcome, status),
        summary=f"exit={exit_code}, outcome={outcome}, status={status or ''}".strip(),
        details={
            "task": task,
            "exit_code": exit_code,
            "outcome": outcome,
            "status": status,
            "runner": runner,
            "model": model,
            "brief_path": brief_path,
            "runner_log_path": runner_log_path,
        },
    )
    conn.commit()


def upsert_brief(conn: sqlite3.Connection, path: Path, remind_until_reviewed: bool | None = None) -> None:
    fm = read_frontmatter(path)
    if not fm:
        return
    stored_path = normalize_repo_path(path)
    log_dir = path.parent.name
    task = fm.get("task", "")
    status = fm.get("status", "")
    generated_at = fm.get("generated_at", "")
    needs_reply_count = int_or_none(fm.get("needs_reply_count"))
    if remind_until_reviewed is None:
        existing = conn.execute(
            "SELECT remind_until_reviewed FROM brief_queue WHERE path = ?",
            (stored_path,),
        ).fetchone()
        remind_flag = int(existing["remind_until_reviewed"]) if existing else 0
    else:
        remind_flag = 1 if remind_until_reviewed else 0
    reviewed_at = utc_now() if status == "reviewed" else None
    conn.execute(
        """
        INSERT INTO brief_queue(
          path, task, log_dir, status, generated_at, needs_reply_count,
          remind_until_reviewed, reviewed_at, source, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'markdown', ?)
        ON CONFLICT(path) DO UPDATE SET
          task=excluded.task,
          log_dir=excluded.log_dir,
          status=excluded.status,
          generated_at=excluded.generated_at,
          needs_reply_count=excluded.needs_reply_count,
          remind_until_reviewed=excluded.remind_until_reviewed,
          reviewed_at=COALESCE(excluded.reviewed_at, brief_queue.reviewed_at),
          source=excluded.source,
          updated_at=excluded.updated_at
        """,
        (
            stored_path,
            task,
            log_dir,
            status,
            generated_at,
            needs_reply_count,
            remind_flag,
            reviewed_at,
            utc_now(),
        ),
    )


def sync_briefs(conn: sqlite3.Connection, logs_dir: Path, schedules: Path | None) -> int:
    reminders = reminder_tasks_from_schedules(schedules)
    count = 0
    if not logs_dir.exists():
        return count
    for brief in sorted(logs_dir.glob("*/*.md")):
        if brief.parent.name == "scheduler":
            continue
        fm = read_frontmatter(brief)
        if not fm:
            continue
        upsert_brief(conn, brief, fm.get("task", "") in reminders)
        count += 1
    remove_duplicate_brief_paths(conn)
    conn.commit()
    return count


def remove_duplicate_brief_paths(conn: sqlite3.Connection) -> None:
    rows = conn.execute("SELECT path FROM brief_queue").fetchall()
    preferred: dict[str, str] = {}
    duplicates: list[str] = []
    for row in rows:
        stored = str(row["path"])
        normalized = normalize_repo_path(Path(stored))
        keep = preferred.get(normalized)
        if keep is None:
            preferred[normalized] = stored
            continue
        if keep == normalized:
            duplicates.append(stored)
        elif stored == normalized:
            duplicates.append(keep)
            preferred[normalized] = stored
        else:
            duplicates.append(stored)
    for path in duplicates:
        conn.execute("DELETE FROM brief_queue WHERE path = ?", (path,))


def rows_to_dicts(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def pending_briefs(conn: sqlite3.Connection, reminders_only: bool) -> list[dict[str, Any]]:
    where = "status = 'pending'"
    params: list[Any] = []
    if reminders_only:
        where += " AND remind_until_reviewed = ?"
        params.append(1)
    rows = conn.execute(
        f"""
        SELECT path AS file, log_dir, task, generated_at, needs_reply_count
        FROM brief_queue
        WHERE {where}
        ORDER BY generated_at DESC
        """,
        params,
    ).fetchall()
    out = rows_to_dicts(rows)
    for item in out:
        item["name"] = Path(item["file"]).name
    return out


def recent_runs(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT task, ran_at, exit_code, outcome, status, runner, model,
               brief_path, runner_log_path
        FROM scheduler_runs
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return rows_to_dicts(rows)


def severity_for_status(status: str) -> int:
    return {
        "ok": 0,
        "informational": 0,
        "warning": 1,
        "blocked": 2,
        "failed": 3,
    }.get(status, 1)


def health_status_from_run(exit_code: int, outcome: str, status: str | None) -> str:
    if exit_code != 0 or outcome == "failed" or status == "failed":
        return "failed"
    if outcome == "blocked" or status == "blocked":
        return "blocked"
    return "ok"


def record_health(
    conn: sqlite3.Connection,
    *,
    component_type: str,
    component_name: str,
    checked_at: str,
    status: str,
    summary: str,
    details: dict[str, Any],
) -> None:
    now = utc_now()
    severity = severity_for_status(status)
    conn.execute(
        """
        INSERT INTO health_events(
          component_type, component_name, checked_at, status, severity,
          summary, details_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            component_type,
            component_name,
            checked_at,
            status,
            severity,
            summary,
            json.dumps(details, sort_keys=True),
            now,
        ),
    )
    existing = conn.execute(
        """
        SELECT consecutive_ok, consecutive_problem, last_ok_at, last_problem_at
        FROM component_health
        WHERE component_type = ? AND component_name = ?
        """,
        (component_type, component_name),
    ).fetchone()
    if status in {"ok", "informational"}:
        consecutive_ok = (int(existing["consecutive_ok"]) if existing else 0) + 1
        consecutive_problem = 0
        last_ok_at = checked_at
        last_problem_at = existing["last_problem_at"] if existing else None
    else:
        consecutive_ok = 0
        consecutive_problem = (int(existing["consecutive_problem"]) if existing else 0) + 1
        last_ok_at = existing["last_ok_at"] if existing else None
        last_problem_at = checked_at
    conn.execute(
        """
        INSERT INTO component_health(
          component_type, component_name, last_checked_at, status, severity,
          summary, consecutive_ok, consecutive_problem, last_ok_at,
          last_problem_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(component_type, component_name) DO UPDATE SET
          last_checked_at=excluded.last_checked_at,
          status=excluded.status,
          severity=excluded.severity,
          summary=excluded.summary,
          consecutive_ok=excluded.consecutive_ok,
          consecutive_problem=excluded.consecutive_problem,
          last_ok_at=excluded.last_ok_at,
          last_problem_at=excluded.last_problem_at,
          updated_at=excluded.updated_at
        """,
        (
            component_type,
            component_name,
            checked_at,
            status,
            severity,
            summary,
            consecutive_ok,
            consecutive_problem,
            last_ok_at,
            last_problem_at,
            now,
        ),
    )


def record_validation(
    conn: sqlite3.Connection,
    *,
    name: str,
    ran_at: str,
    status: str,
    errors: int,
    warnings: int,
    info: int,
    pending_count: int,
    blocked_count: int,
    failed_count: int,
    report_path: str | None,
    brief_path: str | None,
    details: list[dict[str, Any]],
) -> None:
    summary = (
        f"errors={errors}, warnings={warnings}, pending={pending_count}, "
        f"blocked={blocked_count}, failed={failed_count}"
    )
    conn.execute(
        """
        INSERT INTO validation_results(
          name, ran_at, status, errors, warnings, info, pending_count,
          blocked_count, failed_count, report_path, brief_path, details_json,
          created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name,
            ran_at,
            status,
            errors,
            warnings,
            info,
            pending_count,
            blocked_count,
            failed_count,
            report_path,
            brief_path,
            json.dumps(details, sort_keys=True),
            utc_now(),
        ),
    )
    record_health(
        conn,
        component_type="validation",
        component_name=name,
        checked_at=ran_at,
        status=status,
        summary=summary,
        details={
            "name": name,
            "errors": errors,
            "warnings": warnings,
            "info": info,
            "pending_count": pending_count,
            "blocked_count": blocked_count,
            "failed_count": failed_count,
            "report_path": report_path,
            "brief_path": brief_path,
        },
    )
    conn.commit()


def recent_validations(conn: sqlite3.Connection, limit: int) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT name, ran_at, status, errors, warnings, info, pending_count,
               blocked_count, failed_count, report_path, brief_path
        FROM validation_results
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return rows_to_dicts(rows)


def health_summary(conn: sqlite3.Connection, include_ok: bool) -> list[dict[str, Any]]:
    where = "" if include_ok else "WHERE severity > 0"
    rows = conn.execute(
        f"""
        SELECT component_type, component_name, last_checked_at, status, severity,
               summary, consecutive_ok, consecutive_problem, last_ok_at,
               last_problem_at
        FROM component_health
        {where}
        ORDER BY severity DESC, last_checked_at DESC
        """
    ).fetchall()
    return rows_to_dicts(rows)


def due_recurring(conn: sqlite3.Connection, include_not_due: bool) -> list[dict[str, Any]]:
    if include_not_due:
        where = ""
        params: list[Any] = []
    else:
        where = "WHERE state IN (?, ?)"
        params = ["due", "overdue"]
    rows = conn.execute(
        f"""
        SELECT name, cadence, skill, status, status_reason, deferred_until,
               last_done, grace_days, due_on, state, overdue_days
        FROM recurring_tasks
        {where}
        ORDER BY
          CASE state WHEN 'overdue' THEN 0 WHEN 'due' THEN 1 WHEN 'not_due' THEN 2 ELSE 3 END,
          due_on
        """,
        params,
    ).fetchall()
    return rows_to_dicts(rows)


def cmd_init(args: argparse.Namespace) -> None:
    with connect(Path(args.db)):
        pass
    print(f"initialized {args.db}")


def cmd_record_run(args: argparse.Namespace) -> None:
    with connect(Path(args.db)) as conn:
        record_run(
            conn,
            task=args.task,
            ran_at=args.ran_at,
            exit_code=args.exit_code,
            outcome=args.outcome,
            status=args.status,
            runner=args.runner,
            model=args.model,
            brief_path=args.brief_path,
            runner_log_path=args.runner_log_path,
        )


def cmd_sync_briefs(args: argparse.Namespace) -> None:
    with connect(Path(args.db)) as conn:
        count = sync_briefs(conn, Path(args.logs_dir), Path(args.schedules) if args.schedules else None)
    if not args.quiet:
        print(json.dumps({"synced": count}, indent=2))


def cmd_pending_briefs(args: argparse.Namespace) -> None:
    with connect(Path(args.db)) as conn:
        out = pending_briefs(conn, args.reminders_only)
    print(json.dumps(out, indent=2))


def cmd_recent_runs(args: argparse.Namespace) -> None:
    with connect(Path(args.db)) as conn:
        out = recent_runs(conn, args.limit)
    print(json.dumps(out, indent=2))


def cmd_recent_validations(args: argparse.Namespace) -> None:
    with connect(Path(args.db)) as conn:
        out = recent_validations(conn, args.limit)
    print(json.dumps(out, indent=2))


def cmd_health_summary(args: argparse.Namespace) -> None:
    with connect(Path(args.db)) as conn:
        out = health_summary(conn, args.include_ok)
    print(json.dumps(out, indent=2))


def cmd_sync_recurring(args: argparse.Namespace) -> None:
    today = parse_iso_date(args.today) if args.today else date.today()
    if today is None:
        raise SystemExit(f"invalid --today date: {args.today}")
    with connect(Path(args.db)) as conn:
        count = sync_recurring(conn, Path(args.recurring), today)
    if not args.quiet:
        print(json.dumps({"synced": count, "today": today.isoformat()}, indent=2))


def cmd_complete_recurring(args: argparse.Namespace) -> None:
    completed_on = parse_iso_date(args.date)
    if completed_on is None:
        raise SystemExit(f"invalid --date: {args.date}")
    today = parse_iso_date(args.today) if args.today else date.today()
    if today is None:
        raise SystemExit(f"invalid --today date: {args.today}")
    recurring_path = Path(args.recurring)
    try:
        complete_recurring_task(recurring_path, args.name, completed_on)
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    with connect(Path(args.db)) as conn:
        sync_recurring(conn, recurring_path, today)
    print(json.dumps({
        "completed": args.name,
        "last_done": completed_on.isoformat(),
        "synced": True,
    }, indent=2))


def cmd_set_recurring_status(args: argparse.Namespace) -> None:
    deferred_until = parse_iso_date(args.deferred_until) if args.deferred_until else None
    if args.deferred_until and deferred_until is None:
        raise SystemExit(f"invalid --deferred-until date: {args.deferred_until}")
    today = parse_iso_date(args.today) if args.today else date.today()
    if today is None:
        raise SystemExit(f"invalid --today date: {args.today}")
    recurring_path = Path(args.recurring)
    try:
        set_recurring_task_status(
            recurring_path,
            args.name,
            args.status,
            args.reason,
            deferred_until,
        )
    except (OSError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    with connect(Path(args.db)) as conn:
        sync_recurring(conn, recurring_path, today)
    print(json.dumps({
        "task": args.name,
        "status": args.status,
        "reason": args.reason,
        "deferred_until": deferred_until.isoformat() if deferred_until else None,
        "synced": True,
    }, indent=2))


def cmd_due_recurring(args: argparse.Namespace) -> None:
    with connect(Path(args.db)) as conn:
        out = due_recurring(conn, args.include_not_due)
    print(json.dumps(out, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="system/state/ops.db")
    sub = parser.add_subparsers(dest="cmd", required=True)

    init = sub.add_parser("init", help="initialize the SQLite database")
    init.set_defaults(func=cmd_init)

    record = sub.add_parser("record-run", help="record one scheduler run")
    record.add_argument("--task", required=True)
    record.add_argument("--ran-at", required=True)
    record.add_argument("--exit", dest="exit_code", required=True, type=int)
    record.add_argument("--outcome", required=True)
    record.add_argument("--status")
    record.add_argument("--runner")
    record.add_argument("--model")
    record.add_argument("--brief-path")
    record.add_argument("--runner-log-path")
    record.set_defaults(func=cmd_record_run)

    sync = sub.add_parser("sync-briefs", help="sync markdown brief frontmatter into SQLite")
    sync.add_argument("--logs-dir", default="logs")
    sync.add_argument("--schedules")
    sync.add_argument("--quiet", action="store_true")
    sync.set_defaults(func=cmd_sync_briefs)

    pending = sub.add_parser("pending-briefs", help="list pending briefs from SQLite")
    pending.add_argument("--reminders-only", action="store_true")
    pending.set_defaults(func=cmd_pending_briefs)

    runs = sub.add_parser("recent-runs", help="list recent scheduler runs from SQLite")
    runs.add_argument("--limit", default=20, type=int)
    runs.set_defaults(func=cmd_recent_runs)

    validations = sub.add_parser("recent-validations", help="list recent validation results from SQLite")
    validations.add_argument("--limit", default=20, type=int)
    validations.set_defaults(func=cmd_recent_validations)

    health = sub.add_parser("health-summary", help="list current component health")
    health.add_argument("--include-ok", action="store_true")
    health.set_defaults(func=cmd_health_summary)

    sync_rec = sub.add_parser("sync-recurring", help="sync .agents/recurring.yaml into SQLite")
    sync_rec.add_argument("--recurring", default=".agents/recurring.yaml")
    sync_rec.add_argument("--today", default=None, help="YYYY-MM-DD override for due calculations")
    sync_rec.add_argument("--quiet", action="store_true")
    sync_rec.set_defaults(func=cmd_sync_recurring)

    complete_rec = sub.add_parser("complete-recurring", help="set last_done for one recurring task and resync SQLite")
    complete_rec.add_argument("--recurring", default=".agents/recurring.yaml")
    complete_rec.add_argument("--name", required=True, help="Exact recurring task name")
    complete_rec.add_argument("--date", required=True, help="Completion date, YYYY-MM-DD")
    complete_rec.add_argument("--today", default=None, help="YYYY-MM-DD override for due calculations")
    complete_rec.set_defaults(func=cmd_complete_recurring)

    status_rec = sub.add_parser("set-recurring-status", help="set status for one recurring task and resync SQLite")
    status_rec.add_argument("--recurring", default=".agents/recurring.yaml")
    status_rec.add_argument("--name", required=True, help="Exact recurring task name")
    status_rec.add_argument("--status", required=True, choices=["active", "paused", "cancelled"])
    status_rec.add_argument("--reason", help="Short reason for non-active status")
    status_rec.add_argument("--deferred-until", help="YYYY-MM-DD date when paused task should resurface")
    status_rec.add_argument("--today", default=None, help="YYYY-MM-DD override for due calculations")
    status_rec.set_defaults(func=cmd_set_recurring_status)

    due_rec = sub.add_parser("due-recurring", help="list due or overdue recurring tasks from SQLite")
    due_rec.add_argument("--include-not-due", action="store_true")
    due_rec.set_defaults(func=cmd_due_recurring)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
