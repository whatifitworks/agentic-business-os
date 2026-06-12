#!/usr/bin/env python3
"""Generic Agentic Business OS repository audit."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

REQUIRED_ROOT_FILES = {"AGENTS.md", "00-start-here.md", "README.md"}
REQUIRED_ROOT_FOLDERS = {
    ".agents", "context", "domains", "dropped", "evals", "inbox", "indexes", "logs", "outputs",
    "projects", "references", "rules", "scripts", "sources", "state", "system", "wiki"
}
FORBIDDEN_ROOT_FOLDERS = {"memory", "research", "processed"}
DEFAULT_PRIVATE_TERMS = ["<private-company-name>", "<private-person-name>", "<local-user-path>"]

def private_terms(root: Path) -> list[str]:
    path = root / "state" / "privacy-terms.json"
    if not path.exists():
        return DEFAULT_PRIVATE_TERMS
    try:
        data = json.loads(path.read_text() or "{}")
    except json.JSONDecodeError:
        return DEFAULT_PRIVATE_TERMS
    terms = data.get("blocked_terms", []) if isinstance(data, dict) else []
    return [str(term) for term in terms if str(term).strip()]

@dataclass
class Issue:
    level: str
    code: str
    path: str
    message: str

def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()

def add(issues: list[Issue], level: str, code: str, path: str | Path, message: str, root: Path) -> None:
    issues.append(Issue(level, code, rel(path, root) if isinstance(path, Path) else path, message))

def iter_text(root: Path):
    suffixes = {"", ".md", ".py", ".json", ".yaml", ".yml", ".toml", ".txt", ".sh"}
    for path in root.rglob("*"):
        if not path.is_file() or ".git" in path.parts or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        if path.suffix.lower() in suffixes:
            yield path

def markdown_links(text: str) -> list[str]:
    links = [m.group(1).strip() for m in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", text)]
    links.extend(m.group(1).strip() for m in re.finditer(r"(?m)^@([^\s]+\.md)\s*$", text))
    return links

def check_markdown_links(root: Path, issues: list[Issue]) -> None:
    for source in root.rglob("*.md"):
        if ".git" in source.parts:
            continue
        text = source.read_text(errors="replace")
        for raw in markdown_links(text):
            target = unquote(raw.split("#", 1)[0].strip().strip("<>"))
            if not target or "://" in target or target.startswith(("#", "mailto:")):
                continue
            if not (source.parent / target).resolve().exists():
                add(issues, "error", "broken_markdown_link", source, f"Missing target: {raw}", root)

def check_json(path: Path, issues: list[Issue], root: Path) -> None:
    if not path.exists():
        add(issues, "error", "json_missing", path, "Required JSON file is missing", root)
        return
    try:
        json.loads(path.read_text() or "{}")
    except json.JSONDecodeError as exc:
        add(issues, "error", "json_invalid", path, str(exc), root)


WIKI_STALE_DAYS = 60
SKILL_WARN_BYTES = 24_000
SKILL_ERROR_BYTES = 64_000
SKILL_DESCRIPTION_MAX_CHARS = 150
QUEUE_RUNNING_STALE_HOURS = 1.5
QUEUE_PENDING_STALE_HOURS = 24


def read_frontmatter(path: Path) -> dict:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        return {}
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    out = {}
    for line in text[4:end].splitlines():
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out


def parse_dt(value: str):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def canonical_shadows(root: Path) -> dict:
    """Optional mapping of derived/shadow pages to their canonical files.

    Configure in state/canonical-shadows.json as {"wiki/derived-page.md": "context/canonical.md"}.
    Shadow pages must carry an explicit canonical-precedence pointer so agents
    never treat a stale derived page as the source of truth.
    """
    path = root / "state" / "canonical-shadows.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text() or "{}")
    except json.JSONDecodeError:
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def check_lifecycle_guardrails(root: Path, issues: list[Issue]) -> None:
    now = datetime.now(timezone.utc)

    # 1. Pages shadowing a canonical context file must declare precedence.
    for shadow, canonical in canonical_shadows(root).items():
        page = root / shadow
        if not page.exists():
            continue
        text = page.read_text(errors="replace")
        if "canonical" not in text.lower():
            add(issues, "error", "missing_canonical_pointer", page,
                f"Shadows {canonical} but has no canonical-precedence pointer", root)

    # 2. Wiki freshness: respect review_by when present, else flag old pages.
    wiki = root / "wiki"
    if wiki.exists():
        for page in sorted(wiki.rglob("*.md")):
            fm = read_frontmatter(page)
            review_by = parse_dt(fm.get("review_by", ""))
            if review_by is not None:
                if review_by < now:
                    add(issues, "warn", "wiki_review_overdue", page,
                        f"review_by {fm.get('review_by')} is past due", root)
                continue
            updated = parse_dt(fm.get("updated_at", ""))
            if updated is None:
                try:
                    updated = datetime.fromtimestamp(page.stat().st_mtime, tz=timezone.utc)
                except OSError:
                    continue
            age_days = (now - updated).total_seconds() / 86400
            if age_days > WIKI_STALE_DAYS:
                add(issues, "warn", "wiki_stale", page,
                    f"Not updated for {age_days:.0f}d and no review_by date set", root)

    # 3. Skill size budgets and description length budgets.
    skills = root / ".agents" / "skills"
    if skills.exists():
        for skill in sorted(skills.rglob("SKILL.md")):
            size = skill.stat().st_size
            if size > SKILL_ERROR_BYTES:
                add(issues, "error", "skill_too_large", skill,
                    f"{size} bytes; move reference data to sidecar files", root)
            elif size > SKILL_WARN_BYTES:
                add(issues, "warn", "skill_large", skill,
                    f"{size} bytes; consider extracting sidecar files", root)
            description = str(read_frontmatter(skill).get("description", ""))
            if len(description) > SKILL_DESCRIPTION_MAX_CHARS:
                add(issues, "error", "skill_description_too_long", skill,
                    f"description is {len(description)} chars (max {SKILL_DESCRIPTION_MAX_CHARS})", root)

    # 4. Memory ingest queue health: no record may sit running/pending forever.
    queue_path = root / "state" / "memory-ingest-queue.json"
    if queue_path.exists():
        try:
            queue = json.loads(queue_path.read_text() or "{}")
        except (OSError, json.JSONDecodeError):
            queue = {}
        for record in queue.get("records", []) if isinstance(queue, dict) else []:
            if not isinstance(record, dict):
                continue
            status = record.get("status")
            path = str(record.get("path", "?"))
            if status == "failed":
                add(issues, "warn", "ingest_failed", queue_path,
                    f"{path}: {record.get('note', 'failed')}", root)
                continue
            if status not in {"running", "pending"}:
                continue
            anchor = parse_dt(str(record.get("last_started_at") or record.get("detected_at") or ""))
            if anchor is None:
                continue
            age_hours = (now - anchor).total_seconds() / 3600
            if status == "running" and age_hours > QUEUE_RUNNING_STALE_HOURS:
                add(issues, "error", "ingest_running_stale", queue_path,
                    f"{path} running for {age_hours:.1f}h; worker likely hung", root)
            elif status == "pending" and age_hours > QUEUE_PENDING_STALE_HOURS:
                add(issues, "warn", "ingest_pending_stale", queue_path,
                    f"{path} pending for {age_hours:.0f}h", root)


def run(root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for name in REQUIRED_ROOT_FILES:
        if not (root / name).exists():
            add(issues, "error", "required_root_file_missing", name, "Required root file is missing", root)
    for name in REQUIRED_ROOT_FOLDERS:
        if not (root / name).is_dir():
            add(issues, "error", "required_root_folder_missing", name, "Required root folder is missing", root)
    for name in FORBIDDEN_ROOT_FOLDERS:
        if (root / name).exists():
            add(issues, "error", "forbidden_root_folder", name, "Retired/forbidden root folder must not exist", root)
    for path in ["state/ingest-manifest.json", "state/outputs-manifest.json", "state/memory-ingest-queue.json", "system/context/context_index.json"]:
        check_json(root / path, issues, root)
    for skill in (root / ".agents" / "skills").rglob("SKILL.md"):
        if not (skill.parent / "manifest.yaml").exists():
            add(issues, "warn", "skill_manifest_missing", skill.parent, "Skill is missing manifest.yaml", root)
    if (root / "system/tools/template_sync.py").exists():
        add(issues, "error", "private_bridge_public", "system/tools/template_sync.py", "Private downstream sync bridge should not ship in the public template", root)
    for path in iter_text(root):
        text = path.read_text(errors="replace")
        for term in private_terms(root):
            if term in text:
                add(issues, "error", "private_term", path, f"Private term found: {term}", root)
    check_markdown_links(root, issues)
    check_lifecycle_guardrails(root, issues)
    return issues

def render(root: Path, issues: list[Issue]) -> str:
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    errors = [i for i in issues if i.level == "error"]
    warns = [i for i in issues if i.level == "warn"]
    lines = ["# Agentic Business OS Repo Audit", "", f"Root: `{root}`", f"Generated: `{now}`", "", "## Summary", "", f"- Errors: {len(errors)}", f"- Warnings: {len(warns)}"]
    if not issues:
        lines += ["", "No issues found."]
    else:
        for title, items in [("Errors", errors), ("Warnings", warns)]:
            if items:
                lines += ["", f"## {title}", ""]
                lines += [f"- `{i.code}` [{i.path}] {i.message}" for i in items]
    return "\n".join(lines) + "\n"

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output")
    parser.add_argument("--brief-output")
    parser.add_argument("--task-name", default="repo-health")
    parser.add_argument("--state-db")
    parser.add_argument("--exit-zero", action="store_true")
    args = parser.parse_args()
    root = Path.cwd()
    issues = run(root)
    report = render(root, issues)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(report)
    if args.brief_output:
        Path(args.brief_output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.brief_output).write_text(report)
    print(report)
    has_error = any(i.level == "error" for i in issues)
    return 0 if args.exit_zero or not has_error else 1

if __name__ == "__main__":
    raise SystemExit(main())
