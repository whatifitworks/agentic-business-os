#!/usr/bin/env python3
"""Create a review-first project onboarding pack."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class Tool:
    name: str
    category: str
    access_path: str
    purpose: str
    owner: str
    first_workflow: str
    risk: str


@dataclass
class Routine:
    title: str
    cadence: str
    summary: str


@dataclass
class Suggestion:
    id: str
    kind: str
    title: str
    summary: str
    reason: str
    safety: str
    recommended_decision: str
    proposed_destination: str


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "project"


def parse_tool(value: str) -> Tool:
    parts = [part.strip() for part in value.split(":")]
    name = parts[0] if parts and parts[0] else "Unknown tool"
    category = parts[1] if len(parts) > 1 and parts[1] else "unknown"
    access_path = parts[2] if len(parts) > 2 and parts[2] else "review required"
    purpose = parts[3] if len(parts) > 3 and parts[3] else "Purpose needs owner review."
    owner = parts[4] if len(parts) > 4 and parts[4] else "owner"
    first_workflow = parts[5] if len(parts) > 5 and parts[5] else "Define first read-only workflow."
    risk = parts[6] if len(parts) > 6 and parts[6] else "needs-permission"
    return Tool(
        name=name,
        category=category,
        access_path=access_path,
        purpose=purpose,
        owner=owner,
        first_workflow=first_workflow,
        risk=risk,
    )


def parse_routine(value: str) -> Routine:
    parts = [part.strip() for part in value.split(":")]
    title = parts[0] if parts and parts[0] else "Review routine"
    cadence = parts[1] if len(parts) > 1 and parts[1] else "review"
    summary = parts[2] if len(parts) > 2 and parts[2] else "Routine captured during onboarding."
    return Routine(title=title, cadence=cadence, summary=summary)


def load_answers_json(path: Path) -> dict[str, object]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise SystemExit("--answers-json must contain a JSON object")
    return data


def table_row(values: list[str]) -> str:
    return "| " + " | ".join(value.replace("\n", " ").strip() for value in values) + " |"


def make_suggestions(tools: list[Tool], routines: list[Routine], primary_goal: str) -> list[Suggestion]:
    suggestions: list[Suggestion] = [
        Suggestion(
            id="review-project-context",
            kind="review",
            title="Review starter project context",
            summary="Confirm the generated business profile, priorities, tool map, and open questions.",
            reason="The project should be correct before routines or tool setup are enabled.",
            safety="safe-local",
            recommended_decision="prepare",
            proposed_destination="context/",
        ),
        Suggestion(
            id="choose-first-routine",
            kind="routine",
            title="Choose the first operating routine",
            summary="Pick one repeated workflow to make reliable before adding more automation.",
            reason=f"The primary objective is: {primary_goal or 'make the project useful quickly'}.",
            safety="safe-local",
            recommended_decision="prepare",
            proposed_destination=".agents/skills/ or .agents/recurring.yaml",
        ),
    ]

    for tool in tools:
        tool_slug = slugify(tool.name)
        suggestions.append(
            Suggestion(
                id=f"review-{tool_slug}-setup",
                kind="connected-app",
                title=f"Review {tool.name} setup",
                summary=f"Assess whether {tool.name} should be connected or represented as a source contract.",
                reason=f"{tool.name} was listed under tool category: {tool.category}. First workflow: {tool.first_workflow}",
                safety="needs-permission",
                recommended_decision="review-later",
                proposed_destination="sources/ or .agents/adapters/",
            )
        )

    for routine in routines:
        routine_slug = slugify(routine.title)
        suggestions.append(
            Suggestion(
                id=f"prepare-{routine_slug}",
                kind="routine",
                title=routine.title,
                summary=routine.summary,
                reason=f"Captured as a {routine.cadence} routine during onboarding.",
                safety="safe-local",
                recommended_decision="prepare",
                proposed_destination=".agents/recurring.yaml or .agents/skills/",
            )
        )

    return suggestions[:20]


def priority_for_routine(routine: Routine) -> str:
    cadence = routine.cadence.lower()
    if "daily" in cadence:
        return "high"
    if "weekly" in cadence:
        return "high"
    return "medium"


def automation_rows(tools: list[Tool], routines: list[Routine]) -> list[str]:
    rows = [
        table_row(["Candidate", "Type", "Priority", "Safety", "Reason", "Next step"]),
        table_row(["---", "---", "---", "---", "---", "---"]),
        table_row([
            "Review starter project context",
            "review",
            "high",
            "safe-local",
            "Context should be correct before enabling routines.",
            "Review the proposed context files.",
        ]),
        table_row([
            "First operating routine",
            "routine",
            "high",
            "safe-local",
            "A useful project starts with one reliable repeated workflow.",
            "Choose one routine to codify.",
        ]),
        table_row([
            "Weekly project health review",
            "routine",
            "medium",
            "safe-local",
            "Catches stale tasks, missing context, and automation candidates.",
            "Keep as review-only until project cadence is clear.",
        ]),
    ]
    for tool in tools:
        rows.append(table_row([
            f"{tool.name} setup review",
            "connected-app",
            "medium",
            tool.risk or "needs-permission",
            tool.purpose,
            tool.first_workflow,
        ]))
    for routine in routines:
        rows.append(table_row([
            routine.title,
            "routine",
            priority_for_routine(routine),
            "safe-local",
            routine.summary,
            f"Prepare draft procedure for {routine.cadence} cadence.",
        ]))
    return rows


def render_project_agents_md(
    *,
    project_name: str,
    business_type: str,
    country: str,
    product: str,
    customer: str,
    primary_goal: str,
    tools: list[Tool],
    routines: list[Routine],
) -> str:
    tool_lines = (
        "\n".join(
            f"- {tool.name}: {tool.category}; purpose: {tool.purpose}; access path: {tool.access_path}; "
            f"owner: {tool.owner}; first workflow: {tool.first_workflow}; risk: {tool.risk}"
            for tool in tools
        )
        if tools
        else "- No tools were confirmed during onboarding. Read `context/tech-stack.md` before proposing tool setup."
    )
    routine_lines = (
        "\n".join(f"- {routine.title}: {routine.cadence}; {routine.summary}" for routine in routines)
        if routines
        else "- No routines were confirmed during onboarding. Use `projects/onboarding/README.md` to track follow-up."
    )

    return f"""# {project_name} Project

