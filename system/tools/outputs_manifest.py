#!/usr/bin/env python3
"""Keep state/outputs-manifest.json covering every file under outputs/.

The ops_v2 audit flags output files missing from the manifest, but nothing
maintained it, so it sat empty while outputs/ grew to 200+ files. This syncs the
manifest: every current output file gets a record (path, title, bytes, first-seen
date), existing records are preserved (so first_seen and any human-added fields
survive), and records whose file no longer exists are marked status=missing
rather than dropped (audit trail).

Auto-moving superseded reports to archives needs human judgment and is left
manual; this tool only guarantees coverage.

Dry-run by default; --apply writes. Pass --date YYYY-MM-DD for deterministic
first_seen stamps (script clocks are intentionally unavailable in some runners).

Usage:
    python3 system/tools/outputs_manifest.py
    python3 system/tools/outputs_manifest.py --apply --date 2026-06-13
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

MANIFEST_REL = "state/outputs-manifest.json"
SKIP_NAMES = {"README.md", ".gitkeep", ".DS_Store"}
TEXT_SUFFIXES = {".md", ".markdown", ".txt"}
HEADING_RE = re.compile(r"^#\s+(.+)$", re.M)


def title_for(path: Path) -> str:
    if path.suffix.lower() in TEXT_SUFFIXES:
        try:
            m = HEADING_RE.search(path.read_text(errors="replace")[:4000])
            if m:
                return m.group(1).strip()
        except OSError:
            pass
    return path.stem.replace("-", " ").replace("_", " ")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--date", default=None, help="first_seen date for new records (YYYY-MM-DD)")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    manifest_path = root / MANIFEST_REL
    try:
        data = json.loads(manifest_path.read_text())
    except (OSError, json.JSONDecodeError):
        data = {"schema_version": 1, "outputs": []}
    # Preserve existing records IN PLACE (their order may be meaningful and
    # re-sorting creates huge, unreviewable diffs). Only append genuinely new
    # records at the end, and touch existing records minimally.
    records = data.get("outputs") if isinstance(data.get("outputs"), list) else []
    by_path = {r.get("output_path"): r for r in records if isinstance(r, dict)}

    current = set()
    added, updated = [], []
    new_records: list[dict] = []
    for path in sorted((root / "outputs").rglob("*")):
        if not path.is_file() or path.name in SKIP_NAMES:
            continue
        rel = path.relative_to(root).as_posix()
        current.add(rel)
        if rel in by_path:
            continue  # already covered — leave existing record untouched
        new_records.append({
            "output_path": rel,
            "title": title_for(path),
            "bytes": path.stat().st_size,
            "first_seen": args.date or "unknown",
            "status": "present",
        })
        added.append(rel)

    # Mark vanished files as missing (keep the record as an audit trail).
    vanished = [p for p in by_path if p not in current and by_path[p].get("status") != "missing"]
    for p in vanished:
        by_path[p]["status"] = "missing"

    data["outputs"] = records + new_records
    updated = []  # we no longer rewrite existing records

    print(f"outputs manifest sync — added {len(added)}, "
          f"now-missing {len(vanished)}, total {len(data['outputs'])}")
    if added[:10]:
        print("new:")
        for r in added[:10]:
            print(f"  + {r}")
        if len(added) > 10:
            print(f"  …and {len(added) - 10} more")
    if args.apply:
        manifest_path.write_text(json.dumps(data, indent=2) + "\n")
        print(f"wrote {manifest_path.relative_to(root)}")
    else:
        print("(dry-run — use --apply to write)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
