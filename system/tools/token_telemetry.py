#!/usr/bin/env python3
"""Token-spend telemetry for scheduled and ad-hoc runs.

The whole point of this Agentic OS is great answers at the least token cost, but
nothing measured spend. This records per-run token usage to a rolling JSONL and
reports spend by task/skill/week so friday-wrap and repo-health can surface
where the budget actually goes — and whether the lifecycle/sidecar work moved it.

Capture is best-effort and graceful: `codex exec` prints a `tokens used\\n<N>`
footer, and `claude -p --output-format json` emits a usage object; parse-log
extracts whichever is present and records nothing if neither is found.

Subcommands:
    record    --task NAME [--skill S] [--runner R] --total N [--input N --output N]
    parse-log --task NAME [--skill S] [--runner R] --runner-log PATH
    report    [--weeks N] [--json]

Events: state/metrics/token-usage.jsonl
Pure stdlib.
"""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

EVENTS_REL = "state/metrics/token-usage.jsonl"

# codex exec footer:  "tokens used\n123,456"
CODEX_RE = re.compile(r"tokens used\s*\n\s*([\d,]+)", re.IGNORECASE)


def utcnow() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def events_path(root: Path) -> Path:
    return root / EVENTS_REL


def append_event(root: Path, event: dict) -> None:
    p = events_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a") as f:
        f.write(json.dumps(event) + "\n")


def parse_runner_log(text: str) -> dict | None:
    """Extract token usage from a runner log. Returns {total[,input,output]} or None."""
    m = CODEX_RE.search(text)
    if m:
        return {"total": int(m.group(1).replace(",", "")), "source": "codex"}
    # claude --output-format json emits a usage object; scan for the last one.
    best = None
    for jm in re.finditer(r'"usage"\s*:\s*\{[^}]*\}', text):
        block = jm.group(0)
        inp = re.search(r'"input_tokens"\s*:\s*(\d+)', block)
        out = re.search(r'"output_tokens"\s*:\s*(\d+)', block)
        if inp or out:
            i = int(inp.group(1)) if inp else 0
            o = int(out.group(1)) if out else 0
            best = {"total": i + o, "input": i, "output": o, "source": "claude"}
    return best


def iso_week(ts: str) -> str:
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return "unknown"
    y, w, _ = dt.isocalendar()
    return f"{y}-W{w:02d}"


def load_events(root: Path) -> list[dict]:
    p = events_path(root)
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def cmd_record(root: Path, args) -> int:
    if args.total is None and args.input is None and args.output is None:
        print("record: provide --total or --input/--output")
        return 2
    total = args.total if args.total is not None else (args.input or 0) + (args.output or 0)
    event = {
        "ts": utcnow(), "task": args.task, "skill": args.skill,
        "runner": args.runner, "total": total,
    }
    if args.input is not None:
        event["input"] = args.input
    if args.output is not None:
        event["output"] = args.output
    append_event(root, event)
    print(f"recorded {total} tokens for {args.task}")
    return 0


def cmd_parse_log(root: Path, args) -> int:
    path = Path(args.runner_log)
    if not path.is_absolute():
        path = root / path
    if not path.exists():
        print(f"parse-log: {path} not found")
        return 0  # graceful — scheduler should never fail on telemetry
    usage = parse_runner_log(path.read_text(errors="replace"))
    if not usage:
        print("parse-log: no token usage found (nothing recorded)")
        return 0
    event = {
        "ts": utcnow(), "task": args.task, "skill": args.skill,
        "runner": args.runner, **usage,
    }
    append_event(root, event)
    print(f"recorded {usage['total']} tokens ({usage['source']}) for {args.task}")
    return 0


def cmd_report(root: Path, args) -> int:
    events = load_events(root)
    if not events:
        print("No token-usage events recorded yet.")
        return 0
    # filter to recent weeks
    weeks_sorted = sorted({iso_week(e["ts"]) for e in events})
    keep = set(weeks_sorted[-args.weeks:]) if args.weeks else set(weeks_sorted)
    events = [e for e in events if iso_week(e["ts"]) in keep]

    by_skill: dict[str, int] = defaultdict(int)
    by_week: dict[str, int] = defaultdict(int)
    by_task: dict[str, int] = defaultdict(int)
    for e in events:
        t = int(e.get("total", 0))
        by_skill[e.get("skill") or e.get("task") or "?"] += t
        by_week[iso_week(e["ts"])] += t
        by_task[e.get("task") or "?"] += t
    total = sum(by_week.values())

    if args.json:
        print(json.dumps({
            "total": total, "events": len(events),
            "by_week": dict(sorted(by_week.items())),
            "by_skill": dict(sorted(by_skill.items(), key=lambda x: -x[1])),
            "by_task": dict(sorted(by_task.items(), key=lambda x: -x[1])),
        }, indent=2))
        return 0

    print(f"# Token spend — {len(events)} runs, {total:,} tokens total\n")
    print("## By week")
    for w in sorted(by_week):
        print(f"- {w}: {by_week[w]:,}")
    print("\n## By skill (top spenders)")
    for skill, t in sorted(by_skill.items(), key=lambda x: -x[1])[:12]:
        print(f"- {skill}: {t:,}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    sub = parser.add_subparsers(dest="command", required=True)

    r = sub.add_parser("record")
    r.add_argument("--task", required=True)
    r.add_argument("--skill", default=None)
    r.add_argument("--runner", default=None)
    r.add_argument("--total", type=int, default=None)
    r.add_argument("--input", type=int, default=None)
    r.add_argument("--output", type=int, default=None)

    p = sub.add_parser("parse-log")
    p.add_argument("--task", required=True)
    p.add_argument("--skill", default=None)
    p.add_argument("--runner", default=None)
    p.add_argument("--runner-log", required=True)

    rep = sub.add_parser("report")
    rep.add_argument("--weeks", type=int, default=8)
    rep.add_argument("--json", action="store_true")

    args = parser.parse_args()
    root = Path(args.root).resolve()
    if args.command == "record":
        return cmd_record(root, args)
    if args.command == "parse-log":
        return cmd_parse_log(root, args)
    if args.command == "report":
        return cmd_report(root, args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