You are the assistant for {project_name}.

## Mission

Protect this project objective: {primary_goal or "Confirm and protect the owner's primary business outcome."}

Prefer work that improves that objective, operating reliability, knowledge quality, decision speed, or owner leverage.

## Business Snapshot

- Business type: {business_type}
- Region: {country or "Not captured"}
- Product/service: {product}
- Customers/users: {customer or "Not captured"}

## Startup

1. Read this file.
2. Read `00-start-here.md`.
3. Read `context/work.md` and `context/current-priorities.md` before planning, prioritizing, or making strategic recommendations.
4. Load only the relevant source from the source map below.
5. Put generated material with possible durable value into `inbox/` unless a skill says otherwise.

## Source Map

- `context/work.md` - business model, customers/users, product/service, mission, and operating rule.
- `context/current-priorities.md` - active priority contract and next focus.
- `context/goals.md` - active goals, milestones, and measurable outcomes.
- `context/tech-stack.md` - tools, source access, integration notes, and first workflows.
- `context/key-learnings.md` - durable lessons that should shape future work.
- `context/today.md` - current daily plan when daily planning is in use.
- `rules/approval-boundaries.md` - safe actions, approval-required actions, and never-request rules.
- `wiki/start-here.md` - durable knowledge entrypoint after reviewed promotion.
- `projects/onboarding/README.md` - onboarding workstream, open questions, and setup follow-up.
- `.agents/skills/` - reusable workflows; load the matching `SKILL.md` on demand.
- `.agents/recurring.yaml` - real recurring obligations after owner approval.
- `.agents/schedules.yaml` - scheduled workflows after cadence and tool access are proven.
- `inbox/` - review queue for generated artifacts, source drops, and candidate learnings.
- `outputs/` - final human-facing deliverables, reports, dashboards, and briefs.
- `sources/` - source cards, source contracts, raw exports, and adapter evidence.
- `state/` - manifests, queues, and machine-readable histories.
- `dropped/` - rejected material with reasons.

## Known Tools

{tool_lines}

Before connecting or acting through any external tool, read `context/tech-stack.md` and `rules/approval-boundaries.md`.

## Known Routines

