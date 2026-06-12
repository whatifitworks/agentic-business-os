#!/usr/bin/env python3
"""Queue and optionally launch one-at-a-time memory inbox ingest workers."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


QUEUE_REL = "state/memory-ingest-queue.json"
INGEST_MANIFEST_REL = "state/ingest-manifest.json"
LOG_DIR_REL = "logs/memory-ingest"
DEFAULT_MODEL = "gpt-5.4-mini"
IGNORED_TOP_LEVEL: set[str] = set()
IGNORED_NAMES = {"README.md", ".gitkeep", ".DS_Store"}
TERMINAL_STATUSES = {"processed", "dropped", "preserved-source-only", "processed-only", "missing"}
WORKER_TIMEOUT_SECONDS = 3600
STALE_RUNNING_SECONDS = 5400
MAX_AUTO_RETRIES = 3


def utcnow() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return fallback
    try:
        data = json.loads(path.read_text())
    except Exception:
        return fallback
    return data if isinstance(data, dict) else fallback


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=False) + "\n")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def queue_path(root: Path) -> Path:
    return root / QUEUE_REL


def load_queue(root: Path) -> dict[str, Any]:
    return read_json(
        queue_path(root),
        {
            "schema_version": 1,
            "updated_at": utcnow(),
            "records": [],
        },
    )


def save_queue(root: Path, queue: dict[str, Any]) -> None:
    queue["schema_version"] = 1
    queue["updated_at"] = utcnow()
    records = queue.get("records", [])
    if not isinstance(records, list):
        queue["records"] = []
    write_json(queue_path(root), queue)


def manifest_paths(root: Path) -> set[str]:
    data = read_json(root / INGEST_MANIFEST_REL, {"records": []})
    out: set[str] = set()
    records = data.get("records", [])
    if not isinstance(records, list):
        return out
    for record in records:
        if not isinstance(record, dict):
            continue
        for key in ("path", "source_path", "destination_path"):
            value = record.get(key)
            if isinstance(value, str):
                out.add(value)
        artifacts = record.get("artifact_paths")
        if isinstance(artifacts, list):
            out.update(value for value in artifacts if isinstance(value, str))
    return out


def eligible_inbox_files(root: Path) -> list[Path]:
    inbox = root / "inbox"
    if not inbox.exists():
        return []
    out: list[Path] = []
    for path in sorted(p for p in inbox.rglob("*") if p.is_file()):
        parts = path.relative_to(inbox).parts
        if not parts:
            continue
        if parts[0] in IGNORED_TOP_LEVEL:
            continue
        if path.name in IGNORED_NAMES or path.name.startswith("."):
            continue
        out.append(path)
    return out


def record_id(rel_path: str) -> str:
    return "inbox-" + hashlib.sha1(rel_path.encode("utf-8")).hexdigest()[:12]


def _running_is_stale(record: dict[str, Any]) -> bool:
    started = record.get("last_started_at")
    if not isinstance(started, str):
        return True
    try:
        started_at = datetime.fromisoformat(started)
    except ValueError:
        return True
    return (datetime.now(timezone.utc) - started_at.astimezone(timezone.utc)).total_seconds() > STALE_RUNNING_SECONDS


def existing_records_by_path(queue: dict[str, Any]) -> dict[str, dict[str, Any]]:
    records = queue.get("records", [])
    if not isinstance(records, list):
        queue["records"] = []
        return {}
    return {
        str(record.get("path")): record
        for record in records
        if isinstance(record, dict) and isinstance(record.get("path"), str)
    }


def scan(root: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    queue = load_queue(root)
    records = queue.setdefault("records", [])
    if not isinstance(records, list):
        records = []
        queue["records"] = records
    by_path = existing_records_by_path(queue)
    already_handled = manifest_paths(root)
    added: list[dict[str, Any]] = []

    for path in eligible_inbox_files(root):
        rel_path = rel(path, root)
        if rel_path in already_handled:
            continue
        existing = by_path.get(rel_path)
        if existing and str(existing.get("status")) in TERMINAL_STATUSES | {"pending", "running", "blocked", "needs-owner", "failed", "needs-review"}:
            continue
        record = {
            "id": record_id(rel_path),
            "path": rel_path,
            "status": "pending",
            "detected_at": utcnow(),
            "size_bytes": path.stat().st_size,
            "sha256": sha256_file(path),
            "attempts": 0,
            "runner": None,
            "model": None,
            "log_path": None,
            "last_started_at": None,
            "last_finished_at": None,
            "outcome": None,
            "note": "Queued by inbox-auto-ingest-trigger.",
        }
        records.append(record)
        by_path[rel_path] = record
        added.append(record)

    current_files = {rel(path, root) for path in eligible_inbox_files(root)}
    for record in records:
        if not isinstance(record, dict):
            continue
        path = record.get("path")
        status = record.get("status")
        if isinstance(path, str) and path not in current_files and status in {"pending", "running", "blocked", "failed", "needs-review"}:
            record["status"] = "missing"
            record["last_finished_at"] = utcnow()
            record["note"] = "Inbox file no longer exists at the queued path."
            continue
        if status == "running" and _running_is_stale(record):
            attempts = int(record.get("attempts") or 0)
            if attempts < MAX_AUTO_RETRIES:
                record["status"] = "pending"
                record["note"] = f"Auto-recovered: worker exceeded {STALE_RUNNING_SECONDS}s without finishing; requeued (attempt {attempts})."
            else:
                record["status"] = "failed"
                record["last_finished_at"] = utcnow()
                record["note"] = f"Auto-recovery gave up after {attempts} stale-running attempts."

    save_queue(root, queue)
    return queue, added


def next_pending(queue: dict[str, Any]) -> dict[str, Any] | None:
    records = queue.get("records", [])
    if not isinstance(records, list):
        return None
    for record in records:
        if isinstance(record, dict) and record.get("status") == "pending":
            return record
    return None


def update_record(root: Path, rel_path: str, **updates: Any) -> dict[str, Any]:
    queue = load_queue(root)
    records = queue.setdefault("records", [])
    if not isinstance(records, list):
        records = []
        queue["records"] = records
    for record in records:
        if isinstance(record, dict) and record.get("path") == rel_path:
            record.update(updates)
            save_queue(root, queue)
            return record
    record = {
        "id": record_id(rel_path),
        "path": rel_path,
        "status": updates.pop("status", "pending"),
        "detected_at": utcnow(),
        **updates,
    }
    records.append(record)
    save_queue(root, queue)
    return record


def build_prompt(rel_path: str) -> str:
    return f"""Use the memory-ingest skill in one-item worker mode.

