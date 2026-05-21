#!/usr/bin/env python3
"""Run deterministic Agentic Business OS hook checks.

These checks are designed to be callable from future Codex/Claude hooks and
from repo-health. They do not mutate external systems.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


HOOKS = {
    "session-end-memory-candidate",
    "skill-completion-contract",
    "wiki-index-guard",
    "inbox-staleness-check",
    "inbox-auto-ingest-trigger",
    "failure-to-inbox-capture",
    "work-session-journal",
    "ephemeral-chat-capture",
    "ingest-outcome-manifest-check",
    "adapter-evidence-check",
    "scheduler-drift-check",
    "prompt-secret-scan",
    "pre-compaction-handoff",
    "agent-output-contract",
}


SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    re.compile(r"AIza[0-9A-Za-z_-]{20,}"),
    re.compile(r"-----BEGIN PRIVATE KEY-----"),
]


@dataclass
class HookIssue:
    level: str
    hook: str
    code: str
    path: str
    message: str


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def add(issues: list[HookIssue], level: str, hook: str, code: str, path: str | Path, message: str, root: Path) -> None:
    path_str = rel(path, root) if isinstance(path, Path) else path
    issues.append(HookIssue(level=level, hook=hook, code=code, path=path_str, message=message))


def read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def active_skill_dirs(root: Path) -> list[Path]:
    skills = root / ".agents" / "skills"
    if not skills.exists():
        return []
    namespaced = [p for p in skills.glob("*/*") if p.is_dir() and (p / "SKILL.md").exists()]
    namespaced_names = {p.name for p in namespaced}
    direct = [
        p for p in skills.iterdir()
        if p.is_dir() and (p / "SKILL.md").exists() and p.name not in namespaced_names
    ]
    return sorted(direct + namespaced)


def resolve_skill_dir(root: Path, skill: str) -> Path | None:
    skills = root / ".agents" / "skills"
    for path in sorted(skills.glob(f"*/{skill}")):
        if (path / "SKILL.md").exists():
            return path
    direct = skills / skill
    if (direct / "SKILL.md").exists():
        return direct
    return None


def check_session_end(root: Path, issues: list[HookIssue]) -> None:
    hook = "session-end-memory-candidate"
    if not (root / "inbox").is_dir():
        add(issues, "error", hook, "hook_inbox_missing", root / "inbox", "Root inbox is missing.", root)
    if not (root / "system" / "schemas" / "inbox-envelope.schema.yaml").exists():
        add(issues, "error", hook, "hook_inbox_schema_missing", root / "system/schemas/inbox-envelope.schema.yaml", "Inbox envelope schema is missing.", root)


def check_skill_completion(root: Path, issues: list[HookIssue]) -> None:
    hook = "skill-completion-contract"
    index = read(root / "indexes" / "skills.md")
    for skill in active_skill_dirs(root):
        if not (skill / "manifest.yaml").exists():
            add(issues, "error", hook, "hook_skill_manifest_missing", skill / "manifest.yaml", "Skill manifest is missing.", root)
        if skill.name not in index:
            add(issues, "error", hook, "hook_skill_not_indexed", skill, "Skill is missing from indexes/skills.md.", root)


def check_wiki_index(root: Path, issues: list[HookIssue]) -> None:
    hook = "wiki-index-guard"
    try:
        from memory_graph_audit import run as run_memory_graph
    except Exception as exc:  # noqa: BLE001
        add(issues, "error", hook, "hook_memory_audit_import_failed", root / "system/tools/memory_graph_audit.py", str(exc), root)
        return
    for issue in run_memory_graph(root, scope="root"):
        add(issues, issue.level, hook, issue.code, issue.path, issue.message, root)


def check_inbox_staleness(root: Path, issues: list[HookIssue], stale_days: int) -> None:
    hook = "inbox-staleness-check"
    inbox = root / "inbox"
    if not inbox.exists():
        add(issues, "error", hook, "hook_inbox_missing", inbox, "Root inbox is missing.", root)
        return
    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    for path in sorted(p for p in inbox.rglob("*") if p.is_file()):
        rel_path = rel(path, root)
        if path.name in {"README.md", ".gitkeep", ".DS_Store"}:
            continue
        text = read(path)
        if "ingest_status: blocked" in text or "ingest_status: needs-daniels" in text:
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            add(issues, "warn", hook, "hook_stale_inbox_item", path, f"Inbox item older than {stale_days} days.", root)


def check_inbox_auto_ingest(root: Path, issues: list[HookIssue]) -> None:
    hook = "inbox-auto-ingest-trigger"
    script = root / "system" / "tools" / "inbox_auto_ingest.py"
    if not script.exists():
        add(issues, "error", hook, "hook_inbox_auto_ingest_missing", script, "Inbox auto-ingest runner is missing.", root)
    registry = read(root / ".agents" / "agents" / "registry.yaml")
    if "memory-inbox-processor" not in registry:
        add(issues, "error", hook, "hook_memory_ingest_agent_missing", root / ".agents/agents/registry.yaml", "memory-inbox-processor agent is missing.", root)
    queue = root / "state" / "memory-ingest-queue.json"
    if not queue.exists():
        add(issues, "error", hook, "hook_memory_ingest_queue_missing", queue, "Memory ingest queue is missing.", root)
        return
    try:
        data = json.loads(queue.read_text())
    except Exception as exc:  # noqa: BLE001
        add(issues, "error", hook, "hook_memory_ingest_queue_invalid", queue, str(exc), root)
        return
    if not isinstance(data.get("records"), list):
        add(issues, "error", hook, "hook_memory_ingest_queue_records_invalid", queue, "Queue records must be a list.", root)


def check_failure_to_inbox_capture(root: Path, issues: list[HookIssue]) -> None:
    hook = "failure-to-inbox-capture"
    tool = root / "system" / "tools" / "failure_capture.py"
    contract = root / ".agents" / "hooks" / "failure-to-inbox-capture.md"
    fixture = root / "evals" / "failure-capture" / "cases.json"
    for path, message in [
        (tool, "Failure capture tool is missing."),
        (contract, "Failure capture hook contract is missing."),
        (fixture, "Failure capture eval fixture is missing."),
    ]:
        if not path.exists():
            add(issues, "error", hook, "hook_failure_capture_missing", path, message, root)
    if not tool.exists() or not fixture.exists():
        return
    sys.path.insert(0, str(tool.parent))
    try:
        from failure_capture import analyze_failure

        data = json.loads(fixture.read_text())
        cases = [case for case in data.get("cases", []) if isinstance(case, dict)]
        if not any(analyze_failure(case).get("should_capture") for case in cases):
            add(issues, "error", hook, "hook_failure_capture_no_positive_fixture", fixture, "No fixture produces a capture-worthy failure.", root)
    except Exception as exc:  # noqa: BLE001
        add(issues, "error", hook, "hook_failure_capture_invalid", fixture, str(exc), root)


def check_work_session_journal(root: Path, issues: list[HookIssue]) -> None:
    hook = "work-session-journal"
    tool = root / "system" / "tools" / "work_session_journal.py"
    reviewer = root / "system" / "tools" / "learning_review.py"
    contract = root / ".agents" / "hooks" / "work-session-journal.md"
    skill = root / ".agents" / "skills" / "ops" / "learning-review" / "SKILL.md"
    fixture = root / "evals" / "learning" / "cases.json"
    for path, message in [
        (tool, "Work-session journal tool is missing."),
        (reviewer, "Learning review tool is missing."),
        (contract, "Work-session journal hook contract is missing."),
        (skill, "Learning review skill is missing."),
        (fixture, "Learning review eval fixture is missing."),
    ]:
        if not path.exists():
            add(issues, "error", hook, "hook_learning_component_missing", path, message, root)
    if not tool.exists() or not reviewer.exists() or not fixture.exists():
        return
    sys.path.insert(0, str(tool.parent))
    try:
        from learning_review import build_review
        from work_session_journal import record_event

        data = json.loads(fixture.read_text())
        cases = [case for case in data.get("cases", []) if isinstance(case, dict)]
        if not cases:
            add(issues, "error", hook, "hook_learning_fixture_empty", fixture, "Learning review fixture has no cases.", root)
            return
        case = cases[0]
        event = case.get("event")
        if not isinstance(event, dict):
            add(issues, "error", hook, "hook_learning_fixture_invalid", fixture, "Learning review fixture event is not an object.", root)
            return
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            record_event(tmp_root, event)
            review = build_review(tmp_root, days=7, today=date(2026, 5, 19))
        candidates = review.get("candidates", [])
        expected_kind = str(case.get("expected_candidate_kind"))
        expected_owner = str(case.get("expected_owner"))
        matched = any(
            isinstance(candidate, dict)
            and candidate.get("kind") == expected_kind
            and candidate.get("owner") == expected_owner
            for candidate in candidates
        )
        if not matched:
            add(issues, "error", hook, "hook_learning_fixture_failed", fixture, "Learning fixture did not produce expected candidate.", root)
    except Exception as exc:  # noqa: BLE001
        add(issues, "error", hook, "hook_learning_review_invalid", fixture, str(exc), root)


def check_ephemeral_chat_capture(root: Path, issues: list[HookIssue]) -> None:
    hook = "ephemeral-chat-capture"
    tool = root / "system" / "tools" / "ephemeral_chat_capture.py"
    gitignore = read(root / ".gitignore")
    codex = read(root / ".codex" / "config.toml")
    claude = read(root / ".claude" / "settings.json")
    for path, message in [
        (tool, "Ephemeral chat capture tool is missing."),
    ]:
        if not path.exists():
            add(issues, "error", hook, "hook_ephemeral_chat_capture_missing", path, message, root)
    if "logs/raw-chats/" not in gitignore:
        add(issues, "error", hook, "hook_raw_chats_not_ignored", root / ".gitignore", "logs/raw-chats/ must be gitignored.", root)
    if "ephemeral_chat_capture.py" not in codex:
        add(issues, "error", hook, "hook_codex_raw_chat_capture_missing", root / ".codex/config.toml", "Codex Stop hook does not call ephemeral_chat_capture.py.", root)
    if "ephemeral_chat_capture.py" not in claude:
        add(issues, "error", hook, "hook_claude_raw_chat_capture_missing", root / ".claude/settings.json", "Claude Stop hook does not call ephemeral_chat_capture.py.", root)
    if not tool.exists():
        return
    sys.path.insert(0, str(tool.parent))
    try:
        from ephemeral_chat_capture import capture_payload, extract_events, purge_expired

        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            capture_payload(
                tmp_root,
                "manual",
                {
                    "session_id": "fixture",
                    "messages": [
                        {"role": "user", "content": "This repeated manual step should become a skill or hook."}
                    ],
                },
                "",
                retention_days=7,
            )
            extracted = extract_events(tmp_root, retention_days=7)
            deleted = purge_expired(tmp_root, retention_days=0)
        if int(extracted.get("events_written") or 0) < 1:
            add(issues, "error", hook, "hook_raw_chat_extract_failed", tool, "Raw chat fixture did not extract a learning event.", root)
        if not deleted:
            add(issues, "error", hook, "hook_raw_chat_purge_failed", tool, "Raw chat purge fixture did not delete expired capture.", root)
        with tempfile.TemporaryDirectory() as tmp:
            proc = subprocess.run(
                [
                    sys.executable,
                    str(tool),
                    "capture",
                    "--root",
                    tmp,
                    "--runtime",
                    "manual",
                    "--stdin-json",
                    "--extract",
                    "--purge",
                    "--hook-json",
                ],
                input=json.dumps({
                    "session_id": "hook-json-fixture",
                    "messages": [{"role": "user", "content": "This repeated manual step should become a hook."}],
                }),
                text=True,
                capture_output=True,
                check=False,
            )
        try:
            hook_payload = json.loads(proc.stdout)
        except json.JSONDecodeError:
            hook_payload = {}
        if proc.returncode != 0 or hook_payload != {"continue": True}:
            add(issues, "error", hook, "hook_raw_chat_hook_json_invalid", tool, "Hook mode must emit exactly {\"continue\": true}.", root)
    except Exception as exc:  # noqa: BLE001
        add(issues, "error", hook, "hook_raw_chat_capture_invalid", tool, str(exc), root)


def manifest_records(root: Path) -> list[dict[str, object]]:
    path = root / "state" / "ingest-manifest.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return []
    records = data.get("records", [])
    return records if isinstance(records, list) else []


def check_ingest_outcome_manifest(root: Path, issues: list[HookIssue]) -> None:
    hook = "ingest-outcome-manifest-check"
    manifest = root / "state" / "ingest-manifest.json"
    if not manifest.exists():
        add(issues, "error", hook, "hook_ingest_manifest_missing", manifest, "Ingest manifest is missing.", root)
        return
    records = manifest_records(root)
    recorded = {
        str(record.get("path") or record.get("destination_path") or record.get("source_path"))
        for record in records
        if isinstance(record, dict)
    }
    for folder in ["dropped"]:
        for path in sorted(p for p in (root / folder).rglob("*") if p.is_file()):
            if path.name in {"README.md", ".gitkeep", ".DS_Store"}:
                continue
            rel_path = rel(path, root)
            if rel_path not in recorded:
                add(issues, "error", hook, "hook_manifest_record_missing", path, "Dropped file lacks ingest manifest record.", root)


def check_adapter_evidence(root: Path, issues: list[HookIssue]) -> None:
    hook = "adapter-evidence-check"
    registry = read(root / ".agents" / "adapters" / "registry.yaml")
    if "browser-computer-adapter" not in registry:
        add(issues, "error", hook, "hook_adapter_registry_missing", root / ".agents/adapters/registry.yaml", "Browser/Computer adapter is not registered.", root)
    if not (root / "sources" / "adapters" / "browser-computer-adapter.md").exists():
        add(issues, "error", hook, "hook_adapter_source_missing", root / "sources/adapters/browser-computer-adapter.md", "Adapter source contract is missing.", root)
    for record in sorted((root / "sources" / "adapters" / "runs").glob("*.json")):
        try:
            data = json.loads(record.read_text())
        except Exception as exc:  # noqa: BLE001
            add(issues, "error", hook, "hook_adapter_record_invalid", record, str(exc), root)
            continue
        for field in ["adapter", "workflow_name", "target", "tool_type", "status", "created_at", "evidence_path", "confidence", "caveats"]:
            if field not in data:
                add(issues, "error", hook, "hook_adapter_record_field_missing", record, f"Adapter record missing {field}.", root)
        if data.get("status") not in {"success", "blocked", "failed"}:
            add(issues, "error", hook, "hook_adapter_status_invalid", record, "Adapter status must be success, blocked, or failed.", root)
        evidence = data.get("evidence_path")
        if not isinstance(evidence, str) or not (root / evidence).exists():
            add(issues, "error", hook, "hook_adapter_evidence_missing", record, "Adapter evidence_path is missing or does not exist.", root)


def check_scheduler_drift(root: Path, issues: list[HookIssue]) -> None:
    hook = "scheduler-drift-check"
    schedules = root / ".agents" / "schedules.yaml"
    if not schedules.exists():
        add(issues, "error", hook, "hook_schedules_missing", schedules, "Schedule config is missing.", root)
        return
    text = read(schedules)
    for match in re.finditer(r"(?m)skill:\s*([A-Za-z0-9_-]+)", text):
        skill = match.group(1)
        if resolve_skill_dir(root, skill) is None:
            add(issues, "error", hook, "hook_schedule_skill_missing", schedules, f"Schedule points to missing skill {skill}.", root)


def iter_scan_files(root: Path) -> list[Path]:
    folders = ["inbox", "wiki", "outputs", "evals"]
    out: list[Path] = []
    for folder in folders:
        base = root / folder
        if not base.exists():
            continue
        for path in base.rglob("*"):
            if path.is_file() and path.stat().st_size < 1_000_000:
                out.append(path)
    return sorted(out)


def check_prompt_secret_scan(root: Path, issues: list[HookIssue]) -> None:
    hook = "prompt-secret-scan"
    for path in iter_scan_files(root):
        text = read(path)
        for pattern in SECRET_PATTERNS:
            if pattern.search(text):
                add(issues, "error", hook, "hook_possible_secret", path, "Possible secret-like value found.", root)
                break


def check_pre_compaction(root: Path, issues: list[HookIssue]) -> None:
    hook = "pre-compaction-handoff"
    template = root / ".agents" / "templates" / "pre-compaction-handoff.md"
    if not template.exists():
        add(issues, "error", hook, "hook_handoff_template_missing", template, "Pre-compaction handoff template is missing.", root)


def check_agent_output(root: Path, issues: list[HookIssue]) -> None:
    hook = "agent-output-contract"
    registry = read(root / ".agents" / "agents" / "registry.yaml")
    for required in ["handoff_output", "knowledge-librarian", "code-reviewer"]:
        if required not in registry:
            add(issues, "error", hook, "hook_agent_contract_missing", root / ".agents/agents/registry.yaml", f"Agent registry missing {required}.", root)


def run(root: Path, hook: str = "all", stale_days: int = 14) -> list[HookIssue]:
    root = root.resolve()
    if hook != "all" and hook not in HOOKS:
        return [HookIssue("error", hook, "unknown_hook", ".", f"Unknown hook {hook}.")]

    selected = HOOKS if hook == "all" else {hook}
    issues: list[HookIssue] = []
    if "session-end-memory-candidate" in selected:
        check_session_end(root, issues)
    if "skill-completion-contract" in selected:
        check_skill_completion(root, issues)
    if "wiki-index-guard" in selected:
        check_wiki_index(root, issues)
    if "inbox-staleness-check" in selected:
        check_inbox_staleness(root, issues, stale_days)
    if "inbox-auto-ingest-trigger" in selected:
        check_inbox_auto_ingest(root, issues)
    if "failure-to-inbox-capture" in selected:
        check_failure_to_inbox_capture(root, issues)
    if "work-session-journal" in selected:
        check_work_session_journal(root, issues)
    if "ephemeral-chat-capture" in selected:
        check_ephemeral_chat_capture(root, issues)
    if "ingest-outcome-manifest-check" in selected:
        check_ingest_outcome_manifest(root, issues)
    if "adapter-evidence-check" in selected:
        check_adapter_evidence(root, issues)
    if "scheduler-drift-check" in selected:
        check_scheduler_drift(root, issues)
    if "prompt-secret-scan" in selected:
        check_prompt_secret_scan(root, issues)
    if "pre-compaction-handoff" in selected:
        check_pre_compaction(root, issues)
    if "agent-output-contract" in selected:
        check_agent_output(root, issues)
    return sorted(issues, key=lambda item: (item.level, item.hook, item.path, item.code))


def summarize(issues: list[HookIssue]) -> dict[str, int]:
    counts = {"error": 0, "warn": 0, "info": 0}
    for issue in issues:
        counts[issue.level] = counts.get(issue.level, 0) + 1
    return counts


def render_markdown(root: Path, hook: str, issues: list[HookIssue]) -> str:
    counts = summarize(issues)
    lines = [
        "# Ops v2 Hook Check",
        "",
        f"Root: `{root.resolve()}`",
        f"Hook: `{hook}`",
        f"Generated: `{datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}`",
        "",
        "## Summary",
        "",
        f"- Errors: {counts.get('error', 0)}",
        f"- Warnings: {counts.get('warn', 0)}",
        f"- Info: {counts.get('info', 0)}",
        "",
    ]
    if not issues:
        lines.append("No hook issues found.")
        return "\n".join(lines)
    for level in ["error", "warn", "info"]:
        bucket = [issue for issue in issues if issue.level == level]
        if not bucket:
            continue
        lines.extend([f"## {level.title()}s", ""])
        for issue in bucket:
            lines.append(f"- `{issue.hook}:{issue.code}` [{issue.path}] {issue.message}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root, default: current directory")
    parser.add_argument("--hook", default="all", help="Hook name or all")
    parser.add_argument("--stale-days", type=int, default=14, help="Stale inbox threshold")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    issues = run(root, hook=args.hook, stale_days=args.stale_days)
    if args.json:
        print(json.dumps({"root": str(root), "hook": args.hook, "issues": [asdict(issue) for issue in issues]}, indent=2))
    else:
        print(render_markdown(root, args.hook, issues))
    return 1 if any(issue.level == "error" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
