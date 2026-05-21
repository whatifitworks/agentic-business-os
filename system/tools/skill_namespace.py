#!/usr/bin/env python3
"""Validate, print, and optionally apply the skill namespace migration plan."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


PLAN_PATH = Path("state/skill-namespace-plan.json")
STALE_ROOT_LINK_PATTERN = re.compile(r"(?<![./])(?:\.\./){3}(?!\.\./)")


@dataclass
class PlanIssue:
    level: str
    code: str
    path: str
    message: str


def rel(path: Path, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def load_plan(root: Path, plan_path: Path = PLAN_PATH) -> dict[str, object]:
    return json.loads((root / plan_path).read_text())


def is_compatibility_wrapper(path: Path) -> bool:
    try:
        text = (path / "SKILL.md").read_text(errors="replace").lower()
    except OSError:
        return False
    return "compatibility wrapper" in text and "canonical" in text


def validate(root: Path, plan: dict[str, object]) -> list[PlanIssue]:
    issues: list[PlanIssue] = []
    moves = plan.get("moves")
    if not isinstance(moves, list):
        return [PlanIssue("error", "plan_moves_missing", str(PLAN_PATH), "Plan must contain a moves array.")]
    keep_flat_wrappers = bool(plan.get("keep_flat_wrappers", True))
    plan_applied = plan.get("status") == "applied"

    seen_skills: set[str] = set()
    seen_destinations: set[str] = set()
    for index, item in enumerate(moves, start=1):
        if not isinstance(item, dict):
            issues.append(PlanIssue("error", "plan_move_invalid", str(PLAN_PATH), f"Move {index} is not an object."))
            continue
        for field in ["skill", "namespace", "from", "to"]:
            if not item.get(field):
                issues.append(PlanIssue("error", "plan_move_field_missing", str(PLAN_PATH), f"Move {index} missing {field}."))
        skill = str(item.get("skill", ""))
        source = root / str(item.get("from", ""))
        dest = root / str(item.get("to", ""))
        if skill in seen_skills:
            issues.append(PlanIssue("error", "plan_duplicate_skill", skill, "Skill appears more than once in move plan."))
        seen_skills.add(skill)
        if dest.as_posix() in seen_destinations:
            issues.append(PlanIssue("error", "plan_duplicate_destination", rel(dest, root), "Destination appears more than once in move plan."))
        seen_destinations.add(dest.as_posix())
        source_is_wrapper = is_compatibility_wrapper(source)
        if keep_flat_wrappers and not (source / "SKILL.md").exists():
            issues.append(PlanIssue("error", "plan_source_missing", rel(source, root), "Source skill folder or SKILL.md is missing."))
        if not dest.parent.exists():
            issues.append(PlanIssue("error", "plan_destination_parent_missing", rel(dest.parent, root), "Destination namespace folder is missing."))
        if dest.exists() and not source_is_wrapper and not plan_applied:
            issues.append(PlanIssue("warn", "plan_destination_exists", rel(dest, root), "Destination already exists; move may already be partially applied."))

    expected_flat = sorted(p.name for p in (root / ".agents" / "skills").iterdir() if p.is_dir() and (p / "SKILL.md").exists())
    planned = sorted(seen_skills)
    for skill in expected_flat:
        if not keep_flat_wrappers:
            issues.append(PlanIssue("error", "plan_flat_skill_present", skill, "Flat skill wrappers are disabled because they create duplicate skill discovery entries."))
        elif skill not in planned:
            issues.append(PlanIssue("warn", "plan_flat_skill_unplanned", skill, "Flat skill exists but is not in namespace move plan."))
    return issues


def wrapper_text(skill: str, namespace: str) -> str:
    canonical = f"../{namespace}/{skill}/SKILL.md"
    return f"""---
name: {skill}
description: Compatibility wrapper for the namespaced {namespace}/{skill} skill. Use the canonical skill at {canonical}.
---

# {skill} Compatibility Wrapper

This is a compatibility wrapper. The canonical skill is [{namespace}/{skill}]({canonical}).

