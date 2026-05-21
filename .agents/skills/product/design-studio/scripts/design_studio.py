#!/usr/bin/env python3
"""Small helper for Agentic Business OS design-studio workspaces."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path


ROOT = Path.cwd()
PROJECT_ROOT = ROOT / "projects" / "design-studio"
OUTPUT_ROOT = ROOT / "outputs" / "design-studio"
TMP_ROOT = ROOT / "tmp" / "design-studio"
STITCH_ENDPOINT = "https://stitch.googleapis.com/mcp"


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "design-project"


def today() -> str:
    return dt.datetime.now(dt.timezone.utc).astimezone().strftime("%Y-%m-%d")


def write_once(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(content, encoding="utf-8")


def append_line_once(path: Path, line: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text(encoding="utf-8") if path.exists() else ""
    if line not in existing:
        with path.open("a", encoding="utf-8") as handle:
            if existing and not existing.endswith("\n"):
                handle.write("\n")
            handle.write(line + "\n")


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    parent = path.parent
    for index in range(2, 1000):
        candidate = parent / f"{stem}-{index}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not find a unique path for {path}")


def init_project(args: argparse.Namespace) -> int:
    slug = args.slug or slugify(args.name)
    base = PROJECT_ROOT / slug
    output_base = OUTPUT_ROOT / slug
    incoming = TMP_ROOT / slug / "incoming"

    for directory in [
        base / "prompts",
        base / "iterations",
        base / "references" / "files",
        base / "references" / "descriptions",
        output_base,
        output_base / "screens",
        output_base / "benchmarks",
        incoming,
    ]:
        directory.mkdir(parents=True, exist_ok=True)

    write_once(PROJECT_ROOT / "README.md", "# Design Studio\n\nDurable design workspaces for AI-assisted product, website, app, and brand design projects.\n\nEach project owns its `DESIGN.md`, reference inventory, Stitch prompt history, iteration notes, and handoff. Final accepted artifacts are exported or linked from `../../outputs/design-studio/`.\n")

    write_once(
        base / "README.md",
        f"""# {args.name}

Status: active
Created: {today()}
Surface: {args.surface}
Goal: {args.goal}

## Index

- [DESIGN.md](DESIGN.md) - living design system and current visual direction
- [REFERENCES.md](REFERENCES.md) - reference inventory and extracted lessons
- [stitch.md](stitch.md) - Stitch identifiers, prompt history, and current selected direction
- [handoff.md](handoff.md) - implementation handoff when approved
- [prompts/](prompts/) - prompts sent to Stitch
- [iterations/](iterations/) - critique and variant notes
- [references/](references/) - permanent reference files and descriptions
- [outputs](../../../outputs/design-studio/{slug}/) - accepted human-facing exports

## Temporary Drop Zone

Use `tmp/design-studio/{slug}/incoming/` for files that still need reference analysis.
""",
    )

    write_once(
        base / "DESIGN.md",
        f"""# {args.name} Design

## Positioning

{args.goal}

## Target Feeling

TBD

## Color Tokens

TBD

## Typography

TBD

## Layout Rules

TBD

## Components

TBD

## Imagery And Icons

TBD

## Motion

TBD

## Accessibility

TBD

## Do

- TBD

## Do Not

- TBD

## Open Questions

- TBD
""",
    )

    write_once(
        base / "REFERENCES.md",
        """# References

Reference files are analyzed first, then accepted files are moved or copied into `references/files/`.

| Date | File | Type | Relevance | Summary |
| --- | --- | --- | --- | --- |
""",
    )

    write_once(
        base / "stitch.md",
        """# Stitch

## MCP Status

Unknown. Check current session tools before generation.

## Project Identifiers

- Stitch project: TBD
- Current selected direction: TBD

## Prompt History

| Date | Prompt | Result | Notes |
| --- | --- | --- | --- |
""",
    )

    write_once(
        base / "handoff.md",
        """# Handoff

Status: not ready

Use this after the project owner chooses a design direction.
""",
    )

    write_once(base / "iterations" / "README.md", "# Iterations\n\nPer-iteration critique, variant comparison, and review notes.\n")
    write_once(base / "references" / "README.md", "# Reference Files\n\nPermanent accepted references and their concise descriptions.\n")
    write_once(
        output_base / "README.md",
        f"""# {args.name} Outputs

Accepted design exports and handoff artifacts for `projects/design-studio/{slug}`.

## Screens

