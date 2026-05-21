#!/usr/bin/env python3
"""Review recent work logs and produce Agentic Business OS improvement suggestions."""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def read_frontmatter(path: Path) -> dict[str, str]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    out: dict[str, str] = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out


def recent_learning_events(root: Path, days: int, now: datetime) -> list[dict[str, Any]]:
    cutoff = now - timedelta(days=days)
    rows = []
    for event in read_jsonl(root / "state" / "learning-events.jsonl"):
        created = parse_dt(str(event.get("created_at") or ""))
        if created is None or created >= cutoff:
            rows.append(event)
    return rows


def recent_problem_briefs(root: Path, days: int, now: datetime) -> list[dict[str, Any]]:
    cutoff = now - timedelta(days=days)
    out: list[dict[str, Any]] = []
    logs = root / "logs"
    if not logs.exists():
        return out
    for path in sorted(logs.glob("*/*-brief.md")):
        if path.parts[-2] == "learning":
            continue
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).astimezone()
        except OSError:
            continue
        if modified < cutoff:
            continue
        fm = read_frontmatter(path)
        status = fm.get("status", "")
        if status in {"blocked", "failed", "pending"}:
            out.append({
                "path": path.relative_to(root).as_posix(),
                "status": status,
                "task": fm.get("task") or path.parent.name,
                "generated_at": fm.get("generated_at"),
            })
    return out


def candidate_fingerprint(candidate: dict[str, Any]) -> str:
    text = "|".join(str(candidate.get(key) or "").lower() for key in ["kind", "owner", "title"])
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def group_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        key = str(candidate.get("fingerprint") or candidate_fingerprint(candidate))
        current = grouped.get(key)
        if current is None:
            current = dict(candidate)
            current["occurrence_count"] = 1
            grouped[key] = current
            continue
        current["occurrence_count"] = int(current.get("occurrence_count") or 1) + 1
        reason = str(current.get("reason") or "")
        new_reason = str(candidate.get("reason") or "")
        if new_reason and new_reason not in reason:
            current["reason"] = f"{reason}; {new_reason}" if reason else new_reason
    out = list(grouped.values())
    out.sort(key=lambda item: int(item.get("occurrence_count") or 1), reverse=True)
    return out


def event_text(event: dict[str, Any]) -> str:
    parts = [str(event.get("summary") or "")]
    friction = event.get("friction") if isinstance(event.get("friction"), list) else []
    parts.extend(str(item) for item in friction)
    return " ".join(parts)


def learning_topic_tags(text: str) -> set[str]:
    lowered = text.lower()
    tags: set[str] = set()
    if any(term in lowered for term in ["raw-chat", "raw chat", "sent messages", "user messages", "visible user"]):
        tags.add("raw-chat-visible-user")
    if any(term in lowered for term in ["one file", "1 file", "per thread", "one thread", "manual-parse", "hook-runs", "per-turn", "digest-suffixed", "duplicate per-turn"]):
        tags.add("raw-chat-thread-files")
    if any(term in lowered for term in ["stop hook", "hook json", "invalid stop hook json", '{"continue": true}', "continue true"]):
        tags.add("codex-stop-hook-json")
    if any(term in lowered for term in ["candidate quality", "too noisy", "noisy", "grouping", "learn selectively"]):
        tags.add("learning-quality")
    if any(term in lowered for term in ["system itself", "self-improving", "self improving", "business topics", "domain memory", "actual business", "other parts of the system"]):
        tags.add("learning-scope")
    if any(term in lowered for term in ["skill improvement", "improve skills", "skills themselves", "skill-improvement-loop"]):
        tags.add("skill-improvement-scope")
    if any(term in lowered for term in ["file structure", "folder structure", "important files", "needs to be loaded", "need to be loaded", "memory or file"]):
        tags.add("structure-context-scope")
    return tags


SYSTEM_INTERACTION_RE = re.compile(
    r"\b(agentic os|business os|codex|claude|llm|agent|sub-agent|skill|hook|scheduler|schedule|"
    r"memory|inbox|wiki|raw-chat|raw chat|learning|daily-planning|weekly-review|recurring-review|"
    r"adapter|browser use|computer use|mcp|tool|workflow|prompt|eval|test|context|output|"
    r"file structure|folder structure|project structure|entrypoint|agents\.md|claude\.md|00-start-here|"
    r"index|indexes|domain|domains|sources|state|logs|orphan|graph|loaded|read|"
    r"manual|repeated|automate|automation|confusing|frustrated|annoying|misusing|expected|"
    r"happy with|great|beautiful|perfect|works well|useful)\b",
    re.I,
)