{routine_lines}

Use these routines to decide which skills, recurring obligations, or schedules deserve promotion first.

## Safety And Approvals

- Do not ask for passwords, API keys, tokens, bank details, tax IDs, private keys, or credentials in chat.
- Ask before connecting external tools, sending messages, publishing content, changing external records, or enabling schedules.
- If a required MCP server, API integration, or other tool is unavailable, stop and say so clearly.
- Do not hide missing tools with nested agents, nested CLIs, or ad-hoc subprocess clients.
- Read `rules/approval-boundaries.md` before any action that can affect customers, money, accounts, public content, or external systems.

## Memory And Promotion

Generated outputs, source drops, setup lessons, workflow candidates, and durable business learnings start in `inbox/`.

Do not write durable synthesis directly to `wiki/`, `context/`, root docs, schedules, or rules unless the owner explicitly approves promotion or a reviewed ingest path says to do it.

## Skills

Use the matching skill under `.agents/skills/` when a workflow applies. Read only enough of the skill body and sidecars to do the task.

Use `project-onboarding` for onboarding refreshes, `daily-planning` for daily planning, `recurring-review` for recurring obligations, `memory-ingest` for inbox promotion, and `get-help` for setup or maintainer support.

## Development Rules

Preserve unrelated dirty worktree changes. Do not mark work complete unless actual work happened. Keep edits scoped to the requested task and the source map above.

This file is project-specific after onboarding. When pulling upstream template changes, keep private business details here and merge generic upstream instructions deliberately.
"""


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n")


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def build_pack(args: argparse.Namespace) -> Path:
    answers = load_answers_json(Path(args.answers_json)) if args.answers_json else {}
    project_name = args.project_name or str(answers.get("project_name", "")).strip()
    business_type = args.business_type or str(answers.get("business_type", "")).strip()
    country = args.country or str(answers.get("country", "")).strip()
    product = args.product or str(answers.get("product", "")).strip()
    customer = args.customer or str(answers.get("customer", "")).strip()
    primary_goal = args.primary_goal or str(answers.get("primary_goal", "")).strip()

    missing = [
        name
        for name, value in [
            ("project name", project_name),
            ("business type", business_type),
            ("product or service", product),
        ]
        if not value
    ]
    if missing:
        raise SystemExit(f"Missing required onboarding fields: {', '.join(missing)}")

    tool_values = list(args.tool or []) + [str(item) for item in answers.get("tools", []) if isinstance(item, str)]
    routine_values = list(args.routine or []) + [str(item) for item in answers.get("routines", []) if isinstance(item, str)]
    tools = [parse_tool(value) for value in tool_values]
    routines = [parse_routine(value) for value in routine_values]
    suggestions = make_suggestions(tools, routines, primary_goal)

    today = dt.date.today().isoformat()
    output_root = Path(args.out) if args.out else Path("inbox/project-onboarding") / f"{today}-{slugify(project_name)}"
    if output_root.exists() and not args.force:
        raise SystemExit(f"Output already exists: {output_root}. Use --force to overwrite generated files.")
    if args.dry_run:
        print(output_root)
        return output_root

    tool_rows = [
        table_row(["Tool", "Category", "Purpose", "Owner", "Access path", "First workflow", "Risk", "Initial handling"]),
        table_row(["---", "---", "---", "---", "---", "---", "---", "---"]),
    ]
    if tools:
        for tool in tools:
            tool_rows.append(table_row([
                tool.name,
                tool.category,
                tool.purpose,
                tool.owner,
                tool.access_path,
                tool.first_workflow,
                tool.risk,
                "Review before connecting",
            ]))
    else:
        tool_rows.append(table_row(["No tools captured yet", "", "", "Ask during follow-up"]))

    routine_rows = [
        table_row(["Routine", "Cadence", "Summary"]),
        table_row(["---", "---", "---"]),
    ]
    if routines:
        for routine in routines:
            routine_rows.append(table_row([routine.title, routine.cadence, routine.summary]))
    else:
        routine_rows.append(table_row(["No routines captured yet", "review", "Ask during follow-up"]))

    write(
        output_root / "README.md",
        f"""# Project Onboarding Pack

Project: {project_name}
Created: {today}

This pack is review-first. Promote approved files from `proposed/` into the live project only after review.

## Contents

