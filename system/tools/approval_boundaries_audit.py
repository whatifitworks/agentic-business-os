#!/usr/bin/env python3
"""Validate and compile the approval-boundaries contract.

Checks rules/approval-boundaries.yaml against
system/schemas/approval-boundaries.schema.yaml expectations (valid mode and
decisions, unique rule ids, non-empty tool matchers, stated intents) and keeps
the stdlib-readable mirror state/approval-boundaries.compiled.json in sync so
approval_gate.py works on machines without PyYAML.

Usage:
    python3 system/tools/approval_boundaries_audit.py            # validate + mirror sync check
    python3 system/tools/approval_boundaries_audit.py --compile  # validate + rewrite mirror
    python3 system/tools/approval_boundaries_audit.py --exit-zero
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BOUNDARIES_REL = "rules/approval-boundaries.yaml"
COMPILED_REL = "state/approval-boundaries.compiled.json"
VALID_MODES = {"observe", "enforce"}
VALID_DECISIONS = {"allow", "ask", "deny"}


def load_yaml(path: Path):
    try:
        import yaml  # type: ignore
    except ImportError:
        return None, "PyYAML not installed"
    try:
        return yaml.safe_load(path.read_text()), ""
    except Exception as exc:  # parse errors should read as validation failures
        return None, str(exc)


def validate(contract: dict) -> list[str]:
    problems: list[str] = []
    if contract.get("schema_version") != 1:
        problems.append("schema_version must be 1")
    if str(contract.get("mode", "")) not in VALID_MODES:
        problems.append(f"mode must be one of {sorted(VALID_MODES)}")
    defaults = contract.get("defaults")
    if not isinstance(defaults, dict) or str(defaults.get("unmatched", "")) not in VALID_DECISIONS:
        problems.append("defaults.unmatched must be allow | ask | deny")
    rules = contract.get("rules")
    if not isinstance(rules, list) or not rules:
        problems.append("rules must be a non-empty list")
        return problems
    seen_ids: set[str] = set()
    for i, rule in enumerate(rules):
        where = f"rules[{i}]"
        if not isinstance(rule, dict):
            problems.append(f"{where}: must be a mapping")
            continue
        rid = str(rule.get("id", "")).strip()
        if not rid:
            problems.append(f"{where}: missing id")
        elif rid in seen_ids:
            problems.append(f"{where}: duplicate id '{rid}'")
        seen_ids.add(rid)
        if not str(rule.get("intent", "")).strip():
            problems.append(f"{where} ({rid}): missing intent — every rule states why it exists")
        if str(rule.get("decision", "")) not in VALID_DECISIONS:
            problems.append(f"{where} ({rid}): decision must be allow | ask | deny")
        match = rule.get("match")
        tools = (match or {}).get("tools") if isinstance(match, dict) else None
        if not isinstance(tools, list) or not [t for t in tools if str(t).strip()]:
            problems.append(f"{where} ({rid}): match.tools must be a non-empty list")
        input_any = (match or {}).get("input_any") if isinstance(match, dict) else None
        if input_any is not None and (not isinstance(input_any, list) or not input_any):
            problems.append(f"{where} ({rid}): match.input_any, when present, must be a non-empty list")
    return problems


def compiled_form(contract: dict) -> str:
    return json.dumps(contract, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--compile", action="store_true",
                        help="Rewrite the compiled JSON mirror after validating")
    parser.add_argument("--exit-zero", action="store_true")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    source = root / BOUNDARIES_REL
    mirror = root / COMPILED_REL

    problems: list[str] = []
    if not source.exists():
        problems.append(f"{BOUNDARIES_REL} is missing")
        contract = None
    else:
        contract, err = load_yaml(source)
        if contract is None and err == "PyYAML not installed":
            # Degraded machine: validate the mirror so the gate still has a
            # trustworthy input, and say so.
            print("approval-boundaries: PyYAML unavailable — validating compiled mirror only")
            if not mirror.exists():
                problems.append(f"{COMPILED_REL} missing and YAML unreadable — run --compile where PyYAML exists")
            else:
                try:
                    contract = json.loads(mirror.read_text())
                except json.JSONDecodeError as exc:
                    problems.append(f"{COMPILED_REL}: invalid JSON: {exc}")
        elif contract is None:
            problems.append(f"{BOUNDARIES_REL}: YAML parse failed: {err}")

    if isinstance(contract, dict):
        problems.extend(validate(contract))

    if not problems and isinstance(contract, dict) and source.exists():
        expected = compiled_form(contract)
        if args.compile:
            mirror.parent.mkdir(parents=True, exist_ok=True)
            mirror.write_text(expected)
            print(f"approval-boundaries: compiled mirror written to {COMPILED_REL}")
        elif not mirror.exists():
            problems.append(f"{COMPILED_REL} missing — run: python3 system/tools/approval_boundaries_audit.py --compile")
        elif mirror.read_text() != expected:
            problems.append(f"{COMPILED_REL} out of sync with {BOUNDARIES_REL} — rerun --compile")

    if problems:
        print(f"approval-boundaries: FAIL ({len(problems)} problem(s))")
        for p in problems:
            print(f"  - {p}")
    else:
        mode = contract.get("mode") if isinstance(contract, dict) else "?"
        rules = len(contract.get("rules", [])) if isinstance(contract, dict) else 0
        print(f"approval-boundaries: PASS ({rules} rules, mode={mode})")
    return 0 if (args.exit_zero or not problems) else 1


if __name__ == "__main__":
    raise SystemExit(main())
