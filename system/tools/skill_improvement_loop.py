#!/usr/bin/env python3
"""Analyze workflow failures and produce skill-improvement actions."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|pwd|secret|token|api[_-]?key|bearer)\s*[:=]\s*[^,\s]+"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"),
    re.compile(r"https://[^@\s]+:[^@\s]+@"),
]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or "skill-improvement"


def redact(value: str) -> str:
    redacted = value
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub(lambda match: match.group(0).split("=", 1)[0] + "=<redacted>" if "=" in match.group(0) else "<redacted>", redacted)
    return redacted


def clean_case(data: dict[str, Any]) -> dict[str, Any]:
    cleaned: dict[str, Any] = {}
    for key, value in data.items():
        if isinstance(value, str):
            cleaned[key] = redact(value)
        elif isinstance(value, list):
            cleaned[key] = [redact(item) if isinstance(item, str) else item for item in value]
        else:
            cleaned[key] = value
    return cleaned


def contains_any(text: str, needles: list[str]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


SYSTEM_SCOPE_TERMS = [
    "skill",
    "hook",
    "adapter",
    "agent",
    "sub-agent",
    "scheduler",
    "schedule",
    "workflow",
    "tool",
    "eval",
    "test",
    "prompt",
    "context",
    "file structure",
    "folder structure",
    "project structure",
    "load",
    "loaded",
    "read",
    "entrypoint",
    "agents.md",
    "claude.md",
    "00-start-here",
    "index",
    "indexes",
    "memory",
    "inbox",
    "wiki",
    "outputs",
    "sources",
    "state",
    "logs",
    "raw-chat",
    "raw chat",
    "computer use",
    "browser use",
    "mcp",
    "daily-planning",
    "recurring-review",
    "learning-review",
    "skill-improvement",
]


def in_system_improvement_scope(case: dict[str, Any], combined: str, skill: str) -> bool:
    if skill != "unknown":
        return True
    if str(case.get("workflow") or "").strip():
        return True
    return contains_any(combined, SYSTEM_SCOPE_TERMS)


def is_business_domain_case(combined: str, skill: str) -> bool:
    lowered = combined.lower()
    domain_terms = [
        "business fact",
        "business facts",
        "business topic",
        "product finding",
        "product analytics",
        "trial conversion",
        "pricing",
        "revenue",
        "mrr",
        "subscription",
        "support ticket",
        "accounting",
        "strategy decision",
    ]
    os_behavior_terms = [
        "skill failed",
        "hook failed",
        "adapter failed",
        "wrong context",
        "file structure",
        "folder structure",
        "memory structure",
        "loaded the wrong",
        "asked the wrong",
        "workflow behaved",
    ]
    if skill != "unknown":
        return False
    return contains_any(lowered, domain_terms) and not contains_any(lowered, os_behavior_terms)


def improvement_facets(combined: str) -> list[str]:
    facets: list[str] = []
    facet_needles = [
        ("trigger-and-description", ["trigger", "description", "called", "selected", "used the wrong skill"]),
        ("input-contract", ["asked", "input", "default", "default_inputs", "question"]),
        ("workflow-procedure", ["workflow", "step", "procedure", "manual", "actual skill", "script-only"]),
        ("output-contract", ["output", "json", "format", "where to place", "routing"]),
        ("memory-routing", ["memory", "inbox", "wiki", "ingest"]),
        ("memory-structure", ["file structure", "folder structure", "memory structure", "wiki", "inbox", "outputs", "sources", "state", "logs", "orphan", "graph"]),
        ("context-loading", ["load", "loaded", "read", "context", "entrypoint", "agents.md", "claude.md", "00-start-here", "index", "indexes", "missing file"]),
        ("hook-behavior", ["hook", "stop hook", "pretool", "posttool"]),
        ("adapter-contract", ["adapter", "browser use", "computer use"]),
        ("scheduler-behavior", ["scheduler", "schedule", "recurring", "daily-planning"]),
        ("eval-coverage", ["eval", "regression", "deterministic", "test"]),
        ("user-experience", ["confusing", "frustrated", "annoying", "happy", "useful", "expected"]),
    ]
    for name, needles in facet_needles:
        if mentions_outside_narrow_surfaces(combined) and name in {"hook-behavior", "adapter-contract"}:
            continue
        if contains_any(combined, needles):
            facets.append(name)
    return facets or ["workflow-procedure"]


def mentions_outside_narrow_surfaces(text: str) -> bool:
    lowered = text.lower()
    return any(
        phrase in lowered
        for phrase in [
            "outside skills",
            "outside skill",
            "outside skills/hooks/adapters",
            "outside skills, hooks, adapters",
            "not just skills",
            "not only skills",
            "not just skills/hooks/adapters",
            "not only skills/hooks/adapters",
        ]
    )


def analyze_case(data: dict[str, Any]) -> dict[str, Any]:
    case = clean_case(data)
    combined = " ".join(str(case.get(key, "")) for key in ["expected_behavior", "actual_behavior", "user_correction", "command", "tool", "failure"])
    skill = str(case.get("skill") or case.get("workflow") or "unknown")
    deterministic = bool(case.get("deterministic"))
    facets = improvement_facets(combined)

    owners: list[str] = []
    actions: list[str] = []
    checks: list[str] = []

    if is_business_domain_case(combined, skill) or not in_system_improvement_scope(case, combined, skill):
        return {
            "case_id": str(case.get("id") or slugify(skill)),
            "skill": skill,
            "improvement_scope": "out_of_scope",
            "improvement_facets": [],
            "summary": str(case.get("summary") or case.get("actual_behavior") or "Not a skill/system improvement candidate."),
            "recommended_owner_paths": ["domain-skill-or-memory-ingest"],
            "recommended_actions": [
                "do not patch skills from this case; route business/product facts through the relevant domain skill or memory-ingest flow"
            ],
            "regression_checks": [],
            "create_inbox_candidate": False,
            "redacted": case,
        }

    broadening_context = mentions_outside_narrow_surfaces(combined)

    if contains_any(combined, ["adapter", "computer use", "browser use", "default_inputs", "default inputs"]) and not broadening_context:
        owners.extend([".agents/adapters/", ".agents/skills/ops/adapter-builder/", ".agents/skills/ops/adapter-runner/"])
    if contains_any(combined, ["hook", "stop hook", "pretool", "posttool"]) and not broadening_context:
        owners.extend([".agents/hooks/", "system/tools/agentic_os_hooks.py"])
    if contains_any(combined, ["inbox", "memory", "wiki", "ingest"]):
        owners.extend([".agents/skills/knowledge/memory-ingest/", "state/ingest-manifest.json", "inbox/", "wiki/", "indexes/", "state/"])
    if contains_any(combined, ["file structure", "folder structure", "project structure", "orphan", "graph", "outputs", "sources"]):
        owners.extend(["indexes/project-map.md", "indexes/agentic-os-text-map.md", "indexes/README.md", "domains/", "wiki/", "outputs/", "sources/", "state/"])
    if contains_any(combined, ["load", "loaded", "read", "context", "entrypoint", "agents.md", "claude.md", "00-start-here", "index", "indexes", "missing file"]):
        owners.extend(["AGENTS.md", "CLAUDE.md", "00-start-here.md", "system/context/context_index.json", "indexes/"])
    if contains_any(combined, ["schedule", "recurring", "daily-planning"]):
        owners.extend([".agents/recurring.yaml", ".agents/schedules.yaml", ".agents/skills/ops/daily-planning/"])
    if skill != "unknown":
        owners.append(f".agents/skills/*/{skill}/")

    if not owners:
        owners.append("needs-owner-triage")

    if case.get("user_correction"):
        actions.append("patch the owning skill, hook, adapter, tool, or eval so the project owner's correction becomes the default behavior")
    for facet in facets:
        if facet == "trigger-and-description":
            actions.append("tighten the skill trigger/description so the right skill is selected at the right time")
        elif facet == "input-contract":
            actions.append("clarify required inputs, defaults, and when the skill should avoid asking the project owner")
        elif facet == "workflow-procedure":
            actions.append("update the skill procedure so future agents follow the intended workflow, not just backing scripts")
        elif facet == "output-contract":
            actions.append("clarify output format, artifact routing, and validation expectations")
        elif facet == "memory-routing":
            actions.append("clarify memory routing so durable candidates go through inbox/ingest instead of direct wiki edits")
        elif facet == "memory-structure":
            actions.append("update memory/file-structure docs, indexes, or audits so LLMs know where artifacts belong and the graph stays connected")
        elif facet == "context-loading":
            actions.append("update boot/context-loading docs or indexes so future agents load the right files before acting")
        elif facet == "hook-behavior":
            actions.append("add or update hook validation so runtime behavior matches the contract")
        elif facet == "adapter-contract":
            actions.append("update adapter contracts and runner/builder guidance for repeatable UI workflows")
        elif facet == "scheduler-behavior":
            actions.append("clarify schedule/recurring behavior and how daily planning should surface it")
        elif facet == "eval-coverage":
            actions.append("add regression coverage that exercises the skill behavior, not only helper scripts")
        elif facet == "user-experience":
            actions.append("adjust skill wording or flow to reduce user confusion/friction or preserve a praised pattern")
    if deterministic:
        actions.append("add or update a deterministic regression fixture")
        checks.append("agentic_os_eval")
    if contains_any(combined, ["secret", "password", "token", "private"]):
        actions.append("add redaction or fail-closed handling before any memory capture")
        checks.append("prompt-secret-scan")
    if not actions:
        actions.append("write a no-change rationale or create a redacted inbox candidate for later review")

    checks.extend(["repo_audit", "git_diff_check"])

    return {
        "case_id": str(case.get("id") or slugify(skill)),
        "skill": skill,
        "improvement_scope": "agentic_os",
        "improvement_facets": facets,
        "summary": str(case.get("summary") or case.get("actual_behavior") or "Workflow improvement candidate."),
        "recommended_owner_paths": sorted(set(owners)),
        "recommended_actions": list(dict.fromkeys(actions)),
        "regression_checks": sorted(set(checks)),
        "create_inbox_candidate": bool(case.get("durable", True)),
        "redacted": case,
    }


def render_markdown(analysis: dict[str, Any]) -> str:
    lines = [
        "# Skill Improvement Analysis",
        "",
        f"- Case: `{analysis['case_id']}`",
        f"- Skill/workflow: `{analysis['skill']}`",
        f"- Improvement scope: `{analysis.get('improvement_scope', 'agentic_os')}`",
        f"- Summary: {analysis['summary']}",
        "",
        "## Improvement Facets",
        "",
    ]
    lines.extend(f"- `{facet}`" for facet in analysis.get("improvement_facets", []))
    lines.extend([
        "",
        "## Owner Paths",
        "",
    ])
    lines.extend(f"- `{path}`" for path in analysis["recommended_owner_paths"])
    lines.extend(["", "## Recommended Actions", ""])
    lines.extend(f"- {action}" for action in analysis["recommended_actions"])
    lines.extend(["", "## Regression Checks", ""])
    lines.extend(f"- `{check}`" for check in analysis["regression_checks"])
    lines.extend(["", "## Redacted Case", "", "```json"])
    lines.append(json.dumps(analysis["redacted"], indent=2, sort_keys=True, ensure_ascii=False))
    lines.extend(["```", ""])
    return "\n".join(lines)


def write_inbox_candidate(root: Path, analysis: dict[str, Any], rendered: str) -> Path:
    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = inbox / f"{stamp}-{slugify(str(analysis['case_id']))}-improvement-candidate.md"
    path.write_text(
        "\n".join(
            [
                "---",
                f"title: {analysis['case_id']} skill improvement candidate",
                "type: skill-improvement-candidate",
                f"created_at: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
                "ingest_status: pending",
                "---",
                "",
                rendered,
            ]
        )
    )
    return path


def command_analyze(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    case_path = Path(args.case)
    if not case_path.is_absolute():
        case_path = root / case_path
    data = json.loads(case_path.read_text())
    analysis = analyze_case(data)
    rendered = render_markdown(analysis)
    if args.out:
        out = Path(args.out)
        if not out.is_absolute():
            out = root / out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(rendered)
        print(out.relative_to(root).as_posix())
    else:
        print(rendered)
    if args.create_inbox_candidate:
        path = write_inbox_candidate(root, analysis, rendered)
        print(path.relative_to(root).as_posix())
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    analyze = sub.add_parser("analyze", help="Analyze one JSON failure case")
    analyze.add_argument("--root", default=".")
    analyze.add_argument("--case", required=True, help="JSON case path")
    analyze.add_argument("--out", help="Optional markdown output path")
    analyze.add_argument("--create-inbox-candidate", action="store_true")
    analyze.set_defaults(func=command_analyze)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
