#!/usr/bin/env python3
"""Consolidation "sleep cycle" for learning-events — distill, then archive.

Biological memory consolidates: it does not keep every raw episode hot forever.
state/learning-events.jsonl grows ~25 events/day and learning-review re-reads
ALL of them every run, so old, already-consumed events keep paying a cost. This
sweep distills aged/consumed events into a compact digest and moves them out of
the active file into an archive (never deletes) so the active working set stays
small and learning-review focuses on fresh, actionable signal.

What it does NOT do: it never rewrites rules, skills, or wiki pages. Turning
learnings into rule/skill changes stays suggest-only via learning-review; this
only manages the lifecycle of the event log itself.

Archive criteria (an event is consolidated out of the active log if):
  - its date is older than --window days (default 45), OR
  - it carries a terminal status (resolved/fixed/implemented/closed/applied/
    completed/done/patched/dismissed/no-send).
High-importance unresolved events are kept active regardless of age so they are
not quietly buried.

Dry-run by default; --apply writes. Pass --date YYYY-MM-DD for a deterministic
"now" (script clocks are intentionally unavailable in some runners).

Files:
  active:  state/learning-events.jsonl
  archive: state/learning-events-archive.jsonl   (append-only)
  digest:  logs/learning/consolidation-<date>.md  (when --apply)

Usage:
    python3 system/tools/consolidation_sweep.py --date 2026-06-13
    python3 system/tools/consolidation_sweep.py --apply --date 2026-06-13
"""

from __future__ import annotations

import argparse
import collections
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

ACTIVE = "state/learning-events.jsonl"
ARCHIVE = "state/learning-events-archive.jsonl"
DEFAULT_WINDOW = 45
TERMINAL_STATUSES = {
    "resolved", "fixed", "implemented", "closed", "applied", "completed",
    "done", "patched", "dismissed", "no-send", "fixed-contract", "build-succeeded",
}


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def event_date(e: dict) -> str:
    return str(e.get("date") or e.get("created_at") or "")[:10]


def should_archive(e: dict, cutoff: str) -> bool:
    status = str(e.get("status") or "").lower()
    importance = str(e.get("importance") or "").lower()
    d = event_date(e)
    # Never bury a high-importance event that has not reached a terminal status.
    if importance == "high" and status not in TERMINAL_STATUSES:
        return False
    if status in TERMINAL_STATUSES:
        return True
    return bool(d) and d < cutoff


def build_digest(archived: list[dict], cutoff: str, now: str) -> str:
    by_type = collections.Counter(e.get("event_type") for e in archived)
    by_skill = collections.Counter(e.get("skill") or "(none)" for e in archived)
    by_status = collections.Counter(str(e.get("status") or "observed") for e in archived)
    # Surface recurring friction themes (first friction line, trimmed).
    frictions = collections.Counter()
    for e in archived:
        for f in (e.get("friction") or [])[:1]:
            key = str(f).strip().split(".")[0][:80]
            if key:
                frictions[key] += 1

    lines = [
        f"# Learning-events consolidation — {now}",
        "",
        f"Archived {len(archived)} events (older than {cutoff} or terminal status) "
        f"from `state/learning-events.jsonl` into `state/learning-events-archive.jsonl`.",
        "",
        "## By type",
    ]
    lines += [f"- {t or '(none)'}: {n}" for t, n in by_type.most_common()]
    lines += ["", "## By status"]
    lines += [f"- {s}: {n}" for s, n in by_status.most_common()]
    lines += ["", "## By skill (top 10)"]
    lines += [f"- {s}: {n}" for s, n in by_skill.most_common(10)]
    if frictions:
        lines += ["", "## Recurring friction themes (top 10)"]
        lines += [f"- ({n}×) {k}" for k, n in frictions.most_common(10)]
    lines += ["", "_Archived events are preserved in the archive file; nothing is deleted. "
              "Turning these into rule/skill changes remains learning-review's job._"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--window", type=int, default=DEFAULT_WINDOW)
    parser.add_argument("--date", default=None, help="treat this YYYY-MM-DD as 'now'")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if args.date:
        now_dt = datetime.strptime(args.date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    else:
        now_dt = datetime.now(timezone.utc)
    now = now_dt.strftime("%Y-%m-%d")
    cutoff = (now_dt - timedelta(days=args.window)).strftime("%Y-%m-%d")

    events = read_jsonl(root / ACTIVE)
    if not events:
        print("No learning events to consolidate.")
        return 0

    archived = [e for e in events if should_archive(e, cutoff)]
    kept = [e for e in events if not should_archive(e, cutoff)]

    print(f"learning-events consolidation — {'APPLIED' if args.apply else 'DRY-RUN'}")
    print(f"total {len(events)} | archive {len(archived)} | keep active {len(kept)} "
          f"(window {args.window}d, cutoff {cutoff})\n")
    by_type = collections.Counter(e.get("event_type") for e in archived)
    for t, n in by_type.most_common():
        print(f"  archive {t or '(none)'}: {n}")
    high_kept = sum(1 for e in kept if str(e.get("importance")).lower() == "high")
    print(f"\n  kept-active high-importance (protected from archival): {high_kept}")

    if not archived:
        print("\nNothing to archive.")
        return 0

    if args.apply:
        archive_path = root / ARCHIVE
        with archive_path.open("a") as f:
            for e in archived:
                f.write(json.dumps(e) + "\n")
        with (root / ACTIVE).open("w") as f:
            for e in kept:
                f.write(json.dumps(e) + "\n")
        digest_path = root / "logs" / "learning" / f"consolidation-{now}.md"
        digest_path.parent.mkdir(parents=True, exist_ok=True)
        digest_path.write_text(build_digest(archived, cutoff, now))
        print(f"\nArchived to {ARCHIVE}; active log now {len(kept)} events; "
              f"digest at {digest_path.relative_to(root)}")
    else:
        print("\n(dry-run — use --apply to archive + write digest)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