## Benchmarks

## Share Exports
""",
    )
    write_once(incoming / ".gitkeep", "")

    print(json.dumps({"project": slug, "path": str(base), "incoming": str(incoming), "outputs": str(output_base)}, indent=2))
    return 0


def list_projects(_: argparse.Namespace) -> int:
    PROJECT_ROOT.mkdir(parents=True, exist_ok=True)
    projects = []
    for path in sorted(PROJECT_ROOT.iterdir()):
        if path.is_dir():
            projects.append({"project": path.name, "path": str(path)})
    print(json.dumps(projects, indent=2))
    return 0


def check_mcp(_: argparse.Namespace) -> int:
    codex_path = ROOT / ".codex" / "config.toml"
    claude_path = ROOT / ".mcp.json"
    codex_text = codex_path.read_text(encoding="utf-8") if codex_path.exists() else ""
    claude_text = claude_path.read_text(encoding="utf-8") if claude_path.exists() else ""

    claude_json: dict[str, object] = {}
    if claude_text.strip():
        try:
            loaded = json.loads(claude_text)
            if isinstance(loaded, dict):
                claude_json = loaded
        except json.JSONDecodeError:
            claude_json = {}

    mcp_servers = claude_json.get("mcpServers")
    stitch_server = mcp_servers.get("stitch") if isinstance(mcp_servers, dict) else None
    stitch_url = stitch_server.get("url") if isinstance(stitch_server, dict) else None
    stitch_type = stitch_server.get("type") if isinstance(stitch_server, dict) else None

    codex_configured = "[mcp_servers.stitch]" in codex_text and STITCH_ENDPOINT in codex_text
    claude_configured = stitch_url == STITCH_ENDPOINT and (stitch_type in ("http", None))
    result = {
        "endpoint": STITCH_ENDPOINT,
        "codex": {
            "config": str(codex_path),
            "configured": codex_configured,
            "auth_check": "Run `codex mcp list` and `tool_search` after restart. If `mcp__stitch__` tools are visible, runtime auth is working.",
        },
        "claude": {
            "config": str(claude_path),
            "configured": claude_configured,
            "auth_check": "Restart Claude Code and use `/mcp` to approve/connect the project Stitch server.",
        },
        "project_config_ready": codex_configured and claude_configured,
        "notes": [
            "This check validates project config only. Runtime readiness is proven by a successful Stitch tool call such as list_projects.",
            "Never print, persist, or commit Stitch credentials.",
        ],
    }
    print(json.dumps(result, indent=2))
    return 0 if codex_configured and claude_configured else 1


def require_project(project: str) -> Path:
    base = PROJECT_ROOT / project
    if not base.exists():
        raise FileNotFoundError(f"Unknown design-studio project: {project}")
    return base


def output_link(project: str, target: Path) -> str:
    project_output = (OUTPUT_ROOT / project).resolve()
    resolved = target.resolve()
    try:
        return resolved.relative_to(project_output).as_posix()
    except ValueError:
        try:
            return resolved.relative_to(ROOT.resolve()).as_posix()
        except ValueError:
            return str(target)


def manifest_id_for_output(path: str) -> str:
    value = path.lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "design-studio-output"


def output_files_for_manifest(target: Path) -> list[Path]:
    ignored_names = {"README.md", ".gitkeep", ".DS_Store"}
    if target.is_file():
        return [] if target.name in ignored_names else [target]
    files: list[Path] = []
    for path in sorted(target.rglob("*")):
        if path.is_file() and path.name not in ignored_names:
            files.append(path)
    return files


def register_output_manifest(project: str, target: Path, kind: str, title: str, notes: str | None) -> int:
    manifest = ROOT / "state" / "outputs-manifest.json"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    if manifest.exists():
        data = json.loads(manifest.read_text(encoding="utf-8"))
    else:
        data = {"schema_version": 1, "outputs": []}
    outputs = data.setdefault("outputs", [])
    if not isinstance(outputs, list):
        raise RuntimeError("state/outputs-manifest.json has invalid outputs shape")

    existing_paths = {str(record.get("output_path")) for record in outputs if isinstance(record, dict)}
    existing_ids = {str(record.get("id")) for record in outputs if isinstance(record, dict)}
    added = 0
    for path in output_files_for_manifest(target):
        rel_path = path.resolve().relative_to(ROOT.resolve()).as_posix()
        if rel_path in existing_paths:
            continue
        base_id = manifest_id_for_output(rel_path)
        record_id = base_id
        suffix = 2
        while record_id in existing_ids:
            record_id = f"{base_id}-{suffix}"
            suffix += 1
        outputs.append(
            {
                "id": record_id,
                "created_at": today(),
                "source_inbox_item": None,
                "domain": "product",
                "skill": "design-studio",
                "output_path": rel_path,
                "source_paths": [
                    f"projects/design-studio/{project}/README.md",
                    ".agents/skills/product/design-studio/SKILL.md",
                ],
                "memory_links": [
                    "projects/design-studio/README.md",
                    f"outputs/design-studio/{project}/README.md",
                ],
                "ingest_decision": f"design_studio_{kind}_output",
                "notes": notes or title,
            }
        )
        existing_paths.add(rel_path)
        existing_ids.add(record_id)
        added += 1

    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    return added


def register_output(args: argparse.Namespace) -> int:
    try:
        require_project(args.project)
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 2

    target = Path(args.path).expanduser()
    if not target.is_absolute():
        target = ROOT / target
    if not target.exists():
        print(f"Output path does not exist: {target}", file=sys.stderr)
        return 2

    output_base = OUTPUT_ROOT / args.project
    output_base.mkdir(parents=True, exist_ok=True)
    readme = output_base / "README.md"
    write_once(
        readme,
        f"# {args.project} Outputs\n\nAccepted design exports and handoff artifacts for `projects/design-studio/{args.project}`.\n",
    )

    heading = {
        "screen": "## Screens",
        "benchmark": "## Benchmarks",
        "share": "## Share Exports",
        "handoff": "## Handoff",
        "other": "## Other",
    }.get(args.kind, "## Other")

    text = readme.read_text(encoding="utf-8")
    if heading not in text:
        with readme.open("a", encoding="utf-8") as handle:
            if text and not text.endswith("\n"):
                handle.write("\n")
            handle.write(f"\n{heading}\n")

    notes = f" - {args.notes}" if args.notes else ""
    append_line_once(
        readme,
        f"- [{args.title}]({output_link(args.project, target)}){notes}",
    )
    manifest_count = register_output_manifest(args.project, target, args.kind, args.title, args.notes)

    print(
        json.dumps(
            {
                "project": args.project,
                "registered": str(target),
                "readme": str(readme),
                "manifest_records_added": manifest_count,
            },
            indent=2,
        )
    )
    return 0


def benchmark_init(args: argparse.Namespace) -> int:
    try:
        require_project(args.project)
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 2

    slug = args.slug or slugify(args.name)
    benchmark_dir = unique_path(OUTPUT_ROOT / args.project / "benchmarks" / f"{today()}-{slug}")
    screens_dir = benchmark_dir / "screens"
    screens_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "project": args.project,
        "date": today(),
        "name": args.name,
        "candidate": args.candidate or "TBD",
        "reference_strategy": args.reference_strategy,
        "target_reference_count": args.target_reference_count,
        "viewport_targets": ["desktop-first-viewport", "desktop-full-page", "mobile-first-viewport", "mobile-full-page"],
        "rubric": [
            {"criterion": "audience_fit", "weight": 20},
            {"criterion": "category_clarity", "weight": 20},
            {"criterion": "visual_craft", "weight": 20},
            {"criterion": "distinctive_first_impression", "weight": 15},
            {"criterion": "conversion_utility", "weight": 15},
            {"criterion": "responsive_and_motion_potential", "weight": 10},
        ],
        "references": [],
        "candidate_scores": [],
    }
    (benchmark_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    report = f"""# {args.name}