POSITIVE_SIGNAL_RE = re.compile(r"\b(great|beautiful|perfect|works well|working well|happy with|love this|useful|good flow)\b", re.I)
FRICTION_SIGNAL_RE = re.compile(
    r"\b(frustrated|annoying|confusing|wrong|doesn'?t work|didn'?t work|not working|not as expected|"
    r"don'?t see|can'?t see|missing|why did|why hasn'?t|shouldn'?t|too noisy|messy|hard to use)\b",
    re.I,
)
EXPECTATION_SIGNAL_RE = re.compile(r"\b(should|shouldn'?t|expected|why did|why hasn'?t|misusing|using .* differently)\b", re.I)
AUTOMATION_SIGNAL_RE = re.compile(r"\b(manual|again|duplicate|repeat|repeated|same thing|automate|automation)\b", re.I)


def is_system_interaction_event(event: dict[str, Any]) -> bool:
    if str(event.get("source") or "") != "raw-chat-parser":
        return True
    return bool(SYSTEM_INTERACTION_RE.search(event_text(event)))


def candidate_kind_for_event(event: dict[str, Any]) -> str:
    event_type = str(event.get("event_type") or "")
    text = event_text(event)
    if AUTOMATION_SIGNAL_RE.search(text) or event_type in {"manual-work", "automation-candidate"}:
        return "manual-work-automation"
    if FRICTION_SIGNAL_RE.search(text) or event_type in {"correction", "blocker"}:
        return "system-friction"
    if re.search(r"\b(memory|inbox|wiki|file structure|folder structure|project structure|index|indexes|entrypoint|loaded|read|context|graph|orphan)\b", text, re.I):
        return "os-structure-or-context-improvement"
    if EXPECTATION_SIGNAL_RE.search(text):
        return "system-expectation-gap"
    if POSITIVE_SIGNAL_RE.search(text):
        return "successful-pattern-to-preserve"
    return "system-learning"


def suggested_action_for_kind(kind: str) -> str:
    if kind == "successful-pattern-to-preserve":
        return "Keep this behavior; if it repeats, codify it in the relevant skill, hook, eval, or docs."
    if kind == "manual-work-automation":
        return "Consider a skill, hook, adapter, scheduler task, or script that removes the repeated manual step."
    if kind == "os-structure-or-context-improvement":
        return "Update boot docs, indexes, memory structure, audits, or context-loading rules so future agents load and place artifacts correctly."
    if kind == "system-expectation-gap":
        return "Clarify the contract in the relevant skill/docs/eval, or adjust the workflow to match the project owner's expectation."
    if kind == "system-friction":
        return "Run skill-improvement-loop or create a focused system patch with eval coverage."
    return "Review whether this should change a skill, hook, agent, adapter, schedule, eval, memory structure, index, context-loading rule, or project instruction."


def resolved_learning_topics(events: list[dict[str, Any]]) -> set[str]:
    out: set[str] = set()
    resolution_re = re.compile(r"\b(fixed|implemented|validation passed|confirmed|working|worked|resolved)\b|memory update candidate", re.I)
    for event in events:
        source = str(event.get("source") or "")
        role = str(event.get("chat_role") or "")
        status = str(event.get("status") or "").lower()
        text = event_text(event)
        raw_assistant_resolution = source == "raw-chat-parser" and role == "assistant" and bool(resolution_re.search(text))
        structured_resolution = source != "raw-chat-parser" and status in {"resolved", "fixed", "implemented", "closed"}
        if not raw_assistant_resolution and not structured_resolution:
            continue
        out.update(learning_topic_tags(text))
    return out


def is_raw_chat_test_probe(event: dict[str, Any]) -> bool:
    if str(event.get("source") or "") != "raw-chat-parser":
        return False
    role = str(event.get("chat_role") or "")
    if role != "user":
        return False
    text = event_text(event).lower()
    probe_patterns = [
        "testing raw chat",
        "restart codex",
        "restarted codex",
        "check it",
        "let's test it",
        "test it out",
    ]
    return any(pattern in text for pattern in probe_patterns)


