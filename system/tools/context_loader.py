#!/usr/bin/env python3
"""Deterministic context selection for Agentic Business OS.

This tool does not replace reading files. It answers "which files should I read
first for this task?" from a tracked ownership index plus skill manifests.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


DEFAULT_INDEX = "system/context/context_index.json"
DEFAULT_ALLOWED_ROLES = {
    "contract",
    "canonical",
    "rule",
    "skill",
    "manifest",
    "project",
    "state",
    "research",
    "reference",
    "memory",
    "output",
    "historical",
}
DEPRIORITIZED_ROLES = {"output", "historical"}


@dataclass
class ContextItem:
    path: str
    role: str
    reason: str
    topics: list[str]
    owner: str | None = None
    load_when: str | None = None


def repo_root_from(path: Path) -> Path:
    return path.resolve()


def load_index(root: Path, index_path: str | Path = DEFAULT_INDEX) -> dict[str, Any]:
    path = Path(index_path)
    if not path.is_absolute():
        path = root / path
    return json.loads(path.read_text())


def indexed_files(index: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["path"]: item for item in index.get("files", [])}


def normalize_path(path: str) -> str:
    return path.strip().removeprefix("./")


def resolve_indexed_path(root: Path, path: str) -> str:
    raw = normalize_path(path)
    parts = raw.split("/")
    if len(parts) < 4 or parts[0] != ".agents" or parts[1] != "skills":
        return raw
    skill = parts[2]
    rest = Path(*parts[3:])
    canonical = resolve_skill_dir(root, skill)
    if canonical is None:
        return raw
    candidate = canonical / rest
    if candidate.exists():
        return candidate.relative_to(root).as_posix()
    return raw


def path_exists(root: Path, path: str) -> bool:
    raw = resolve_indexed_path(root, path)
    if raw.endswith("/"):
        return (root / raw).is_dir()
    return (root / raw).exists()


def add_item(
    root: Path,
    out: list[ContextItem],
    seen: set[str],
    files: dict[str, dict[str, Any]],
    path: str,
    reason: str,
    role: str = "unindexed",
    include_deprioritized: bool = False,
) -> None:
    original_path = normalize_path(path)
    path = resolve_indexed_path(root, original_path)
    if not path or path in seen:
        return
    meta = files.get(path, files.get(original_path, {}))
    item_role = str(meta.get("role") or role)
    if item_role in DEPRIORITIZED_ROLES and not include_deprioritized:
        return
    seen.add(path)
    out.append(ContextItem(
        path=path,
        role=item_role,
        reason=reason,
        topics=list(meta.get("topics") or []),
        owner=meta.get("owner"),
        load_when=meta.get("load_when"),
    ))


def domain_items(root: Path, index: dict[str, Any], domain: str, include_deprioritized: bool) -> list[ContextItem]:
    domains = index.get("domains", {})
    if domain not in domains:
        raise SystemExit(f"unknown domain: {domain}")
    spec = domains[domain]
    files = indexed_files(index)
    out: list[ContextItem] = []
    seen: set[str] = set()
    for key, reason in (
        ("entrypoints", "domain entrypoint"),
        ("canonical", "domain canonical file"),
        ("deprioritize", "domain deprioritized file"),
    ):
        if key == "deprioritize" and not include_deprioritized:
            continue
        for path in spec.get(key, []):
            add_item(root, out, seen, files, path, reason, include_deprioritized=include_deprioritized)
    for path, meta in files.items():
        if domain in (meta.get("topics") or []):
            add_item(root, out, seen, files, path, "indexed topic match", include_deprioritized=include_deprioritized)
    return out


def manifest_bootstrap_docs(root: Path, skill: str, include_optional: bool) -> list[str]:
    skill_dir = resolve_skill_dir(root, skill)
    if skill_dir is None:
        return []
    manifest = skill_dir / "manifest.yaml"
    if not manifest.exists():
        return []
    docs: list[str] = []
    in_bootstrap = False
    bucket: str | None = None
    for raw in manifest.read_text(errors="replace").splitlines():
        if re.match(r"^[a-zA-Z_]+:", raw):
            in_bootstrap = raw.startswith("bootstrap_docs:")
            bucket = None
            continue
        if not in_bootstrap:
            continue
        bucket_match = re.match(r"^\s{2}([a-zA-Z_]+):\s*$", raw)
        if bucket_match:
            bucket = bucket_match.group(1)
            continue
        item_match = re.match(r"^\s{4}-\s+(.+?)\s*$", raw)
        if item_match and bucket:
            if bucket == "required" or include_optional:
                docs.append(item_match.group(1).strip().strip("'\""))
    return docs


def resolve_skill_dir(root: Path, skill: str) -> Path | None:
    skills = root / ".agents" / "skills"
    for path in sorted(skills.glob(f"*/{skill}")):
        if (path / "SKILL.md").exists():
            return path
    direct = skills / skill
    if (direct / "SKILL.md").exists():
        return direct
    return None


def skill_items(root: Path, index: dict[str, Any], skill: str, include_optional: bool) -> list[ContextItem]:
    files = indexed_files(index)
    out: list[ContextItem] = []
    seen: set[str] = set()
    resolved = resolve_skill_dir(root, skill)
    skill_dir = resolved.relative_to(root).as_posix() if resolved else f".agents/skills/{skill}"
    manifest = f"{skill_dir}/manifest.yaml"
    skill_md = f"{skill_dir}/SKILL.md"
    if path_exists(root, manifest):
        add_item(root, out, seen, files, manifest, "skill manifest", role="manifest", include_deprioritized=True)
    if path_exists(root, skill_md):
        add_item(root, out, seen, files, skill_md, "skill procedure", role="skill", include_deprioritized=True)
    for path in manifest_bootstrap_docs(root, skill, include_optional):
        add_item(root, out, seen, files, path, "manifest bootstrap doc", include_deprioritized=True)
    for path, meta in files.items():
        if skill in (meta.get("topics") or []) or path.startswith(f"{skill_dir}/"):
            add_item(root, out, seen, files, path, "indexed skill match", include_deprioritized=True)
    return out


def query_items(root: Path, index: dict[str, Any], query: str, include_deprioritized: bool) -> list[ContextItem]:
    terms = [term for term in re.findall(r"[a-z0-9-]+", query.lower()) if len(term) > 2]
    if not terms:
        return []
    files = indexed_files(index)
    scored: list[tuple[int, str, str]] = []
    for domain, spec in index.get("domains", {}).items():
        haystack = " ".join([domain, spec.get("description", ""), *spec.get("entrypoints", []), *spec.get("canonical", [])]).lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score + 2, domain, "domain query match"))
    for path, meta in files.items():
        haystack = " ".join([
            path,
            meta.get("role", ""),
            meta.get("owner", ""),
            meta.get("load_when", ""),
            " ".join(meta.get("topics") or []),
        ]).lower()
        score = sum(1 for term in terms if term in haystack)
        if score:
            scored.append((score, path, "file query match"))

    out: list[ContextItem] = []
    seen: set[str] = set()
    for _score, key, reason in sorted(scored, key=lambda item: (-item[0], item[1])):
        if key in index.get("domains", {}):
            for item in domain_items(root, index, key, include_deprioritized):
                add_item(root, out, seen, files, item.path, reason, item.role, include_deprioritized)
        else:
            add_item(root, out, seen, files, key, reason, include_deprioritized=include_deprioritized)
    return out


def validate_index(root: Path, index: dict[str, Any]) -> list[dict[str, str]]:
    issues: list[dict[str, str]] = []
    if index.get("schema_version") != 1:
        issues.append({"level": "error", "code": "context_index_schema", "path": DEFAULT_INDEX, "message": "schema_version must be 1"})

    domains = index.get("domains")
    files = index.get("files")
    if not isinstance(domains, dict):
        issues.append({"level": "error", "code": "context_index_domains", "path": DEFAULT_INDEX, "message": "domains must be an object"})
        domains = {}
    if not isinstance(files, list):
        issues.append({"level": "error", "code": "context_index_files", "path": DEFAULT_INDEX, "message": "files must be a list"})
        files = []

    roles = set((index.get("roles") or {}).keys()) or DEFAULT_ALLOWED_ROLES
    known_domains = set(domains.keys())
    seen_paths: set[str] = set()

    for domain, spec in domains.items():
        for key in ("entrypoints", "canonical", "deprioritize"):
            for path in spec.get(key, []):
                if not path_exists(root, path):
                    issues.append({
                        "level": "error",
                        "code": "context_index_missing_target",
                        "path": path,
                        "message": f"{domain}.{key} points to a missing file or directory",
                    })

    for item in files:
        path = normalize_path(str(item.get("path", "")))
        if not path:
            issues.append({"level": "error", "code": "context_index_missing_path", "path": DEFAULT_INDEX, "message": "file entry is missing path"})
            continue
        if path in seen_paths:
            issues.append({"level": "error", "code": "context_index_duplicate_path", "path": path, "message": "duplicate file entry"})
        seen_paths.add(path)
        if not path_exists(root, path):
            issues.append({"level": "error", "code": "context_index_missing_target", "path": path, "message": "indexed path is missing"})
        role = str(item.get("role", ""))
        if role not in roles:
            issues.append({"level": "error", "code": "context_index_unknown_role", "path": path, "message": f"unknown role: {role}"})
        topics = item.get("topics") or []
        for topic in topics:
            if topic in {"bootstrap", "context-loading", "scheduler-state", "recurring", "repo-health", "planning", "strategy", "writing", "memory", "priorities", "claude", "retrieval"}:
                continue
            if topic not in known_domains:
                issues.append({"level": "warn", "code": "context_index_unknown_topic", "path": path, "message": f"topic is not a domain: {topic}"})
    return issues


def render_markdown(items: list[ContextItem], title: str, root: Path) -> str:
    lines = [f"# {title}", ""]
    if not items:
        lines.append("No context files matched.")
        return "\n".join(lines)
    for idx, item in enumerate(items, start=1):
        suffix = f" ({item.role})" if item.role else ""
        exists = "" if path_exists(root, item.path) else " [missing]"
        lines.append(f"{idx}. `{item.path}`{suffix}{exists}")
        details = item.load_when or item.reason
        if details:
            lines.append(f"   - {details}")
    return "\n".join(lines)


def cmd_list_domains(args: argparse.Namespace) -> None:
    root = repo_root_from(Path(args.root))
    index = load_index(root, args.index)
    for name, spec in sorted(index.get("domains", {}).items()):
        print(f"{name}\t{spec.get('description', '')}")


def cmd_load(args: argparse.Namespace) -> None:
    root = repo_root_from(Path(args.root))
    index = load_index(root, args.index)
    items: list[ContextItem] = []
    seen: set[str] = set()
    files = indexed_files(index)

    def append_many(next_items: list[ContextItem]) -> None:
        for item in next_items:
            add_item(root, items, seen, files, item.path, item.reason, item.role, include_deprioritized=True)

    if args.skill:
        append_many(skill_items(root, index, args.skill, args.include_optional))
    if args.domain:
        for domain in args.domain:
            append_many(domain_items(root, index, domain, args.include_deprioritized))
    if args.query:
        append_many(query_items(root, index, args.query, args.include_deprioritized))

    if args.paths_only:
        for item in items:
            print(item.path)
        return
    if args.json:
        print(json.dumps([item.__dict__ for item in items], indent=2))
        return
    print(render_markdown(items, "Context Load Plan", root))


def cmd_validate(args: argparse.Namespace) -> None:
    root = repo_root_from(Path(args.root))
    index = load_index(root, args.index)
    issues = validate_index(root, index)
    if args.json:
        print(json.dumps({"issues": issues}, indent=2))
    elif issues:
        for issue in issues:
            print(f"{issue['level']}: {issue['code']} [{issue['path']}] {issue['message']}")
    else:
        print("context index ok")
    if any(issue["level"] == "error" for issue in issues):
        raise SystemExit(1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".")
    parser.add_argument("--index", default=DEFAULT_INDEX)
    sub = parser.add_subparsers(dest="cmd", required=True)

    domains = sub.add_parser("list-domains", help="list indexed context domains")
    domains.set_defaults(func=cmd_list_domains)

    load = sub.add_parser("load", help="print a deterministic context load plan")
    load.add_argument("--skill", help="Skill name, e.g. morning-coffee")
    load.add_argument("--domain", action="append", help="Context domain; can be repeated")
    load.add_argument("--query", help="Free-text query matched against the index")
    load.add_argument("--include-optional", action="store_true", help="Include optional/conditional manifest bootstrap docs")
    load.add_argument("--include-deprioritized", action="store_true", help="Include output/historical/deprioritized files")
    load.add_argument("--paths-only", action="store_true")
    load.add_argument("--json", action="store_true")
    load.set_defaults(func=cmd_load)

    validate = sub.add_parser("validate", help="validate context index targets and metadata")
    validate.add_argument("--json", action="store_true")
    validate.set_defaults(func=cmd_validate)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
