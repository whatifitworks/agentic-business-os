#!/usr/bin/env python3
"""Record structured learning events from Agentic Business OS work sessions."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\s*([:=])\s*[^,\s;]+"), r"\1\2<redacted>"),
    (re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"), r"\1<redacted>"),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "<redacted-openai-key>"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"), "<redacted-slack-token>"),
    (re.compile(r"https://[^@\s]+:[^@\s]+@"), "https://<redacted>@"),
]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug[:80] or "learning-event"


def redact_text(value: str) -> str:
    redacted = value
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact(item) for key, item in value.items()}
    return value


def split_values(values: list[str] | None) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    for value in values:
        out.extend(part.strip() for part in value.split(",") if part.strip())
    return out


def normalize_for_fingerprint(value: Any) -> str:
    text = " ".join(str(item) for item in value) if isinstance(value, list) else str(value or "")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def event_fingerprint(event: dict[str, Any]) -> str:
    parts = [
        normalize_for_fingerprint(event.get("event_type")),
        normalize_for_fingerprint(event.get("skill") or event.get("workflow")),
        normalize_for_fingerprint(event.get("summary")),
        normalize_for_fingerprint(event.get("friction")),
        normalize_for_fingerprint(event.get("manual_steps")),
        normalize_for_fingerprint(event.get("automation_candidates")),
    ]
    base = "|".join(part for part in parts if part)
    return hashlib.sha256(base.encode("utf-8", errors="replace")).hexdigest()[:16]


def record_event(root: Path, event: dict[str, Any]) -> Path:
    root = root.resolve()
    now = datetime.now(timezone.utc).astimezone()
    stamp = now.strftime("%Y%m%dT%H%M%S%z")
    event = redact(event)
    event["schema_version"] = 1
    event["fingerprint"] = event.get("fingerprint") or event_fingerprint(event)
    event["id"] = event.get("id") or f"{stamp}-{slugify(str(event.get('summary') or event.get('event_type') or 'event'))}"
    event["created_at"] = now.isoformat(timespec="seconds")
    event["date"] = now.date().isoformat()

    state_path = root / "state" / "learning-events.jsonl"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    with state_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event, ensure_ascii=False, sort_keys=True) + "\n")
    return state_path


def write_memory_candidate(
    root: Path,
    title: str,
    summary: str,
    why: str,
    source: str,
    tags: list[str] | None = None,
    related: list[str] | None = None,
) -> Path:
    root = root.resolve()
    now = datetime.now(timezone.utc).astimezone()
    stamp = now.strftime("%Y%m%dT%H%M%S%z")
    safe_title = redact_text(title.strip())
    safe_summary = redact_text(summary.strip())
    safe_why = redact_text(why.strip())
    safe_source = redact_text(source.strip())
    safe_tags = [redact_text(item) for item in (tags or []) if item]
    safe_related = [redact_text(item) for item in (related or []) if item]

    slug = slugify(safe_title)
    path = root / "inbox" / f"{stamp}-{slug}.md"
    frontmatter = {
        "title": safe_title,
        "type": "memory-candidate",
        "source": safe_source or "assistant",
        "created_at": now.isoformat(timespec="seconds"),
        "tags": safe_tags,
        "related": safe_related,
        "ingest_status": "pending",
    }
    lines = ["---"]
    for key, value in frontmatter.items():
        if isinstance(value, list):
            if value:
                lines.append(f"{key}:")
                for item in value:
                    lines.append(f"  - {item}")
            else:
                lines.append(f"{key}: []")
        else:
            lines.append(f"{key}: {value}")
    lines.extend(
        [
            "---",
            "",
            f"# {safe_title}",
            "",
            "## Summary",
            "",
            safe_summary,
            "",
            "## Why It Matters",
            "",
            safe_why,
            "",
            "## Ingest Guidance",
            "",
            "Memory-ingest should dedupe, merge, promote, record process-only, or drop this candidate.",
            "",
        ]
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def command_record(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    event = {
        "event_type": args.event_type,
        "summary": args.summary,
        "skill": args.skill,
        "workflow": args.workflow,
        "status": args.status,
        "importance": args.importance,
        "source": args.source,
        "files_read": split_values(args.file_read),
        "files_written": split_values(args.file_written),
        "tools": split_values(args.tool),
        "manual_steps": split_values(args.manual_step),
        "friction": split_values(args.friction),
        "automation_candidates": split_values(args.automation_candidate),
        "follow_up": args.follow_up,
        "memory_candidate": bool(args.memory_candidate),
    }
    state_path = record_event(root, event)
    print(json.dumps({
        "state_path": state_path.relative_to(root).as_posix(),
        "event": event,
    }, indent=2, ensure_ascii=False))
    return 0


def command_tail(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = root / "state" / "learning-events.jsonl"
    if not path.exists():
        print("[]")
        return 0
    rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    print(json.dumps(rows[-args.limit:], indent=2, ensure_ascii=False))
    return 0


def command_memory_candidate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = write_memory_candidate(
        root=root,
        title=args.title,
        summary=args.summary,
        why=args.why,
        source=args.source,
        tags=split_values(args.tag),
        related=split_values(args.related),
    )
    print(json.dumps({"path": path.relative_to(root).as_posix()}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    record = sub.add_parser("record", help="Record one structured learning event")
    record.add_argument("--root", default=".")
    record.add_argument("--event-type", required=True, choices=[
        "session",
        "skill-run",
        "manual-work",
        "correction",
        "blocker",
        "automation-candidate",
        "decision",
        "learning",
    ])
    record.add_argument("--summary", required=True)
    record.add_argument("--skill")
    record.add_argument("--workflow")
    record.add_argument("--status", default="observed")
    record.add_argument("--importance", default="medium", choices=["low", "medium", "high"])
    record.add_argument("--source", default="manual")
    record.add_argument("--file-read", action="append")
    record.add_argument("--file-written", action="append")
    record.add_argument("--tool", action="append")
    record.add_argument("--manual-step", action="append")
    record.add_argument("--friction", action="append")
    record.add_argument("--automation-candidate", action="append")
    record.add_argument("--follow-up")
    record.add_argument("--memory-candidate", action="store_true")
    record.set_defaults(func=command_record)

    tail = sub.add_parser("tail", help="Print recent learning events")
    tail.add_argument("--root", default=".")
    tail.add_argument("--limit", type=int, default=20)
    tail.set_defaults(func=command_tail)

    memory = sub.add_parser("memory-candidate", help="Write a redacted memory candidate to inbox/")
    memory.add_argument("--root", default=".")
    memory.add_argument("--title", required=True)
    memory.add_argument("--summary", required=True)
    memory.add_argument("--why", required=True)
    memory.add_argument("--source", default="assistant")
    memory.add_argument("--tag", action="append")
    memory.add_argument("--related", action="append")
    memory.set_defaults(func=command_memory_candidate)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