Process exactly this inbox item and no other inbox files:

`{rel_path}`

Required behavior:
- Read `.agents/skills/knowledge/memory-ingest/SKILL.md`.
- Process only the queued inbox path. The Agentic OS inbox should not contain compatibility shelves.
- If the item is an envelope, inspect the referenced full artifact before deciding.
- Pick exactly one outcome: promote wiki, append evidence, preserve source-only, promote output, process-only, drop, or block/escalate.
- Keep wiki edits short and linked. Do not copy bulky artifacts into wiki pages.
- Do not create a root `processed/` directory. For process-only outcomes, record the manifest decision and remove the inbox copy unless there is a concrete retention reason.
- Update `state/ingest-manifest.json`.
- Update `state/memory-ingest-queue.json` for `{rel_path}` with the final status, outcome, and note. You may use:
  `python3 system/tools/inbox_auto_ingest.py mark --path {rel_path} --status processed --outcome <outcome> --note <summary>`
- Run `python3 system/tools/memory_graph_audit.py --scope root`.
- Run `python3 system/tools/agentic_os_hooks.py --hook all`.

If the item is strategically ambiguous or needs the project owner's judgment, mark it `needs-owner` or `blocked` instead of guessing.
"""


def run_worker(root: Path, rel_path: str, runner: str, model: str, log_path: Path) -> int:
    update_record(
        root,
        rel_path,
        status="running",
        attempts_increment_pending=True,
        runner=runner,
        model=model,
        log_path=rel(log_path, root),
        last_started_at=utcnow(),
        note="Background ingest worker started.",
    )
    queue = load_queue(root)
    for record in queue.get("records", []):
        if isinstance(record, dict) and record.get("path") == rel_path:
            record["attempts"] = int(record.get("attempts") or 0) + 1
            record.pop("attempts_increment_pending", None)
    save_queue(root, queue)

    prompt = build_prompt(rel_path)
    if runner == "codex":
        executable = shutil.which("codex")
        if not executable:
            update_record(root, rel_path, status="failed", last_finished_at=utcnow(), note="codex executable not found.")
            return 127
        command = [
            executable,
            "exec",
            "--cd",
            str(root),
            "--model",
            model,
            "--dangerously-bypass-approvals-and-sandbox",
            prompt,
        ]
    elif runner == "claude":
        executable = shutil.which("claude")
        if not executable:
            update_record(root, rel_path, status="failed", last_finished_at=utcnow(), note="claude executable not found.")
            return 127
        command = [
            executable,
            "-p",
            prompt,
            "--model",
            model,
            "--permission-mode",
            "bypassPermissions",
            "--output-format",
            "text",
        ]
    else:
        update_record(root, rel_path, status="failed", last_finished_at=utcnow(), note=f"Unsupported runner: {runner}")
        return 2

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a") as log:
        log.write(f"[{utcnow()}] START runner={runner} model={model} path={rel_path}\n")
        try:
            proc = subprocess.run(
                command,
                cwd=root,
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                check=False,
                timeout=WORKER_TIMEOUT_SECONDS,
            )
            returncode = proc.returncode
        except subprocess.TimeoutExpired:
            returncode = -1
            log.write(f"[{utcnow()}] TIMEOUT after {WORKER_TIMEOUT_SECONDS}s; worker killed\n")
        log.write(f"[{utcnow()}] END rc={returncode}\n")

    queue = load_queue(root)
    status = None
    for record in queue.get("records", []):
        if isinstance(record, dict) and record.get("path") == rel_path:
            status = record.get("status")
            break
    if returncode != 0:
        update_record(root, rel_path, status="failed", last_finished_at=utcnow(), note=f"Background worker exited {returncode}.")
    elif status == "running":
        update_record(
            root,
            rel_path,
            status="needs-review",
            last_finished_at=utcnow(),
            note="Background worker exited successfully but did not mark a terminal ingest outcome.",
        )
    return returncode


def render_queue(queue: dict[str, Any], added: list[dict[str, Any]] | None = None) -> str:
    records = queue.get("records", [])
    if not isinstance(records, list):
        records = []
    lines = [
        "# Memory Ingest Queue",
        "",
        f"Updated: `{queue.get('updated_at', '')}`",
        f"Records: `{len(records)}`",
    ]
    if added is not None:
        lines.append(f"Added: `{len(added)}`")
    lines.append("")
    for record in records:
        if not isinstance(record, dict):
            continue
        lines.append(f"- `{record.get('status')}` `{record.get('path')}` attempts={record.get('attempts', 0)}")
    if len(lines) == 5:
        lines.append("No queued inbox files.")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root")
    sub = parser.add_subparsers(dest="command", required=True)

    scan_parser = sub.add_parser("scan", help="Detect eligible inbox files and update the queue")
    scan_parser.add_argument("--json", action="store_true", help="Emit JSON")

    status_parser = sub.add_parser("status", help="Print queue status")
    status_parser.add_argument("--json", action="store_true", help="Emit JSON")

    launch_parser = sub.add_parser("launch", help="Launch one pending ingest worker in the background")
    launch_parser.add_argument("--runner", choices=["codex", "claude"], default="codex")
    launch_parser.add_argument("--model", default=DEFAULT_MODEL)
    launch_parser.add_argument("--dry-run", action="store_true", help="Print the worker prompt without launching")
    launch_parser.add_argument(
        "--hook-json",
        action="store_true",
        help="Emit Codex Stop-hook compatible JSON instead of plain text",
    )

    worker_parser = sub.add_parser("worker", help=argparse.SUPPRESS)
    worker_parser.add_argument("--path", required=True)
    worker_parser.add_argument("--runner", choices=["codex", "claude"], required=True)
    worker_parser.add_argument("--model", required=True)
    worker_parser.add_argument("--log-path", required=True)

    mark_parser = sub.add_parser("mark", help="Mark one queue item after ingest")
    mark_parser.add_argument("--path", required=True)
    mark_parser.add_argument("--status", required=True)
    mark_parser.add_argument("--outcome", default=None)
    mark_parser.add_argument("--note", default=None)

    args = parser.parse_args()
    root = Path(args.root).resolve()

    if args.command == "scan":
        queue, added = scan(root)
        if args.json:
            print(json.dumps({"queue": queue, "added": added}, indent=2))
        else:
            print(render_queue(queue, added))
        return 0

    if args.command == "status":
        queue = load_queue(root)
        if args.json:
            print(json.dumps(queue, indent=2))
        else:
            print(render_queue(queue))
        return 0

    if args.command == "launch":
        queue, _ = scan(root)
        record = next_pending(queue)
        if not record:
            if args.hook_json:
                print(json.dumps({"continue": True}))
            else:
                print("No pending inbox items.")
            return 0
        rel_path = str(record["path"])
        if args.dry_run:
            print(build_prompt(rel_path))
            return 0
        timestamp = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d-%H%M%S")
        log_path = root / LOG_DIR_REL / f"{timestamp}-{Path(rel_path).stem}.log"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--root",
            str(root),
            "worker",
            "--path",
            rel_path,
            "--runner",
            args.runner,
            "--model",
            args.model,
            "--log-path",
            str(log_path),
        ]
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a") as log:
            proc = subprocess.Popen(command, cwd=root, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        update_record(
            root,
            rel_path,
            status="running",
            runner=args.runner,
            model=args.model,
            log_path=rel(log_path, root),
            last_started_at=utcnow(),
            note=f"Background worker launched with pid {proc.pid}.",
        )
        if args.hook_json:
            print(
                json.dumps(
                    {
                        "continue": True,
                        "systemMessage": f"Launched memory inbox ingest worker for {rel_path}.",
                    }
                )
            )
        else:
            print(f"LAUNCHED: {rel_path} pid={proc.pid} log={rel(log_path, root)}")
        return 0

    if args.command == "worker":
        return run_worker(root, args.path, args.runner, args.model, Path(args.log_path))

    if args.command == "mark":
        updates: dict[str, Any] = {
            "status": args.status,
            "last_finished_at": utcnow(),
        }
        if args.outcome:
            updates["outcome"] = args.outcome
        if args.note:
            updates["note"] = args.note
        record = update_record(root, args.path, **updates)
        print(json.dumps(record, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
