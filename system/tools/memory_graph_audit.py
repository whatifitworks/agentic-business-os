#!/usr/bin/env python3
"""Audit the Agentic Business OS Obsidian memory graph."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import unquote


@dataclass
class MemoryIssue:
    level: str
    code: str
    path: str
    message: str


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def is_memory_excluded(path: Path, memory_root: Path) -> bool:
    try:
        parts = path.relative_to(memory_root).parts
    except ValueError:
        return True
    return ".obsidian" in parts or "__pycache__" in parts


def iter_markdown(folder: Path, memory_root: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.rglob("*.md") if not is_memory_excluded(p, memory_root))


def graph_sources(root: Path, memory_root: Path) -> list[Path]:
    sources: list[Path] = []
    start = memory_root / "00-start-here.md"
    if start.exists():
        sources.append(start)
    sources.extend(iter_markdown(memory_root / "indexes", memory_root))
    if memory_root == root:
        sources.extend(iter_markdown(memory_root / "domains", memory_root))
    sources.extend(iter_markdown(memory_root / "wiki", memory_root))
    return sorted(set(sources))


def wiki_pages(memory_root: Path) -> list[Path]:
    return iter_markdown(memory_root / "wiki", memory_root)


def markdown_links(text: str) -> list[str]:
    links = [m.group(1).strip() for m in re.finditer(r"!?\[[^\]]*\]\(([^)]+)\)", text)]
    links.extend(m.group(1).strip() for m in re.finditer(r"(?m)^@([^\s]+\.md)\s*$", text))
    return links


def wikilinks(text: str) -> list[str]:
    return [m.group(1).split("|", 1)[0].split("#", 1)[0].strip() for m in re.finditer(r"\[\[([^\]]+)\]\]", text)]


def normalize_target(raw: str) -> str:
    target = raw.split("#", 1)[0].strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    return unquote(target)


def skip_target(target: str) -> bool:
    return (
        not target
        or "://" in target
        or target.startswith(("mailto:", "#", "/Users/"))
    )


def resolve_wikilink(target: str, memory_root: Path, by_stem: dict[str, list[Path]]) -> Path | None:
    if not target:
        return None
    candidate = memory_root / target
    if candidate.suffix != ".md":
        candidate = candidate.with_suffix(".md")
    if candidate.exists():
        return candidate.resolve()
    matches = by_stem.get(Path(target).stem, [])
    if len(matches) == 1:
        return matches[0].resolve()
    return None


def audit_links(root: Path, memory_root: Path, issues: list[MemoryIssue]) -> dict[Path, set[Path]]:
    pages = graph_sources(root, memory_root)
    wiki = wiki_pages(memory_root)
    by_stem: dict[str, list[Path]] = {}
    for page in wiki:
        by_stem.setdefault(page.stem, []).append(page)

    inbound: dict[Path, set[Path]] = {page.resolve(): set() for page in wiki}

    for source in pages:
        text = source.read_text(errors="replace")
        for raw in markdown_links(text):
            target = normalize_target(raw)
            if skip_target(target):
                continue
            dest = (source.parent / target).resolve()
            if not dest.exists():
                issues.append(MemoryIssue(
                    "error",
                    "memory_broken_link",
                    rel(source, root),
                    f"Missing target: {raw}",
                ))
                continue
            if dest in inbound and dest != source.resolve():
                inbound[dest].add(source.resolve())

        for raw in wikilinks(text):
            dest = resolve_wikilink(raw, memory_root, by_stem)
            if dest is None:
                issues.append(MemoryIssue(
                    "error",
                    "memory_broken_wikilink",
                    rel(source, root),
                    f"Missing wiki target: [[{raw}]]",
                ))
                continue
            if dest in inbound and dest != source.resolve():
                inbound[dest].add(source.resolve())

    return inbound


def audit_orphans(root: Path, inbound: dict[Path, set[Path]], issues: list[MemoryIssue]) -> None:
    for page, sources in sorted(inbound.items()):
        if sources:
            continue
        issues.append(MemoryIssue(
            "warn",
            "memory_orphan_wiki_page",
            rel(page, root),
            "Wiki page has no inbound link from memory start, indexes, or another wiki page.",
        ))


def audit_inbox(root: Path, memory_root: Path, issues: list[MemoryIssue], stale_days: int) -> None:
    inbox = memory_root / "inbox"
    if not inbox.exists():
        issues.append(MemoryIssue("error", "memory_missing_inbox", rel(inbox, root), "Memory inbox is missing."))
        return

    cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
    for path in sorted(p for p in inbox.rglob("*") if p.is_file()):
        try:
            inbox_parts = path.relative_to(inbox).parts
        except ValueError:
            inbox_parts = ()
        if inbox_parts and inbox_parts[0] in {"basic-memory", "legacy-project-brain"}:
            continue
        if path.name in {"README.md", ".gitkeep", ".DS_Store"}:
            continue
        if ".obsidian" in path.parts:
            continue
        modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
        if modified < cutoff:
            issues.append(MemoryIssue(
                "warn",
                "memory_stale_inbox_item",
                rel(path, root),
                f"Inbox item older than {stale_days} days.",
            ))


def audit_skill_index(root: Path, memory_root: Path, issues: list[MemoryIssue]) -> None:
    skills_dir = root / ".agents" / "skills"
    index = memory_root / "indexes" / "skills.md"
    if not skills_dir.exists() or not index.exists():
        return
    text = index.read_text(errors="replace")
    skill_paths = [p for p in skills_dir.iterdir() if p.is_dir() and (p / "SKILL.md").exists()]
    skill_paths.extend(p for p in skills_dir.glob("*/*") if p.is_dir() and (p / "SKILL.md").exists())
    for skill in sorted({p.name for p in skill_paths}):
        expected = f".agents/skills/{skill}/SKILL.md"
        if expected not in text and f"`{skill}`" not in text and skill not in text:
            issues.append(MemoryIssue(
                "warn",
                "memory_skill_not_indexed",
                rel(skills_dir / skill, root),
                f"Skill is missing from {rel(index, root)}.",
            ))


def select_memory_root(root: Path, scope: str) -> Path:
    if scope == "root":
        return root
    if scope == "legacy":
        return root / "memory"
    root_spine = [root / "00-start-here.md", root / "indexes", root / "wiki", root / "inbox"]
    if all(path.exists() for path in root_spine):
        return root
    return root / "memory"


def required_files_for(memory_root: Path, root: Path) -> list[str]:
    if memory_root == root:
        return [
            "00-start-here.md",
            "indexes/domains.md",
            "indexes/skills.md",
            "indexes/sources.md",
            "indexes/outputs.md",
            "wiki/README.md",
        ]
    return ["00-start-here.md", "wiki/start-here.md", "indexes/domains.md", "indexes/skills.md", "indexes/sources.md"]


def run(root: Path, stale_days: int = 14, scope: str = "auto") -> list[MemoryIssue]:
    root = root.resolve()
    memory_root = select_memory_root(root, scope)
    issues: list[MemoryIssue] = []

    if not memory_root.exists():
        return [MemoryIssue("error", "memory_root_missing", rel(memory_root, root), "Memory root is missing.")]

    for required in required_files_for(memory_root, root):
        path = memory_root / required
        if not path.exists():
            issues.append(MemoryIssue("error", "memory_required_file_missing", rel(path, root), "Required memory file is missing."))

    inbound = audit_links(root, memory_root, issues)
    audit_orphans(root, inbound, issues)
    audit_inbox(root, memory_root, issues, stale_days)
    audit_skill_index(root, memory_root, issues)
    return issues


def render_markdown(root: Path, issues: list[MemoryIssue]) -> str:
    counts = {
        "error": sum(1 for issue in issues if issue.level == "error"),
        "warn": sum(1 for issue in issues if issue.level == "warn"),
        "info": sum(1 for issue in issues if issue.level == "info"),
    }
    lines = [
        "# Memory Graph Audit",
        "",
        f"Root: `{root.resolve()}`",
        f"Generated: `{datetime.now().astimezone().isoformat(timespec='seconds')}`",
        "",
        "## Summary",
        "",
        f"- Errors: {counts['error']}",
        f"- Warnings: {counts['warn']}",
        f"- Info: {counts['info']}",
        "",
    ]
    if not issues:
        lines.append("No memory graph issues found.")
        return "\n".join(lines)
    for level in ("error", "warn", "info"):
        bucket = [issue for issue in issues if issue.level == level]
        if not bucket:
            continue
        lines.extend([f"## {level.title()}s", ""])
        for issue in bucket:
            lines.append(f"- `{issue.code}` [{issue.path}] {issue.message}")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root, default: current directory")
    parser.add_argument("--json", action="store_true", help="Emit JSON instead of markdown")
    parser.add_argument("--stale-days", type=int, default=14, help="Warn when inbox items are older than this many days")
    parser.add_argument("--scope", choices=["auto", "root", "legacy"], default="auto", help="Memory graph scope")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    issues = run(root, stale_days=args.stale_days, scope=args.scope)
    if args.json:
        print(json.dumps({"root": str(root), "issues": [asdict(issue) for issue in issues]}, indent=2))
    else:
        print(render_markdown(root, issues))
    return 1 if any(issue.level == "error" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