def is_routine_raw_chat_event(event: dict[str, Any]) -> bool:
    if str(event.get("source") or "") != "raw-chat-parser":
        return False
    if str(event.get("chat_role") or "") != "user":
        return False
    text = event_text(event).lower()
    if "memory-ingest skill in one-item worker mode" in text and "process exactly this inbox item" in text:
        return True
    routine_phrases = [
        "ok, great. so now, what's next",
        "ok, great, now, let's continue",
        "when i should schedule it",
        "when should i schedule it",
        "have you also updated",
    ]
    if any(phrase in text for phrase in routine_phrases):
        return True
    if POSITIVE_SIGNAL_RE.search(text) and not (
        FRICTION_SIGNAL_RE.search(text)
        or EXPECTATION_SIGNAL_RE.search(text)
        or AUTOMATION_SIGNAL_RE.search(text)
    ):
        return True
    return False


def is_non_actionable_event(event: dict[str, Any], resolved_topics: set[str]) -> bool:
    status = str(event.get("status") or "").lower()
    if status in {"resolved", "fixed", "implemented", "dismissed", "closed"}:
        return True
    if str(event.get("source") or "") != "raw-chat-parser":
        return False
    role = str(event.get("chat_role") or "")
    if role == "assistant":
        return True
    if is_raw_chat_test_probe(event):
        return True
    if is_routine_raw_chat_event(event):
        return True
    tags = learning_topic_tags(event_text(event))
    return bool(tags & resolved_topics)


