#!/usr/bin/env python3
"""Prune ephemeral run artifacts past their retention window.

The vault accumulates per-run transcripts and runner logs that have no durable
value once they age out: memory-ingest worker logs, statistics runner logs,
scheduler ticks, etc. Nothing pruned them, so logs/ grew to tens of MB. This
sweep enforces per-category retention windows.

Dry-run by default — prints what it WOULD delete and the bytes reclaimed.
Pass --apply to actually delete. Briefs and reviewed human-facing artifacts are
preserved; only raw run logs and transcripts are in scope.

Pure stdlib. Wire into the scheduler (weekly) once you trust the dry-run output.

Usage:
    python3 system/tools/retention_sweep.py            # dry-run report
    python3 system/tools/retention_sweep.py --apply    # actually delete
    python3 system/tools/retention_sweep.py --json
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import re
import time
from datetime import datetime, timezone
from dataclasses import dataclass, field
from pathlib import Path

# Most run artifacts embed their real date in the filename (2026-04-22-...).
# Git operations (checkout, clone) reset mtime to "now", so mtime alone would
# make April logs look fresh. We use the OLDER of (filename date, mtime).
FILENAME_DATE_RE = re.compile(r"(20\d{2})[-_]?(\d{2})[-_]?(\d{2})")

# (glob relative to root, retention_days). Globs match files; matched files
# older than the window are pruned. Keep windows generous — these only remove
# regenerable run artifacts, never source, wiki, outputs, or state.
RULES: list[tuple[str, int]] = [
    ("logs/memory-ingest/*.log", 14),
    ("logs/statistics/*-runner.log", 21),
    ("logs/scheduler/*.log", 45),
    ("logs/reddit/*-runner.log", 30),
    ("logs/dev-tasks/*-runner.log", 30),
    ("logs/learning/*-runner.log", 30),
    ("logs/daily-plans/*-runner.log", 30),
    ("logs/repo-health/*-runner.log", 30),
    ("logs/seo/*-runner.log", 30),
]

# State files that grow unbounded and need consolidation, not blind deletion.
# The sweep only REPORTS these; pruning belongs to the owning workflow
# (learning-review consumes learning-events; ingest compaction keeps a summary).
GROWTH_WATCH = [
    ("state/learning-events.jsonl", 1500, "consume + prune via learning-review"),
    ("state/ingest-manifest.json", 500, "compact: keep last N records + summary"),
]


@dataclass
class CategoryResult:
    pattern: str
    retention_days: int
    matched: int = 0
    expired: int = 0
    bytes_reclaimed: int = 0
    examples: list[str] = field(default_factory=list)


def effective_age_seconds(path: Path, now: float) -> float:
    """Age by the OLDER of filename-embedded date and mtime (git resets mtime)."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return 0.0
    m = FILENAME_DATE_RE.search(path.name)
    if m:
        try:
            dt = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)), tzinfo=timezone.utc)
            name_ts = dt.timestamp()
            return now - min(name_ts, mtime)
        except ValueError:
            pass
    return now - mtime


def human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.0f}TB"


def sweep(root: Path, now: float, apply: bool) -> tuple[list[CategoryResult], list[dict]]:
    results: list[CategoryResult] = []
    for pattern, days in RULES:
        window = days * 86400
        cat = CategoryResult(pattern=pattern, retention_days=days)
        base_dir = root / Path(pattern).parent
        glob_name = Path(pattern).name
        if base_dir.exists():
            for path in sorted(base_dir.iterdir()):
                if not path.is_file() or not fnmatch.fnmatch(path.name, glob_name):
                    continue
                cat.matched += 1
                try:
                    size = path.stat().st_size
                except OSError:
                    continue
                if effective_age_seconds(path, now) > window:
                    cat.expired += 1
                    cat.bytes_reclaimed += size
                    if len(cat.examples) < 3:
                        cat.examples.append(path.relative_to(root).as_posix())
                    if apply:
                        try:
                            path.unlink()
                        except OSError:
                            pass
        results.append(cat)

    watch: list[dict] = []
    for rel, limit, advice in GROWTH_WATCH:
        p = root / rel
        if not p.exists():
            continue
        if rel.endswith(".jsonl"):
            try:
                count = sum(1 for _ in p.open())
            except OSError:
                count = 0
            unit = "lines"
        else:
            try:
                count = len(json.loads(p.read_text()).get("records", []))
            except (OSError, json.JSONDecodeError, AttributeError):
                count = 0
            unit = "records"
        watch.append({
            "path": rel, "count": count, "limit": limit, "unit": unit,
            "over_limit": count > limit, "advice": advice,
            "bytes": p.stat().st_size,
        })
    return results, watch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--apply", action="store_true", help="actually delete (default: dry-run)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    now = time.time()
    results, watch = sweep(root, now, args.apply)
    total_files = sum(c.expired for c in results)
    total_bytes = sum(c.bytes_reclaimed for c in results)

    if args.json:
        print(json.dumps({
            "applied": args.apply,
            "total_files": total_files,
            "total_bytes": total_bytes,
            "categories": [c.__dict__ for c in results],
            "growth_watch": watch,
        }, indent=2))
        return 0

    mode = "APPLIED" if args.apply else "DRY-RUN (use --apply to delete)"
    print(f"# Retention sweep — {mode}\n")
    print(f"Reclaimable: {total_files} files, {human(total_bytes)}\n")
    for c in results:
        if c.expired:
            ex = f"  e.g. {c.examples[0]}" if c.examples else ""
            print(f"- {c.pattern}  (>{c.retention_days}d): {c.expired}/{c.matched} expired, {human(c.bytes_reclaimed)}{ex}")
        else:
            print(f"- {c.pattern}  (>{c.retention_days}d): nothing expired ({c.matched} kept)")
    if watch:
        print("\n## Growth watch (consolidate, do not blind-delete)")
        for w in watch:
            flag = "⚠ OVER" if w["over_limit"] else "ok"
            print(f"- [{flag}] {w['path']}: {w['count']} {w['unit']} (limit {w['limit']}, {human(w['bytes'])}) — {w['advice']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