Date: {today()}

Purpose: judge whether the candidate design is strong enough against relevant real-world references before calling it final.

## Reference Strategy

{args.reference_strategy}

Target reference count: {args.target_reference_count}

## Candidate

{args.candidate or "TBD"}

## References

Add captured screenshots under `screens/` and record structured metadata in `manifest.json`.

## Rubric

| Criterion | Weight | Notes |
| --- | ---: | --- |
| Audience fit | 20 | Does it feel built for the intended buyer/user? |
| Category clarity | 20 | Is the offer, product, pain, trust, and next action clear? |
| Visual craft | 20 | Typography, spacing, surface quality, color, and polish. |
| Distinctive first impression | 15 | Does the first viewport have a memorable idea? |
| Conversion utility | 15 | Does the page help the user decide what to do next? |
| Responsive and motion potential | 10 | Can the concept become a polished responsive site/app? |

## Verdict

TBD

## Next Design Pass

- TBD
"""
    (benchmark_dir / "report.md").write_text(report, encoding="utf-8")

    register_args = argparse.Namespace(
        project=args.project,
        path=str(benchmark_dir),
        kind="benchmark",
        title=args.name,
        notes="benchmark workspace initialized",
    )
    register_output(register_args)

    print(json.dumps({"project": args.project, "benchmark": str(benchmark_dir), "screens": str(screens_dir)}, indent=2))
    return 0


def add_reference(args: argparse.Namespace) -> int:
    try:
        base = require_project(args.project)
    except FileNotFoundError as error:
        print(str(error), file=sys.stderr)
        return 2

    source = Path(args.source).expanduser()
    if not source.exists():
        print(f"Reference source does not exist: {source}", file=sys.stderr)
        return 2

    files_dir = base / "references" / "files"
    descriptions_dir = base / "references" / "descriptions"
    files_dir.mkdir(parents=True, exist_ok=True)
    descriptions_dir.mkdir(parents=True, exist_ok=True)

    destination = unique_path(files_dir / source.name)
    if args.move:
        shutil.move(str(source), str(destination))
    elif source.is_dir():
        shutil.copytree(source, destination)
    else:
        shutil.copy2(source, destination)

    description = args.description or ""
    if args.description_file:
        description = Path(args.description_file).read_text(encoding="utf-8").strip()
    description = description.strip() or "TBD"

    kind = args.kind or ("directory" if destination.is_dir() else destination.suffix.lstrip(".") or "file")
    relevance = args.relevance or "medium"
    description_path = descriptions_dir / f"{destination.stem}.md"
    write_once(
        description_path,
        f"""# {destination.name}

