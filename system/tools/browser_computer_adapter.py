#!/usr/bin/env python3
"""Computer Use adapter contract runner.

Adapters are lower-trust, evidence-producing UI workflows for cases where no
API, MCP server, or project script exists. This runner does not automate the UI
by itself. It gives Computer Use runs a stable, MCP-like contract:
list adapter tools, show their recorded steps, record structured results, and
validate evidence before anything enters memory.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


REQUIRED_RUN_FIELDS = [
    "adapter",
    "workflow_name",
    "target",
    "tool_type",
    "status",
    "created_at",
    "freshness_requirement",
    "structured_values",
    "evidence_path",
    "confidence",
    "caveats",
]

REQUIRED_ADAPTER_FIELDS = [
    "name",
    "owner_domain",
    "purpose",
    "target_app",
    "tool_type",
    "login_requirements",
    "inputs",
    "outputs",
    "evidence_requirements",
    "freshness_window",
    "failure_modes",
    "confidence_rules",
    "recording_path",
    "source_contract",
    "last_verified_at",
    "status",
]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or "adapter-run"


def parse_key_values(items: Iterable[str]) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Expected key=value, got {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Empty key in {item!r}")
        parsed[key] = value.strip()
    return parsed


def parse_json_file(path: str, root: Path) -> Any:
    source = Path(path)
    if not source.is_absolute():
        source = root / source
    try:
        return json.loads(source.read_text())
    except FileNotFoundError as exc:
        raise ValueError(f"JSON file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {path}: {exc}") from exc


def parse_field_json(items: Iterable[str], root: Path) -> dict[str, Any]:
    parsed: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Expected key=json-path, got {item!r}")
        key, value = item.split("=", 1)
        key = key.strip()
        if not key:
            raise ValueError(f"Empty key in {item!r}")
        parsed[key] = parse_json_file(value.strip(), root)
    return parsed


def now_local() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def registry_path(root: Path) -> Path:
    return root / ".agents" / "adapters" / "registry.yaml"


def adapter_dir(root: Path, name: str) -> Path:
    return root / ".agents" / "adapters" / name


def source_contract_path(root: Path, name: str) -> Path:
    return root / "sources" / "adapters" / f"{name}.md"


def parse_registry(root: Path) -> list[dict[str, str]]:
    path = registry_path(root)
    if not path.exists():
        return []
    adapters: list[dict[str, str]] = []
    current: dict[str, str] | None = None
    for line in path.read_text().splitlines():
        name_match = re.match(r"\s*-\s+name:\s*(.+?)\s*$", line)
        if name_match:
            if current:
                adapters.append(current)
            current = {"name": name_match.group(1).strip().strip('"')}
            continue
        if current is None:
            continue
        field_match = re.match(r"\s{4}([A-Za-z0-9_]+):\s*(.*?)\s*$", line)
        if field_match:
            key, value = field_match.groups()
            current[key] = value.strip().strip('"')
    if current:
        adapters.append(current)
    return adapters


def parse_adapter_yaml(path: Path) -> dict[str, str]:
    data: dict[str, str] = {}
    if not path.exists():
        return data
    for line in path.read_text().splitlines():
        match = re.match(r"^([A-Za-z0-9_]+):\s*(.*?)\s*$", line)
        if match:
            key, value = match.groups()
            data[key] = value.strip().strip('"')
    return data


def rel(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def today_date() -> str:
    return datetime.now(timezone.utc).astimezone().date().isoformat()


def default_status(tool_type: str) -> str:
    if tool_type == "Browser":
        return "draft-browser"
    if tool_type == "Computer":
        return "deferred"
    return "active-fixture"


def yaml_list(items: list[str], fallback: list[str]) -> list[str]:
    values = items or fallback
    return [str(item).strip() for item in values if str(item).strip()]


def render_yaml_list(key: str, items: list[str], indent: str = "") -> list[str]:
    values = yaml_list(items, [])
    if not values:
        return [f"{indent}{key}: []"]
    lines = [f"{indent}{key}:"]
    lines.extend(f"{indent}  - {item}" for item in values)
    return lines


def render_yaml_map(key: str, items: list[str], indent: str = "") -> list[str]:
    parsed = parse_key_values(items)
    if not parsed:
        return []
    lines = [f"{indent}{key}:"]
    lines.extend(f"{indent}  {item_key}: {json.dumps(value)}" for item_key, value in parsed.items())
    return lines


def render_adapter_yaml(args: argparse.Namespace, name: str) -> str:
    status = args.status or default_status(args.tool_type)
    lines = [
        f"name: {name}",
        f"owner_domain: {args.owner_domain}",
        f"purpose: {args.purpose}",
        f"target_app: {args.target_app}",
        f"tool_type: {args.tool_type}",
        f"login_requirements: {args.login_requirements}",
    ]
    lines.extend(render_yaml_list("inputs", yaml_list(args.input, ["target", "checklist"])))
    lines.extend(render_yaml_map("default_inputs", args.default_input))
    lines.extend(render_yaml_list("outputs", yaml_list(args.output, ["status", "structured_values", "evidence_path", "confidence", "caveats"])))
    lines.extend(render_yaml_list("evidence_requirements", yaml_list(args.evidence_requirement, ["timestamp", "target", "redacted visible-state summary", "structured values"])))
    lines.extend(render_yaml_list("failure_modes", yaml_list(args.failure_mode, ["target unavailable", "login or manual verification required", "UI changed", "evidence missing"])))
    lines.extend(
        [
            f"freshness_window: {args.freshness}",
            "confidence_rules: high when evidence and structured values agree; medium when interpretation is needed; low when evidence is partial or stale.",
            "recording_path: sources/adapters/runs/",
            f"source_contract: sources/adapters/{name}.md",
            f"last_verified_at: \"{today_date()}\"",
            f"status: {status}",
            "",
        ]
    )
    return "\n".join(lines)


def render_steps(args: argparse.Namespace, name: str) -> str:
    inputs = yaml_list(args.input, ["target", "checklist"])
    outputs = yaml_list(args.output, ["status", "structured_values", "evidence_path", "confidence", "caveats"])
    return "\n".join(
        [
            f"# {name} Steps",
            "",
            f"Use {args.tool_type} for this workflow. Stop and record `blocked` if login, captcha, two-factor verification, sensitive confirmation, or missing evidence prevents a safe run.",
            "",
            "## Inputs",
            "",
            *[f"- `{item}`" for item in inputs],
            "",
            "## Expected Outputs",
            "",
            *[f"- `{item}`" for item in outputs],
            "",
            "## Procedure",
            "",
            "1. Open the target app or URL.",
            "2. Confirm the current page/window matches the adapter target.",
            "3. Follow the requested checklist or recorded workflow.",
            "4. Capture the required evidence artifact.",
            "5. Record structured values that are visible in the evidence.",
            "6. Save the run with:",
            "",
            "   ```bash",
            "   python3 system/tools/browser_computer_adapter.py record \\",
            f"     --adapter {name} \\",
            f"     --tool-type {args.tool_type} \\",
            "     --target \"<url-or-app>\" \\",
            "     --field result=\"<short-result>\"",
            "   ```",
            "",
            "7. Use `--create-inbox-envelope` only when the result has durable business, product, or system value.",
            "",
            "## Failure Behavior",
            "",
            "Record `blocked` or `failed` instead of guessing when:",
            "",
            *[f"- {item}" for item in yaml_list(args.failure_mode, ["target unavailable", "login or manual verification required", "UI changed", "evidence missing"])],
            "",
        ]
    )


def render_source_contract(args: argparse.Namespace, name: str) -> str:
    return "\n".join(
        [
            f"# {name} Adapter Contract",
            "",
            f"Purpose: {args.purpose}",
            "",
            "## Target",
            "",
            f"- App/site: {args.target_app}",
            f"- Tool type: {args.tool_type}",
            f"- Login: {args.login_requirements}",
            "",
            "## Evidence Rules",
            "",
            *[f"- {item}" for item in yaml_list(args.evidence_requirement, ["timestamp", "target", "redacted visible-state summary", "structured values"])],
            "- Store data-first evidence. Screenshots, raw accessibility trees, and exports are optional and should be used only when needed.",
            "- Do not store secrets, credentials, private account data, unrelated tabs, or raw Computer Use state that contains sensitive material.",
            "",
            "If the result affects durable strategy, conversion analysis, product priorities, or operating-system behavior, create an inbox envelope and let memory ingest decide whether to promote it.",
            "",
            "## Failure Rules",
            "",
            "Record `blocked` or `failed` when evidence is missing, the UI changes, manual verification appears, or the requested value cannot be read directly from captured evidence.",
            "",
        ]
    )


def render_registry_entry(args: argparse.Namespace, name: str) -> str:
    status = args.status or default_status(args.tool_type)
    lines = [
        f"  - name: {name}",
        f"    owner_domain: {args.owner_domain}",
        f"    purpose: {args.purpose}",
        f"    target_app: {args.target_app}",
        f"    tool_type: {args.tool_type}",
        f"    login_requirements: {args.login_requirements}",
        "    inputs:",
    ]
    lines.extend(f"      - {item}" for item in yaml_list(args.input, ["target", "checklist"]))
    if args.default_input:
        lines.append("    default_inputs:")
        defaults = parse_key_values(args.default_input)
        lines.extend(f"      {key}: {json.dumps(value)}" for key, value in defaults.items())
    lines.append("    outputs:")
    lines.extend(f"      - {item}" for item in yaml_list(args.output, ["status", "structured_values", "evidence_path", "confidence", "caveats"]))
    lines.append("    evidence_requirements:")
    lines.extend(f"      - {item}" for item in yaml_list(args.evidence_requirement, ["timestamp", "target", "redacted visible-state summary", "structured values"]))
    lines.extend(
        [
            f"    freshness_window: {args.freshness}",
            "    failure_modes:",
        ]
    )
    lines.extend(f"      - {item}" for item in yaml_list(args.failure_mode, ["target unavailable", "login or manual verification required", "UI changed", "evidence missing"]))
    lines.extend(
        [
            "    confidence_rules:",
            "      high: Evidence and structured values agree exactly.",
            "      medium: Evidence is visible but needs interpretation.",
            "      low: Evidence is missing, partial, stale, or unstable; record blocked instead of success.",
            "    recording_path: sources/adapters/runs/",
            f"    source_contract: sources/adapters/{name}.md",
            f"    last_verified_at: \"{today_date()}\"",
            f"    status: {status}",
        ]
    )
    return "\n".join(lines) + "\n"


def append_registry(root: Path, args: argparse.Namespace, name: str) -> None:
    path = registry_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    known = {item.get("name") for item in parse_registry(root)}
    if name in known:
        return
    if not path.exists():
        path.write_text("registry_version: 2\nadapters:\n")
    text = path.read_text().rstrip() + "\n"
    path.write_text(text + render_registry_entry(args, name))


def update_index(root: Path, args: argparse.Namespace, name: str) -> None:
    path = root / "indexes" / "ui-adapters.md"
    if not path.exists():
        return
    text = path.read_text()
    if f"`{name}`" in text:
        return
    line = f"- `{name}` - {args.purpose}\n"
    marker = "\n## Local Commands"
    if marker in text:
        text = text.replace(marker, f"{line}{marker}", 1)
    else:
        text = text.rstrip() + "\n" + line
    path.write_text(text)


def render_evidence(record: dict[str, object]) -> str:
    lines = [
        "# Computer Use Adapter Evidence",
        "",
        f"- Adapter: `{record['adapter']}`",
        f"- Workflow: `{record['workflow_name']}`",
        f"- Target: `{record['target']}`",
        f"- Tool type: `{record['tool_type']}`",
        f"- Status: `{record['status']}`",
        f"- Created: `{record['created_at']}`",
        f"- Freshness: `{record['freshness_requirement']}`",
        f"- Confidence: `{record['confidence']}`",
        "",
        "## Inputs",
        "",
    ]
    inputs = record.get("inputs")
    if isinstance(inputs, dict) and inputs:
        for key, value in sorted(inputs.items()):
            lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- none")
    lines.extend(["", "## Values", ""])
    values = record.get("structured_values")
    if isinstance(values, dict) and values:
        if any(isinstance(value, (dict, list)) for value in values.values()):
            lines.append("```json")
            lines.append(json.dumps(values, indent=2, sort_keys=True, ensure_ascii=False))
            lines.append("```")
        else:
            for key, value in sorted(values.items()):
                lines.append(f"- `{key}`: {value}")
    else:
        lines.append("- none")
    lines.extend(["", "## Evidence Artifacts", ""])
    artifacts = record.get("evidence_artifacts")
    if isinstance(artifacts, list) and artifacts:
        for artifact in artifacts:
            lines.append(f"- `{artifact}`")
    else:
        lines.append("- none")
    lines.extend(["", "## Caveats", ""])
    caveats = record.get("caveats")
    if isinstance(caveats, list) and caveats:
        for caveat in caveats:
            lines.append(f"- {caveat}")
    else:
        lines.append("- none")
    lines.append("")
    return "\n".join(lines)


def build_record(args: argparse.Namespace, root: Path, evidence_path: Path) -> dict[str, object]:
    inputs = parse_key_values(args.input)
    fields = parse_key_values(args.field)
    fields.update(parse_field_json(args.field_json, root))
    for values_path in args.values_json:
        values = parse_json_file(values_path, root)
        if not isinstance(values, dict):
            raise ValueError(f"--values-json must point to a JSON object, got {values_path}")
        fields.update(values)
    evidence_artifacts = [str(Path(item).as_posix()) for item in args.evidence_artifact]
    workflow = args.workflow or args.adapter
    return {
        "schema_version": 1,
        "adapter": args.adapter,
        "workflow_name": workflow,
        "target": args.target,
        "tool_type": args.tool_type,
        "status": args.status,
        "created_at": now_local(),
        "freshness_requirement": args.freshness,
        "inputs": inputs,
        "structured_values": fields,
        "evidence_path": rel(evidence_path, root),
        "evidence_artifacts": evidence_artifacts,
        "confidence": args.confidence,
        "caveats": args.caveat,
        "adapter_contract_path": f".agents/adapters/{args.adapter}/adapter.yaml",
        "steps_path": f".agents/adapters/{args.adapter}/steps.md",
        "source_contract_path": f"sources/adapters/{args.adapter}.md",
        "inbox_envelope_path": None,
    }


def write_inbox_envelope(root: Path, record: dict[str, object], record_path: Path) -> str:
    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    stem = f"{stamp}-{slugify(str(record['workflow_name']))}-adapter-envelope"
    path = inbox / f"{stem}.md"
    path.write_text(
        "\n".join(
            [
                "---",
                f"title: {record['workflow_name']} adapter envelope",
                "type: adapter-envelope",
                f"created_at: {record['created_at']}",
                f"owner_domain: {record['adapter']}",
                "ingest_status: pending",
                "---",
                "",
                f"# {record['workflow_name']} Adapter Envelope",
                "",
                f"- Adapter: `{record['adapter']}`",
                f"- Status: `{record['status']}`",
                f"- Record: `{rel(record_path, root)}`",
                f"- Evidence: `{record['evidence_path']}`",
                "",
                "## Summary",
                "",
                "Review this adapter result and decide whether it should promote to wiki, outputs, sources, process-only, dropped, or needs-the project owner.",
                "",
            ]
        )
    )
    return rel(path, root)


def command_list(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    adapters = parse_registry(root)
    if not adapters:
        print("No adapters registered.")
        return 1
    for item in adapters:
        name = item.get("name", "unknown")
        status = item.get("status", "unknown")
        tool_type = item.get("tool_type", item.get("tool", "unknown"))
        print(f"{name}\t{status}\t{tool_type}")
    return 0


def command_show(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    base = adapter_dir(root, args.adapter)
    contract = base / "adapter.yaml"
    steps = base / "steps.md"
    source = source_contract_path(root, args.adapter)
    if not contract.exists():
        print(f"Missing adapter contract: {rel(contract, root)}", file=sys.stderr)
        return 1
    print(f"# {args.adapter}")
    print()
    print(f"## Contract: {rel(contract, root)}")
    print()
    print(contract.read_text().rstrip())
    if steps.exists():
        print()
        print(f"## Steps: {rel(steps, root)}")
        print()
        print(steps.read_text().rstrip())
    if source.exists():
        print()
        print(f"## Source Contract: {rel(source, root)}")
        print()
        print(source.read_text().rstrip())
    return 0


def command_scaffold(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    name = slugify(args.name)
    base = adapter_dir(root, name)
    contract = base / "adapter.yaml"
    steps = base / "steps.md"
    source = source_contract_path(root, name)
    if base.exists() and not args.allow_existing:
        print(f"Adapter already exists: {rel(base, root)}", file=sys.stderr)
        return 1
    base.mkdir(parents=True, exist_ok=True)
    source.parent.mkdir(parents=True, exist_ok=True)
    contract.write_text(render_adapter_yaml(args, name))
    steps.write_text(render_steps(args, name))
    source.write_text(render_source_contract(args, name))
    append_registry(root, args, name)
    if not args.skip_index:
        update_index(root, args, name)
    print("\n".join([
        rel(contract, root),
        rel(steps, root),
        rel(source, root),
        rel(registry_path(root), root),
    ]))
    return 0


def command_record(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    known = {item.get("name") for item in parse_registry(root)}
    if args.adapter not in known and not args.allow_unregistered:
        print(f"Adapter {args.adapter!r} is not registered.", file=sys.stderr)
        return 1
    run_dir = root / "sources" / "adapters" / "runs"
    run_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    workflow = args.workflow or args.adapter
    stem = f"{stamp}-{slugify(workflow)}"
    evidence_path = run_dir / f"{stem}.md"
    record_path = run_dir / f"{stem}.json"
    record = build_record(args, root, evidence_path)
    if args.create_inbox_envelope:
        record["inbox_envelope_path"] = write_inbox_envelope(root, record, record_path)
    evidence_path.write_text(render_evidence(record))
    record_path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    print(rel(record_path, root))
    return 0


def recording_path(root: Path, name: str) -> Path:
    return root / "tmp" / "adapter-recordings" / f"{slugify(name)}.md"


def command_start_recording(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = recording_path(root, args.name)
    if path.exists() and not args.allow_existing:
        print(f"Recording notes already exist: {rel(path, root)}", file=sys.stderr)
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                f"# {slugify(args.name)} Adapter Recording Notes",
                "",
                f"- App: {args.app}",
                f"- Goal: {args.goal}",
                f"- Started: {now_local()}",
                "- Status: recording",
                "",
                "## Steps",
                "",
            ]
        )
    )
    print(rel(path, root))
    return 0


def command_note_step(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    path = recording_path(root, args.name)
    if not path.exists():
        raise ValueError(f"Recording notes not found: {rel(path, root)}. Run start-recording first.")
    text = path.read_text().rstrip()
    step_count = len(re.findall(r"^\d+\. ", text, flags=re.MULTILINE))
    next_step = step_count + 1
    entry = "\n".join(
        [
            "",
            f"{next_step}. {args.action}",
            f"   - Visible anchor: {args.visible_anchor}",
            f"   - Expected state: {args.expected_state}",
            f"   - Failure/block condition: {args.failure_block}",
            f"   - Evidence: {args.evidence}",
        ]
    )
    path.write_text(text + entry + "\n")
    print(rel(path, root))
    return 0


def adapter_schema_path(root: Path, name: str) -> Path | None:
    contract_data = parse_adapter_yaml(adapter_dir(root, name) / "adapter.yaml")
    schema = contract_data.get("output_schema") or contract_data.get("output_schema_path")
    if not schema:
        return None
    path = Path(schema)
    if not path.is_absolute():
        path = root / path
    return path


def schema_type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int) and not isinstance(value, bool):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    return type(value).__name__


def type_matches(value: Any, expected: str) -> bool:
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    return schema_type_name(value) == expected


def validate_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    issues: list[str] = []
    expected_type = schema.get("type")
    if isinstance(expected_type, list):
        if not any(type_matches(value, item) for item in expected_type):
            issues.append(f"{path}: expected one of {expected_type}, got {schema_type_name(value)}")
            return issues
    elif isinstance(expected_type, str):
        if not type_matches(value, expected_type):
            issues.append(f"{path}: expected {expected_type}, got {schema_type_name(value)}")
            return issues

    if isinstance(value, dict):
        required = schema.get("required", [])
        if isinstance(required, list):
            for key in required:
                if key not in value:
                    issues.append(f"{path}: missing required key {key}")
        properties = schema.get("properties", {})
        if isinstance(properties, dict):
            for key, child_schema in properties.items():
                if key in value and isinstance(child_schema, dict):
                    issues.extend(validate_schema(value[key], child_schema, f"{path}.{key}"))
        if schema.get("additionalProperties") is False and isinstance(properties, dict):
            allowed = set(properties)
            for key in value:
                if key not in allowed:
                    issues.append(f"{path}: unexpected key {key}")

    if isinstance(value, list):
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            issues.append(f"{path}: expected at least {min_items} items, got {len(value)}")
        max_items = schema.get("maxItems")
        if isinstance(max_items, int) and len(value) > max_items:
            issues.append(f"{path}: expected at most {max_items} items, got {len(value)}")
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for index, item in enumerate(value):
                issues.extend(validate_schema(item, item_schema, f"{path}[{index}]"))

    return issues


def validate_adapters(root: Path) -> list[str]:
    issues: list[str] = []
    adapters = parse_registry(root)
    if not adapters:
        return ["adapter registry is missing or empty"]
    for adapter in adapters:
        name = adapter.get("name")
        if not name:
            issues.append("registered adapter missing name")
            continue
        for field in REQUIRED_ADAPTER_FIELDS:
            if field not in adapter:
                issues.append(f"{name}: registry missing {field}")
        base = adapter_dir(root, name)
        contract = base / "adapter.yaml"
        steps = base / "steps.md"
        source = source_contract_path(root, name)
        if not contract.exists():
            issues.append(f"{name}: missing {rel(contract, root)}")
        else:
            contract_data = parse_adapter_yaml(contract)
            for field in ["name", "tool_type", "status", "source_contract"]:
                if field not in contract_data:
                    issues.append(f"{name}: adapter.yaml missing {field}")
        if not steps.exists():
            issues.append(f"{name}: missing {rel(steps, root)}")
        if not source.exists():
            issues.append(f"{name}: missing {rel(source, root)}")
    return issues


def validate_runs(root: Path) -> list[str]:
    issues: list[str] = []
    run_dir = root / "sources" / "adapters" / "runs"
    for record_path in sorted(run_dir.glob("*.json")):
        try:
            data = json.loads(record_path.read_text())
        except Exception as exc:  # noqa: BLE001
            issues.append(f"{rel(record_path, root)}: invalid JSON: {exc}")
            continue
        for field in REQUIRED_RUN_FIELDS:
            if field not in data:
                issues.append(f"{rel(record_path, root)}: missing {field}")
        if data.get("status") not in {"success", "blocked", "failed"}:
            issues.append(f"{rel(record_path, root)}: invalid status {data.get('status')!r}")
        if data.get("confidence") not in {"high", "medium", "low"}:
            issues.append(f"{rel(record_path, root)}: invalid confidence {data.get('confidence')!r}")
        evidence = data.get("evidence_path")
        if not isinstance(evidence, str) or not (root / evidence).exists():
            issues.append(f"{rel(record_path, root)}: evidence_path missing or unreadable")
        adapter_name = data.get("adapter")
        if isinstance(adapter_name, str):
            schema_path = adapter_schema_path(root, adapter_name)
            if schema_path:
                if not schema_path.exists():
                    issues.append(f"{rel(record_path, root)}: output schema missing: {rel(schema_path, root)}")
                else:
                    try:
                        schema = json.loads(schema_path.read_text())
                    except json.JSONDecodeError as exc:
                        issues.append(f"{rel(schema_path, root)}: invalid JSON schema: {exc}")
                    else:
                        structured_values = data.get("structured_values")
                        if not isinstance(schema, dict):
                            issues.append(f"{rel(schema_path, root)}: output schema must be a JSON object")
                        else:
                            for issue in validate_schema(structured_values, schema, "structured_values"):
                                issues.append(f"{rel(record_path, root)}: {issue}")
    return issues


def command_validate(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    issues = validate_adapters(root) + validate_runs(root)
    if issues:
        print("# Adapter Validation")
        print()
        print(f"Errors: {len(issues)}")
        for issue in issues:
            print(f"- {issue}")
        return 1
    run_count = len(list((root / "sources" / "adapters" / "runs").glob("*.json")))
    adapter_count = len(parse_registry(root))
    print("# Adapter Validation")
    print()
    print("Errors: 0")
    print(f"Registered adapters: {adapter_count}")
    print(f"Run records: {run_count}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    list_parser = sub.add_parser("list", help="List registered adapter tools")
    list_parser.add_argument("--root", default=".")
    list_parser.set_defaults(func=command_list)

    show_parser = sub.add_parser("show", help="Show one adapter contract and steps")
    show_parser.add_argument("adapter")
    show_parser.add_argument("--root", default=".")
    show_parser.set_defaults(func=command_show)

    scaffold_parser = sub.add_parser("scaffold", help="Create an adapter contract, steps file, source contract, and registry entry")
    scaffold_parser.add_argument("--root", default=".")
    scaffold_parser.add_argument("--name", required=True, help="Adapter name; will be slugified")
    scaffold_parser.add_argument("--owner-domain", default="tooling")
    scaffold_parser.add_argument("--purpose", required=True)
    scaffold_parser.add_argument("--target-app", required=True)
    scaffold_parser.add_argument("--tool-type", choices=["Browser", "Computer", "Fixture"], default="Computer")
    scaffold_parser.add_argument("--login-requirements", default="Already-authorized session only; stop for passwords, captcha, two-factor verification, or sensitive confirmations.")
    scaffold_parser.add_argument("--input", action="append", default=[], help="Input field name")
    scaffold_parser.add_argument("--default-input", action="append", default=[], help="Default input as key=value for zero-prompt adapter runs")
    scaffold_parser.add_argument("--output", action="append", default=[], help="Output field name")
    scaffold_parser.add_argument("--evidence-requirement", action="append", default=[], help="Required evidence item")
    scaffold_parser.add_argument("--freshness", default="30 days unless the source contract overrides it")
    scaffold_parser.add_argument("--failure-mode", action="append", default=[], help="Known failure mode")
    scaffold_parser.add_argument("--status", help="Registry status; defaults by tool type")
    scaffold_parser.add_argument("--allow-existing", action="store_true")
    scaffold_parser.add_argument("--skip-index", action="store_true")
    scaffold_parser.set_defaults(func=command_scaffold)

    recording_parser = sub.add_parser("start-recording", help="Create persistent notes for an interactive adapter recording")
    recording_parser.add_argument("--root", default=".")
    recording_parser.add_argument("--name", required=True, help="Adapter or working recording name")
    recording_parser.add_argument("--app", required=True, help="Target app or surface")
    recording_parser.add_argument("--goal", required=True, help="Short recording goal")
    recording_parser.add_argument("--allow-existing", action="store_true")
    recording_parser.set_defaults(func=command_start_recording)

    note_parser = sub.add_parser("note-step", help="Append one recorded UI step to persistent adapter notes")
    note_parser.add_argument("--root", default=".")
    note_parser.add_argument("--name", required=True, help="Adapter or working recording name")
    note_parser.add_argument("--action", required=True)
    note_parser.add_argument("--visible-anchor", required=True)
    note_parser.add_argument("--expected-state", required=True)
    note_parser.add_argument("--failure-block", required=True)
    note_parser.add_argument("--evidence", default="redacted visible-state summary and extracted values")
    note_parser.set_defaults(func=command_note_step)

    record_parser = sub.add_parser("record", help="Record one adapter run")
    record_parser.add_argument("--root", default=".")
    record_parser.add_argument("--adapter", default="browser-computer-adapter")
    record_parser.add_argument("--workflow", help="Workflow name; defaults to adapter name")
    record_parser.add_argument("--target", required=True, help="Target URL, app, or fixture")
    record_parser.add_argument("--tool-type", choices=["Browser", "Computer", "Fixture"], default="Fixture")
    record_parser.add_argument("--input", action="append", default=[], help="Input as key=value")
    record_parser.add_argument("--field", action="append", default=[], help="Structured output as key=value")
    record_parser.add_argument("--field-json", action="append", default=[], help="Structured output as key=json-file; value may be any JSON type")
    record_parser.add_argument("--values-json", action="append", default=[], help="Merge a JSON object into structured_values")
    record_parser.add_argument("--evidence-artifact", action="append", default=[], help="Optional screenshot, export, recording note, or artifact path")
    record_parser.add_argument("--status", choices=["success", "blocked", "failed"], default="success")
    record_parser.add_argument("--confidence", choices=["high", "medium", "low"], default="high")
    record_parser.add_argument("--freshness", default="30d", help="Freshness requirement")
    record_parser.add_argument("--caveat", action="append", default=[], help="Caveat line")
    record_parser.add_argument("--create-inbox-envelope", action="store_true")
    record_parser.add_argument("--allow-unregistered", action="store_true")
    record_parser.set_defaults(func=command_record)

    validate_parser = sub.add_parser("validate", help="Validate adapter contracts and run evidence")
    validate_parser.add_argument("--root", default=".")
    validate_parser.set_defaults(func=command_validate)
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0].startswith("--"):
        argv = ["record"] + argv
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
