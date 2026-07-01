#!/usr/bin/env python3
"""Append-only, hash-chained business ledger.

Every consequential agent or owner event — a decision, an external action, an
outcome, a piece of evidence, an approval-boundary evaluation — can be recorded
as one JSONL entry in state/ledger.jsonl. Each entry carries the sha256 of the
previous entry, so the history is tamper-evident: editing or deleting a past
entry breaks the chain and `verify` reports exactly where.

The ledger is the machine-readable spine behind "why did we do X?". Human
narrative stays in decisions/log.md (see decisions_index.py); ledger entries
reference those lines and the evidence files under sources/ or outputs/.

Pure stdlib. Append never rewrites existing lines.

Usage:
    python3 system/tools/ledger.py append --kind decision --actor human:owner \
        --summary "Dropped supplier X over lead times" --ref decisions/log.md
    python3 system/tools/ledger.py verify
    python3 system/tools/ledger.py query --kind boundary_evaluation --limit 20
    python3 system/tools/ledger.py show
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

LEDGER_REL = "state/ledger.jsonl"
GENESIS = "genesis"
KINDS = {"decision", "action", "outcome", "evidence", "boundary_evaluation", "note"}


def ledger_path(root: Path) -> Path:
    return root / LEDGER_REL


def canonical(entry: dict) -> str:
    body = {k: v for k, v in entry.items() if k != "hash"}
    return json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def entry_hash(entry: dict) -> str:
    return hashlib.sha256(canonical(entry).encode("utf-8")).hexdigest()


def read_entries(path: Path) -> list[tuple[int, dict]]:
    """Return (line_number, entry) pairs, skipping blank lines."""
    if not path.exists():
        return []
    out: list[tuple[int, dict]] = []
    for n, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            out.append((n, {"_corrupt": line[:120]}))
            continue
        if isinstance(data, dict):
            out.append((n, data))
    return out


def last_hash(entries: list[tuple[int, dict]]) -> str:
    for _, entry in reversed(entries):
        if "hash" in entry:
            return str(entry["hash"])
    return GENESIS


def append_entry(root: Path, kind: str, summary: str, actor: str,
                 refs: list[str], data: dict | None) -> dict:
    path = ledger_path(root)
    entries = read_entries(path)
    entry = {
        "id": f"led-{len(entries) + 1:06d}",
        "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "actor": actor,
        "kind": kind,
        "summary": summary.strip(),
        "refs": refs,
        "prev_hash": last_hash(entries),
    }
    if data:
        entry["data"] = data
    entry["hash"] = entry_hash(entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")
    return entry


def verify_chain(entries: list[tuple[int, dict]]) -> list[str]:
    problems: list[str] = []
    prev = GENESIS
    for n, entry in entries:
        if "_corrupt" in entry:
            problems.append(f"line {n}: not valid JSON: {entry['_corrupt']}")
            continue
        if entry.get("prev_hash") != prev:
            problems.append(
                f"line {n} ({entry.get('id', '?')}): prev_hash mismatch — chain broken here")
        recomputed = entry_hash(entry)
        if entry.get("hash") != recomputed:
            problems.append(
                f"line {n} ({entry.get('id', '?')}): hash mismatch — entry was altered")
        prev = str(entry.get("hash", prev))
    return problems


def matches(entry: dict, args: argparse.Namespace) -> bool:
    if args.kind and entry.get("kind") != args.kind:
        return False
    if args.ref and args.ref not in [str(r) for r in entry.get("refs", [])]:
        return False
    if args.contains:
        blob = json.dumps(entry, ensure_ascii=False).lower()
        if args.contains.lower() not in blob:
            return False
    if args.since:
        if str(entry.get("ts", "")) < args.since:
            return False
    return True


def render_line(entry: dict) -> str:
    refs = f" refs={','.join(str(r) for r in entry.get('refs', []))}" if entry.get("refs") else ""
    return (f"[{entry.get('ts', '?')}] {entry.get('id', '?')} {entry.get('kind', '?')}"
            f" ({entry.get('actor', '?')}): {entry.get('summary', '')}{refs}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    p_append = sub.add_parser("append", help="Append one entry to the chain")
    p_append.add_argument("--kind", required=True, choices=sorted(KINDS))
    p_append.add_argument("--summary", required=True)
    p_append.add_argument("--actor", default="agent:unspecified",
                          help="e.g. human:owner, agent:claude, hook:approval-gate")
    p_append.add_argument("--ref", action="append", default=[],
                          help="Repo-relative evidence/decision path; repeatable")
    p_append.add_argument("--data-json", default="",
                          help="Optional JSON object with structured detail")
    p_append.add_argument("--quiet", action="store_true")

    p_verify = sub.add_parser("verify", help="Verify the hash chain end to end")
    p_verify.add_argument("--exit-zero", action="store_true")

    p_query = sub.add_parser("query", help="Filter entries")
    for p in (p_query,):
        p.add_argument("--kind", choices=sorted(KINDS))
        p.add_argument("--ref")
        p.add_argument("--contains")
        p.add_argument("--since", help="ISO date lower bound, e.g. 2026-07-01")
        p.add_argument("--limit", type=int, default=50)
        p.add_argument("--json", action="store_true")

    p_show = sub.add_parser("show", help="Show the newest entries")
    p_show.add_argument("--limit", type=int, default=10)

    args = parser.parse_args()
    root = Path(args.root).resolve()
    entries = read_entries(ledger_path(root))

    if args.command == "append":
        data = None
        if args.data_json:
            data = json.loads(args.data_json)
            if not isinstance(data, dict):
                parser.error("--data-json must be a JSON object")
        entry = append_entry(root, args.kind, args.summary, args.actor, args.ref, data)
        if not args.quiet:
            print(entry["id"])
        return 0

    if args.command == "verify":
        problems = verify_chain(entries)
        if problems:
            print(f"Ledger verify: FAIL ({len(problems)} problem(s))")
            for p in problems:
                print(f"  - {p}")
        else:
            print(f"Ledger verify: PASS ({len(entries)} entries, chain intact)")
        return 0 if (args.exit_zero or not problems) else 1

    if args.command == "query":
        hits = [e for _, e in entries if "_corrupt" not in e and matches(e, args)]
        hits = hits[-args.limit:]
        if args.json:
            print(json.dumps(hits, indent=2, ensure_ascii=False))
        else:
            for e in hits:
                print(render_line(e))
            if not hits:
                print("No matching entries.")
        return 0

    if args.command == "show":
        for _, e in entries[-args.limit:]:
            if "_corrupt" not in e:
                print(render_line(e))
        if not entries:
            print("Ledger is empty.")
        return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
