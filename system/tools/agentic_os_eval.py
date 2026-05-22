#!/usr/bin/env python3
"""Run generic Agentic Business OS fixture checks."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Result:
    area: str
    case_id: str
    status: str
    message: str


def read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            rows.append(data)
    return rows


def skill_path(root: Path, name: str) -> Path:
    skills = root / ".agents" / "skills"
    for path in sorted(skills.glob(f"*/{name}")):
        if (path / "SKILL.md").exists():
            return path
    return skills / name


def skill_exists(root: Path, name: str) -> bool:
    return (skill_path(root, name) / "SKILL.md").exists()


def manifest_text(root: Path, skill: str) -> str:
    return read(skill_path(root, skill) / "manifest.yaml")


def skill_contract_text(root: Path, skill: str) -> str:
    path = skill_path(root, skill)
    return "\n".join([read(path / "SKILL.md"), read(path / "manifest.yaml")])


def add(results: list[Result], area: str, case_id: str, ok: bool, message: str) -> None:
    results.append(Result(area, case_id, "pass" if ok else "fail", message))


def evaluate_skill_behavior_case(root: Path, case: dict[str, Any]) -> tuple[bool, list[str]]:
    skill = str(case.get("skill") or "")
    text = skill_contract_text(root, skill).lower()
    reasons: list[str] = []
    for expected in [str(item) for item in case.get("expected_paths", []) if isinstance(item, str)]:
        if not (root / expected).exists():
            reasons.append(f"missing_path:{expected}")
    for keyword in [str(item) for item in case.get("memory_keywords", []) if isinstance(item, str)]:
        if keyword.lower() not in text:
            reasons.append(f"missing_memory_keyword:{keyword}")
    for keyword in [str(item) for item in case.get("failure_keywords", []) if isinstance(item, str)]:
        if keyword.lower() not in text:
            reasons.append(f"missing_failure_keyword:{keyword}")
    return not reasons, reasons


def run_learning_review(root: Path, results: list[Result]) -> None:
    fixture = root / "evals" / "learning" / "cases.json"
    tool_dir = root / "system" / "tools"
    sys.path.insert(0, str(tool_dir))
    try:
        from ephemeral_chat_capture import capture_payload, extract_events
        from learning_review import build_review
        from work_session_journal import record_event
    except Exception as exc:  # noqa: BLE001
        add(results, "Learning", "import", False, str(exc))
        return

    data = read_json(fixture)
    for case in data.get("cases", []):
        if not isinstance(case, dict):
            continue
        case_id = str(case.get("id"))
        raw_chat_payload = case.get("raw_chat_payload")
        raw_chat_transcript = case.get("raw_chat_transcript_jsonl")
        raw_chat_thread_updates = case.get("raw_chat_thread_updates")
        events_value = case.get("events")
        event = case.get("event")
        expected_kind = str(case.get("expected_candidate_kind") or "")
        expected_owner = str(case.get("expected_owner") or "")
        expected_title = str(case.get("expected_candidate_title_contains") or "")
        expected_absent = str(case.get("expected_absent_title_contains") or "")
        try:
            with tempfile.TemporaryDirectory() as tmp:
                tmp_root = Path(tmp)
                if isinstance(raw_chat_payload, dict):
                    capture_payload(tmp_root, "manual", raw_chat_payload, "", retention_days=7)
                    extracted = extract_events(tmp_root, retention_days=7)
                    rows = read_jsonl(tmp_root / "state" / "learning-events.jsonl")
                    expected_source = str(case.get("expected_source"))
                    ok = int(extracted.get("events_written") or 0) >= 1 and any(row.get("source") == expected_source for row in rows)
                    add(results, "Learning", case_id, ok, f"events_written={extracted.get('events_written')}")
                    continue
                if isinstance(raw_chat_transcript, list):
                    transcript = tmp_root / "fixture-transcript.jsonl"
                    transcript.write_text(
                        "\n".join(json.dumps(item, ensure_ascii=False) for item in raw_chat_transcript) + "\n",
                        encoding="utf-8",
                    )
                    captured = capture_payload(
                        tmp_root,
                        "manual",
                        {"session_id": "fixture-transcript", "transcript_path": str(transcript)},
                        "",
                        retention_days=7,
                    )
                    captured_data = read_json(captured)
                    messages = captured_data.get("messages") if isinstance(captured_data.get("messages"), list) else []
                    roles = [str(message.get("role")) for message in messages if isinstance(message, dict)]
                    expected_roles = [str(role) for role in case.get("expected_message_roles", [])]
                    expected_text = str(case.get("expected_user_text") or "")
                    ok = (
                        roles == expected_roles
                        and any(
                            isinstance(message, dict)
                            and message.get("role") == "user"
                            and expected_text in str(message.get("text") or "")
                            for message in messages
                        )
                    )
                    add(results, "Learning", case_id, ok, f"roles={roles}, message_count={len(messages)}")
                    continue
                if isinstance(raw_chat_thread_updates, list):
                    captured_paths: list[Path] = []
                    for update in raw_chat_thread_updates:
                        if isinstance(update, dict):
                            captured_paths.append(capture_payload(tmp_root, "manual", update, "", retention_days=7))
                    unique_paths = {path.relative_to(tmp_root).as_posix() for path in captured_paths}
                    last_data = read_json(captured_paths[-1]) if captured_paths else {}
                    messages = last_data.get("messages") if isinstance(last_data.get("messages"), list) else []
                    ok = (
                        len(unique_paths) == int(case.get("expected_file_count") or 0)
                        and len(messages) == int(case.get("expected_message_count") or 0)
                        and int(last_data.get("capture_count") or 0) == int(case.get("expected_capture_count") or 0)
                    )
                    add(results, "Learning", case_id, ok, f"files={len(unique_paths)}, messages={len(messages)}, captures={last_data.get('capture_count')}")
                    continue
                if isinstance(events_value, list):
                    for item in events_value:
                        if isinstance(item, dict):
                            record_event(tmp_root, item)
                elif isinstance(event, dict):
                    record_event(tmp_root, event)
                else:
                    add(results, "Learning", case_id, False, "event/events/raw_chat_payload missing")
                    continue
                review = build_review(tmp_root, days=7, today=date(2026, 5, 19))
        except Exception as exc:  # noqa: BLE001
            add(results, "Learning", case_id, False, str(exc))
            continue

        candidates = [candidate for candidate in review.get("candidates", []) if isinstance(candidate, dict)]

        def candidate_matches(candidate: dict[str, Any]) -> bool:
            if expected_kind and candidate.get("kind") != expected_kind:
                return False
            if expected_owner and candidate.get("owner") != expected_owner:
                return False
            if expected_title and expected_title.lower() not in str(candidate.get("title") or "").lower():
                return False
            return int(candidate.get("occurrence_count") or 1) >= int(case.get("expected_occurrence_count") or 1)

        if expected_absent:
            needle = expected_absent.lower()
            title_absent = not any(needle in str(candidate.get("title") or "").lower() for candidate in candidates)
            needs_positive_match = bool(expected_kind or expected_owner or expected_title)
            positive_match = not needs_positive_match or any(candidate_matches(candidate) for candidate in candidates)
            add(results, "Learning", case_id, title_absent and positive_match, f"candidates={len(candidates)}, absent={expected_absent}")
            continue
        matched = any(candidate_matches(candidate) for candidate in candidates)
        add(results, "Learning", case_id, matched, f"candidates={len(candidates)}, expected={expected_kind}/{expected_owner}")


def run(root: Path) -> list[Result]:
    results: list[Result] = []
    routing = read_json(root / "evals/routing/cases.json")
    for case in routing.get("cases", []):
        skill = str(case.get("expected_skill"))
        domain = str(case.get("expected_domain"))
        out = str(case.get("expected_output_area"))
        ok = skill_exists(root, skill) and (root / f"domains/{domain}.md").exists() and (root / out).exists()
        add(results, "Routing", str(case.get("id")), ok, f"skill={skill} domain={domain} output={out}")
    skills = read_json(root / "evals/skills/cases.json")
    for case in skills.get("cases", []):
        skill = str(case.get("skill"))
        text = manifest_text(root, skill)
        required = [str(x) for x in case.get("required_manifest_fields", [])]
        missing = [field for field in required if field not in text]
        add(results, "Skills", skill, bool(text) and not missing, "missing=" + ",".join(missing))
    behavior = read_json(root / "evals/skills/behavior-cases.json")
    for case in behavior.get("cases", []):
        if not isinstance(case, dict):
            continue
        ok, reasons = evaluate_skill_behavior_case(root, case)
        add(results, "Skill-Behavior", str(case.get("id")), ok, "ok" if ok else ",".join(reasons))
    for case in behavior.get("negative_cases", []):
        if not isinstance(case, dict):
            continue
        expected_failure = str(case.get("expected_failure"))
        ok, reasons = evaluate_skill_behavior_case(root, case)
        failed_for_expected_reason = not ok and any(reason.startswith(expected_failure) for reason in reasons)
        add(results, "Skill-Behavior", str(case.get("id")), failed_for_expected_reason, ",".join(reasons) if reasons else "unexpected pass")
    first = read_json(root / "evals/routing/first-read.json")
    for case in first.get("cases", []):
        files = [str(x) for x in case.get("first_files", [])]
        missing = [p for p in files if not (root / p).exists()]
        add(results, "First-Read", str(case.get("id")), not missing, "missing=" + ",".join(missing))
    run_learning_review(root, results)
    for path in ["evals/ingest/cases.json", "evals/routing/artifact-placement.json", "evals/agents/cases.json", "evals/recurring/cases.json", "evals/structure/cases.json"]:
        add(results, "Structure", path, (root / path).exists(), "exists" if (root / path).exists() else "missing")
    for folder in ["inbox", "wiki", "outputs", "sources", "state", ".agents", "system", "evals", "domains", "indexes"]:
        add(results, "Structure", f"folder-{folder}", (root / folder).is_dir(), folder)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    root = Path.cwd()
    results = run(root)
    passed = sum(1 for r in results if r.status == "pass")
    failed = sum(1 for r in results if r.status == "fail")
    now = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    print("# Agentic Business OS Eval Results")
    print()
    print(f"Root: `{root}`")
    print(f"Generated: `{now}`")
    print()
    print("## Summary")
    print()
    print(f"- Passed: {passed}")
    print(f"- Failed: {failed}")
    current = None
    for result in results:
        if result.area != current:
            current = result.area
            print(f"\n## {current}\n")
        print(f"- `{result.status}` `{result.case_id}` - {result.message}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