- `onboarding-summary.md` - starter business/project context
- `tool-map.md` - tools and source access review
- `automation-candidates.md` - review-only automation ideas
- `starter-file-plan.md` - proposed project file placements
- `setup-suggestions.json` - machine-readable setup suggestions
- `proposed/` - draft starter files
- `proposed/AGENTS.md` - project-specific agent contract to promote after review

## Setup Status

The onboarding agent should already have run local bootstrap and baseline checks before presenting this pack. If it could not, the final onboarding response should name the blocker.

## Runtime Hook Activation

- Codex may require hooks to be enabled or approved in the app/runtime UI even though `.codex/config.toml` is present.
- Claude Code projects include `.claude/settings.json`; verify hook execution in the installed runtime.
- Static local checks can validate hook files, but cannot prove a runtime UI has activated them.

## After Review

Promote `proposed/AGENTS.md` first so future agent turns load the project-specific mission and source map.

Optional macOS background jobs, only after reviewing schedules and memory workflow:

```bash
bash .agents/install-launchd.sh
bash .agents/hooks/install-inbox-auto-ingest-launchd.sh
```

## Help

Ask the agent to run `get-help` or visit What If It Works: https://whatifitworks.co
""",
    )
    write(
        output_root / "onboarding-summary.md",
        f"""# Onboarding Summary

## Business Snapshot

- Project/business: {project_name}
- Country/region: {country or "Not captured"}
- Business type: {business_type}
- Product or service: {product}
- Main customers/users: {customer or "Not captured"}
- Primary objective: {primary_goal or "Not captured"}

## Routines Captured

{chr(10).join(routine_rows)}

## Open Questions

- Which routine should become the first fully defined skill or recurring workflow?
- Which tools are read-only sources, and which require explicit approval before any action?
- Which metrics or signals should the project protect first?
""",
    )
    write(
        output_root / "tool-map.md",
        f"""# Tool Map

{chr(10).join(tool_rows)}

## Rules

- Do not request credentials in chat.
- Keep external tools review-only until the owner approves the setup method.
- Prefer read-only exports, APIs, MCP servers, or source contracts before browser automation.
""",
    )
    write(
        output_root / "automation-candidates.md",
        "# Automation Candidates\n\n" + "\n".join(automation_rows(tools, routines)) + "\n",
    )
    write(
        output_root / "approval-boundaries.md",
        """# Approval Boundaries

## Safe Without Additional Approval

- Read local project files.
- Draft summaries, plans, reports, and reply suggestions.
- Create review-only setup plans.
- Run deterministic local checks that do not change external systems.

## Approval Required

- Connect external tools or accounts.
- Send customer-facing messages.
- Publish content.
- Change billing, accounting, legal, or customer records.
- Enable schedules or recurring jobs that touch external systems.

## Never Ask For In Chat

- Passwords, API keys, tokens, private keys, bank details, tax IDs, or credentials.
""",
    )
    write(
        output_root / "starter-file-plan.md",
        """# Starter File Plan

Promote only after review.

| Proposed file | Purpose |
| --- | --- |
| `AGENTS.md` | Project-specific agent contract with direct file references |
| `context/work.md` | Business and project operating context |
| `context/current-priorities.md` | Initial priority contract |
| `context/goals.md` | Initial goals and milestones |
| `context/tech-stack.md` | Tools, sources, and integration notes |
| `context/key-learnings.md` | Durable lessons that should shape future work |
| `context/today.md` | Optional same-day plan placeholder |
| `wiki/start-here.md` | Durable knowledge entrypoint |
| `rules/approval-boundaries.md` | Safe action and approval rules |
| `projects/onboarding/README.md` | Setup workstream and open questions |
| `.agents/recurring.yaml` | Real recurring obligations after approval |
| `.agents/schedules.yaml` | Scheduled workflows only after tools and cadence are proven |
""",
    )
    write_json(output_root / "setup-suggestions.json", [asdict(suggestion) for suggestion in suggestions])

    write(
        output_root / "proposed/AGENTS.md",
        render_project_agents_md(
            project_name=project_name,
            business_type=business_type,
            country=country,
            product=product,
            customer=customer,
            primary_goal=primary_goal,
            tools=tools,
            routines=routines,
        ),
    )
    write(
        output_root / "proposed/context/work.md",
        f"""# Work

