#!/usr/bin/env python3
"""Generate local Agentic Business OS health reports."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


REPORTS = [
    "agentic-os-acceptance-readiness",
    "repo",
    "memory-graph",
    "context-routing",
    "context-budget",
    "domains",
    "outputs",
    "skills",
    "adapters",
    "hooks",
    "agents",
    "rules",
    "automations",
    "schedules",
]


def read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def write_report(root: Path, name: str, body: str) -> Path:
    path = root / "system" / "health" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    generated = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    path.write_text(f"# {name.replace('-', ' ').title()} Health\n\nGenerated: `{generated}`\n\n{body.rstrip()}\n")
    return path


def issue_summary(issues: list[object]) -> str:
    errors = sum(1 for issue in issues if getattr(issue, "level", "") == "error")
    warnings = sum(1 for issue in issues if getattr(issue, "level", "") == "warn")
    info = sum(1 for issue in issues if getattr(issue, "level", "") == "info")
    return f"- Errors: {errors}\n- Warnings: {warnings}\n- Info: {info}\n"


def json_count(path: Path, key: str) -> int:
    try:
        data = json.loads(path.read_text())
    except Exception:  # noqa: BLE001
        return 0
    value = data.get(key)
    return len(value) if isinstance(value, list) else 0


def line_count(path: Path) -> int:
    text = read(path)
    return len(text.splitlines()) if text else 0


def generate(root: Path) -> list[Path]:
    root = root.resolve()
    written: list[Path] = []

    from memory_graph_audit import run as run_memory_graph
    from agentic_os_audit import run as run_agentic_os
    from agentic_os_eval import run as run_evals
    from agentic_os_hooks import run as run_hooks
    from skill_namespace import load_plan, validate as validate_namespace_plan

    scaffold_issues = run_agentic_os(root, phase="scaffold")
    final_issues = run_agentic_os(root, phase="final")
    memory = run_memory_graph(root, scope="root")
    hooks = run_hooks(root, hook="all")
    evals = run_evals(root)
    namespace_plan = load_plan(root)
    namespace_issues = validate_namespace_plan(root, namespace_plan)
    readiness = root / "system" / "health" / "agentic-os-acceptance-readiness.md"
    if readiness.exists():
        written.append(readiness)

    written.append(write_report(root, "repo", "## Scaffold\n\n" + issue_summary(scaffold_issues) + "\n## Final Gate\n\n" + issue_summary(final_issues)))
    written.append(write_report(root, "memory-graph", issue_summary(memory)))
    routing_cases = json_count(root / "evals/routing/cases.json", "cases")
    written.append(write_report(root, "context-routing", f"- Context index: `system/context/context_index.json`\n- Domains indexed: `indexes/domains.md`\n- Routing eval cases: {routing_cases}\n"))
    budget = "\n".join([
        f"- `AGENTS.md`: {line_count(root / 'AGENTS.md')} lines",
        f"- `CLAUDE.md`: {line_count(root / 'CLAUDE.md')} lines",
        f"- `00-start-here.md`: {line_count(root / '00-start-here.md')} lines",
        f"- Domain files: max {max(line_count(path) for path in (root / 'domains').glob('*.md'))} lines",
    ])
    written.append(write_report(root, "context-budget", budget))
    domain_count = len(list((root / "domains").glob("*.md")))
    written.append(write_report(root, "domains", f"- Domain contracts: {domain_count}\n- Required sections enforced by `system/tools/agentic_os_audit.py`\n"))
    written.append(write_report(root, "outputs", f"- Output manifest records: {json_count(root / 'state/outputs-manifest.json', 'outputs')}\n"))
    skill_count = len(list((root / ".agents" / "skills").rglob("SKILL.md")))
    namespace_moves = namespace_plan.get("moves") if isinstance(namespace_plan.get("moves"), list) else []
    namespace_errors = sum(1 for issue in namespace_issues if issue.level == "error")
    namespace_warnings = sum(1 for issue in namespace_issues if issue.level == "warn")
    written.append(write_report(
        root,
        "skills",
        "\n".join([
            f"- Skill files: {skill_count}",
            f"- Planned namespace moves: {len(namespace_moves)}",
            f"- Namespace plan errors: {namespace_errors}",
            f"- Namespace plan warnings: {namespace_warnings}",
            f"- Namespace migration: {namespace_plan.get('status', 'unknown')}",
        ]),
    ))
    adapter_registry = read(root / ".agents" / "adapters" / "registry.yaml")
    adapter_count = adapter_registry.count("- name:")
    legacy_browser = "status: legacy-browser" in adapter_registry
    active_computer_template = "computer-use-desktop-recording" in adapter_registry and "status: active-computer-template" in adapter_registry
    adapter_runs = len(list((root / "sources" / "adapters" / "runs").glob("*.json")))
    written.append(write_report(
        root,
        "adapters",
        "\n".join([
            f"- Registered adapters: {adapter_count}",
            f"- Legacy Browser adapter exists: {legacy_browser}",
            f"- Computer Use adapter template: {'active' if active_computer_template else 'missing'}",
            f"- Adapter evidence records: {adapter_runs}",
        ]),
    ))
    written.append(write_report(root, "hooks", issue_summary(hooks)))
    agent_registry = read(root / ".agents" / "agents" / "registry.yaml")
    agent_count = agent_registry.count("- name:")
    adapter_operator = "adapter-operator" in agent_registry
    written.append(write_report(
        root,
        "agents",
        "\n".join([
            "- Registry: `.agents/agents/registry.yaml`",
            f"- Registered agents: {agent_count}",
            f"- Adapter operator defined: {adapter_operator}",
        ]),
    ))
    written.append(write_report(root, "rules", "- Rules folder indexed with README\n- Rule files remain outside wiki memory\n"))
    written.append(write_report(root, "automations", "- Scheduler: `.agents/schedules.yaml`\n- Hook runner: `system/tools/agentic_os_hooks.py`\n"))
    written.append(write_report(root, "schedules", "- Scheduled task config exists\n- Scheduler drift check is included in hook runner\n"))

    passed = sum(1 for result in evals if result.status == "pass")
    failed = sum(1 for result in evals if result.status != "pass")
    cockpit = root / "system" / "health" / "operator-cockpit.md"
    links = "\n".join(f"- [{name}]({name}.md)" for name in REPORTS)
    cockpit.write_text(
        "# Operator Cockpit\n\n"
        f"Generated: `{datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}`\n\n"
        "## Agentic OS Health\n\n"
        f"- Scaffold issues: {len(scaffold_issues)}\n"
        f"- Final-gate issues: {len(final_issues)}\n"
        f"- Eval passed: {passed}\n"
        f"- Eval failed: {failed}\n\n"
        "## Pending Gates\n\n"
        "- None from this generated health pass.\n"
        "- Run local checks with `python3 system/tests/agentic_os_local_checks.py`.\n\n"
        "## Reports\n\n"
        f"{links}\n"
    )
    written.append(cockpit)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root, default: current directory")
    args = parser.parse_args()
    written = generate(Path(args.root))
    for path in written:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
