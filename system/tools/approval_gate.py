#!/usr/bin/env python3
"""Runtime approval-boundary gate.

Evaluates one tool call against rules/approval-boundaries.yaml and, in
`enforce` mode, returns an allow/ask/deny decision to the Claude Code
PreToolUse hook. In `observe` mode (the default contract state) it only logs
matched rules to the ledger, so an owner can watch what WOULD be gated for a
week before turning enforcement on.

Design rule number one: FAIL OPEN. A broken contract file, a missing ledger,
or a bug here must never block work or brick a session — on any internal
error the call is allowed and the error is recorded when possible.

Wired in .claude/settings.json:
    PreToolUse -> python3 system/tools/approval_gate.py --hook

Manual check (also used by evals):
    python3 system/tools/approval_gate.py --check --tool Bash \
        --input '{"command": "rm -rf build"}'
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path

BOUNDARIES_REL = "rules/approval-boundaries.yaml"
COMPILED_REL = "state/approval-boundaries.compiled.json"
GLOB_CHARS = set("*?[")
SEVERITY = {"allow": 0, "ask": 1, "deny": 2}
INPUT_HEAD_CHARS = 160

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ledger  # noqa: E402


def load_contract(root: Path) -> dict | None:
    """YAML contract when PyYAML is importable, else the compiled mirror."""
    yaml_path = root / BOUNDARIES_REL
    if yaml_path.exists():
        try:
            import yaml  # type: ignore
            data = yaml.safe_load(yaml_path.read_text())
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    compiled = root / COMPILED_REL
    if compiled.exists():
        try:
            data = json.loads(compiled.read_text())
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return None


def flatten_input(tool_input) -> str:
    try:
        return json.dumps(tool_input, ensure_ascii=False, sort_keys=True).lower()
    except (TypeError, ValueError):
        return str(tool_input).lower()


def pattern_hits(pattern: str, text: str) -> bool:
    p = pattern.lower()
    if GLOB_CHARS & set(p):
        return fnmatch.fnmatch(text, p)
    return p in text


def rule_matches(rule: dict, tool_name: str, input_text: str) -> bool:
    match = rule.get("match") or {}
    tool_patterns = [str(t) for t in match.get("tools", [])]
    if not any(fnmatch.fnmatch(tool_name.lower(), t.lower()) for t in tool_patterns):
        return False
    input_patterns = [str(p) for p in match.get("input_any", [])]
    if not input_patterns:
        return True
    return any(pattern_hits(p, input_text) for p in input_patterns)


def evaluate(contract: dict, tool_name: str, tool_input) -> dict:
    """Return {decision, matched: [rule ids], mode}."""
    input_text = flatten_input(tool_input)
    matched: list[dict] = []
    for rule in contract.get("rules", []) or []:
        if isinstance(rule, dict) and rule_matches(rule, tool_name, input_text):
            matched.append(rule)
    mode = str(contract.get("mode", "observe"))
    if not matched:
        unmatched = str((contract.get("defaults") or {}).get("unmatched", "allow"))
        return {"decision": unmatched, "matched": [], "mode": mode,
                "log": bool((contract.get("defaults") or {}).get("log_unmatched", False))}
    decision = max((str(r.get("decision", "allow")) for r in matched),
                   key=lambda d: SEVERITY.get(d, 0))
    return {"decision": decision, "matched": matched, "mode": mode, "log": True}


def log_evaluation(root: Path, tool_name: str, tool_input, result: dict) -> None:
    rule_ids = [str(r.get("id", "?")) for r in result["matched"]]
    intents = "; ".join(str(r.get("intent", "")) for r in result["matched"][:2])
    summary = (f"{result['decision']} {tool_name}"
               f" [{', '.join(rule_ids) if rule_ids else 'unmatched-default'}]"
               f" ({result['mode']} mode)")
    try:
        ledger.append_entry(
            root, "boundary_evaluation", summary, "hook:approval-gate",
            refs=[BOUNDARIES_REL],
            data={
                "tool": tool_name,
                "decision": result["decision"],
                "mode": result["mode"],
                "rules": rule_ids,
                "intent": intents,
                "input_head": flatten_input(tool_input)[:INPUT_HEAD_CHARS],
            })
    except Exception:
        pass  # logging must never break the gate


def emit_hook_decision(result: dict) -> None:
    reasons = "; ".join(
        f"{r.get('id')}: {r.get('intent', '')}" for r in result["matched"]) or "approval boundaries"
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": result["decision"],
            "permissionDecisionReason": f"approval-boundaries — {reasons}",
        }
    }))


def run_gate(root: Path, tool_name: str, tool_input, hook_mode: bool) -> int:
    contract = load_contract(root)
    if contract is None:
        return 0  # no contract → nothing to gate
    result = evaluate(contract, tool_name, tool_input)
    if result["log"]:
        log_evaluation(root, tool_name, tool_input, result)
    if hook_mode:
        # Only enforce mode talks back to the runtime; observe mode stays silent.
        if result["mode"] == "enforce" and result["decision"] in {"ask", "deny"}:
            emit_hook_decision(result)
        return 0
    decision = result["decision"] if result["mode"] == "enforce" else f"observe:{result['decision']}"
    rule_ids = [str(r.get("id")) for r in result["matched"]]
    print(json.dumps({"tool": tool_name, "decision": decision, "rules": rule_ids}))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--root", default=".")
    parser.add_argument("--hook", action="store_true",
                        help="Read the PreToolUse JSON payload from stdin")
    parser.add_argument("--check", action="store_true",
                        help="Evaluate --tool/--input from the command line")
    parser.add_argument("--tool", default="")
    parser.add_argument("--input", default="{}")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    if args.hook:
        payload = json.load(sys.stdin)
        tool_name = str(payload.get("tool_name", ""))
        tool_input = payload.get("tool_input", {})
        if not tool_name:
            return 0
        return run_gate(root, tool_name, tool_input, hook_mode=True)

    if args.check:
        return run_gate(root, args.tool, json.loads(args.input), hook_mode=False)

    parser.error("use --hook (stdin payload) or --check (--tool/--input)")
    return 0


def _fail_open() -> int:
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception:
        # Fail open: never block the session because the gate itself broke.
        raise SystemExit(_fail_open())