Load and follow the canonical `SKILL.md`. Do not duplicate procedure here.
"""


def rewrite_moved_root_links(skill_dir: Path, root: Path) -> list[str]:
    rewritten: list[str] = []
    for path in top_level_text_files(skill_dir):
        if not path.is_file() or path.suffix not in {".md", ".yaml", ".yml"}:
            continue
        text = path.read_text(errors="replace")
        updated = STALE_ROOT_LINK_PATTERN.sub("../../../../", text)
        if updated != text:
            path.write_text(updated)
            rewritten.append(rel(path, root))
    return rewritten


def preview_root_link_rewrites(skill_dir: Path, root: Path) -> list[str]:
    rewrites: list[str] = []
    if not skill_dir.exists():
        return rewrites
    for path in top_level_text_files(skill_dir):
        try:
            text = path.read_text(errors="replace")
        except OSError:
            continue
        if STALE_ROOT_LINK_PATTERN.search(text):
            rewrites.append(rel(path, root))
    return rewrites


def top_level_text_files(skill_dir: Path) -> list[Path]:
    if not skill_dir.exists():
        return []
    return sorted(
        path for path in skill_dir.iterdir()
        if path.is_file() and path.suffix in {".md", ".yaml", ".yml"}
    )


def verify_applied(root: Path, plan: dict[str, object]) -> list[PlanIssue]:
    issues: list[PlanIssue] = []
    moves = plan.get("moves")
    if not isinstance(moves, list):
        return [PlanIssue("error", "verify_moves_missing", str(PLAN_PATH), "Plan must contain a moves array.")]
    keep_flat_wrappers = bool(plan.get("keep_flat_wrappers", True))

    planned_skills: set[str] = set()
    for item in moves:
        if not isinstance(item, dict):
            issues.append(PlanIssue("error", "verify_move_invalid", str(PLAN_PATH), "Move item is not an object."))
            continue
        skill = str(item.get("skill", ""))
        namespace = str(item.get("namespace", ""))
        source = root / str(item.get("from", ""))
        dest = root / str(item.get("to", ""))
        source_skill = source / "SKILL.md"
        dest_skill = dest / "SKILL.md"
        planned_skills.add(skill)

        if not dest_skill.exists():
            issues.append(PlanIssue("error", "verify_destination_missing", rel(dest, root), "Namespaced destination skill is missing."))
            continue
        if is_compatibility_wrapper(dest):
            issues.append(PlanIssue("error", "verify_destination_is_wrapper", rel(dest, root), "Canonical namespaced skill must not be a compatibility wrapper."))

        if not source_skill.exists() and keep_flat_wrappers:
            issues.append(PlanIssue("error", "verify_wrapper_missing", rel(source, root), "Flat compatibility wrapper is missing."))
        elif source_skill.exists() and not is_compatibility_wrapper(source):
            issues.append(PlanIssue("error", "verify_wrapper_invalid", rel(source_skill, root), "Flat skill path exists but is not a compatibility wrapper."))
        elif source_skill.exists():
            expected = f"../{namespace}/{skill}/SKILL.md"
            text = source_skill.read_text(errors="replace")
            wrapper_target = (source / expected).resolve()
            if expected not in text:
                issues.append(PlanIssue("error", "verify_wrapper_target_missing", rel(source_skill, root), f"Wrapper does not point to {expected}."))
            if not wrapper_target.exists():
                issues.append(PlanIssue("error", "verify_wrapper_target_broken", rel(source_skill, root), f"Wrapper target does not exist: {expected}."))

        for path in top_level_text_files(dest):
            text = path.read_text(errors="replace")
            if STALE_ROOT_LINK_PATTERN.search(text):
                issues.append(PlanIssue("error", "verify_root_link_depth_unfixed", rel(path, root), "Moved top-level skill file still contains ../../../ root-style links."))

    flat_skills = [
        path for path in (root / ".agents" / "skills").iterdir()
        if path.is_dir() and (path / "SKILL.md").exists()
    ]
    for path in flat_skills:
        if path.name in planned_skills:
            if not keep_flat_wrappers:
                issues.append(PlanIssue("error", "verify_flat_wrapper_present", rel(path, root), "Flat compatibility wrapper should be removed to prevent duplicate skill discovery."))
            continue
        issues.append(PlanIssue("warn", "verify_unplanned_flat_skill", rel(path, root), "Flat skill exists but is not in the namespace plan."))
    return issues


def apply_plan(root: Path, plan: dict[str, object], approval_note: str) -> list[str]:
    moves = plan.get("moves")
    if not isinstance(moves, list):
        raise ValueError("Plan must contain a moves array.")

    operations = [f"approval: {approval_note}"]
    for item in moves:
        if not isinstance(item, dict):
            raise ValueError("Move item is not an object.")
        skill = str(item["skill"])
        namespace = str(item["namespace"])
        source = root / str(item["from"])
        dest = root / str(item["to"])
        source_skill = source / "SKILL.md"
        dest_skill = dest / "SKILL.md"

        if dest_skill.exists():
            if source_skill.exists() and not is_compatibility_wrapper(source):
                raise ValueError(f"Refusing to overwrite {rel(dest, root)} while non-wrapper source still exists at {rel(source, root)}.")
            operations.append(f"already moved: {rel(dest, root)}")
        else:
            if not source_skill.exists():
                raise ValueError(f"Source skill is missing: {rel(source, root)}")
            dest.parent.mkdir(parents=True, exist_ok=True)
            source.rename(dest)
            operations.append(f"moved: {rel(source, root)} -> {rel(dest, root)}")

        for rewritten in rewrite_moved_root_links(dest, root):
            operations.append(f"rewrote root links: {rewritten}")

        source.mkdir(parents=True, exist_ok=True)
        source_skill.write_text(wrapper_text(skill, namespace))
        operations.append(f"wrapper: {rel(source_skill, root)} -> {rel(dest_skill, root)}")

    return operations


def preview_apply_plan(root: Path, plan: dict[str, object]) -> list[str]:
    moves = plan.get("moves")
    if not isinstance(moves, list):
        raise ValueError("Plan must contain a moves array.")

    operations = ["dry-run: no files changed"]
    for item in moves:
        if not isinstance(item, dict):
            raise ValueError("Move item is not an object.")
        skill = str(item["skill"])
        namespace = str(item["namespace"])
        source = root / str(item["from"])
        dest = root / str(item["to"])
        source_skill = source / "SKILL.md"
        dest_skill = dest / "SKILL.md"

        if dest_skill.exists():
            operations.append(f"would keep existing canonical: {rel(dest, root)}")
        elif source_skill.exists():
            operations.append(f"would move: {rel(source, root)} -> {rel(dest, root)}")
        else:
            operations.append(f"would fail missing source: {rel(source, root)}")

        rewrite_source = dest if dest_skill.exists() else source
        for rewritten in preview_root_link_rewrites(rewrite_source, root):
            operations.append(f"would rewrite root links after move: {rewritten}")

        operations.append(f"would write wrapper: {rel(source_skill, root)} -> {rel(dest_skill, root)}")
        operations.append(f"wrapper canonical link: ../{namespace}/{skill}/SKILL.md")
    return operations


def render_markdown(root: Path, plan: dict[str, object], issues: list[PlanIssue]) -> str:
    moves = plan.get("moves") if isinstance(plan.get("moves"), list) else []
    lines = [
        "# Skill Namespace Plan",
        "",
        f"Status: `{plan.get('status', 'unknown')}`",
        f"Approval doc: `{plan.get('approval_doc', '')}`",
        f"Moves: {len(moves)}",
        "",
        "## Validation",
        "",
        f"- Errors: {sum(1 for issue in issues if issue.level == 'error')}",
        f"- Warnings: {sum(1 for issue in issues if issue.level == 'warn')}",
        "",
    ]
    if issues:
        for issue in issues:
            lines.append(f"- `{issue.level}` `{issue.code}` [{issue.path}] {issue.message}")
        lines.append("")
    lines.extend(["## Moves", ""])
    for item in moves:
        if isinstance(item, dict):
            lines.append(f"- `{item.get('from')}` -> `{item.get('to')}`")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root, default: current directory")
    parser.add_argument("--json", action="store_true", help="Emit JSON")
    parser.add_argument("--preview-apply", action="store_true", help="Preview approved move operations without changing files")
    parser.add_argument("--verify-applied", action="store_true", help="Verify the namespace migration has already been applied correctly")
    parser.add_argument("--apply", action="store_true", help="Apply the approved move plan and write compatibility wrappers")
    parser.add_argument("--approval-note", help="Required with --apply unless plan status is already approved")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    plan = load_plan(root)
    issues = validate(root, plan)
    if args.verify_applied:
        verify_issues = verify_applied(root, plan)
        if args.json:
            print(json.dumps({"issues": [asdict(issue) for issue in verify_issues]}, indent=2))
        else:
            print(render_markdown(root, plan, verify_issues))
        return 1 if any(issue.level == "error" for issue in verify_issues) else 0
    if args.preview_apply:
        print("\n".join(preview_apply_plan(root, plan)))
        return 0 if not any(issue.level == "error" for issue in issues) else 1
    if args.apply:
        if any(issue.level == "error" for issue in issues):
            print(render_markdown(root, plan, issues))
            return 1
        approval_note = args.approval_note
        if not approval_note and plan.get("status") != "approved":
            print("blocked: --apply requires --approval-note while plan status is not approved")
            return 2
        operations = apply_plan(root, plan, approval_note or "plan status approved")
        print("\n".join(operations))
        return 0
    if args.json:
        print(json.dumps({"plan": plan, "issues": [asdict(issue) for issue in issues]}, indent=2))
    else:
        print(render_markdown(root, plan, issues))
    return 1 if any(issue.level == "error" for issue in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