def event_candidates(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    resolved_topics = resolved_learning_topics(events)
    for event in events:
        if is_non_actionable_event(event, resolved_topics):
            continue
        if not is_system_interaction_event(event):
            continue
        event_type = str(event.get("event_type") or "")
        summary = str(event.get("summary") or "").strip()
        skill = str(event.get("skill") or event.get("workflow") or "").strip()
        friction = event.get("friction") if isinstance(event.get("friction"), list) else []
        manual_steps = event.get("manual_steps") if isinstance(event.get("manual_steps"), list) else []
        automation = event.get("automation_candidates") if isinstance(event.get("automation_candidates"), list) else []
        if event_type in {"correction", "blocker"} or friction:
            kind = candidate_kind_for_event(event)
            candidates.append({
                "kind": kind,
                "title": summary or "Investigate recorded friction",
                "reason": "; ".join(str(item) for item in friction) or f"Recorded {event_type} event.",
                "owner": skill or "needs-owner-triage",
                "suggested_action": suggested_action_for_kind(kind),
                "fingerprint": f"process:{event.get('fingerprint') or candidate_fingerprint(event)}",
            })
        for step in manual_steps:
            candidates.append({
                "kind": "manual-work-automation",
                "title": str(step),
                "reason": summary or "Manual step was recorded during project work.",
                "owner": skill or "needs-owner-triage",
                "suggested_action": suggested_action_for_kind("manual-work-automation"),
                "fingerprint": f"manual:{event.get('fingerprint') or candidate_fingerprint(event)}:{candidate_fingerprint({'kind': 'manual', 'owner': skill, 'title': step})}",
            })
        for item in automation:
            candidates.append({
                "kind": "automation-candidate",
                "title": str(item),
                "reason": summary or "Automation candidate was explicitly recorded.",
                "owner": skill or "needs-owner-triage",
                "suggested_action": suggested_action_for_kind("manual-work-automation"),
                "fingerprint": f"automation:{event.get('fingerprint') or candidate_fingerprint(event)}:{candidate_fingerprint({'kind': 'automation', 'owner': skill, 'title': item})}",
            })
    return candidates


def brief_candidates(problem_briefs: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for brief in problem_briefs:
        status = str(brief.get("status"))
        if status == "pending":
            continue
        out.append({
            "kind": "blocked-scheduled-work",
            "title": f"{brief.get('task')} brief is {status}",
            "reason": f"Recent scheduled brief `{brief.get('path')}` is `{status}`.",
            "owner": str(brief.get("task") or "scheduler"),
            "suggested_action": "Inspect the runner log and convert repeated blockers into a skill/tool fix.",
        })
    return out


def build_review(root: Path, days: int, today: date | None = None) -> dict[str, Any]:
    root = root.resolve()
    now = datetime.now(timezone.utc).astimezone()
    today = today or now.date()
    raw_chat_result: dict[str, Any] = {}
    try:
        from ephemeral_chat_capture import extract_events, purge_expired

        deleted = purge_expired(root, retention_days=7, now=now)
        extracted = extract_events(root, retention_days=7)
        raw_chat_result = {"deleted": deleted, "extracted": extracted}
    except Exception as exc:  # noqa: BLE001
        raw_chat_result = {"error": str(exc)}
    events = recent_learning_events(root, days, now)
    problem_briefs = recent_problem_briefs(root, days, now)
    candidates = event_candidates(events)
    candidates.extend(brief_candidates(problem_briefs))
    if not events:
        candidates.append({
            "kind": "logging-gap",
            "title": "No structured learning events recorded in the review window",
            "reason": "System friction, user satisfaction/frustration, repeated manual steps, and workflow misuse are still only partially journaled.",
            "owner": "work-session-journal",
            "suggested_action": "Record compact system-learning events when the project owner corrects the OS, praises a workflow, repeats manual work, or uses the system differently than expected.",
        })
    candidates = group_candidates(candidates)
    return {
        "generated_at": now.isoformat(timespec="seconds"),
        "review_period_days": days,
        "event_count": len(events),
        "problem_brief_count": len(problem_briefs),
        "raw_chat_result": raw_chat_result,
        "candidate_count": len(candidates),
        "events": events,
        "problem_briefs": problem_briefs,
        "candidates": candidates,
    }


def render_markdown(review: dict[str, Any]) -> str:
    status = "pending" if review["candidate_count"] else "informational"
    lines = [
        "---",
        f"status: {status}",
        "task: learning-review",
        f"generated_at: {review['generated_at']}",
        f"review_period_days: {review['review_period_days']}",
        f"candidate_count: {review['candidate_count']}",
        f"event_count: {review['event_count']}",
        f"problem_brief_count: {review['problem_brief_count']}",
        "---",
        "",
        "# Learning Review",
        "",
        "## Summary",
        "",
        f"- Structured learning events: {review['event_count']}",
        f"- Recent blocked/problem briefs: {review['problem_brief_count']}",
        f"- Improvement candidates: {review['candidate_count']}",
        f"- Raw chat extraction: `{review.get('raw_chat_result', {})}`",
        "",
        "## Candidates",
        "",
    ]
    if not review["candidates"]:
        lines.append("- No improvement candidates found.")
    for candidate in review["candidates"]:
        lines.extend([
            f"### {candidate['title']}",
            "",
            f"- Kind: `{candidate['kind']}`",
            f"- Owner: `{candidate['owner']}`",
            f"- Reason: {candidate['reason']}",
            f"- Suggested action: {candidate['suggested_action']}",
            f"- Occurrences: `{candidate.get('occurrence_count', 1)}`",
            "",
        ])
    lines.extend([
        "## Review Actions",
        "",
        "- Accept: route to `skill-improvement-loop`, a focused patch, or a project task.",
        "- Defer: leave the brief pending and add a concrete follow-up date.",
        "- Dismiss: mark the brief reviewed with a short reason.",
        "- Do not auto-patch from this brief without the project owner's approval.",
        "",
    ])
    return "\n".join(lines)


def command_review(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    today = date.fromisoformat(args.today) if args.today else None
    review = build_review(root, args.days, today=today)
    rendered = render_markdown(review)
    if args.json:
        print(json.dumps(review, indent=2, ensure_ascii=False))
    if args.brief_output:
        output = Path(args.brief_output)
        if not output.is_absolute():
            output = root / output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered)
        print(f"WROTE: {output}")
    elif not args.json:
        print(rendered)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    review = sub.add_parser("review", help="Produce a learning review")
    review.add_argument("--root", default=".")
    review.add_argument("--days", type=int, default=7)
    review.add_argument("--today", help="YYYY-MM-DD override for recurring review")
    review.add_argument("--brief-output", help="Optional markdown brief path")
    review.add_argument("--json", action="store_true")
    review.set_defaults(func=command_review)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