Date: {today()}
Type: {kind}
Relevance: {relevance}
Source file: ../files/{destination.name}

## Description

{description}

## Reusable Lessons

- TBD

## Avoid

- TBD
""",
    )

    safe_summary = description.replace("\n", " ")
    if len(safe_summary) > 140:
        safe_summary = safe_summary[:137].rstrip() + "..."
    append_line_once(
        base / "REFERENCES.md",
        f"| {today()} | [references/files/{destination.name}](references/files/{destination.name}) | {kind} | {relevance} | {safe_summary} |",
    )

    print(json.dumps({"project": args.project, "file": str(destination), "description": str(description_path)}, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Manage Agentic Business OS design-studio workspaces.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init = subparsers.add_parser("init", help="Create a design-studio project workspace.")
    init.add_argument("--name", required=True)
    init.add_argument("--slug")
    init.add_argument("--surface", required=True)
    init.add_argument("--goal", required=True)
    init.set_defaults(func=init_project)

    list_cmd = subparsers.add_parser("list", help="List design-studio projects.")
    list_cmd.set_defaults(func=list_projects)

    check = subparsers.add_parser("check-mcp", help="Check Codex and Claude project config for Stitch MCP.")
    check.set_defaults(func=check_mcp)

    benchmark = subparsers.add_parser("benchmark-init", help="Create a benchmark report workspace for a candidate design.")
    benchmark.add_argument("--project", required=True)
    benchmark.add_argument("--name", required=True)
    benchmark.add_argument("--slug")
    benchmark.add_argument("--candidate")
    benchmark.add_argument("--reference-strategy", default="Weighted mix of direct category relevance, adjacent category quality, and high-craft inspiration.")
    benchmark.add_argument("--target-reference-count", default="10-15")
    benchmark.set_defaults(func=benchmark_init)

    out = subparsers.add_parser("register-output", help="Register an accepted output artifact in the project output README.")
    out.add_argument("--project", required=True)
    out.add_argument("--path", required=True)
    out.add_argument("--title", required=True)
    out.add_argument("--kind", choices=["screen", "benchmark", "share", "handoff", "other"], default="other")
    out.add_argument("--notes")
    out.set_defaults(func=register_output)

    ref = subparsers.add_parser("add-reference", help="Register an analyzed reference file.")
    ref.add_argument("--project", required=True)
    ref.add_argument("--source", required=True)
    ref.add_argument("--description")
    ref.add_argument("--description-file")
    ref.add_argument("--kind")
    ref.add_argument("--relevance", choices=["high", "medium", "low"])
    ref.add_argument("--move", action="store_true")
    ref.set_defaults(func=add_reference)

    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