## Mission

Support {project_name} by protecting: {primary_goal or "the owner's highest-priority business outcome"}.

## Business

- Type: {business_type}
- Region: {country or "Not captured"}
- Product/service: {product}
- Customers/users: {customer or "Not captured"}

## Operating Rule

External actions, tool connections, customer replies, publishing, financial changes, and account setup require owner approval.
""",
    )
    write(
        output_root / "proposed/context/current-priorities.md",
        f"""# Current Priorities

## Primary Objective

{primary_goal or "Confirm the first project objective."}

## Next Focus

1. Review the onboarding pack.
2. Choose the first operating routine to codify.
3. Confirm which tools should become read-only sources.
""",
    )
    write(
        output_root / "proposed/context/tech-stack.md",
        "# Tech Stack And Tools\n\n" + "\n".join(
            f"- {tool.name}: {tool.category}; purpose: {tool.purpose}; owner: {tool.owner}; access path: {tool.access_path}; first workflow: {tool.first_workflow}; risk: {tool.risk}"
            for tool in tools
        )
        + ("\n" if tools else "- No tools captured yet.\n"),
    )
    write(
        output_root / "proposed/context/goals.md",
        f"""# Goals

## Active Goals

- Confirm the first measurable goal for {project_name}.

## Milestones

- Review onboarding pack.
- Promote approved starter files.
- Enable the first useful routine.
""",
    )
    write(
        output_root / "proposed/context/key-learnings.md",
        """# Key Learnings

Durable lessons that should shape future work go here after review.

New candidate learnings should usually start in `inbox/` and be promoted through `memory-ingest`.
""",
    )
    write(
        output_root / "proposed/context/today.md",
        """# Today

## Active Task

- Review onboarding pack.

## Notes

- Replace this with a daily plan only if the project uses daily planning.
""",
    )
    write(
        output_root / "proposed/rules/approval-boundaries.md",
        """# Approval Boundaries

## Safe Without Additional Approval

- Read local project files.
- Draft summaries, plans, reports, and reply suggestions.
- Create review-only setup plans.
- Run deterministic local checks that do not change external systems.

## Approval Required

- Connect external tools or accounts.
- Send customer-facing messages.
- Publish content.
- Change billing, accounting, legal, or customer records.
- Enable schedules or recurring jobs that touch external systems.

## Never Ask For In Chat

- Passwords, API keys, tokens, private keys, bank details, tax IDs, or credentials.
""",
    )
    write(
        output_root / "proposed/wiki/start-here.md",
        f"""# Start Here

This wiki is the durable knowledge layer for {project_name}.

## First Links

- Business context: `context/work.md`
- Current priorities: `context/current-priorities.md`
- Tools: `context/tech-stack.md`

## Open Questions

- What should be remembered as durable business context?
- What should stay as process-only setup history?
- Which first routine should be automated or scheduled?
""",
    )
    write(
        output_root / "proposed/projects/onboarding/README.md",
        f"""# Onboarding

Setup workstream for {project_name}.

## Status

Review-first onboarding pack created. No tool connections or recurring actions are enabled by this file.

## Next Steps

- Review business context.
- Confirm tools and source access.
- Choose first routine.
- Promote approved files into the project.
""",
    )
    write(
        output_root / "proposed/.agents/recurring.yaml",
        """# Starter recurring obligations.
# Promote entries only after the owner confirms they are real obligations.

items:
  - id: review-project-onboarding
    title: Review project onboarding pack
    status: pending
    cadence: once
    skill: /project-onboarding
    notes: Confirm starter context, tools, and first routine.
""",
    )
    return output_root


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-name")
    parser.add_argument("--business-type")
    parser.add_argument("--country", default="")
    parser.add_argument("--product")
    parser.add_argument("--customer", default="")
    parser.add_argument("--primary-goal", default="")
    parser.add_argument(
        "--tool",
        action="append",
        help="Format: name:category:access path:purpose:owner:first workflow:risk",
    )
    parser.add_argument("--routine", action="append", help="Format: title:cadence:summary")
    parser.add_argument("--answers-json", help="Optional JSON object with project_name, business_type, product, tools, routines.")
    parser.add_argument("--out")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    output_root = build_pack(args)
    print(f"onboarding_pack={output_root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
