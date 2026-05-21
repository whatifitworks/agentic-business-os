#!/usr/bin/env python3
"""Capture ephemeral raw chat payloads and extract compact learning events."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from work_session_journal import record_event, redact


RAW_DIR = Path("logs/raw-chats")
MANIFEST = Path("state/learning-raw-chat-manifest.json")
RETENTION_DAYS = 7
EXTRACT_RECENT_MESSAGE_LIMIT = 30

SIGNAL_PATTERNS = [
    re.compile(r"\b(no[, ]|not like that|wrong|doesn'?t work|didn'?t work|not working|not as expected)\b", re.I),
    re.compile(r"\b(don'?t see|can'?t see|not seeing|missing|maybe i'?m missing)\b", re.I),
    re.compile(r"\b(should|shouldn'?t|we need|we should|why did|why hasn'?t|confusing|expected|misusing|using .* differently)\b", re.I),
    re.compile(r"\b(manual|again|duplicate|repeat|repeated|same thing|automate|hook|skill)\b", re.I),
    re.compile(r"\b(frustrated|annoying|painful|too noisy|messy|hard to use|waste|slow)\b", re.I),
    re.compile(r"\b(great|beautiful|perfect|works well|working well|happy with|love this|useful|good flow)\b", re.I),
]

ASSISTANT_SIGNAL_PATTERNS = [
    re.compile(r"\b(memory update candidate|brain update candidate)\b", re.I),
    re.compile(r"\b(i changed|i fixed|implemented|validation passed|root cause|the issue was)\b", re.I),
    re.compile(r"\b(design decision|decision:|accepted candidate)\b", re.I),
]


def now_local() -> datetime:
    return datetime.now(timezone.utc).astimezone()


def sha(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(errors="replace"))
    except json.JSONDecodeError:
        return fallback


def save_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True) + "\n")


def append_hook_diagnostic(root: Path, record: dict[str, Any]) -> None:
    path = root / RAW_DIR / "_hook-runs.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "created_at": now_local().isoformat(timespec="seconds"),
        **record,
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def safe_session_id(value: str | None) -> str:
    if not value:
        return "unknown-session"
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-")
    return safe[:96] or "unknown-session"


def parse_stdin_json() -> tuple[dict[str, Any], str]:
    raw = sys.stdin.read()
    if not raw.strip():
        return {}, ""
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        data = {"raw_stdin": raw}
    return data if isinstance(data, dict) else {"payload": data}, raw


def text_from_message_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") in {"input_text", "output_text", "text"}:
                    parts.append(str(item.get("text") or ""))
                elif isinstance(item.get("content"), str):
                    parts.append(str(item.get("content")))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(part for part in parts if part)
    if isinstance(content, dict):
        return str(content.get("text") or content.get("message") or content.get("content") or "")
    return ""


def add_message(messages: list[dict[str, str]], timestamp: str, role: str, text: str) -> None:
    text = re.sub(r"\s+", " ", text).strip()
    if not text:
        return
    if len(text) > 12_000:
        text = text[:12_000]
    key = sha(f"{timestamp}|{role}|{text}")
    if any(message.get("key") == key for message in messages):
        return
    messages.append({
        "timestamp": timestamp,
        "role": role,
        "text": text,
        "key": key,
    })


def messages_from_transcript_text(transcript: str) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for line in transcript.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(row, dict):
            continue
        timestamp = str(row.get("timestamp") or "")
        row_type = row.get("type")
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        if row_type == "event_msg" and payload.get("type") == "user_message":
            add_message(messages, timestamp, "user", str(payload.get("message") or ""))
        elif row_type == "event_msg" and payload.get("type") == "agent_message":
            add_message(messages, timestamp, "assistant", str(payload.get("message") or ""))
    return messages


def messages_from_payload(payload: dict[str, Any]) -> tuple[list[dict[str, str]], str]:
    transcript_source = ""
    for key in ["transcript_path", "conversation_path", "session_path"]:
        value = payload.get(key)
        if isinstance(value, str) and value:
            path = Path(value).expanduser()
            transcript_source = str(path)
            if path.exists() and path.is_file():
                try:
                    return messages_from_transcript_text(path.read_text(errors="replace")), transcript_source
                except OSError:
                    return [], transcript_source
    for key in ["transcript", "conversation"]:
        value = payload.get(key)
        if value:
            text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
            return messages_from_transcript_text(text), transcript_source
    value = payload.get("messages")
    if isinstance(value, list):
        messages: list[dict[str, str]] = []
        for item in value:
            if isinstance(item, dict):
                add_message(
                    messages,
                    str(item.get("timestamp") or ""),
                    str(item.get("role") or "unknown"),
                    text_from_message_content(item.get("content") or item.get("message") or item.get("text")),
                )
        return messages, transcript_source
    return [], transcript_source


def thread_capture_path(root: Path, runtime: str, session_id: str, captured_at: datetime) -> Path:
    base = root / RAW_DIR / runtime
    filename = f"{session_id}.json"
    if base.exists():
        existing = sorted(path for path in base.rglob(filename) if path.is_file())
        if existing:
            return existing[0]
    return base / captured_at.date().isoformat() / filename


def merge_messages(existing: Any, incoming: list[dict[str, str]]) -> tuple[list[dict[str, str]], int]:
    messages: list[dict[str, str]] = []
    seen: set[str] = set()
    new_count = 0
    if isinstance(existing, list):
        for message in existing:
            if not isinstance(message, dict):
                continue
            key = str(message.get("key") or "")
            if not key or key in seen:
                continue
            messages.append({str(k): str(v) for k, v in message.items()})
            seen.add(key)
    for message in incoming:
        key = str(message.get("key") or "")
        if not key or key in seen:
            continue
        messages.append(message)
        seen.add(key)
        new_count += 1
    return messages, new_count


def capture_payload(root: Path, runtime: str, payload: dict[str, Any], raw_stdin: str, retention_days: int) -> Path:
    captured_at = now_local()
    session_id = safe_session_id(str(payload.get("session_id") or payload.get("conversation_id") or payload.get("id") or ""))
    messages, transcript_source = messages_from_payload(payload)
    out = thread_capture_path(root, runtime, session_id, captured_at)
    existing = load_json(out, {})
    merged_messages, new_message_count = merge_messages(existing.get("messages"), messages if messages else [])
    capture_count = int(existing.get("capture_count") or 0) + 1
    content = redact({
        "schema_version": 1,
        "runtime": runtime,
        "session_id": session_id,
        "captured_at": existing.get("captured_at") or captured_at.isoformat(timespec="seconds"),
        "updated_at": captured_at.isoformat(timespec="seconds"),
        "expires_at": (captured_at + timedelta(days=retention_days)).isoformat(timespec="seconds"),
        "capture_count": capture_count,
        "transcript_source": transcript_source,
        "message_count": len(merged_messages),
        "new_message_count": new_message_count,
        "messages": merged_messages,
        "payload": payload,
        "raw_stdin": raw_stdin if raw_stdin and len(raw_stdin) <= 200_000 else "",
    })
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(content, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    return out


def raw_chat_files(root: Path) -> list[Path]:
    base = root / RAW_DIR
    if not base.exists():
        return []
    return sorted(path for path in base.rglob("*.json") if path.is_file())


def purge_expired(root: Path, retention_days: int, now: datetime | None = None) -> list[str]:
    now = now or now_local()
    cutoff = now - timedelta(days=retention_days)
    deleted: list[str] = []
    for path in raw_chat_files(root):
        data = load_json(path, {})
        expires = str(data.get("expires_at") or "")
        expired_at = None
        if expires:
            try:
                expired_at = datetime.fromisoformat(expires)
            except ValueError:
                expired_at = None
        try:
            modified = datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).astimezone()
        except OSError:
            continue
        if (expired_at and expired_at <= now) or modified < cutoff:
            path.unlink(missing_ok=True)
            deleted.append(path.relative_to(root).as_posix())
    return deleted


def flatten_text(value: Any) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "\n".join(flatten_text(item) for item in value)
    if isinstance(value, dict):
        parts: list[str] = []
        for key in ["role", "type", "text", "content", "message", "summary"]:
            if key in value:
                parts.append(flatten_text(value[key]))
        if parts:
            return " ".join(part for part in parts if part)
        return " ".join(flatten_text(item) for item in value.values())
    return ""


def flatten_possible_json_text(value: Any) -> str:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith(("[", "{")):
            try:
                return flatten_text(json.loads(stripped))
            except json.JSONDecodeError:
                return value
    return flatten_text(value)


def learning_snippets(text: str, role: str = "unknown", limit: int = 5) -> list[str]:
    snippets: list[str] = []
    patterns = ASSISTANT_SIGNAL_PATTERNS if role == "assistant" else SIGNAL_PATTERNS
    for line in re.split(r"[\r\n]+", text):
        normalized = re.sub(r"\s+", " ", line).strip()
        if len(normalized) < 24:
            continue
        match = next((found for pattern in patterns if (found := pattern.search(normalized))), None)
        if match:
            start = 0 if role != "assistant" else max(0, match.start() - 80)
            snippet = normalized[start:match.start() + 240]
            if start:
                snippet = f"...{snippet}"
            snippets.append(snippet[:320])
        if len(snippets) >= limit:
            break
    return snippets


def load_manifest(root: Path) -> dict[str, Any]:
    data = load_json(root / MANIFEST, {"processed": {}, "processed_messages": {}})
    if not isinstance(data, dict):
        data = {"processed": {}, "processed_messages": {}}
    if not isinstance(data.get("processed"), dict):
        data["processed"] = {}
    if not isinstance(data.get("processed_messages"), dict):
        data["processed_messages"] = {}
    return data


def extract_events(root: Path, retention_days: int = RETENTION_DAYS) -> dict[str, Any]:
    manifest = load_manifest(root)
    processed = manifest["processed"]
    processed_messages = manifest["processed_messages"]
    written = 0
    skipped = 0
    for path in raw_chat_files(root):
        rel_path = path.relative_to(root).as_posix()
        digest = sha(path.read_text(errors="replace"))
        if processed.get(rel_path) == digest:
            skipped += 1
            continue
        data = load_json(path, {})
        messages = data.get("messages") if isinstance(data.get("messages"), list) else []
        if messages:
            for message in messages[-EXTRACT_RECENT_MESSAGE_LIMIT:]:
                if not isinstance(message, dict):
                    continue
                text = str(message.get("text") or "")
                key = str(message.get("key") or sha(f"{data.get('session_id')}|{message.get('timestamp')}|{message.get('role')}|{text}"))
                if processed_messages.get(key):
                    continue
                role = str(message.get("role") or "unknown")
                snippets = learning_snippets(text, role=role, limit=2)
                for snippet in snippets:
                    record_event(root, {
                        "event_type": "learning",
                        "summary": f"{role}: {snippet}",
                        "workflow": "ephemeral-chat-parser",
                        "status": "observed",
                        "importance": "medium",
                        "source": "raw-chat-parser",
                        "friction": [snippet],
                        "automation_candidates": [],
                        "raw_chat_ref": rel_path,
                        "chat_role": role,
                        "chat_timestamp": message.get("timestamp"),
                    })
                    written += 1
                processed_messages[key] = {
                    "raw_chat_ref": rel_path,
                    "role": message.get("role"),
                    "timestamp": message.get("timestamp"),
                }
        processed[rel_path] = digest
    manifest["processed"] = processed
    manifest["processed_messages"] = processed_messages
    manifest["updated_at"] = now_local().isoformat(timespec="seconds")
    manifest["retention_days"] = retention_days
    save_json(root / MANIFEST, manifest)
    return {"processed_files": len(processed), "events_written": written, "skipped_files": skipped}


def command_capture(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    payload, raw_stdin = parse_stdin_json() if args.stdin_json else ({}, "")
    path: Path | None = None
    if payload or raw_stdin:
        path = capture_payload(root, args.runtime, payload, raw_stdin, args.retention_days)
    deleted = purge_expired(root, args.retention_days) if args.purge else []
    extracted = extract_events(root, args.retention_days) if args.extract else {}
    result = {
        "ok": True,
        "captured_path": path.relative_to(root).as_posix() if path else None,
        "deleted": deleted,
        "extracted": extracted,
    }
    if args.diagnostics:
        append_hook_diagnostic(root, {
            "runtime": args.runtime,
            "had_payload": bool(payload or raw_stdin),
            "payload_keys": sorted(payload.keys()) if isinstance(payload, dict) else [],
            "raw_stdin_bytes": len(raw_stdin.encode("utf-8", errors="replace")),
            "captured_path": result["captured_path"],
            "events_written": int(extracted.get("events_written") or 0) if isinstance(extracted, dict) else 0,
            "deleted_count": len(deleted),
        })
    print(json.dumps({"continue": True}) if args.hook_json else json.dumps(result, indent=2))
    return 0


def command_extract(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    deleted = purge_expired(root, args.retention_days) if args.purge else []
    extracted = extract_events(root, args.retention_days)
    result = {"ok": True, "deleted": deleted, "extracted": extracted}
    print(json.dumps(result, indent=2))
    return 0


def command_purge(args: argparse.Namespace) -> int:
    root = Path(args.root).resolve()
    deleted = purge_expired(root, args.retention_days)
    print(json.dumps({"ok": True, "deleted": deleted}, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    capture = sub.add_parser("capture", help="Capture one hook payload as an ephemeral raw chat")
    capture.add_argument("--root", default=".")
    capture.add_argument("--runtime", required=True, choices=["codex", "claude", "manual"])
    capture.add_argument("--stdin-json", action="store_true")
    capture.add_argument("--retention-days", type=int, default=RETENTION_DAYS)
    capture.add_argument("--extract", action="store_true")
    capture.add_argument("--purge", action="store_true")
    capture.add_argument("--hook-json", action="store_true")
    capture.add_argument("--diagnostics", action="store_true")
    capture.set_defaults(func=command_capture)

    extract = sub.add_parser("extract", help="Extract compact learning events from captured raw chats")
    extract.add_argument("--root", default=".")
    extract.add_argument("--retention-days", type=int, default=RETENTION_DAYS)
    extract.add_argument("--purge", action="store_true")
    extract.set_defaults(func=command_extract)

    purge = sub.add_parser("purge", help="Delete expired raw chat captures")
    purge.add_argument("--root", default=".")
    purge.add_argument("--retention-days", type=int, default=RETENTION_DAYS)
    purge.set_defaults(func=command_purge)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
