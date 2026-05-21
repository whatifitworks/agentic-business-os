#!/usr/bin/env python3
"""Capture repeatable workflow failures as redacted inbox candidates."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SECRET_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (
        re.compile(r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key)\s*([:=])\s*[^,\s;]+"),
        r"\1\2<redacted>",
    ),
    (
        re.compile(r"(?i)(authorization\s*:\s*bearer\s+)[A-Za-z0-9._~+/=-]+"),
        r"\1<redacted>",
    ),
    (re.compile(r"sk-[A-Za-z0-9_-]{20,}"), "<redacted-openai-key>"),
    (re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"), "<redacted-slack-token>"),
    (re.compile(r"https://[^@\s]+:[^@\s]+@"), "https://<redacted>@"),
]


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9_-]+", "-", value.strip().lower()).strip("-")
    return slug or "failure-candidate"


def redact_text(value: str) -> str:
    redacted = value
    for pattern, replacement in SECRET_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def redact_value(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, list):
        return [redact_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): redact_value(item) for key, item in value.items()}
    return value


def contains_any(text: str, needles: list[str]) -> bool:
    lowered = text.lower()
    return any(needle in lowered for needle in needles)


def select_owner(case: dict[str, Any], combined: str) -> str:
    owner_hint = str(case.get("owner_hint") or "").strip()
    if owner_hint:
        return owner_hint
    skill = str(case.get("skill") or case.get("workflow") or "").strip()
    if contains_any(combined, ["adapter", "computer use", "browser use", "ui automation"]):
        return ".agents/adapters/ and .agents/skills/ops/adapter-runner/"
    if contains_any(combined, ["hook", "stop hook", "posttool", "pretool"]):
        return ".agents/hooks/ and system/tools/ops_v2_hooks.py"
    if contains_any(combined, ["inbox", "memory", "wiki", "ingest"]):
        return ".agents/skills/knowledge/memory-ingest/ and system/tools/inbox_auto_ingest.py"
    if contains_any(combined, ["schedule", "recurring", "morning-coffee"]):
        return ".agents/recurring.yaml and .agents/skills/ops/morning-coffee/"
    if skill:
        return f".agents/skills/*/{skill}/"
    return "needs-owner-triage"


def select_ingest_outcome(owner: str, combined: str) -> str:
    if "adapter" in owner:
        return "skill-update-or-process-only"
    if "hooks" in owner or "hook" in combined.lower():
        return "hook-update-or-process-only"
    if "memory-ingest" in owner:
        return "memory-rule-update-or-process-only"
    if ".agents/skills/" in owner:
        return "skill-update-or-process-only"
    return "process-only-or-dropped"


def should_capture_failure(case: dict[str, Any]) -> tuple[bool, str]:
    if bool(case.get("one_off")):
        return False, "one_off"
    if str(case.get("severity", "")).lower() in {"harmless", "noise", "transient"} and not case.get("repeated"):
        return False, "low_value_transient"
    if case.get("user_correction") or case.get("deterministic") or case.get("repeated"):
        return True, "actionable_repeatable_failure"
    try:
        exit_code = int(case.get("exit_code", 0))
    except (TypeError, ValueError):
        exit_code = 0
    if exit_code != 0 and (case.get("expected_behavior") or case.get("actual_behavior")):
        return True, "reproducible_command_failure"
    return False, "insufficient_signal"


def analyze_failure(data: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_value(data)
    assert isinstance(redacted, dict)
    combined = " ".join(
        str(redacted.get(key, ""))
        for key in [
            "workflow",
            "skill",
            "command",
            "tool",
            "expected_behavior",
            "actual_behavior",
            "user_correction",
            "stdout_excerpt",
            "stderr_excerpt",
        ]
    )
    should_capture, reason = should_capture_failure(redacted)
    owner = select_owner(redacted, combined)
    case_id = str(redacted.get("id") or slugify(str(redacted.get("workflow") or redacted.get("skill") or "failure")))
    return {
        "case_id": case_id,
        "should_capture": should_capture,
        "capture_reason": reason,
        "summary": str(redacted.get("summary") or redacted.get("actual_behavior") or "Workflow failure candidate."),
        "suggested_owner": owner,
        "suggested_ingest_outcome": select_ingest_outcome(owner, combined),
        "deterministic": bool(redacted.get("deterministic")),
        "redacted_case": redacted,
    }


def render_markdown(analysis: dict[str, Any]) -> str:
    lines = [
        "# Failure Capture Candidate",
        "",
        f"- Case: `{analysis['case_id']}`",
        f"- Should capture: `{str(analysis['should_capture']).lower()}`",
        f"- Reason: `{analysis['capture_reason']}`",
        f"- Suggested owner: `{analysis['suggested_owner']}`",
        f"- Suggested ingest outcome: `{analysis['suggested_ingest_outcome']}`",
        f"- Deterministic: `{str(analysis['deterministic']).lower()}`",
        f"- Summary: {analysis['summary']}",
        "",
        "## Redacted Case",
        "",
        "```json",
        json.dumps(analysis["redacted_case"], indent=2, sort_keys=True, ensure_ascii=False),
        "```",
        "",
    ]
    return "\n".join(lines)


def write_inbox_candidate(root: Path, analysis: dict[str, Any]) -> Path:
    inbox = root / "inbox"
    inbox.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = inbox / f"{stamp}-{slugify(str(analysis['case_id']))}-failure-candidate.md"
    path.write_text(
        "\n".join(
            [
                "---",
                f"title: {analysis['case_id']} failure candidate",
                "type: failure-candidate",
                "source: failure-to-inbox-capture",
                f"created_at: {datetime.now(timezone.utc).astimezone().isoformat(timespec='seconds')}",
                "ingest_status: pending",
                f"suggested_owner: {analysis['suggested_owner']}",
                f"suggested_ingest_outcome: {analysis['suggested_ingest_outcome']}",
                "---",
                "",
                render_markdown(analysis),
            ]
        )
    )
    return path


def load_case(path: Path, case_id: str | None = None) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if isinstance(data, dict) and isinstance(data.get("cases"), list):
        cases = [case for case in data["cases"] if isinstance(case, dict)]
        if case_id:
            for case in cases:
                if str(case.get("id")) == case_id:
                    return case
            raise SystemExit(f"Case id not found: {case_id}")
        if not cases:
            raise SystemExit("No cases found.")
        return cases[0]
    if not isinstance(data, dict):
        raise SystemExit("Case file must contain a JSON object.")
    return data


def command_capture(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    case_path = Path(args.case)
    if not case_path.is_absolute():
        case_path = root / case_path
    analysis = analyze_failure(load_case(case_path, args.case_id))
    if args.write_inbox:
        if not analysis["should_capture"]:
            print(json.dumps({"written": False, "analysis": analysis}, indent=2))
            return 0
        path = write_inbox_candidate(root, analysis)
        print(json.dumps({"written": True, "path": path.relative_to(root).as_posix(), "analysis": analysis}, indent=2))
        return 0
    if args.json:
        print(json.dumps(analysis, indent=2))
    else:
        print(render_markdown(analysis))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    capture = sub.add_parser("capture", help="Analyze or write one failure candidate")
    capture.add_argument("--root", default=".")
    capture.add_argument("--case", required=True, help="JSON case path")
    capture.add_argument("--case-id", help="Case id when --case contains a cases array")
    capture.add_argument("--write-inbox", action="store_true", help="Write redacted candidate to inbox when capture-worthy")
    capture.add_argument("--json", action="store_true", help="Print JSON analysis")
    capture.set_defaults(func=command_capture)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
