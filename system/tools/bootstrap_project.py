#!/usr/bin/env python3
"""Initialize local Agentic Business OS runtime state and run baseline checks."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def run(root: Path, command: list[str], *, required: bool = True) -> int:
    print("$ " + " ".join(command))
    result = subprocess.run(command, cwd=root, text=True)
    if result.returncode != 0 and required:
        print(f"ERROR: command failed with exit {result.returncode}", file=sys.stderr)
    return result.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=".", help="Repository root, default: current directory")
    parser.add_argument("--skip-checks", action="store_true", help="Initialize state without running audits")
    args = parser.parse_args()

    root = Path(args.root).resolve()
    if not (root / "AGENTS.md").exists():
        print(f"ERROR: {root} does not look like an Agentic Business OS repo", file=sys.stderr)
        return 2

    commands = [
        ["python3", "system/tools/ops_state.py", "init"],
        ["python3", "system/tools/ops_state.py", "sync-recurring"],
        ["python3", "system/tools/ops_state.py", "sync-briefs", "--logs-dir", "logs", "--schedules", ".agents/schedules.yaml"],
    ]
    if not args.skip_checks:
        commands.extend(
            [
                ["python3", "system/tools/repo_audit.py", "--output", "system/health/repo-audit.md", "--exit-zero"],
                ["python3", "system/tools/agentic_os_audit.py", "--phase", "scaffold"],
                ["python3", "system/tools/agentic_os_eval.py"],
            ]
        )

    failures = 0
    for command in commands:
        failures += 1 if run(root, command) != 0 else 0

    print()
    print("Bootstrap complete." if failures == 0 else f"Bootstrap completed with {failures} failing command(s).")
    print()
    print("Next steps:")
    print("- Run project-onboarding through your agent to create a review pack, unless onboarding is already running.")
    print("- Review and promote approved files from inbox/project-onboarding/...")
    print("- Verify runtime hook activation; Codex may require enabling or approving hooks in the app/runtime UI.")
    print("- Optional macOS scheduler install: bash .agents/install-launchd.sh")
    print("- Optional macOS inbox watcher install: bash .agents/hooks/install-inbox-auto-ingest-launchd.sh")
    print("- Add project-specific MCP servers only after approval boundaries are clear.")
    print("- For help, run the get-help skill or visit https://whatifitworks.co.")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
