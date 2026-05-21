#!/usr/bin/env python3
"""Read env values from the project-local .claude/settings.local.json file.

Usage:
  python3 scripts/get_env.py EXAMPLE_API_KEY
  python3 scripts/get_env.py EXAMPLE_API_KEY EXAMPLE_PROJECT_ID
  python3 scripts/get_env.py --shell EXAMPLE_API_KEY EXAMPLE_PROJECT_ID
"""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path


SETTINGS_PATH = Path(__file__).resolve().parent.parent / ".claude" / "settings.local.json"


def load_env() -> dict[str, str]:
    if not SETTINGS_PATH.exists():
        sys.stderr.write(f"error: settings file not found: {SETTINGS_PATH}\n")
        sys.exit(2)

    try:
        data = json.loads(SETTINGS_PATH.read_text())
    except json.JSONDecodeError as exc:
        sys.stderr.write(f"error: failed to parse {SETTINGS_PATH}: {exc}\n")
        sys.exit(2)

    env = data.get("env")
    if not isinstance(env, dict):
        sys.stderr.write(f"error: missing 'env' object in {SETTINGS_PATH}\n")
        sys.exit(2)

    out: dict[str, str] = {}
    for key, value in env.items():
        if isinstance(key, str) and isinstance(value, str):
            out[key] = value
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Read env vars from .claude/settings.local.json")
    parser.add_argument("--shell", action="store_true", help="Print shell export statements")
    parser.add_argument("names", nargs="+", help="Environment variable names to fetch")
    args = parser.parse_args()

    env = load_env()
    missing = [name for name in args.names if name not in env]
    if missing:
        sys.stderr.write(f"error: missing env var(s): {', '.join(missing)}\n")
        sys.exit(2)

    if args.shell:
        for name in args.names:
            print(f"export {name}={shlex.quote(env[name])}")
        return

    if len(args.names) == 1:
        print(env[args.names[0]])
        return

    print(json.dumps({name: env[name] for name in args.names}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
