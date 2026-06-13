#!/usr/bin/env python3
"""Stamp and report `review_by` freshness dates on wiki pages.

The repo_audit lifecycle guardrail flags wiki pages past their `review_by` date
(or, absent one, older than a blunt fallback window). For that to be useful,
pages need review_by dates that reflect how fast their content goes stale. This
tool stamps them with per-directory volatility windows, computed from each
page's `updated_at` (falling back to file mtime).

High-churn areas (context, themes — priorities and learnings that move weekly)
get short windows; baselines and founder/payment context get long ones.

Idempotent: by default only stamps pages missing review_by. Use --refresh to
recompute all (e.g. after changing windows). Dry-run by default; --apply writes.

Usage:
    python3 system/tools/wiki_freshness.py            # report what's stale / unstamped
    python3 system/tools/wiki_freshness.py --apply    # stamp missing review_by
    python3 system/tools/wiki_freshness.py --apply --refresh
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

# (path prefix relative to wiki/, review window in days). First match wins;
# more specific prefixes must come first. Default applies if nothing matches.
WINDOWS: list[tuple[str, int]] = [
    ("evidence/context/", 45),
    ("themes/", 45),
    ("open-questions/", 30),
    ("evidence/baselines/", 180),
    ("evidence/references/", 180),
    ("sources/", 120),
    ("areas/", 90),
    ("entities/", 90),
    ("evidence/", 90),
]
DEFAULT_WINDOW = 90
# A freshly-stamped review_by should never land in the past (that would flag a
# page as overdue the instant we stamp it). Give at least this much runway.
MIN_GRACE_DAYS = 21
SKIP_NAMES = {"README.md", "index.md", "log.md", "start-here.md"}

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def window_for(rel: str) -> int:
    for prefix, days in WINDOWS:
        if rel.startswith(prefix):
            return days
    return DEFAULT_WINDOW


def parse_frontmatter(text: str) -> tuple[dict, int, int]:
    """Return (fields, fm_start_idx, fm_end_idx) for a leading --- block."""
    if not text.startswith("---\n"):
        return {}, -1, -1
    end = text.find("\n---", 4)
    if end == -1:
        return {}, -1, -1
    block = text[4:end]
    fields = {}
    for line in block.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            fields[k.strip()] = v.strip()
    return fields, 0, end + len("\n---")


def base_date(fields: dict, path: Path) -> datetime:
    raw = fields.get("updated_at", "")
    m = DATE_RE.search(raw)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
        except ValueError:
            pass
    return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--apply", action="store_true", help="write changes (default: dry-run)")
    parser.add_argument("--refresh", action="store_true", help="recompute review_by even if already set")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    wiki = root / "wiki"
    now = datetime.now(timezone.utc)
    stamped, skipped, overdue = [], 0, []

    for path in sorted(wiki.rglob("*.md")):
        if path.name in SKIP_NAMES:
            continue
        rel = path.relative_to(wiki).as_posix()
        text = path.read_text(errors="replace")
        fields, fm_start, fm_end = parse_frontmatter(text)
        if fm_start == -1:
            skipped += 1
            continue
        existing = fields.get("review_by", "")
        if existing and not args.refresh:
            rb = DATE_RE.search(existing)
            if rb:
                d = datetime.strptime(rb.group(1), "%Y-%m-%d").replace(tzinfo=timezone.utc)
                if d < now:
                    overdue.append((rel, rb.group(1)))
            continue
        window = window_for(rel)
        computed = base_date(fields, path) + timedelta(days=window)
        floor = now + timedelta(days=MIN_GRACE_DAYS)
        review_dt = max(computed, floor)
        review_by = review_dt.strftime("%Y-%m-%d")
        stamped.append((rel, review_by, window))
        if args.apply:
            fm = text[: fm_end]
            rest = text[fm_end:]
            if "review_by:" in fm:
                fm = re.sub(r"review_by:.*", f"review_by: {review_by}", fm)
            else:
                # insert before the closing ---
                fm = fm[: -len("\n---")] + f"\nreview_by: {review_by}\n---"
            path.write_text(fm + rest)

    mode = "APPLIED" if args.apply else "DRY-RUN (use --apply)"
    print(f"# Wiki freshness — {mode}\n")
    print(f"Stamped/would-stamp: {len(stamped)} | already-set skipped: depends | no-frontmatter skipped: {skipped}\n")
    for rel, rb, w in stamped:
        print(f"- {rel}: review_by {rb} (+{w}d)")
    if overdue:
        print(f"\n## Overdue (already past review_by) — {len(overdue)}")
        for rel, rb in overdue:
            print(f"- {rel}: review_by {rb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
