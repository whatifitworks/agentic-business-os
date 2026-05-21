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
